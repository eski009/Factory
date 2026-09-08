import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.factory.lib import initrepo, items, ledger, logs


class GitRepoTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Factory Tests")
        self.git("config", "user.email", "factory@example.test")
        self.counter = 0

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def git(self, *args, env=None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=merged_env).stdout.strip()

    def stamp(self, offset=None):
        if offset is None:
            offset = self.counter
            self.counter += 1
        value = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
            seconds=offset)
        return value.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def commit(self, rel, content=None, stamp=None, message=None):
        if content is None:
            content = f"content-{self.counter}\n"
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.git("add", "--", rel)
        when = stamp or self.stamp()
        self.git("commit", "-q", "-m", message or f"change {rel}", env={
            "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
        return self.git("rev-parse", "HEAD")

    def merge(self, branch, stamp=None):
        when = stamp or self.stamp()
        self.git("merge", "-q", "--no-ff", branch, "-m", f"merge {branch}",
                 env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
        return self.git("rev-parse", "HEAD")


class CommitLedgerTest(GitRepoTestCase):
    def test_classifies_first_parent_commits_and_product_merge_exactly(self):
        base = self.commit("README.md", "base\n")
        admin = self.commit("docs/note.md", "admin\n")

        self.git("switch", "-q", "-c", "product")
        self.commit("apps/ios/view.swift", "product\n")
        self.git("switch", "-q", "main")
        product_merge = self.merge("product")

        self.git("switch", "-q", "-c", "nonproduct")
        self.commit("docs/another.md", "admin\n")
        self.commit("scripts/tool.py", "other\n")
        self.git("switch", "-q", "main")
        nonproduct_merge = self.merge("nonproduct")

        result = ledger.summarize(
            self.repo, base, nonproduct_merge, product_paths=["apps/ios"])
        rows = {row["sha"]: row for row in result["commits"]["rows"]}
        self.assertEqual(rows[admin]["classification"], "admin-only")
        self.assertEqual(rows[product_merge]["classification"], "product-only")
        self.assertTrue(rows[product_merge]["has_product_path"])
        self.assertEqual(rows[nonproduct_merge]["classification"], "mixed")
        self.assertFalse(rows[nonproduct_merge]["has_product_path"])
        self.assertEqual(
            result["commits"]["product_changing_merges"]["value"],
            {"count": 1, "shas": [product_merge]})
        self.assertEqual(
            result["commits"]["admin_only_commits"]["value"],
            {"count": 1, "shas": [admin]})

    def test_rename_classifies_both_old_and_new_paths_and_weird_names(self):
        base = self.commit("apps/ios/old.swift", "old\n")
        target = "docs/new\nname.md"
        (self.repo / "docs").mkdir(exist_ok=True)
        self.git("mv", "--", "apps/ios/old.swift", target)
        when = self.stamp()
        self.git("commit", "-q", "-m", "rename", env={
            "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
        head = self.git("rev-parse", "HEAD")
        row = ledger.summarize(
            self.repo, base, head, product_paths=["apps/ios"]
        )["commits"]["rows"][0]
        self.assertEqual(row["classification"], "mixed")
        self.assertTrue(row["has_product_path"])
        self.assertEqual(row["paths"], ["apps/ios/old.swift", target])

    def test_no_product_paths_is_loudly_unavailable(self):
        base = self.commit("README.md")
        head = self.commit("docs/note.md")
        result = ledger.summarize(self.repo, base, head)
        self.assertEqual(result["commits"]["status"], "unavailable")
        self.assertIsNone(
            result["commits"]["product_changing_merges"]["value"])
        self.assertEqual(
            result["commits"]["rows"][0]["classification"], "unavailable")

    def test_rejects_non_first_parent_range_and_overlapping_prefixes(self):
        base = self.commit("README.md")
        self.git("switch", "-q", "-c", "side")
        side = self.commit("side.txt")
        self.git("switch", "-q", "main")
        head = self.commit("main.txt")
        with self.assertRaisesRegex(ledger.LedgerError, "first-parent"):
            ledger.summarize(self.repo, side, head, product_paths=["apps"])
        with self.assertRaisesRegex(ledger.LedgerError, "overlap"):
            ledger.summarize(
                self.repo, base, head, product_paths=["docs/product"])

    def test_empty_range_is_valid(self):
        head = self.commit("README.md")
        result = ledger.summarize(
            self.repo, head, head, product_paths=["apps/ios"])
        self.assertEqual(result["commits"]["rows"], [])
        self.assertEqual(
            result["commits"]["admin_only_commits"]["value"]["count"], 0)

    def test_reversed_endpoint_time_keeps_commits_but_not_observations(self):
        base = self.commit("README.md", stamp="2026-01-02T00:00:00+00:00")
        head = self.commit(
            "docs/note.md", stamp="2026-01-01T00:00:00+00:00")
        result = ledger.summarize(
            self.repo, base, head, product_paths=["apps/ios"])
        self.assertEqual(len(result["commits"]["rows"]), 1)
        self.assertEqual(result["timing"]["status"], "unavailable")
        self.assertIsNone(result["factory_items"]["completions"]["value"])
        self.assertTrue(any("reversed" in warning
                            for warning in result["warnings"]))


class ItemAliasTimingTest(GitRepoTestCase):
    def setUp(self):
        super().setUp()
        self.base = self.commit(
            "README.md", stamp="2026-01-01T10:00:00+00:00")
        self.head = self.commit(
            "docs/end.md", stamp="2026-01-01T14:00:00+00:00")
        initrepo.init(self.repo)
        self.item = "0001-example"
        items.save_item(self.repo, {
            "id": self.item, "title": "Example", "stage": "done",
            "kind": "backend", "created": "2026-01-01T09:00:00Z",
            "updated": "2026-01-01T13:30:00Z",
        }, "")
        os.environ["FACTORY_NOW"] = "2026-01-01T09:00:00Z"
        logs.append_event(self.repo, self.item, "item.created")

    def log_at(self, stamp, from_stage, to_stage):
        os.environ["FACTORY_NOW"] = stamp
        logs.append_event(self.repo, self.item, "stage.advance",
                          {"from": from_stage, "to": to_stage})

    def evidence_at(self, stamp, event, data):
        os.environ["FACTORY_NOW"] = stamp
        logs.append_event(self.repo, self.item, event, data)

    def wave(self, wave_id, tested_sha, started, finished, **changes):
        data = {
            "wave_id": wave_id,
            "purpose": "integrated",
            "stage": "verify",
            "command": ["python3", "-m", "unittest"],
            "started_at": started,
            "finished_at": finished,
            "result": "passed",
            "tests": {"passed": 4, "failed": 0, "skipped": 0},
            "tested_sha": tested_sha,
            "green_sha": tested_sha,
            "shipping_ref": None,
            "flows": ["J-001:S1"],
            "shipped_flows": [],
            "screenshots": [],
        }
        data.update(changes)
        return data

    def test_current_inventory_completions_and_timing_are_separate(self):
        self.log_at("2026-01-01T09:30:00Z", "idea", "plan")
        self.log_at("2026-01-01T11:00:00Z", "plan", "review")
        self.log_at("2026-01-01T12:00:00Z", "review", "waiting-human")
        self.log_at("2026-01-01T13:00:00Z", "waiting-human", "done")
        self.log_at("2026-01-01T13:30:00Z", "ship", "done")
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        current = result["factory_items"]["current"]["value"]
        completions = result["factory_items"]["completions"]["value"]
        self.assertEqual(current["count"], 1)
        self.assertEqual(current["by_stage"], {"done": 1})
        self.assertEqual(completions["count"], 1)
        self.assertEqual(completions["items"], [self.item])
        self.assertEqual(len(completions["events"]), 2)
        rows = result["timing"]["rows"]
        self.assertEqual(
            [(row["stage"], row["seconds"]) for row in rows],
            [("plan", 3600), ("review", 3600), ("waiting-human", 3600)])
        self.assertEqual([row["category"] for row in rows],
                         ["active", "review", "waiting"])
        self.assertTrue(rows[0]["clipped"])

    def test_aliases_are_cumulative_separate_and_allow_same_target(self):
        alias_path = self.repo / ".factory/ledger-aliases.json"
        alias_path.write_text(json.dumps({
            "AUD-1": {"item": self.item, "status": "closed"},
            "AUD-2": {"item": self.item},
            "AUD-3": {"item": "9999-missing", "status": None},
        }), encoding="utf-8")
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        aliases = result["aliases"]["value"]
        self.assertEqual(aliases["count"], 3)
        self.assertEqual(result["factory_items"]["current"]["value"]["count"], 1)
        self.assertIsNone(aliases["rows"][1]["status"])
        self.assertTrue(any("unknown item" in warning
                            for warning in result["warnings"]))

    def test_duplicate_alias_key_is_rejected(self):
        alias_path = self.repo / ".factory/ledger-aliases.json"
        alias_path.write_text(
            '{"AUD-1":{"item":"0001-example"},'
            '"AUD-1":{"item":"0001-example"}}', encoding="utf-8")
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(result["aliases"]["status"], "unavailable")
        self.assertTrue(any("duplicate JSON key" in warning
                            for warning in result["warnings"]))

    def test_broken_alias_symlink_is_not_treated_as_absent(self):
        alias_path = self.repo / ".factory/ledger-aliases.json"
        alias_path.symlink_to(self.repo / "missing-alias-target.json")
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(result["aliases"]["status"], "unavailable")
        self.assertTrue(any("regular file" in warning
                            for warning in result["warnings"]))

    def test_out_of_order_stage_history_is_unavailable_for_that_item(self):
        self.log_at("2026-01-01T12:00:00Z", "idea", "review")
        self.log_at("2026-01-01T11:00:00Z", "review", "done")
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(result["timing"]["rows"], [])
        self.assertEqual(result["timing"]["unavailable"][0]["item"], self.item)
        self.assertEqual(
            result["factory_items"]["completions"]["value"]["count"], 0)

    def test_missing_history_for_current_non_idea_item_is_unavailable(self):
        (self.repo / f".factory/items/{self.item}/log.jsonl").unlink()
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(result["timing"]["rows"], [])
        self.assertIn("item.created boundary", result["warnings"][0])

    def test_completion_survives_missing_timing_boundary(self):
        log_path = self.repo / f".factory/items/{self.item}/log.jsonl"
        log_path.unlink()
        self.log_at("2026-01-01T11:00:00Z", "ship", "done")
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(
            result["factory_items"]["completions"]["value"]["items"],
            [self.item])
        self.assertEqual(result["timing"]["rows"], [])
        self.assertIn("item.created boundary",
                      result["timing"]["unavailable"][0]["reason"])

    def test_unreadable_log_is_item_specific_unavailable(self):
        log_path = self.repo / f".factory/items/{self.item}/log.jsonl"
        log_path.unlink()
        log_path.mkdir()
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(result["timing"]["rows"], [])
        self.assertEqual(result["timing"]["unavailable"][0]["item"], self.item)
        self.assertTrue(any("log is unreadable" in warning
                            for warning in result["warnings"]))

    def test_invalid_utf8_line_is_reported_as_corrupt(self):
        log_path = self.repo / f".factory/items/{self.item}/log.jsonl"
        with log_path.open("ab") as stream:
            stream.write(
                b'{"data":{"note":"\xff"},"event":"evidence",'
                b'"ts":"2026-01-01T10:30:00Z"}\n')
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertTrue(any("1 corrupt log line" in warning
                            for warning in result["warnings"]))

    def test_waves_distinguish_delivered_candidate_and_component_evidence(self):
        screenshot = self.repo / "evidence/wave.png"
        screenshot.parent.mkdir()
        screenshot.write_bytes(b"captured-state")
        digest = hashlib.sha256(screenshot.read_bytes()).hexdigest()
        delivered = self.wave(
            "delivered", self.head, "2026-01-01T10:30:00Z",
            "2026-01-01T11:00:00Z", shipping_ref=self.head,
            shipped_flows=["J-001:S1"], screenshots=[{
                "path": "evidence/wave.png", "sha256": digest,
                "flow": "J-001:S1", "state": "checkout"}])
        candidate = self.wave(
            "candidate", self.base, "2026-01-01T11:00:00Z",
            "2026-01-01T11:30:00Z")
        component = self.wave(
            "component", self.head, "2026-01-01T11:30:00Z",
            "2026-01-01T12:00:00Z", purpose="component")
        for data in (delivered, candidate, component):
            self.evidence_at("2026-01-01T12:00:00Z", "test.wave", data)
        rows = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"]
        )["waves"]["value"]["rows"]
        self.assertEqual([row["delivery_status"] for row in rows],
                         ["delivery-bound", "candidate", "non-production"])
        self.assertEqual(rows[0]["duration_seconds"], 1800)
        self.assertTrue(rows[0]["screenshots"][0]["hash_matches"])

    def test_wave_finish_boundary_and_duplicate_ids_are_excluded(self):
        at_base = self.wave(
            "at-base", self.head, "2026-01-01T09:59:00Z",
            "2026-01-01T10:00:00Z")
        at_head = self.wave(
            "at-head", self.head, "2026-01-01T13:59:00Z",
            "2026-01-01T14:00:00Z")
        duplicate = self.wave(
            "duplicate", self.head, "2026-01-01T12:00:00Z",
            "2026-01-01T12:01:00Z")
        for data in (at_base, at_head, duplicate, duplicate):
            self.evidence_at("2026-01-01T12:00:00Z", "test.wave", data)
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual([row["wave_id"]
                          for row in result["waves"]["value"]["rows"]],
                         ["at-head"])
        self.assertTrue(any("duplicate wave_id" in warning
                            for warning in result["warnings"]))

    def test_stale_screenshot_hash_excludes_wave(self):
        screenshot = self.repo / "evidence/stale.png"
        screenshot.parent.mkdir()
        screenshot.write_bytes(b"current")
        wave = self.wave(
            "stale", self.head, "2026-01-01T11:00:00Z",
            "2026-01-01T11:01:00Z", screenshots=[{
                "path": "evidence/stale.png", "sha256": "0" * 64,
                "flow": "J-001:S1", "state": "checkout"}])
        self.evidence_at("2026-01-01T12:00:00Z", "test.wave", wave)
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(result["waves"]["value"]["rows"], [])
        self.assertTrue(any("hash mismatch" in warning
                            for warning in result["warnings"]))

    def test_activity_spans_overlap_clip_and_remain_separate(self):
        spans = [
            {"span_id": "test-crossing", "category": "test",
             "started_at": "2026-01-01T09:30:00Z",
             "finished_at": "2026-01-01T10:30:00Z", "source": "suite-a"},
            {"span_id": "review-one", "category": "review",
             "started_at": "2026-01-01T11:00:00Z",
             "finished_at": "2026-01-01T12:00:00Z", "source": "reviewer"},
        ]
        for data in spans:
            self.evidence_at("2026-01-01T12:00:00Z", "activity.span", data)
        timing = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"]
        )["timing"]
        rows = timing["activity_spans"]
        self.assertEqual([(row["span_id"], row["seconds"]) for row in rows],
                         [("test-crossing", 1800), ("review-one", 3600)])
        self.assertTrue(rows[0]["clipped"])
        self.assertEqual(timing["category_status"]["admin"],
                         {"status": "unmeasured", "value": None})
        self.assertNotIn("total", timing)

    def test_duplicate_spans_all_excluded(self):
        span = {"span_id": "same", "category": "admin",
                "started_at": "2026-01-01T11:00:00Z",
                "finished_at": "2026-01-01T12:00:00Z", "source": "ops"}
        self.evidence_at("2026-01-01T12:00:00Z", "activity.span", span)
        self.evidence_at("2026-01-01T12:01:00Z", "activity.span", span)
        result = ledger.summarize(
            self.repo, self.base, self.head, product_paths=["apps/ios"])
        self.assertEqual(result["timing"]["activity_spans"], [])
        self.assertTrue(any("duplicate span_id" in warning
                            for warning in result["warnings"]))

    def test_empty_observation_window_contains_no_spans(self):
        span = {"span_id": "crossing", "category": "admin",
                "started_at": "2026-01-01T09:00:00Z",
                "finished_at": "2026-01-01T11:00:00Z", "source": "ops"}
        self.evidence_at("2026-01-01T10:00:00Z", "activity.span", span)
        result = ledger.summarize(
            self.repo, self.base, self.base, product_paths=["apps/ios"])
        self.assertEqual(result["timing"]["activity_spans"], [])
        self.assertEqual(result["timing"]["category_status"]["admin"],
                         {"status": "unmeasured", "value": None})


class SyntheticAcceptanceTest(GitRepoTestCase):
    def test_123_first_parent_rows_are_six_product_merges_and_117_admin(self):
        base = self.commit("README.md", "base\n")
        expected_admin = []
        expected_product_merges = []
        for index in range(117):
            expected_admin.append(self.commit(
                f"docs/admin-{index:03d}.md", f"{index}\n"))
        for index in range(6):
            branch = f"product-{index}"
            self.git("switch", "-q", "-c", branch)
            self.commit(f"apps/ios/feature-{index}.swift", f"{index}\n")
            self.git("switch", "-q", "main")
            expected_product_merges.append(self.merge(branch))
        head = self.git("rev-parse", "HEAD")

        result = ledger.summarize(
            self.repo, base, head, product_paths=["apps/ios/"], synthetic=True)
        rows = result["commits"]["rows"]
        product = result["commits"]["product_changing_merges"]["value"]
        admin = result["commits"]["admin_only_commits"]["value"]
        self.assertTrue(result["run"]["synthetic"])
        self.assertEqual(len(rows), 123)
        self.assertEqual(product,
                         {"count": 6, "shas": expected_product_merges})
        self.assertEqual(admin, {"count": 117, "shas": expected_admin})
        self.assertTrue(set(product["shas"]).isdisjoint(admin["shas"]))
        self.assertTrue(any("not speed" in limit for limit in result["limits"]))


if __name__ == "__main__":
    unittest.main()
