import json
import shutil
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
        self.assertTrue((self.repo / "docs/factory/packets/reports").is_dir())
        config = json.loads((self.repo / ".factory/config.json").read_text())
        self.assertEqual(config["merge"], "auto")
        self.assertEqual(config["gates"], ["design"])
        self.assertEqual(config["product"], "demo")
        self.assertEqual(created, sorted(created))

    def test_init_creates_escapes_ledger(self):
        initrepo.init(self.repo)
        self.assertTrue((self.repo / ".factory" / "ledgers" / "escapes.jsonl").exists())

    def test_init_is_idempotent_and_never_clobbers(self):
        initrepo.init(self.repo)
        marker = self.repo / "docs/factory/brain/vision.md"
        marker.write_text("MY EDIT\n", encoding="utf-8")
        second = initrepo.init(self.repo)
        self.assertEqual(second, [])
        self.assertEqual(marker.read_text(), "MY EDIT\n")

    def test_init_scaffolds_packets_reports_idempotently(self):
        # F2: packets/reports dir is created on first init, idempotent on second
        first = initrepo.init(self.repo)
        self.assertTrue((self.repo / "docs/factory/packets/reports").is_dir())
        self.assertTrue(any("packets/reports" in p for p in first))
        second = initrepo.init(self.repo)
        self.assertEqual(second, [])

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

    def test_validate_flags_dir_id_mismatch(self):
        # C1: a copied item dir whose item.md still names the original id.
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        copy_dir = paths.item_dir(self.repo, "0002-x-copy")
        shutil.copytree(paths.item_dir(self.repo, "0001-x"), copy_dir)
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "0002-x-copy" in e and "does not match directory name" in e
            for e in errors))

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

    def test_validate_flags_hand_edited_stage_mismatching_log(self):
        # C2: hand-edit stage idea -> ship with no stage.advance events logged.
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        item_md = paths.item_dir(self.repo, "0001-x") / "item.md"
        item_md.write_text(item_md.read_text().replace("stage: idea", "stage: ship"))
        errors = initrepo.validate_tree(self.repo)
        self.assertIn(
            "0001-x: stage 'ship' does not match log (expected 'idea')", errors)

    def test_validate_clean_for_legitimately_advanced_item(self):
        # C2: an item advanced through the real engine stays clean.
        initrepo.init(self.repo)
        import os
        from scripts.factory.lib import machine
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        try:
            meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "backend",
                    "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
            items.save_item(self.repo, meta, "")
            machine.advance(self.repo, "0001-x", "triage")
        finally:
            os.environ.pop("FACTORY_NOW", None)
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_clean_for_fresh_add_at_idea_with_only_created_event(self):
        # C2: a fresh item with only an item.created log event (stage idea,
        # no stage.advance events) must not be flagged.
        initrepo.init(self.repo)
        from scripts.factory.lib import logs
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        logs.append_event(self.repo, "0001-x", "item.created")
        self.assertEqual(initrepo.validate_tree(self.repo), [])

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

    def test_validate_ignores_stage_advance_with_non_dict_data(self):
        # F1: non-dict data in stage.advance should not crash; expected stays unchanged
        initrepo.init(self.repo)
        from scripts.factory.lib import logs
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        # Append a malformed stage.advance with string data; it should be ignored
        logs.append_event(self.repo, "0001-x", "stage.advance", "oops")
        # Validate should not crash; expected stays at "idea", matching the item
        errors = initrepo.validate_tree(self.repo)
        self.assertEqual(errors, [])

    def test_default_config_has_research_depth_web(self):
        initrepo.init(self.repo, product="demo")
        config = json.loads((self.repo / ".factory/config.json").read_text())
        self.assertEqual(config["research"], {"depth": "web"})

    def test_validate_accepts_valid_research_depth(self):
        initrepo.init(self.repo)
        cfg = self.repo / ".factory/config.json"
        data = json.loads(cfg.read_text())
        data["research"] = {"depth": "deep"}
        cfg.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_rejects_bad_research_depth(self):
        initrepo.init(self.repo)
        cfg = self.repo / ".factory/config.json"
        data = json.loads(cfg.read_text())
        data["research"] = {"depth": "exhaustive"}
        cfg.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("depth" in e for e in errors))

    def test_init_scaffolds_personas_and_market(self):
        initrepo.init(self.repo)
        self.assertTrue((self.repo / "docs/factory/brain/personas.md").exists())
        self.assertTrue((self.repo / "docs/factory/brain/market.md").exists())

    def test_init_scaffolds_journeys_and_tree_validates(self):
        initrepo.init(self.repo)
        self.assertTrue((self.repo / "docs" / "factory" / "journeys" / "inventory.md").exists())
        self.assertTrue((self.repo / "docs" / "factory" / "journeys" / "graph.json").exists())
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_validate_flags_undecodable_config(self):
        # Item spec 0009 §1: byte corruption lands in the existing
        # invalid-JSON flag path — validate never tracebacks.
        initrepo.init(self.repo)
        (self.repo / ".factory/config.json").write_bytes(b"\xff\xfe{ not json")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("config.json: invalid JSON" in e for e in errors),
                        errors)

    def test_validate_flags_non_dict_config(self):
        initrepo.init(self.repo)
        (self.repo / ".factory/config.json").write_text(
            '["not", "an", "object"]\n', encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertIn("config.json: not an object", errors)

    def test_validate_flags_undecodable_item_md(self):
        initrepo.init(self.repo)
        bad = paths.item_dir(self.repo, "0001-bad")
        bad.mkdir(parents=True)
        (bad / "item.md").write_bytes(b"\xff\xfe not utf-8 \x80")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("0001-bad/item.md" in e for e in errors), errors)

    def test_validate_flags_item_with_missing_id_value(self):
        # Item spec 0009 §1: the id-mismatch path must use the .get value
        # in its message; an id-less/empty-id frontmatter is flagged
        # "missing id", never crashed on.
        initrepo.init(self.repo)
        bad = paths.item_dir(self.repo, "0001-x")
        bad.mkdir(parents=True)
        (bad / "item.md").write_text(
            "---\nid:\ntitle: X\nstage: idea\nkind: ui\n"
            "created: 2026-07-03T10:00:00Z\nupdated: 2026-07-03T10:00:00Z\n"
            "---\n\n# X\n", encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("missing id" in e for e in errors), errors)

    def test_validate_flags_non_dict_json_log_line(self):
        # Item spec 0009 rework (review round 1 blocking finding): a
        # parseable-but-non-dict log line (list, string, ...) must be
        # flagged, not fed to the stage-reconciliation loop below, which
        # calls .get() assuming every entry is a dict.
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        log_path = paths.item_dir(self.repo, "0001-x") / "log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write("[1, 2]\n")
            f.write('"hello"\n')
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(
            any("log.jsonl:1: invalid event" in e for e in errors), errors)
        self.assertTrue(
            any("log.jsonl:2: invalid event" in e for e in errors), errors)

    def test_validate_flags_bad_assurance_artifacts(self):
        initrepo.init(self.repo)
        meta = {"id": "0001-a", "title": "A", "stage": "assure", "kind": "ui",
                "journeys": "J-001",
                "created": "2026-07-15T10:00:00Z", "updated": "2026-07-15T10:00:00Z"}
        items.save_item(self.repo, meta, "# A\n")
        adir = paths.item_dir(self.repo, "0001-a") / "assurance"
        adir.mkdir(parents=True)
        (adir / "verdicts.json").write_text('{"nope": true}', encoding="utf-8")
        (adir / "impact.json").write_text('not json', encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("verdicts.json" in e for e in errors))
        self.assertTrue(any("impact.json" in e for e in errors))

    def test_validate_flags_bad_journey_graph(self):
        initrepo.init(self.repo)
        graph = paths.docs_root(self.repo) / "journeys" / "graph.json"
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_text('{"journeys": [{"id": "banana"}]}', encoding="utf-8")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("graph.json" in e for e in errors))

    def test_validate_flags_event_dict_missing_keys(self):
        # A dict line missing the required "event"/"ts" keys (append_event
        # writes both unconditionally) is corrupt at the same boundary
        # logs.read_events_with_stats already treats as skipped.
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        log_path = paths.item_dir(self.repo, "0001-x") / "log.jsonl"
        with log_path.open("a", encoding="utf-8") as f:
            f.write('{"foo": 1}\n')
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(
            any("log.jsonl:1: invalid event" in e for e in errors), errors)


class SpendValidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        meta = {"id": "0001-x", "title": "X", "stage": "idea", "kind": "ui",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "")
        import os
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        import os
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def log_spend(self, data):
        from scripts.factory.lib import logs
        logs.append_event(self.repo, "0001-x", "spend", data)

    def test_schema_loads_and_requires_provenance(self):
        schema = initrepo.load_schema("spend-event")
        self.assertEqual(schema["required"], ["provenance"])
        self.assertEqual(schema["properties"]["provenance"]["enum"],
                         ["measured", "proxy", "unmeasured"])
        self.assertNotIn("additionalProperties", schema)

    def test_spend_missing_provenance_flagged_with_file_line(self):
        self.log_spend({"stage": "implement", "dispatches": 2})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "0001-x/log.jsonl:1" in e and "provenance" in e for e in errors))

    def test_spend_bad_provenance_enum_flagged(self):
        self.log_spend({"provenance": "estimated"})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "0001-x/log.jsonl:1" in e and "'estimated'" in e for e in errors))

    def test_tokens_on_proxy_event_flagged(self):
        self.log_spend({"provenance": "proxy", "tokens": {"input": 5}})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "tokens present but provenance is not 'measured'" in e
            for e in errors))

    def test_measured_without_tokens_flagged(self):
        self.log_spend({"provenance": "measured", "dispatches": 1})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "measured spend event requires tokens" in e for e in errors))

    def test_spend_with_non_object_data_flagged(self):
        self.log_spend("oops")
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any(
            "0001-x/log.jsonl:1" in e and "must be an object" in e
            for e in errors))

    def test_spend_event_stage_assure_valid(self):
        errors = initrepo.spend_event_errors(
            {"provenance": "proxy", "stage": "assure", "source": "factory-assure",
             "dispatches": 1}, "x")
        self.assertEqual(errors, [])

    def test_valid_spend_and_unknown_events_stay_clean(self):
        self.log_spend({"provenance": "measured", "stage": "review",
                        "source": "factory-review", "dispatches": 6,
                        "tokens": {"input": 182340, "output": 21877},
                        "extra-key": "tolerated"})
        self.log_spend({"provenance": "proxy", "stage": "implement",
                        "dispatches": 2})
        from scripts.factory.lib import logs
        logs.append_event(self.repo, "0001-x", "some.unknown.event", {"x": 1})
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

    def test_duplicate_bid_id_flagged(self):
        # I1: hand-forged duplicate bid ids must be flagged by validate.
        forged = {"id": "bid-0001", "ts": "2026-07-03T12:00:00Z", "agent": "product",
                  "topic": "t2", "item": "", "claim": "another claim",
                  "evidence": ["e"], "surface": "s", "severity": "low"}
        self.council.append_ledger(self.repo, "bids", forged)
        errors = initrepo.validate_tree(self.repo)
        self.assertIn("ledgers/consistency: duplicate id bid-0001", errors)

    def test_duplicate_judgement_id_flagged(self):
        # I1: hand-forged duplicate judgement ids must be flagged.
        self.council.record_judgement(
            self.repo, "bid-0001", "reject", "no")
        forged = {"id": "jdg-0001", "ts": "2026-07-03T12:00:00Z", "bid": "bid-0001",
                  "decision": "reject", "reason": "dup"}
        self.council.append_ledger(self.repo, "judgements", forged)
        errors = initrepo.validate_tree(self.repo)
        self.assertIn("ledgers/consistency: duplicate id jdg-0001", errors)

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
