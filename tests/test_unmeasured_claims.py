"""AC19 - no artifact this item produces states a token or cost saving
without an explicit UNMEASURED provenance tag (brain/constraints.md:
"UNMEASURED is a loud literal").

`.factory/` is gitignored in this repo, so the item's own spec.md is
checked only when it is present on disk; the tracked artifacts
(CHANGELOG.md, the assure skill) are checked unconditionally.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIM_RE = re.compile(r"token sav|cost sav|saves? tokens|token saver",
                      re.IGNORECASE)
TRACKED = ("CHANGELOG.md", "skills/factory-assure/SKILL.md")


def _paragraphs(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _offending(path):
    text = path.read_text(encoding="utf-8")
    return [p for p in _paragraphs(text)
            if CLAIM_RE.search(p) and "UNMEASURED" not in p]


class TestUnmeasuredClaims(unittest.TestCase):
    def test_tracked_artifacts_tag_every_saving_claim(self):
        for rel in TRACKED:
            path = ROOT / rel
            self.assertTrue(path.exists(), rel)
            self.assertEqual(_offending(path), [], rel)

    def test_item_spec_tags_its_largest_token_saver_claim(self):
        spec = (ROOT / ".factory/items"
                / "0013-assure-attribution-gate-only-on-regressi" / "spec.md")
        if not spec.exists():
            self.skipTest(".factory/ is gitignored; spec.md not in this tree")
        text = spec.read_text(encoding="utf-8")
        self.assertIn("largest token saver", text)
        self.assertEqual(_offending(spec), [])

    def test_item_spec_states_the_accepted_boundary_verbatim(self):
        # AC18's stated-residual half.
        spec = (ROOT / ".factory/items"
                / "0013-assure-attribution-gate-only-on-regressi" / "spec.md")
        if not spec.exists():
            self.skipTest(".factory/ is gitignored; spec.md not in this tree")
        self.assertIn(
            "sha-match plus presence does not prove the evidence was "
            "produced by running that scenario at that sha; branch-run "
            "evidence copied into the `base/` directory passes every engine "
            "check and would ship a genuine regression as `pre-existing`",
            spec.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
