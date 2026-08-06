import unittest

from scripts.factory.lib import council, review_selection as selection


def signal(name, evidence=None):
    return {"name": name, "evidence": evidence or [f"src/{name}.py:10"]}


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


if __name__ == "__main__":
    unittest.main()
