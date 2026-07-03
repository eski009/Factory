import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, paths


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_creates_expected_tree(self):
        created = initrepo.init(self.repo, product="demo")
        self.assertTrue((self.repo / ".factory/config.json").exists())
        self.assertTrue((self.repo / ".factory/ledgers/bids.jsonl").exists())
        self.assertTrue((self.repo / "docs/factory/roadmap.md").exists())
        self.assertTrue((self.repo / "docs/factory/brain/vision.md").exists())
        self.assertTrue((self.repo / "docs/factory/council/product.md").exists())
        self.assertTrue((self.repo / "docs/factory/packets").is_dir())
        config = json.loads((self.repo / ".factory/config.json").read_text())
        self.assertEqual(config["merge"], "auto")
        self.assertEqual(config["gates"], ["design"])
        self.assertEqual(config["product"], "demo")
        self.assertEqual(created, sorted(created))

    def test_init_is_idempotent_and_never_clobbers(self):
        initrepo.init(self.repo)
        marker = self.repo / "docs/factory/brain/vision.md"
        marker.write_text("MY EDIT\n", encoding="utf-8")
        second = initrepo.init(self.repo)
        self.assertEqual(second, [])
        self.assertEqual(marker.read_text(), "MY EDIT\n")

    def test_validate_missing_config(self):
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 1)
        self.assertIn("run init", errors[0])

    def test_validate_clean_tree(self):
        initrepo.init(self.repo)
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_flags_bad_item_and_bad_ledger_line(self):
        initrepo.init(self.repo)
        bad = paths.item_dir(self.repo, "0001-bad")
        bad.mkdir(parents=True)
        (bad / "item.md").write_text("not frontmatter\n", encoding="utf-8")
        (paths.ledgers_dir(self.repo) / "bids.jsonl").write_text("{oops\n", encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 2)

    def test_validate_flags_bad_log_line(self):
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        log_path = paths.item_dir(self.repo, "0001-x") / "log.jsonl"
        log_path.write_text('{"event": "item.created", "ts": "x"}\n{oops\n',
                             encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(errors, ["0001-x/log.jsonl:2: invalid JSON"])

    def test_validate_flags_schema_violation(self):
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        item_md = paths.item_dir(self.repo, "0001-x") / "item.md"
        item_md.write_text(item_md.read_text().replace("stage: idea", "stage: shipping"))
        self.assertTrue(initrepo.validate_tree(self.repo))

    def test_validate_flags_schema_invalid_ledger_entry(self):
        initrepo.init(self.repo)
        bad_bid = {"id": "bid-0001", "ts": "2026-07-03T12:00:00Z", "agent": "intern",
                   "topic": "t", "item": "", "claim": "c", "evidence": ["e"],
                   "surface": "s", "severity": "low"}
        (paths.ledgers_dir(self.repo) / "bids.jsonl").write_text(
            json.dumps(bad_bid, sort_keys=True) + "\n", encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(len(errors), 1)
        self.assertIn("bids.jsonl:1", errors[0])

    def test_validate_accepts_valid_ledger_entries(self):
        initrepo.init(self.repo)
        from scripts.factory.lib import council
        import os
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        try:
            council.file_bid(self.repo, agent="product", topic="t", claim="c",
                             evidence=["e"], surface="s", severity="low")
            council.record_judgement(self.repo, "bid-0001", "reject", "no")
        finally:
            os.environ.pop("FACTORY_NOW", None)
        self.assertEqual(initrepo.validate_tree(self.repo), [])


class ConsistencyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        from scripts.factory.lib import council
        self.council = council
        initrepo.init(self.repo)
        import os
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.bid = council.file_bid(
            self.repo, agent="architecture", topic="boundaries",
            claim="Split module", evidence=["src/big.py"],
            surface="brain/decisions.md", severity="high")

    def tearDown(self):
        import os
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_clean_state_via_file_bid_and_record_judgement_validates(self):
        self.council.record_judgement(
            self.repo, "bid-0001", "accept", "good find",
            surface="brain/decisions.md", anchor="## Module boundaries")
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_double_judgement_flagged(self):
        self.council.record_judgement(self.repo, "bid-0001", "reject", "no")
        forged = {"id": "jdg-0002", "ts": "2026-07-03T12:00:00Z", "bid": "bid-0001",
                  "decision": "accept", "reason": "changed my mind",
                  "surface": "brain/decisions.md", "anchor": "## X"}
        self.council.append_ledger(self.repo, "judgements", forged)
        rep = {"ts": "2026-07-03T12:00:00Z", "agent": "architecture",
               "topic": "boundaries", "delta": 0.05, "judgement": "jdg-0002"}
        self.council.append_ledger(self.repo, "reputation", rep)
        errors = initrepo.validate_tree(self.repo)
        self.assertIn(
            "ledgers/consistency: bid bid-0001 judged more than once", errors)

    def test_accept_judgement_missing_surface_anchor_flagged(self):
        forged = {"id": "jdg-0001", "ts": "2026-07-03T12:00:00Z", "bid": "bid-0001",
                  "decision": "accept", "reason": "no surface/anchor"}
        self.council.append_ledger(self.repo, "judgements", forged)
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "ledgers/consistency: judgement jdg-0001 (accept) missing surface/anchor" in e
            for e in errors))

    def test_reputation_wrong_delta_flagged(self):
        jdg, rep = self.council.record_judgement(
            self.repo, "bid-0001", "accept", "good find",
            surface="brain/decisions.md", anchor="## Module boundaries")
        # Overwrite the ledger with a forged reputation event carrying the wrong delta.
        ledger_path = self.repo / ".factory/ledgers/reputation.jsonl"
        bad_rep = dict(rep)
        bad_rep["delta"] = 0.99
        ledger_path.write_text(json.dumps(bad_rep, sort_keys=True) + "\n",
                                encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertIn(
            f"ledgers/consistency: reputation for {jdg['id']} has wrong delta/agent/topic",
            errors)

    def test_judgement_unknown_bid_flagged(self):
        forged = {"id": "jdg-0001", "ts": "2026-07-03T12:00:00Z", "bid": "bid-0999",
                  "decision": "reject", "reason": "no such bid"}
        self.council.append_ledger(self.repo, "judgements", forged)
        errors = initrepo.validate_tree(self.repo)
        self.assertIn(
            "ledgers/consistency: judgement jdg-0001 references unknown bid bid-0999",
            errors)

    def test_orphan_reputation_event_flagged(self):
        self.council.record_judgement(
            self.repo, "bid-0001", "accept", "good find",
            surface="brain/decisions.md", anchor="## Module boundaries")
        forged = {"ts": "2026-07-03T12:00:00Z", "agent": "product",
                  "topic": "t", "delta": 0.05, "judgement": "jdg-9999"}
        self.council.append_ledger(self.repo, "reputation", forged)
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "references unknown judgement jdg-9999" in e for e in errors))

    def test_judgement_missing_reputation_flagged(self):
        forged = {"id": "jdg-0001", "ts": "2026-07-03T12:00:00Z", "bid": "bid-0001",
                  "decision": "reject", "reason": "r",
                  "surface": "brain/decisions.md", "anchor": "## X"}
        self.council.append_ledger(self.repo, "judgements", forged)
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "has 0 reputation events" in e for e in errors))

    def test_duplicate_reputation_events_flagged(self):
        jdg, rep = self.council.record_judgement(
            self.repo, "bid-0001", "accept", "good find",
            surface="brain/decisions.md", anchor="## Module boundaries")
        forged = {"ts": "2026-07-03T12:00:00Z", "agent": "architecture",
                  "topic": "boundaries", "delta": 0.05, "judgement": "jdg-0001"}
        self.council.append_ledger(self.repo, "reputation", forged)
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "has 2 reputation events" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
