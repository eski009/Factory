import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, tiers


def _set_tiers(repo, block):
    p = repo / ".factory" / "config.json"
    data = json.loads(p.read_text())
    data["tiers"] = block
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                 encoding="utf-8")


class TierProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults(self):
        self.assertEqual(tiers.profile(self.repo, "epic"),
                         {"research": "deep", "review": "full", "assure": "full"})
        self.assertEqual(tiers.profile(self.repo, "feature"),
                         {"research": "web", "review": "full", "assure": "affected"})
        self.assertEqual(tiers.profile(self.repo, "bug"),
                         {"research": "off", "review": "light", "assure": "node"})

    def test_unknown_tier_falls_back_to_feature(self):
        self.assertEqual(tiers.profile(self.repo, "mystery"),
                         tiers.profile(self.repo, "feature"))

    def test_config_overrides_merge_over_defaults(self):
        _set_tiers(self.repo, {"feature": {"research": "deep"}})
        prof = tiers.profile(self.repo, "feature")
        self.assertEqual(prof["research"], "deep")
        self.assertEqual(prof["review"], "full")   # unspecified key kept

    def test_config_validates(self):
        _set_tiers(self.repo, {"bug": {"research": "off", "review": "light"}})
        self.assertEqual(initrepo.validate_tree(self.repo), [])

    def test_bad_review_enum_rejected(self):
        _set_tiers(self.repo, {"bug": {"review": "medium"}})
        errors = initrepo.validate_tree(self.repo)
        self.assertTrue(any("review" in e for e in errors), errors)

    def test_assure_defaults_per_tier(self):
        self.assertEqual(tiers.profile(self.repo, "epic")["assure"], "full")
        self.assertEqual(tiers.profile(self.repo, "feature")["assure"], "affected")
        self.assertEqual(tiers.profile(self.repo, "bug")["assure"], "node")

    def test_assure_config_override(self):
        _set_tiers(self.repo, {"bug": {"assure": "affected"}})
        self.assertEqual(tiers.profile(self.repo, "bug")["assure"], "affected")


class TierRecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_keys_are_exactly_the_six(self):
        rec = tiers.record(self.repo, "bug", declared=True)
        self.assertEqual(
            set(rec),
            {"tier", "tier_declared", "research", "review", "assure", "source"})

    def test_record_stock_config_is_defaults(self):
        self.assertEqual(
            tiers.record(self.repo, "bug", declared=True),
            {"tier": "bug", "tier_declared": True, "research": "off",
             "review": "light", "assure": "node", "source": "defaults"})

    def test_record_levels_are_enum_members_for_every_tier(self):
        for tier in ("epic", "feature", "bug"):
            rec = tiers.record(self.repo, tier, declared=True)
            self.assertIn(rec["research"],
                          ("off", "inputs-only", "web", "deep"))
            self.assertIn(rec["review"], ("light", "full"))
            self.assertIn(rec["assure"], ("node", "affected", "full"))

    def test_record_source_is_config_when_any_one_key_overridden(self):
        _set_tiers(self.repo, {"bug": {"review": "full"}})
        rec = tiers.record(self.repo, "bug", declared=True)
        self.assertEqual(rec["source"], "config")
        self.assertEqual(rec["review"], "full")
        self.assertEqual(rec["assure"], "node")

    def test_record_source_is_fallback_for_unknown_tier(self):
        rec = tiers.record(self.repo, "chore", declared=False)
        self.assertEqual(rec["source"], "fallback")
        self.assertEqual(rec["tier"], "chore")
        self.assertEqual(rec["research"], "web")
        self.assertEqual(rec["review"], "full")
        self.assertEqual(rec["assure"], "affected")

    def test_record_tier_declared_is_carried_verbatim(self):
        self.assertIs(
            tiers.record(self.repo, "feature", declared=False)["tier_declared"],
            False)
        self.assertIs(
            tiers.record(self.repo, "feature", declared=True)["tier_declared"],
            True)

    def test_record_degrades_to_defaults_on_malformed_config(self):
        (self.repo / ".factory" / "config.json").write_text(
            "{not json", encoding="utf-8")
        self.assertEqual(
            tiers.record(self.repo, "bug", declared=True),
            {"tier": "bug", "tier_declared": True, "research": "off",
             "review": "light", "assure": "node", "source": "defaults"})

    def test_record_ignores_unknown_override_keys(self):
        _set_tiers(self.repo, {"bug": {"verify": "deep"}})
        rec = tiers.record(self.repo, "bug", declared=True)
        self.assertEqual(rec["source"], "defaults")
        self.assertNotIn("verify", rec)

    def test_defaults_still_has_exactly_three_keys_per_tier(self):
        for tier, levels in tiers.DEFAULTS.items():
            self.assertEqual(set(levels), {"research", "review", "assure"},
                             f"{tier} grew or lost a key")
        self.assertEqual(set(tiers.DEFAULTS), {"epic", "feature", "bug"})


if __name__ == "__main__":
    unittest.main()
