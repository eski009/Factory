import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNEYS = ROOT / "docs/factory/journeys"
ITEM = ROOT / ".factory/items/0016-cost-circuit-breaker-on-engine-authorita"


def has_live_item():
    """True only when this checkout carries item 0016's live state.

    `.factory/` is gitignored (`.gitignore:6`), so the item's own meta and
    impact.json are absent on CI and in a fresh clone. The registry,
    inventory and contract files under `docs/factory/journeys/` are
    tracked and are asserted unconditionally.
    """
    return (ITEM / "item.md").is_file()


def graph():
    return json.loads((JOURNEYS / "graph.json").read_text(encoding="utf-8"))


def journey(journey_id):
    for entry in graph()["journeys"]:
        if entry["id"] == journey_id:
            return entry
    raise AssertionError(f"{journey_id} is not registered in graph.json")


class TestJ002Registration(unittest.TestCase):
    """AC26: the journey this item creates is registered in all three
    places, and its contract names the nodes and the commitment point."""

    def test_graph_entry_shape(self):
        entry = journey("J-002")
        self.assertEqual(entry["slug"], "cost-breaker-decision")
        self.assertEqual(entry["criticality"], "high")
        self.assertEqual(entry["contract"],
                         "contracts/J-002-cost-breaker-decision.md")
        self.assertIn("Overnight Operator", entry["persona"])

    def test_graph_entry_links_every_touched_api(self):
        links = journey("J-002")["links"]
        for api in ("scripts/factory/lib/breaker.py::verdict",
                    "scripts/factory/lib/breaker.py::record_answer",
                    "scripts/factory/lib/machine.py::advance",
                    "scripts/factory/lib/cost.py::summarize",
                    "scripts/factory/lib/packet.py::render_packet",
                    "scripts/factory/lib/packet.py::render_packet_html",
                    "scripts/factory/factory.py::cmd_cost_answer"):
            self.assertIn(api, links["apis"])
        for test in ("tests/test_breaker.py", "tests/test_machine.py",
                     "tests/test_packet.py"):
            self.assertIn(test, links["tests"])

    def test_every_linked_api_symbol_exists(self):
        for api in journey("J-002")["links"]["apis"]:
            rel, symbol = api.split("::")
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertTrue(f"def {symbol}(" in source,
                            f"{rel} does not define {symbol}")
        for test in journey("J-002")["links"]["tests"]:
            self.assertTrue((ROOT / test).exists(), test)

    def test_inventory_carries_the_entry(self):
        text = (JOURNEYS / "inventory.md").read_text(encoding="utf-8")
        self.assertIn("**J-002 — Cost breaker decision**", text)
        self.assertIn("cost-breaker-decision", text)

    def test_contract_has_nodes_n1_to_n5_and_the_commitment_point(self):
        text = (JOURNEYS
                / "contracts/J-002-cost-breaker-decision.md").read_text(
                    encoding="utf-8")
        for node in ("N1 threshold crossed", "N2 item parked, packet written",
                     "N3 packet read", "N4 answer recorded",
                     "N5 resume"):
            self.assertIn(node, text)
        self.assertIn("commitment point is **N3 → N4**", text)

    @unittest.skipUnless(
        has_live_item(),
        ".factory/ is gitignored: item 0016's live state is absent on CI "
        "and in a fresh clone")
    def test_item_declares_both_journeys(self):
        meta = (ITEM / "item.md").read_text(encoding="utf-8")
        self.assertIn("journeys: J-001,J-002", meta)

    @unittest.skipUnless(
        has_live_item(),
        ".factory/ is gitignored: item 0016's live state is absent on CI "
        "and in a fresh clone")
    def test_impact_file_covers_both_journeys_with_scenarios(self):
        impact = json.loads(
            (ITEM / "assurance/impact.json").read_text(encoding="utf-8"))
        covered = {j["id"]: j for j in impact["journeys"]}
        self.assertEqual(set(covered), {"J-001", "J-002"})
        self.assertEqual(
            [s["id"] for s in covered["J-002"]["scenarios"]],
            ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"])
        self.assertTrue(covered["J-001"]["scenarios"])


class TestJ001OracleNarrowing(unittest.TestCase):
    """AC26: J-001's byte-comparison oracle names the diffs this item is
    permitted to make, and nothing else.

    The narrowing paragraph in item 0016's spec names two — the receipt
    label and the `status --json` key — but §6/B3 of the same spec
    mandates a third, the `## Respond` block, on every packet. The oracle
    must name every diff the shipped renderers actually make: a two-diff
    list would make J-001's byte comparison report the Respond block as a
    regression. The spec is not editable here; the contract is the
    surface that records shipped behaviour, and it carries all three.
    """

    def oracle_line(self):
        text = (JOURNEYS
                / "contracts/J-001-assure-outcome-readout.md").read_text(
                    encoding="utf-8")
        lines = [l for l in text.splitlines() if l.startswith("| default path")]
        self.assertEqual(len(lines), 1)
        return lines[0]

    def test_oracle_line_names_every_permitted_diff(self):
        line = self.oracle_line()
        self.assertIn("narrowed by item 0016", line)
        self.assertIn("`retries` → `rework edges`", line)
        self.assertIn("`spend.retries` → `spend.rework_edges`", line)
        self.assertIn("`## Respond`", line)

    def test_oracle_line_cites_its_source(self):
        self.assertIn(
            ".factory/items/0016-cost-circuit-breaker-on-engine-authorita"
            "/spec.md", self.oracle_line())


if __name__ == "__main__":
    unittest.main()
