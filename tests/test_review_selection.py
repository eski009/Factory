import copy
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, review_selection as selection


def signal(name, evidence=None):
    return {"name": name, "evidence": evidence or [f"src/{name}.py:10"]}


def valid_receipt(item="0001-x"):
    return {
        "item": item, "round": 1, "mode": "adaptive",
        "diff": {"base": "abc123", "head": "def456",
                 "changed_paths": ["scripts/factory/lib/x.py"]},
        "signals": [],
        "selected": [
            {"role": "engineering-quality",
             "reasons": ["baseline.correctness-evidence"]},
            {"role": "architecture",
             "reasons": ["fallback.general-backend"]}],
        "omitted": [
            {"role": "product", "reasons": ["signal.not-applicable"]},
            {"role": "ui-taste", "reasons": ["signal.not-applicable"]},
            {"role": "customer", "reasons": ["signal.not-applicable"]},
            {"role": "commercial", "reasons": ["signal.not-applicable"]}],
        "escalation": {"conflicts": [], "blocking_roles": [],
                       "prior_roles": [], "added_role": ""},
        "outcomes": [
            {"role": "engineering-quality", "status": "returned",
             "report": "round-1/engineering-quality.md"},
            {"role": "architecture", "status": "returned",
             "report": "round-1/architecture.md"}],
        "independence": {"requested": True, "achieved": True,
                         "degradation": []}}


class SelectorTest(unittest.TestCase):
    def roles(self, **kwargs):
        return [r["role"] for r in selection.select_roles(**kwargs)["selected"]]

    def test_round_one_matrix(self):
        cases = (
            ([], ["engineering-quality", "architecture"]),
            ([signal("ui-taste")], ["engineering-quality", "ui-taste"]),
            ([signal("security")], ["engineering-quality", "architecture"]),
            ([signal("architecture")], ["engineering-quality", "architecture"]),
            ([signal("customer-trust")], ["engineering-quality", "customer"]),
            ([signal("product-behavior")], ["engineering-quality", "product"]),
            ([signal("commercial")], ["engineering-quality", "commercial"]),
        )
        for signals, expected in cases:
            with self.subTest(signals=signals):
                self.assertEqual(self.roles(mode="adaptive", round_number=1,
                                            signals=signals), expected)

    def test_round_one_reasons_caps_and_escalation(self):
        fallback = selection.select_roles(
            mode="adaptive", round_number=1, signals=[])
        self.assertEqual(fallback["selected"][1], {
            "role": "architecture", "reasons": ["fallback.general-backend"]})

        ordinary = [signal("security"), signal("customer-trust")]
        self.assertEqual(
            self.roles(mode="adaptive", round_number=1, signals=ordinary),
            ["engineering-quality", "architecture", "customer"])

        capped = selection.select_roles(
            mode="adaptive", round_number=1,
            signals=ordinary + [signal("commercial")])
        self.assertEqual([r["role"] for r in capped["selected"]],
                         ["engineering-quality", "architecture", "customer"])
        self.assertIn({"role": "commercial",
                       "reasons": ["adaptive.ordinary-cap"]},
                      capped["omitted"])

        for special in ("high-blast-radius", "irreversible"):
            with self.subTest(special=special):
                plan = selection.select_roles(
                    mode="adaptive", round_number=1,
                    signals=ordinary + [signal("ui-taste"), signal(special)])
                self.assertEqual([r["role"] for r in plan["selected"]],
                                 ["engineering-quality", "architecture",
                                  "customer", "ui-taste"])

        all_signals = [signal(name) for name in
                       selection.SIGNAL_PRECEDENCE + selection.SPECIAL_SIGNALS]
        self.assertLessEqual(len(self.roles(
            mode="adaptive", round_number=1, signals=all_signals)), 4)

    def test_ambiguous_uses_conservative_fallback(self):
        plan = selection.select_roles(
            mode="adaptive", round_number=1, signals=[signal("ambiguous")])
        self.assertEqual([r["role"] for r in plan["selected"]],
                         ["engineering-quality", "architecture", "product"])
        self.assertEqual(plan["selected"][1]["reasons"],
                         ["fallback.general-backend"])
        self.assertEqual(plan["selected"][2]["reasons"], ["ambiguous"])

    def test_duplicate_mapping_retains_both_reasons(self):
        plan = selection.select_roles(
            mode="adaptive", round_number=1,
            signals=[signal("architecture"), signal("security")])
        architecture = [r for r in plan["selected"]
                        if r["role"] == "architecture"]
        self.assertEqual(architecture, [{
            "role": "architecture", "reasons": ["security", "architecture"]}])

    def test_full_returns_every_role_once(self):
        plan = selection.select_roles(mode="full", round_number=1, signals=[])
        self.assertEqual([r["role"] for r in plan["selected"]],
                         list(council.ROLES))
        self.assertEqual(len({r["role"] for r in plan["selected"]}),
                         len(council.ROLES))
        self.assertTrue(all(r["reasons"] == ["override.full"]
                            for r in plan["selected"]))

    def test_tier_is_not_accepted(self):
        with self.assertRaises(TypeError):
            selection.select_roles(mode="adaptive", round_number=1,
                                   signals=[], tier="epic")

    def test_round_two_delta_selection(self):
        plan = selection.select_roles(
            mode="adaptive", round_number=2, signals=[],
            prior_roles=["engineering-quality", "architecture"],
            blocking_roles=["engineering-quality"])
        self.assertEqual([r["role"] for r in plan["selected"]],
                         ["engineering-quality"])
        self.assertEqual(plan["selected"][0]["reasons"],
                         ["round2.blocking-finding"])

        conflict = selection.select_roles(
            mode="adaptive", round_number=2, signals=[],
            prior_roles=["engineering-quality", "architecture", "customer"],
            conflicts=[{"roles": ["architecture", "customer"],
                        "evidence": "synthesis-1.md:F2"}], added_role="product")
        self.assertEqual([r["role"] for r in conflict["selected"]],
                         ["architecture", "customer", "product"])
        self.assertEqual(conflict["selected"][-1]["reasons"],
                         ["round2.next-omitted-lens"])

    def test_round_two_refusals(self):
        with self.assertRaisesRegex(
                ValueError, "review has a maximum two rounds"):
            selection.select_roles(mode="adaptive", round_number=3, signals=[])
        with self.assertRaisesRegex(ValueError, "delta-only"):
            selection.select_roles(
                mode="adaptive", round_number=2, signals=[],
                prior_roles=["engineering-quality", "architecture"],
                blocking_roles=["engineering-quality"], added_role="product")
        with self.assertRaisesRegex(ValueError, "four distinct"):
            selection.select_roles(
                mode="adaptive", round_number=2, signals=[],
                prior_roles=["engineering-quality", "architecture", "customer",
                             "commercial"],
                conflicts=[{"roles": ["architecture", "customer"],
                            "evidence": "synthesis-1.md:F2"}],
                added_role="product")

    def test_requires_concrete_evidence_and_distinct_known_roles(self):
        with self.assertRaises(ValueError):
            selection.select_roles(
                mode="adaptive", round_number=1,
                signals=[{"name": "security", "evidence": []}])
        with self.assertRaises(ValueError):
            selection.select_roles(
                mode="adaptive", round_number=2, signals=[],
                prior_roles=["architecture", "architecture"],
                blocking_roles=["architecture"])
        with self.assertRaises(ValueError):
            selection.select_roles(
                mode="adaptive", round_number=2, signals=[],
                prior_roles=["architecture", "customer"],
                conflicts=[{"roles": ["architecture", "customer"],
                            "evidence": ""}])


class ReceiptTest(unittest.TestCase):
    def errors(self, mutate=None):
        data = valid_receipt()
        if mutate:
            mutate(data)
        return selection.receipt_errors(data, "receipt")

    def test_valid_receipt_with_returned_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for outcome in valid_receipt()["outcomes"]:
                path = root / outcome["report"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# review\n", encoding="utf-8")
            self.assertEqual(selection.receipt_errors(
                valid_receipt(), "receipt", review_root=root), [])

    def test_refuses_schema_and_semantic_mutations(self):
        mutations = {
            "unknown top-level field":
                lambda d: d.__setitem__("surprise", True),
            "unknown role":
                lambda d: d["selected"][0].__setitem__("role", "intern"),
            "empty changed paths":
                lambda d: d["diff"].__setitem__("changed_paths", []),
            "empty signal evidence": lambda d: d["signals"].append(
                {"name": "security", "evidence": []}),
            "empty reasons":
                lambda d: d["selected"][0].__setitem__("reasons", []),
            "duplicate selected":
                lambda d: d["selected"].append(copy.deepcopy(d["selected"][0])),
            "selected omitted overlap":
                lambda d: d["omitted"].append(
                    {"role": "architecture", "reasons": ["x"]}),
            "incomplete partition": lambda d: d["omitted"].pop(),
            "outcome mismatch": lambda d: d["outcomes"].pop(),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.assertTrue(self.errors(mutate), name)

    def test_refuses_selector_receipt_disagreement(self):
        data = valid_receipt()
        data["selected"][1]["role"] = "customer"
        data["omitted"][2]["role"] = "architecture"
        data["outcomes"][1] = {
            "role": "customer", "status": "returned",
            "report": "round-1/customer.md"}
        errors = selection.receipt_errors(data, "receipt")
        self.assertTrue(any("selector" in error for error in errors), errors)

    def test_refuses_round_two_without_trigger(self):
        data = valid_receipt()
        data["round"] = 2
        errors = selection.receipt_errors(data, "receipt")
        self.assertTrue(any("delta-only" in error for error in errors), errors)

    def test_refuses_round_two_with_five_distinct_roles(self):
        data = valid_receipt()
        data["round"] = 2
        data["escalation"] = {
            "prior_roles": ["engineering-quality", "architecture",
                            "customer", "commercial"],
            "blocking_roles": [],
            "conflicts": [{"roles": ["architecture", "customer"],
                           "evidence": "synthesis-1.md:F2"}],
            "added_role": "product"}
        errors = selection.receipt_errors(data, "receipt")
        self.assertTrue(any("four distinct" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
