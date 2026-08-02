"""Item 0013 - assure attribution: merge-base primitives and the ship
gate's ordered attribution rules."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, machine, paths

ITEM = "0001-thing"
OWNER = "0002-stale-restriction-values"
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, env=GIT_ENV,
                          capture_output=True, text=True).stdout.strip()


class AttributionTest(unittest.TestCase):
    """A factory repo on a real git repo whose integration branch is
    `main` and whose item branch is `factory/0001-thing`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        initrepo.init(self.repo, product="demo")
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "root")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "branch", f"factory/{ITEM}")
        self.base_sha = git(self.repo, "rev-parse", "HEAD")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def move_merge_base(self):
        """Advance main AND the item branch so the merge base moves."""
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "second")
        head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "branch", "-f", f"factory/{ITEM}", head)
        return head


class TestMergeBasePrimitives(AttributionTest):
    def test_default_branch_prefers_origin_head(self):
        git(self.repo, "update-ref", "refs/remotes/origin/main", self.base_sha)
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD",
            "refs/remotes/origin/main")
        self.assertEqual(machine._default_branch(self.repo), "main")

    def test_default_branch_falls_back_to_main(self):
        self.assertEqual(machine._default_branch(self.repo), "main")

    def test_default_branch_falls_back_to_master(self):
        git(self.repo, "branch", "-M", "master")
        self.assertEqual(machine._default_branch(self.repo), "master")

    def test_default_branch_none_when_unresolvable(self):
        git(self.repo, "branch", "-M", "trunk")
        git(self.repo, "branch", "-D", f"factory/{ITEM}")
        self.assertIsNone(machine._default_branch(self.repo))

    def test_default_branch_none_outside_a_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(machine._default_branch(Path(tmp)))

    def test_merge_base_returns_forty_hex(self):
        sha = machine._merge_base(self.repo, "main", ITEM)
        self.assertEqual(sha, self.base_sha)
        self.assertRegex(sha, r"^[0-9a-f]{40}$")

    def test_merge_base_none_for_missing_item_branch(self):
        self.assertIsNone(machine._merge_base(self.repo, "main", "0099-nope"))

    def test_merge_base_none_for_missing_branch_argument(self):
        self.assertIsNone(machine._merge_base(self.repo, None, ITEM))

    def test_merge_base_moves_when_both_branches_advance(self):
        moved = self.move_merge_base()
        self.assertNotEqual(moved, self.base_sha)
        self.assertEqual(machine._merge_base(self.repo, "main", ITEM), moved)


class GateTest(AttributionTest):
    """Builds an item parked at assure with one failing scenario, then
    exercises the ordered rules of item 0013 §5."""

    def enable(self, on=True):
        cfg = json.loads(paths.config_path(self.repo).read_text(
            encoding="utf-8"))
        cfg["assure"] = {"attribution": bool(on)}
        paths.config_path(self.repo).write_text(
            json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def make_item(self, journeys="J-001"):
        items.save_item(self.repo, {
            "id": ITEM, "title": "Thing", "stage": "assure", "kind": "backend",
            "tier": "feature", "journeys": journeys, "priority": 1,
            "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z"}, "# Thing\n")
        for event in ("implement.completed", "verify.green", "assure.passed"):
            logs.append_event(self.repo, ITEM, event)

    def make_owner(self, stage="idea", item_id=OWNER):
        items.save_item(self.repo, {
            "id": item_id, "title": "Stale values", "stage": stage,
            "kind": "backend", "tier": "bug",
            "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z"}, "# Stale values\n")
        return item_id

    def branch_evidence(self):
        d = paths.item_dir(self.repo, ITEM) / "assurance" / "screenshots"
        d.mkdir(parents=True, exist_ok=True)
        (d / "s1.txt").write_text("branch walk\n", encoding="utf-8")
        return [{"type": "transcript", "path": "assurance/screenshots/s1.txt"}]

    def base_evidence(self, sha=None, rel=None, on_disk=True):
        sha = sha or self.base_sha
        rel = rel if rel is not None else f"assurance/base/{sha}/t.txt"
        if on_disk and not rel.startswith("/") and ".." not in rel:
            p = paths.item_dir(self.repo, ITEM) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("base walk\n", encoding="utf-8")
        return [{"type": "transcript", "path": rel}]

    def base(self, sha=None, branch="main", evidence=None):
        sha = sha or self.base_sha
        return {"branch": branch, "merge_base": sha,
                "evidence": self.base_evidence(sha)
                if evidence is None else evidence}

    def scenario(self, **over):
        s = {"id": "S2", "verdict": "fail", "expected": "card shows",
             "actual": "card missing", "evidence": self.branch_evidence()}
        s.update(over)
        return s

    def write_verdicts(self, *scenarios):
        payload = {"item": ITEM, "journeys": [
            {"id": "J-001", "surface": "cli", "scenarios": list(scenarios)}]}
        p = paths.item_dir(self.repo, ITEM) / "assurance" / "verdicts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def ship(self):
        # machine.advance returns (meta, breaker_verdict) since item 0016;
        # the gate tests only care about the advanced meta.
        meta, _verdict = machine.advance(self.repo, ITEM, "ship")
        return meta

    def refusal(self):
        with self.assertRaises(machine.GateError) as ctx:
            self.ship()
        return str(ctx.exception)


class TestAttributionOff(GateTest):
    def test_non_pass_blocks_with_todays_message(self):
        self.make_item()
        self.write_verdicts(self.scenario())
        message = self.refusal()
        self.assertEqual(
            message,
            "journey J-001 scenario S2: verdict 'fail' is not pass")

    def test_unsolicited_attribution_is_a_clear_gate_error(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER, base=self.base()))
        message = self.refusal()
        self.assertIn("unsolicited attribution", message)
        self.assertIn("assure.attribution", message)

    def test_unsolicited_base_alone_is_rejected(self):
        self.make_item()
        self.write_verdicts(self.scenario(base=self.base()))
        self.assertIn("unsolicited attribution", self.refusal())

    def test_schema_invalid_payload_is_a_gate_error_not_a_traceback(self):
        self.make_item()
        self.write_verdicts(self.scenario(attribution="out-of-scope"))
        with self.assertRaises(machine.GateError) as ctx:
            self.ship()
        self.assertIn("assurance/verdicts.json", str(ctx.exception))

    def test_pass_still_ships(self):
        self.make_item()
        self.write_verdicts(self.scenario(verdict="pass"))
        self.assertEqual(self.ship()["stage"], "ship")


class TestAttributionOn(GateTest):
    def setUp(self):
        super().setUp()
        self.enable()

    def test_regression_blocks_naming_journey_scenario_and_class(self):
        self.make_item()
        self.write_verdicts(self.scenario(attribution="regression"))
        message = self.refusal()
        self.assertIn("J-001", message)
        self.assertIn("S2", message)
        self.assertIn("regression", message)

    def test_validated_pre_existing_ships(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER, base=self.base()))
        self.assertEqual(self.ship()["stage"], "ship")

    def test_attribution_on_a_passing_scenario_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            verdict="pass", attribution="pre-existing", owner=OWNER,
            base=self.base()))
        self.assertIn("passing scenario", self.refusal())

    def test_absent_attribution_on_a_non_pass_blocks(self):
        self.make_item()
        self.write_verdicts(self.scenario())
        self.assertIn("no attribution", self.refusal())

    def test_pre_existing_on_ambiguity_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            verdict="ambiguity", attribution="pre-existing", owner=OWNER,
            base=self.base()))
        self.assertIn("only an objective 'fail'", self.refusal())

    def test_pre_existing_on_blocker_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            verdict="blocker", attribution="pre-existing", owner=OWNER,
            base=self.base()))
        self.assertIn("only an objective 'fail'", self.refusal())

    def test_missing_base_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER))
        self.assertIn("without base evidence", self.refusal())

    def test_empty_base_evidence_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER,
            base={"branch": "main", "merge_base": self.base_sha,
                  "evidence": []}))
        self.assertIn("without base evidence", self.refusal())

    def test_absolute_base_evidence_path_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER,
            base=self.base(evidence=[{"type": "transcript",
                                      "path": "/etc/passwd"}])))
        self.assertIn("escapes the item dir", self.refusal())

    def test_dotdot_base_evidence_path_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER,
            base=self.base(evidence=[{"type": "transcript",
                                      "path": "assurance/../../secrets"}])))
        self.assertIn("escapes the item dir", self.refusal())

    def test_base_evidence_outside_the_sha_directory_blocks(self):
        self.make_item()
        self.make_owner()
        evidence = self.base_evidence(rel="assurance/screenshots/s1.txt")
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER,
            base=self.base(evidence=evidence)))
        message = self.refusal()
        self.assertIn(f"assurance/base/{self.base_sha}/", message)

    def test_base_evidence_missing_on_disk_blocks(self):
        self.make_item()
        self.make_owner()
        rel = f"assurance/base/{self.base_sha}/gone.txt"
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER,
            base=self.base(evidence=[{"type": "transcript", "path": rel}])))
        self.assertIn("missing on disk", self.refusal())

    def test_stale_merge_base_blocks_naming_both_shas(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER, base=self.base()))
        moved = self.move_merge_base()
        message = self.refusal()
        self.assertIn(self.base_sha, message)
        self.assertIn(moved, message)
        self.assertIn("stale", message)

    def test_merge_base_is_recomputed_even_when_self_consistent(self):
        # The recorded value alone is never trusted: the manifest here is
        # internally consistent (evidence lives under its own sha) and
        # still blocks, because the recomputed merge base differs.
        self.make_item()
        self.make_owner()
        moved = self.move_merge_base()
        stale = "b" * 40
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER,
            base=self.base(sha=stale)))
        message = self.refusal()
        self.assertIn(stale, message)
        self.assertIn(moved, message)

    def test_recovery_after_a_stale_refusal(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER, base=self.base()))
        moved = self.move_merge_base()
        self.refusal()
        stale_dir = (paths.item_dir(self.repo, ITEM) / "assurance" / "base"
                     / self.base_sha)
        self.assertTrue(stale_dir.exists())
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER, base=self.base(sha=moved)))
        self.assertEqual(self.ship()["stage"], "ship")

    def test_wrong_recorded_branch_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER,
            base=self.base(branch="develop")))
        self.assertIn("stale", self.refusal())

    def test_unresolvable_merge_base_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER, base=self.base()))
        git(self.repo, "branch", "-D", f"factory/{ITEM}")
        self.assertIn("unresolvable", self.refusal())

    def test_absent_owner_blocks(self):
        self.make_item()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", base=self.base()))
        self.assertIn("open owning item", self.refusal())

    def test_owner_naming_a_missing_item_blocks(self):
        self.make_item()
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner="0099-nobody",
            base=self.base()))
        message = self.refusal()
        self.assertIn("open owning item", message)
        self.assertIn("0099-nobody", message)

    def test_owner_at_stage_done_blocks(self):
        self.make_item()
        self.make_owner(stage="done")
        self.write_verdicts(self.scenario(
            attribution="pre-existing", owner=OWNER, base=self.base()))
        message = self.refusal()
        self.assertIn("open owning item", message)
        self.assertIn("done", message)

    def test_mixed_verdict_ships_when_every_non_pass_is_validated(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(
            self.scenario(id="S1", verdict="pass"),
            self.scenario(id="S2", attribution="pre-existing", owner=OWNER,
                          base=self.base()))
        self.assertEqual(self.ship()["stage"], "ship")

    def test_one_regression_among_pre_existing_still_blocks(self):
        self.make_item()
        self.make_owner()
        self.write_verdicts(
            self.scenario(id="S2", attribution="pre-existing", owner=OWNER,
                          base=self.base()),
            self.scenario(id="S3", attribution="regression"))
        self.assertIn("regression", self.refusal())

    def test_every_refusal_message_is_distinct(self):
        # AC7: each blocking condition names its own cause.
        seen = set()
        self.make_item()
        self.make_owner()
        cases = [
            self.scenario(attribution="pre-existing", owner=OWNER),
            self.scenario(verdict="pass", attribution="regression"),
            self.scenario(verdict="ambiguity", attribution="pre-existing",
                          owner=OWNER, base=self.base()),
            self.scenario(attribution="pre-existing", base=self.base()),
            self.scenario(attribution="regression"),
            self.scenario(),
        ]
        for scenario in cases:
            self.write_verdicts(scenario)
            message = self.refusal()
            self.assertNotIn(message, seen, message)
            seen.add(message)


if __name__ == "__main__":
    unittest.main()
