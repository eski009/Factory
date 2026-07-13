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
                         {"research": "deep", "review": "full"})
        self.assertEqual(tiers.profile(self.repo, "feature"),
                         {"research": "web", "review": "full"})
        self.assertEqual(tiers.profile(self.repo, "bug"),
                         {"research": "off", "review": "light"})

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


if __name__ == "__main__":
    unittest.main()
