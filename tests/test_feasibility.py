import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.factory.lib import config_state, feasibility, items, safeio, work


class FeasibilityTest(unittest.TestCase):
    item_id = "0001-feature"
    dependency_id = "0002-root"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name).resolve()
        (self.repo / ".factory" / "items").mkdir(parents=True)
        self.spec = b"Acceptance: the feature works.\n"
        self.plan = b"# Plan\n- [ ] Build feature\n- [x] Existing proof\n"
        self.write_config(["feasibility"])
        self.write_item(self.item_id, stage="plan")

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, gates):
        path = self.repo / ".factory" / "config.json"
        path.write_text(json.dumps({
            "version": 1, "merge": "auto", "gates": gates,
        }), encoding="utf-8")

    def config_snapshot(self, value=None):
        file = safeio.snapshot_path(self.repo, ".factory/config.json")
        parsed = json.loads(file.data) if value is None else value
        return config_state.ConfigSnapshot(file=file, value=parsed)

    def write_item(self, item_id, *, stage):
        directory = self.repo / ".factory" / "items" / item_id
        directory.mkdir(parents=True, exist_ok=True)
        meta = {
            "id": item_id,
            "title": item_id,
            "stage": stage,
            "kind": "backend",
            "created": "2026-09-09",
            "updated": "2026-09-09",
        }
        (directory / "item.md").write_text(
            items.render_item(meta, "Fixture."), encoding="utf-8")

    def solo(self, *, mode="solo", plan=None):
        plan = self.plan if plan is None else plan
        return {
            "version": 1,
            "item": self.item_id,
            "spec_sha256": feasibility.sha256_bytes(self.spec),
            "plan_structure_sha256": feasibility.plan_structure_sha256(plan),
            "revision": {
                "reason": "Initial complete contract",
                "changed_sections": ["initial"],
            },
            "resume_cursor": {"strategy": "first-unchecked-task"},
            "participants": [{
                "item": self.item_id,
                "owned_paths": ["src"],
            }],
            "dependencies": [],
            "resources": [
                {
                    "id": "feature-code",
                    "kind": "path",
                    "value": "src/feature.py",
                    "access": "modify",
                    "provider": self.item_id,
                    "availability": "available",
                },
                {
                    "id": "python",
                    "kind": "runtime",
                    "value": "python3",
                    "access": "use",
                    "provider": "environment",
                    "availability": "available",
                },
            ],
            "interfaces": [],
            "criteria": [{
                "id": "AC-1",
                "statement": "The feature passes its test",
                "requires": ["feature-code", "python"],
                "tests": ["unit"],
            }],
            "tests": [{
                "id": "unit",
                "purpose": "component",
                "command": ["python3", "-m", "unittest"],
                "covers": ["feature-code", "python"],
            }],
            "delivery": {
                "mode": mode,
                "participants": [self.item_id],
                "merge_order": [self.item_id],
                "shared_gates": [],
            },
            "out_of_scope": ["physical device proof"],
        }

    def joint(self):
        value = self.solo()
        value["participants"].append({
            "item": self.dependency_id,
            "owned_paths": ["app"],
        })
        value["dependencies"] = [{
            "item": self.dependency_id,
            "relation": "joint",
            "provides": ["root-mount", "home-route"],
        }]
        value["resources"].extend([
            {
                "id": "root-mount",
                "kind": "path",
                "value": "app/root.py",
                "access": "modify",
                "provider": self.dependency_id,
                "availability": "available",
            },
            {
                "id": "home-route",
                "kind": "route",
                "value": "signed-in/home",
                "access": "use",
                "provider": self.dependency_id,
                "availability": "available",
            },
        ])
        value["criteria"][0]["requires"].extend(["root-mount", "home-route"])
        value["criteria"][0]["tests"] = ["integrated"]
        value["tests"] = [{
            "id": "integrated",
            "purpose": "integrated",
            "command": ["python3", "-m", "unittest", "tests.test_home"],
            "covers": [
                "feature-code", "python", "root-mount", "home-route",
            ],
        }]
        value["delivery"] = {
            "mode": "joint-staged",
            "participants": [self.item_id, self.dependency_id],
            "merge_order": [self.item_id, self.dependency_id],
            "shared_gates": ["integrated"],
        }
        return value

    def assert_invalid(self, value, text, *, stages=None, plan=None):
        with self.assertRaisesRegex(feasibility.FeasibilityError, text):
            feasibility.validate_acceptance(
                value,
                item_id=self.item_id,
                spec_bytes=self.spec,
                plan_bytes=self.plan if plan is None else plan,
                dependency_stages=stages,
            )

    def write_contract(self, value=None, *, plan=None):
        directory = self.repo / ".factory" / "items" / self.item_id
        plan = self.plan if plan is None else plan
        value = self.solo(plan=plan) if value is None else value
        (directory / "spec.md").write_bytes(self.spec)
        (directory / "plan.md").write_bytes(plan)
        (directory / "acceptance.json").write_text(
            json.dumps(value, sort_keys=True), encoding="utf-8")

    def test_solo_component_and_corrected_joint_contracts_pass(self):
        for contract in (self.solo(), self.solo(mode="component-only")):
            with self.subTest(mode=contract["delivery"]["mode"]):
                report = feasibility.validate_acceptance(
                    contract, item_id=self.item_id,
                    spec_bytes=self.spec, plan_bytes=self.plan)
                self.assertEqual(report["cursor"], "Build feature")

        joint = self.joint()
        report = feasibility.validate_acceptance(
            joint, item_id=self.item_id, spec_bytes=self.spec,
            plan_bytes=self.plan,
            dependency_stages={self.dependency_id: "implement"})
        self.assertEqual(report["delivery"]["mode"], "joint-staged")

    def test_checkbox_state_alone_advances_cursor_without_changing_hash(self):
        first = b"- [ ] one\n- [X] old\n  - [ ] three\n* [ ] ignored\n"
        advanced = b"- [x] one\n- [X] old\n  - [ ] three\n* [ ] ignored\n"
        complete = b"- [x] one\n- [X] old\n  - [x] three\n* [ ] ignored\n"
        self.assertEqual(
            feasibility.plan_structure_sha256(first),
            feasibility.plan_structure_sha256(advanced))
        self.assertEqual(feasibility.derive_resume_cursor(first), "one")
        self.assertEqual(feasibility.derive_resume_cursor(advanced), "three")
        self.assertEqual(feasibility.derive_resume_cursor(complete), "COMPLETE")

    def test_task_parser_matches_existing_unicode_splitline_semantics(self):
        cases = (
            "- [ ] first\r- [ ] second\r",
            "\u00a0- [ ] first\n",
            "- [ ]    \n",
            "- [ ] first\u2028- [ ] second\n",
            "\t-\t[ ]\tfirst\x85  - [x] old\n",
        )
        for text in cases:
            with self.subTest(text=repr(text)):
                self.assertEqual(
                    list(feasibility.pending_plan_tasks(text.encode("utf-8"))),
                    work.unticked_tasks(text))
                normalized = feasibility.normalize_plan_structure(
                    text.encode("utf-8")).decode("utf-8")
                self.assertEqual(
                    work.unticked_tasks(normalized),
                    [marker.text for marker in
                     feasibility.plan_task_markers(text.encode("utf-8"))])

    def test_compact_and_long_complete_plans_have_no_subjective_limit(self):
        for plan in (b"- [x] done\n", (b"prose\n" * 100_000) + b"- [x] done\n"):
            with self.subTest(length=len(plan)):
                contract = self.solo(plan=plan)
                report = feasibility.validate_acceptance(
                    contract, item_id=self.item_id,
                    spec_bytes=self.spec, plan_bytes=plan)
                self.assertEqual(report["cursor"], "COMPLETE")

    def test_closed_shape_hash_cursor_revision_and_paths_fail_closed(self):
        cases = []
        missing = self.solo()
        del missing["revision"]
        cases.append((missing, "revision"))
        nested_extra = self.solo()
        nested_extra["resources"][0]["surprise"] = True
        cases.append((nested_extra, "unknown keys"))
        stale_spec = self.solo()
        stale_spec["spec_sha256"] = "0" * 64
        cases.append((stale_spec, "spec_sha256"))
        stale_plan = self.solo()
        stale_plan["plan_structure_sha256"] = "0" * 64
        cases.append((stale_plan, "plan_structure_sha256"))
        cursor = self.solo()
        cursor["resume_cursor"]["strategy"] = "stored-line-number"
        cases.append((cursor, "resume_cursor.strategy"))
        empty_revision = self.solo()
        empty_revision["revision"]["reason"] = ""
        cases.append((empty_revision, "revision.reason"))
        unsafe_path = self.solo()
        unsafe_path["participants"][0]["owned_paths"] = ["../escape"]
        cases.append((unsafe_path, "unsafe non-normalized"))
        unavailable = self.solo()
        unavailable["resources"][0]["availability"] = "unavailable"
        cases.append((unavailable, "required resource is unavailable"))
        malformed = self.solo()
        malformed["resources"][0]["kind"] = {}
        cases.append((malformed, r"resources\[0\].kind"))
        for value, message in cases:
            with self.subTest(message=message):
                self.assert_invalid(value, message)

    def test_dangling_duplicate_coverage_and_permutation_errors_fail(self):
        dangling = self.solo()
        dangling["criteria"][0]["requires"].append("missing")
        self.assert_invalid(dangling, "dangling resource")

        duplicate = self.solo()
        duplicate["resources"].append(copy.deepcopy(duplicate["resources"][0]))
        self.assert_invalid(duplicate, "duplicate resource id")

        uncovered = self.solo()
        uncovered["tests"][0]["covers"] = ["feature-code"]
        self.assert_invalid(uncovered, "named tests do not cover")

        joint = self.joint()
        joint["delivery"]["merge_order"] = [self.item_id, self.item_id]
        self.assert_invalid(joint, "merge_order", stages={self.dependency_id: "implement"})

    def test_impossible_solo_and_disconnected_shared_gate_fail(self):
        impossible = self.joint()
        impossible["delivery"]["mode"] = "solo"
        self.assert_invalid(
            impossible, "permits only the current item",
            stages={self.dependency_id: "implement"})

        disconnected = self.joint()
        disconnected["tests"][0]["covers"] = ["feature-code", "python"]
        self.assert_invalid(
            disconnected, "criterion-local shared gates",
            stages={self.dependency_id: "implement"})

    def test_dependency_providers_relations_and_stages_are_exact(self):
        delivered = self.joint()
        delivered["dependencies"][0]["relation"] = "delivered"
        delivered["participants"] = delivered["participants"][:1]
        delivered["delivery"] = {
            "mode": "solo", "participants": [self.item_id],
            "merge_order": [self.item_id], "shared_gates": [],
        }
        delivered["resources"][2]["access"] = "read"
        delivered["criteria"][0]["tests"] = ["integrated"]
        self.assert_invalid(
            delivered, "must be at stage done",
            stages={self.dependency_id: "verify"})

        bad_provides = self.joint()
        bad_provides["dependencies"][0]["provides"] = ["root-mount"]
        self.assert_invalid(
            bad_provides, "provides must equal",
            stages={self.dependency_id: "implement"})

        outside = self.solo()
        outside["resources"][0]["provider"] = "0099-unknown"
        self.assert_invalid(outside, "not the current item or a dependency")

    def test_item_provided_runtime_and_device_resources_are_valid(self):
        for kind in ("runtime", "device"):
            with self.subTest(kind=kind):
                value = self.solo()
                value["resources"][1]["kind"] = kind
                value["resources"][1]["provider"] = self.item_id
                feasibility.validate_acceptance(
                    value, item_id=self.item_id,
                    spec_bytes=self.spec, plan_bytes=self.plan)

    def test_require_uses_captured_config_bytes_and_returns_immutable_snapshot(self):
        self.write_contract()
        config = self.config_snapshot(value={
            "version": 1, "merge": "auto", "gates": [],
        })
        snapshot = feasibility.require(self.repo, self.item_id, config=config)

        self.assertEqual(snapshot.pending_tasks, ("Build feature",))
        self.assertEqual(snapshot.report["status"], "pass")
        with self.assertRaises(TypeError):
            snapshot.acceptance["item"] = "9999-mutated"
        with self.assertRaises(TypeError):
            snapshot.report["status"] = "mutated"
        handoff = json.loads(feasibility.worker_handoff(snapshot))
        self.assertEqual(handoff["spec"], self.spec.decode())
        self.assertEqual(handoff["plan"], self.plan.decode())
        self.assertEqual(handoff["owned_paths"], ["src"])

        self.write_config([])
        disabled = self.config_snapshot(value={
            "version": 1, "merge": "auto", "gates": ["feasibility"],
        })
        self.assertIsNone(feasibility.require(
            self.repo, self.item_id, config=disabled))

    def test_require_reads_dependency_metadata_and_requires_done_delivery(self):
        self.write_item(self.dependency_id, stage="verify")
        contract = self.joint()
        contract["dependencies"][0]["relation"] = "delivered"
        contract["participants"] = contract["participants"][:1]
        contract["delivery"] = {
            "mode": "solo", "participants": [self.item_id],
            "merge_order": [self.item_id], "shared_gates": [],
        }
        contract["resources"][2]["access"] = "read"
        self.write_contract(contract)
        with self.assertRaisesRegex(feasibility.FeasibilityError, "stage done"):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

        self.write_item(self.dependency_id, stage="done")
        snapshot = feasibility.require(
            self.repo, self.item_id, config=self.config_snapshot())
        self.assertEqual(snapshot.report["status"], "pass")

    def test_unsafe_artifacts_invalid_bytes_duplicates_and_oversize_refuse(self):
        self.write_contract()
        acceptance = self.repo / ".factory/items" / self.item_id / "acceptance.json"
        outside = self.repo / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        acceptance.unlink()
        acceptance.symlink_to(outside)
        with self.assertRaises(feasibility.FeasibilityError):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

        acceptance.unlink()
        acceptance.write_bytes(b'{"version":1,"version":1}')
        with self.assertRaisesRegex(feasibility.FeasibilityError, "duplicate key"):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

        self.write_contract()
        (acceptance.parent / "plan.md").write_bytes(b"\xff")
        with self.assertRaisesRegex(feasibility.FeasibilityError, "invalid UTF-8"):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

        self.write_contract()
        (acceptance.parent / "plan.md").write_bytes(b"x" * (1_048_576 + 1))
        with self.assertRaisesRegex(feasibility.FeasibilityError, "read limit"):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

    def test_invalid_spec_and_completed_repository_plan_refuse(self):
        invalid_spec = b"\xff"
        contract = self.solo()
        contract["spec_sha256"] = feasibility.sha256_bytes(invalid_spec)
        self.write_contract(contract)
        directory = self.repo / ".factory/items" / self.item_id
        (directory / "spec.md").write_bytes(invalid_spec)
        config = self.config_snapshot()
        with self.assertRaisesRegex(feasibility.FeasibilityError, "spec.md: invalid UTF-8"):
            feasibility.require(self.repo, self.item_id, config=config)
        report = feasibility.inspect(self.repo, self.item_id, config=config)
        self.assertEqual(report["status"], "fail")
        self.assertIn("spec.md: invalid UTF-8", report["errors"][0])

        complete = b"- [x] complete\n"
        self.spec = b"valid spec\n"
        self.write_contract(self.solo(plan=complete), plan=complete)
        with self.assertRaisesRegex(feasibility.FeasibilityError, "unchecked task"):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unsupported")
    def test_fifo_config_artifact_and_dependency_are_rejected_without_blocking(self):
        self.write_contract()
        config_path = self.repo / ".factory/config.json"
        config_path.unlink()
        os.mkfifo(config_path)
        with self.assertRaises(config_state.ConfigStateError):
            config_state.capture(self.repo)

        config_path.unlink()
        self.write_config(["feasibility"])
        acceptance = self.repo / ".factory/items" / self.item_id / "acceptance.json"
        acceptance.unlink()
        os.mkfifo(acceptance)
        with self.assertRaises(feasibility.FeasibilityError):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

        acceptance.unlink()
        self.write_item(self.dependency_id, stage="implement")
        self.write_contract(self.joint())
        dependency = self.repo / ".factory/items" / self.dependency_id / "item.md"
        dependency.unlink()
        os.mkfifo(dependency)
        with self.assertRaises(feasibility.FeasibilityError):
            feasibility.require(
                self.repo, self.item_id, config=self.config_snapshot())

    def test_cross_file_change_and_detached_item_ancestor_are_rejected(self):
        self.write_contract()
        real_snapshot = safeio._snapshot_from_chain
        acceptance_reads = 0

        def change_spec_after_final_acceptance(*args, **kwargs):
            nonlocal acceptance_reads
            result = real_snapshot(*args, **kwargs)
            if result.relative.name == "acceptance.json":
                acceptance_reads += 1
                if acceptance_reads == 2:
                    (self.repo / ".factory/items" / self.item_id / "spec.md").write_bytes(
                        b"changed\n")
            return result

        with mock.patch.object(
                safeio, "_snapshot_from_chain",
                side_effect=change_spec_after_final_acceptance):
            with self.assertRaises(feasibility.FeasibilityError):
                feasibility.require(
                    self.repo, self.item_id, config=self.config_snapshot())

        self.write_contract()
        snapshot = feasibility.require(
            self.repo, self.item_id, config=self.config_snapshot())
        directory = self.repo / ".factory/items" / self.item_id
        moved = directory.with_name(self.item_id + "-moved")
        directory.rename(moved)
        directory.mkdir()
        try:
            with self.assertRaises(safeio.SafeIOError):
                safeio.revalidate(snapshot.inputs)
        finally:
            directory.rmdir()
            moved.rename(directory)

    def test_inspect_is_deterministic_json_safe_and_never_exposes_other_scope(self):
        self.write_item(self.dependency_id, stage="implement")
        self.write_contract(self.joint())
        first = feasibility.inspect(
            self.repo, self.item_id, config=self.config_snapshot())
        second = feasibility.inspect(
            self.repo, self.item_id, config=self.config_snapshot())
        self.assertEqual(first, second)
        json.dumps(first, sort_keys=True)
        self.assertNotIn('"owned_paths": [\n      "app"', first["handoff"])

        broken = self.solo()
        broken["resources"][0]["availability"] = "unavailable"
        self.write_contract(broken)
        report = feasibility.inspect(
            self.repo, self.item_id, config=self.config_snapshot())
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["errors"], sorted(report["errors"]))


if __name__ == "__main__":
    unittest.main()
