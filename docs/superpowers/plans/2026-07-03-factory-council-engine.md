# Factory Council Engine (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 2 of the Factory spec (`docs/superpowers/specs/2026-07-03-software-factory-design.md` §6, §11 phase 2): the council memory engine — escalation-bid and judgement ledgers with the code-enforced memory firewall, wolf-tax reputation derivation, memory-health computation, the provenance-preserving prune CLI, plus CLI subcommands and ledger validation.

**Architecture:** Three JSONL ledgers under `.factory/ledgers/` (created empty by Phase 1 init). Specialists file **bids**; the orchestrator records exactly one **judgement** per bid (`accept/reject/defer/merge/downgrade`); only accept/merge authorize a canonical edit naming a surface+anchor; every judgement deterministically appends a derived **reputation** event. Health and prune operate on council role files under `docs/factory/council/`. All business rules live in `scripts/factory/lib/` modules and are enforced (raising `CouncilError`), never prose.

**Tech Stack:** Python 3.11+ stdlib only, reusing Phase 1 modules: `lib/validate.py` (`validate(instance, schema, path) -> list[str]`), `lib/logs.py` (`now_stamp()`), `lib/paths.py` (`ledgers_dir`, `docs_root`, `factory_root`), `lib/initrepo.py` (`load_schema(name)`).

## Global Constraints

- Python 3 **stdlib only** — zero third-party dependencies (spec §2).
- Deterministic output: `json.dumps(..., sort_keys=True)`, one JSON object per JSONL line, LF endings; timestamps via `logs.now_stamp()` (`FACTORY_NOW` override).
- **Council roles, exactly:** `product, ui-taste, architecture, engineering-quality, customer, commercial` (must match the 6 template files from Phase 1).
- **Judgement decisions, exactly:** `accept, reject, defer, merge, downgrade`. Only `accept`/`merge` authorize canonical edits, and both require `surface` + `anchor`.
- **Reputation deltas (wolf tax), exactly:** accept/merge `+0.05`, defer `0.0`, downgrade (overclaimed) `-0.05`, reject (false/noisy) `-0.10`. Reputation is derived per agent **per topic**, never hand-authored.
- **Prune invariant:** kept lines ∪ archived lines == input lines (nothing silently erased).
- Ledger ids: `bid-NNNN` / `jdg-NNNN`, zero-padded, sequential from 0001 per ledger.
- CLI exit codes: 0 success, 1 usage/internal error, 2 business-rule refusal or validation errors.
- Run tests from repo root with: `python3 -m unittest discover -s tests -v`
- Commit after every task; `feat:`/`test:`/`chore:` prefixes.

---

### Task 1: Council schemas and the bid ledger

**Files:**
- Create: `schemas/escalation-bid.schema.json`
- Create: `schemas/orchestrator-judgement.schema.json`
- Create: `schemas/reputation-event.schema.json`
- Create: `scripts/factory/lib/council.py`
- Test: `tests/test_council_bids.py`

**Interfaces:**
- Consumes: `validate.validate`, `initrepo.load_schema`, `logs.now_stamp`, `paths.ledgers_dir`.
- Produces (used by Tasks 2, 5, 6):
  - `council.ROLES = ("product", "ui-taste", "architecture", "engineering-quality", "customer", "commercial")`
  - `council.DECISIONS = ("accept", "reject", "defer", "merge", "downgrade")`
  - `council.AUTHORIZING = ("accept", "merge")`
  - `council.DECISION_DELTAS = {"accept": 0.05, "merge": 0.05, "defer": 0.0, "downgrade": -0.05, "reject": -0.10}`
  - `council.CouncilError(Exception)`
  - `council.read_ledger(repo, name) -> list[dict]` (name in `bids|judgements|reputation`)
  - `council.append_ledger(repo, name, entry)` — sorted-keys JSONL append
  - `council.next_ledger_id(repo, name, prefix) -> str` — e.g. `"bid-0001"`
  - `council.file_bid(repo, agent, topic, claim, evidence, surface, severity, item="") -> dict` — validates against schema + business rules (agent in ROLES, evidence list non-empty), appends, returns the bid.

- [ ] **Step 1: Write the three schemas**

`schemas/escalation-bid.schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "escalation-bid",
  "type": "object",
  "required": ["id", "ts", "agent", "topic", "item", "claim", "evidence", "surface", "severity"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string", "pattern": "^bid-[0-9]{4}$"},
    "ts": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "agent": {"type": "string", "enum": ["product", "ui-taste", "architecture", "engineering-quality", "customer", "commercial"]},
    "topic": {"type": "string", "minLength": 1},
    "item": {"type": "string"},
    "claim": {"type": "string", "minLength": 1},
    "evidence": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "surface": {"type": "string", "minLength": 1},
    "severity": {"type": "string", "enum": ["low", "medium", "high"]}
  }
}
```

`schemas/orchestrator-judgement.schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "orchestrator-judgement",
  "type": "object",
  "required": ["id", "ts", "bid", "decision", "reason"],
  "additionalProperties": false,
  "properties": {
    "id": {"type": "string", "pattern": "^jdg-[0-9]{4}$"},
    "ts": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "bid": {"type": "string", "pattern": "^bid-[0-9]{4}$"},
    "decision": {"type": "string", "enum": ["accept", "reject", "defer", "merge", "downgrade"]},
    "reason": {"type": "string", "minLength": 1},
    "surface": {"type": "string", "minLength": 1},
    "anchor": {"type": "string", "minLength": 1}
  }
}
```

`schemas/reputation-event.schema.json`:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "reputation-event",
  "type": "object",
  "required": ["ts", "agent", "topic", "delta", "judgement"],
  "additionalProperties": false,
  "properties": {
    "ts": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "agent": {"type": "string", "enum": ["product", "ui-taste", "architecture", "engineering-quality", "customer", "commercial"]},
    "topic": {"type": "string", "minLength": 1},
    "delta": {"type": "number"},
    "judgement": {"type": "string", "pattern": "^jdg-[0-9]{4}$"}
  }
}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_council_bids.py`:
```python
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, initrepo


class CouncilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def bid(self, **kw):
        args = dict(agent="ui-taste", topic="interaction", claim="Buttons inconsistent",
                    evidence=["docs/factory/brain/design-system.md"],
                    surface="brain/design-system.md", severity="medium")
        args.update(kw)
        return council.file_bid(self.repo, **args)


class TestLedgerPlumbing(CouncilTest):
    def test_read_empty_ledger(self):
        self.assertEqual(council.read_ledger(self.repo, "bids"), [])

    def test_append_and_read_sorted_keys(self):
        council.append_ledger(self.repo, "bids", {"b": 1, "a": 2})
        line = (self.repo / ".factory/ledgers/bids.jsonl").read_text().strip()
        self.assertEqual(line, json.dumps({"a": 2, "b": 1}, sort_keys=True))

    def test_next_ledger_id_increments(self):
        self.assertEqual(council.next_ledger_id(self.repo, "bids", "bid"), "bid-0001")
        self.bid()
        self.assertEqual(council.next_ledger_id(self.repo, "bids", "bid"), "bid-0002")


class TestFileBid(CouncilTest):
    def test_valid_bid_appended(self):
        bid = self.bid()
        self.assertEqual(bid["id"], "bid-0001")
        self.assertEqual(bid["ts"], "2026-07-03T12:00:00Z")
        self.assertEqual(len(council.read_ledger(self.repo, "bids")), 1)

    def test_unknown_agent_refused(self):
        with self.assertRaises(council.CouncilError):
            self.bid(agent="intern")
        self.assertEqual(council.read_ledger(self.repo, "bids"), [])

    def test_empty_evidence_refused(self):
        with self.assertRaises(council.CouncilError):
            self.bid(evidence=[])

    def test_bad_severity_refused(self):
        with self.assertRaises(council.CouncilError):
            self.bid(severity="catastrophic")

    def test_item_defaults_empty(self):
        self.assertEqual(self.bid()["item"], "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_council_bids -v`
Expected: FAIL — council module missing.

- [ ] **Step 4: Implement council.py (bid half)**

`scripts/factory/lib/council.py`:
```python
"""Council memory firewall: bids -> judgements -> derived reputation.

Specialists never mutate canonical memory. They file schema-validated
escalation bids; the orchestrator records exactly one judgement per bid;
only accept/merge authorize a canonical edit naming surface + anchor.
Reputation is derived from judgements (wolf tax), never hand-authored.
Spec §6.
"""

import json

from . import logs, paths
from .initrepo import load_schema
from .validate import validate

ROLES = ("product", "ui-taste", "architecture", "engineering-quality",
         "customer", "commercial")
DECISIONS = ("accept", "reject", "defer", "merge", "downgrade")
AUTHORIZING = ("accept", "merge")
DECISION_DELTAS = {"accept": 0.05, "merge": 0.05, "defer": 0.0,
                   "downgrade": -0.05, "reject": -0.10}


class CouncilError(Exception):
    """Business-rule refusal: the ledger stays untouched."""


def _ledger_path(repo, name):
    return paths.ledgers_dir(repo) / f"{name}.jsonl"


def read_ledger(repo, name):
    path = _ledger_path(repo, name)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_ledger(repo, name, entry):
    path = _ledger_path(repo, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def next_ledger_id(repo, name, prefix):
    return f"{prefix}-{len(read_ledger(repo, name)) + 1:04d}"


def _check(entry, schema_name, label):
    errors = validate(entry, load_schema(schema_name), label)
    if errors:
        raise CouncilError("; ".join(errors))


def file_bid(repo, agent, topic, claim, evidence, surface, severity, item=""):
    if not evidence:
        raise CouncilError("bid requires at least one evidence entry")
    bid = {
        "id": next_ledger_id(repo, "bids", "bid"),
        "ts": logs.now_stamp(),
        "agent": agent, "topic": topic, "item": item, "claim": claim,
        "evidence": list(evidence), "surface": surface, "severity": severity,
    }
    _check(bid, "escalation-bid", "bid")
    append_ledger(repo, "bids", bid)
    return bid
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_council_bids -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add schemas scripts/factory/lib/council.py tests/test_council_bids.py
git commit -m "feat: council schemas and escalation-bid ledger"
```

---

### Task 2: Judgements, derived reputation, and the authorization firewall

**Files:**
- Modify: `scripts/factory/lib/council.py` (append to the file)
- Test: `tests/test_council_judgements.py`

**Interfaces:**
- Consumes: Task 1's module contents.
- Produces (used by Tasks 5, 6 and Phase 3 skills):
  - `council.record_judgement(repo, bid_id, decision, reason, surface=None, anchor=None) -> (dict, dict)` — returns (judgement, reputation_event). Rules enforced: bid exists; no prior judgement for that bid; decision in DECISIONS; accept/merge require surface AND anchor (refused otherwise); appends judgement then derived reputation event atomically-in-order.
  - `council.reputation_table(repo) -> dict[str, float]` — key `"agent/topic"`, value summed delta, rounded to 2 decimals.
  - `council.is_change_authorized(repo, bid_id, surface) -> bool` — True iff an accept/merge judgement exists for `bid_id` whose `surface` equals the given surface.

- [ ] **Step 1: Write the failing tests**

`tests/test_council_judgements.py`:
```python
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, initrepo


class JudgementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.bid = council.file_bid(
            self.repo, agent="architecture", topic="boundaries",
            claim="Split module", evidence=["src/big.py"],
            surface="brain/decisions.md", severity="high")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()


class TestRecordJudgement(JudgementTest):
    def test_accept_requires_surface_and_anchor(self):
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0001", "accept", "good find")

    def test_accept_appends_judgement_and_reputation(self):
        jdg, rep = council.record_judgement(
            self.repo, "bid-0001", "accept", "good find",
            surface="brain/decisions.md", anchor="## Module boundaries")
        self.assertEqual(jdg["id"], "jdg-0001")
        self.assertEqual(rep["delta"], 0.05)
        self.assertEqual(rep["agent"], "architecture")
        self.assertEqual(rep["topic"], "boundaries")
        self.assertEqual(rep["judgement"], "jdg-0001")
        self.assertEqual(len(council.read_ledger(self.repo, "judgements")), 1)
        self.assertEqual(len(council.read_ledger(self.repo, "reputation")), 1)

    def test_reject_wolf_tax(self):
        _, rep = council.record_judgement(self.repo, "bid-0001", "reject", "no evidence")
        self.assertEqual(rep["delta"], -0.10)

    def test_downgrade_overclaim_tax(self):
        _, rep = council.record_judgement(self.repo, "bid-0001", "downgrade", "overstated")
        self.assertEqual(rep["delta"], -0.05)

    def test_defer_neutral(self):
        _, rep = council.record_judgement(self.repo, "bid-0001", "defer", "needs data")
        self.assertEqual(rep["delta"], 0.0)

    def test_unknown_bid_refused(self):
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0999", "reject", "what bid")

    def test_double_judgement_refused(self):
        council.record_judgement(self.repo, "bid-0001", "reject", "no")
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0001", "accept", "changed my mind",
                                     surface="brain/decisions.md", anchor="## X")

    def test_bad_decision_refused(self):
        with self.assertRaises(council.CouncilError):
            council.record_judgement(self.repo, "bid-0001", "maybe", "hmm")


class TestReputationAndAuthorization(JudgementTest):
    def test_reputation_table_sums_per_agent_topic(self):
        council.record_judgement(self.repo, "bid-0001", "accept", "ok",
                                 surface="brain/decisions.md", anchor="## A")
        council.file_bid(self.repo, agent="architecture", topic="boundaries",
                         claim="Another", evidence=["x"], surface="brain/decisions.md",
                         severity="low")
        council.record_judgement(self.repo, "bid-0002", "reject", "no")
        table = council.reputation_table(self.repo)
        self.assertEqual(table["architecture/boundaries"], -0.05)

    def test_is_change_authorized(self):
        self.assertFalse(council.is_change_authorized(
            self.repo, "bid-0001", "brain/decisions.md"))
        council.record_judgement(self.repo, "bid-0001", "accept", "ok",
                                 surface="brain/decisions.md", anchor="## A")
        self.assertTrue(council.is_change_authorized(
            self.repo, "bid-0001", "brain/decisions.md"))
        self.assertFalse(council.is_change_authorized(
            self.repo, "bid-0001", "brain/vision.md"))

    def test_reject_never_authorizes(self):
        council.record_judgement(self.repo, "bid-0001", "reject", "no")
        self.assertFalse(council.is_change_authorized(
            self.repo, "bid-0001", "brain/decisions.md"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_council_judgements -v`
Expected: FAIL — record_judgement not defined.

- [ ] **Step 3: Append the judgement half to council.py**

Append to `scripts/factory/lib/council.py`:
```python
def _find_bid(repo, bid_id):
    for bid in read_ledger(repo, "bids"):
        if bid["id"] == bid_id:
            return bid
    raise CouncilError(f"no such bid: {bid_id}")


def _judgement_for(repo, bid_id):
    for jdg in read_ledger(repo, "judgements"):
        if jdg["bid"] == bid_id:
            return jdg
    return None


def record_judgement(repo, bid_id, decision, reason, surface=None, anchor=None):
    bid = _find_bid(repo, bid_id)
    if decision not in DECISIONS:
        raise CouncilError(f"unknown decision {decision!r}; one of {DECISIONS}")
    if _judgement_for(repo, bid_id) is not None:
        raise CouncilError(f"{bid_id} already judged; judgements are final")
    if decision in AUTHORIZING and not (surface and anchor):
        raise CouncilError(f"{decision} requires --surface and --anchor naming the edit")
    jdg = {
        "id": next_ledger_id(repo, "judgements", "jdg"),
        "ts": logs.now_stamp(),
        "bid": bid_id, "decision": decision, "reason": reason,
    }
    if surface:
        jdg["surface"] = surface
    if anchor:
        jdg["anchor"] = anchor
    _check(jdg, "orchestrator-judgement", "judgement")
    rep = {
        "ts": logs.now_stamp(),
        "agent": bid["agent"], "topic": bid["topic"],
        "delta": DECISION_DELTAS[decision], "judgement": jdg["id"],
    }
    _check(rep, "reputation-event", "reputation")
    append_ledger(repo, "judgements", jdg)
    append_ledger(repo, "reputation", rep)
    return jdg, rep


def reputation_table(repo):
    table = {}
    for event in read_ledger(repo, "reputation"):
        key = f"{event['agent']}/{event['topic']}"
        table[key] = round(table.get(key, 0.0) + event["delta"], 2)
    return table


def is_change_authorized(repo, bid_id, surface):
    jdg = _judgement_for(repo, bid_id)
    return bool(jdg and jdg["decision"] in AUTHORIZING
                and jdg.get("surface") == surface)
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `python3 -m unittest tests.test_council_judgements -v` — Expected: all PASS.
Run: `python3 -m unittest discover -s tests -v` — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/council.py tests/test_council_judgements.py
git commit -m "feat: judgement ledger with authorization firewall and wolf-tax reputation"
```

---

### Task 3: Memory health

**Files:**
- Create: `scripts/factory/lib/health.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: `paths.docs_root`, `paths.factory_root`, `council.read_ledger`, `logs.now_stamp`.
- Produces (used by Task 5 and Phase 3):
  - `health.THRESHOLDS = {"max_role_lines": 200, "max_duplicate_claims": 2, "max_unjudged_bids": 10}`
  - `health.compute_health(repo) -> dict` — `{"ts", "roles": {role: {"lines", "claims", "duplicate_claims"}}, "ledgers": {"bids", "judged", "unjudged", "deferred"}, "recommendation": "ok"|"prune", "reasons": [str]}`. Recommendation is `"prune"` iff any threshold is exceeded; reasons name each exceeded threshold. Never mutates anything except writing the report.
  - `health.write_health(repo) -> Path` — writes `.factory/memory-health.json` (sorted keys, indent 2, trailing newline), returns the path.
- Definitions: a **claim** is a line starting `- ` in a role file; a **duplicate claim** is a claim line whose exact text already appeared earlier in the same file; **deferred** counts judgements with decision `defer`.

- [ ] **Step 1: Write the failing tests**

`tests/test_health.py`:
```python
import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, health, initrepo


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def role_path(self, role):
        return self.repo / "docs/factory/council" / f"{role}.md"

    def test_clean_tree_recommends_ok(self):
        report = health.compute_health(self.repo)
        self.assertEqual(report["recommendation"], "ok")
        self.assertEqual(report["reasons"], [])
        self.assertIn("product", report["roles"])
        self.assertEqual(len(report["roles"]), 6)

    def test_duplicate_claims_counted_and_trigger_prune(self):
        text = self.role_path("customer").read_text() + \
            "- users hate modals\n- users hate modals\n- users hate modals\n"
        self.role_path("customer").write_text(text, encoding="utf-8")
        report = health.compute_health(self.repo)
        self.assertEqual(report["roles"]["customer"]["duplicate_claims"], 2)
        self.assertEqual(report["recommendation"], "ok")
        text += "- users hate modals\n"
        self.role_path("customer").write_text(text, encoding="utf-8")
        report = health.compute_health(self.repo)
        self.assertEqual(report["recommendation"], "prune")
        self.assertTrue(any("duplicate" in r for r in report["reasons"]))

    def test_oversized_role_file_triggers_prune(self):
        self.role_path("product").write_text("x\n" * 201, encoding="utf-8")
        report = health.compute_health(self.repo)
        self.assertEqual(report["recommendation"], "prune")
        self.assertTrue(any("product" in r for r in report["reasons"]))

    def test_unjudged_bids_counted(self):
        for i in range(3):
            council.file_bid(self.repo, agent="product", topic="t",
                             claim=f"claim {i}", evidence=["e"],
                             surface="brain/vision.md", severity="low")
        council.record_judgement(self.repo, "bid-0001", "defer", "later")
        report = health.compute_health(self.repo)
        self.assertEqual(report["ledgers"]["bids"], 3)
        self.assertEqual(report["ledgers"]["judged"], 1)
        self.assertEqual(report["ledgers"]["unjudged"], 2)
        self.assertEqual(report["ledgers"]["deferred"], 1)

    def test_write_health_deterministic(self):
        path = health.write_health(self.repo)
        self.assertEqual(path, self.repo / ".factory/memory-health.json")
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        data = json.loads(text)
        self.assertEqual(data["ts"], "2026-07-03T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_health -v`
Expected: FAIL — health module missing.

- [ ] **Step 3: Implement health.py**

`scripts/factory/lib/health.py`:
```python
"""Cheap deterministic memory-health check. Recommends prune/no-prune
with reasons; never mutates council files. Spec §6.
"""

import json

from . import council, logs, paths

THRESHOLDS = {"max_role_lines": 200, "max_duplicate_claims": 2,
              "max_unjudged_bids": 10}


def _role_stats(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    claims = [line for line in lines if line.startswith("- ")]
    seen, duplicates = set(), 0
    for claim in claims:
        if claim in seen:
            duplicates += 1
        seen.add(claim)
    return {"lines": len(lines), "claims": len(claims),
            "duplicate_claims": duplicates}


def compute_health(repo):
    roles = {}
    council_dir = paths.docs_root(repo) / "council"
    for path in sorted(council_dir.glob("*.md")):
        roles[path.stem] = _role_stats(path)
    bids = council.read_ledger(repo, "bids")
    judgements = council.read_ledger(repo, "judgements")
    judged_ids = {j["bid"] for j in judgements}
    ledgers = {
        "bids": len(bids),
        "judged": len(judged_ids),
        "unjudged": sum(1 for b in bids if b["id"] not in judged_ids),
        "deferred": sum(1 for j in judgements if j["decision"] == "defer"),
    }
    reasons = []
    for role, stats in sorted(roles.items()):
        if stats["lines"] > THRESHOLDS["max_role_lines"]:
            reasons.append(f"{role}: {stats['lines']} lines exceeds "
                           f"{THRESHOLDS['max_role_lines']}")
        if stats["duplicate_claims"] > THRESHOLDS["max_duplicate_claims"]:
            reasons.append(f"{role}: {stats['duplicate_claims']} duplicate claims "
                           f"exceeds {THRESHOLDS['max_duplicate_claims']}")
    if ledgers["unjudged"] > THRESHOLDS["max_unjudged_bids"]:
        reasons.append(f"{ledgers['unjudged']} unjudged bids exceeds "
                       f"{THRESHOLDS['max_unjudged_bids']}")
    return {
        "ts": logs.now_stamp(),
        "roles": roles,
        "ledgers": ledgers,
        "recommendation": "prune" if reasons else "ok",
        "reasons": reasons,
    }


def write_health(repo):
    report = compute_health(repo)
    path = paths.factory_root(repo) / "memory-health.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_health -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/health.py tests/test_health.py
git commit -m "feat: deterministic memory-health check with prune recommendation"
```

---

### Task 4: Provenance-preserving prune

**Files:**
- Create: `scripts/factory/lib/prune.py`
- Test: `tests/test_prune.py`

**Interfaces:**
- Consumes: `paths.docs_root`, `paths.factory_root`, `logs.now_stamp`, `council.ROLES`, `council.CouncilError`.
- Produces (used by Task 5):
  - `prune.propose(lines) -> (kept, archived)` — pure function on a list of strings. Archives exact-duplicate claim lines (`- ` prefix) beyond their first occurrence; everything else kept in order. **Invariant: sorted(kept + archived) == sorted(lines).**
  - `prune.prune_role(repo, role, apply=False) -> dict` — `{"role", "kept", "archived", "archive_path"|None}`. Refuses unknown roles with `CouncilError`. With `apply=False` (default) computes counts only, writes nothing. With `apply=True`: writes kept lines back to `docs/factory/council/<role>.md` and appends archived lines (with a `## pruned <ts>` header) to `.factory/pruning/<role>.md` — only when there is something to archive.

- [ ] **Step 1: Write the failing tests**

`tests/test_prune.py`:
```python
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import council, initrepo, prune


class TestPropose(unittest.TestCase):
    def test_no_duplicates_all_kept(self):
        lines = ["# Role", "- a", "- b", "prose"]
        kept, archived = prune.propose(lines)
        self.assertEqual(kept, lines)
        self.assertEqual(archived, [])

    def test_duplicates_archived_first_kept(self):
        lines = ["- a", "- b", "- a", "- a"]
        kept, archived = prune.propose(lines)
        self.assertEqual(kept, ["- a", "- b"])
        self.assertEqual(archived, ["- a", "- a"])

    def test_provenance_invariant(self):
        lines = ["# h", "- x", "- x", "prose", "- y", "- x"]
        kept, archived = prune.propose(lines)
        self.assertEqual(sorted(kept + archived), sorted(lines))

    def test_non_claim_duplicates_untouched(self):
        lines = ["prose", "prose"]
        kept, archived = prune.propose(lines)
        self.assertEqual(kept, lines)
        self.assertEqual(archived, [])


class TestPruneRole(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.path = self.repo / "docs/factory/council/customer.md"
        self.path.write_text("# Role\n- dup\n- dup\n- keep\n", encoding="utf-8")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_dry_run_writes_nothing(self):
        result = prune.prune_role(self.repo, "customer")
        self.assertEqual(result["archived"], 1)
        self.assertIsNone(result["archive_path"])
        self.assertIn("- dup\n- dup", self.path.read_text())
        self.assertFalse((self.repo / ".factory/pruning/customer.md").exists())

    def test_apply_rewrites_and_archives(self):
        result = prune.prune_role(self.repo, "customer", apply=True)
        self.assertEqual(result["kept"], 3)
        self.assertEqual(result["archived"], 1)
        self.assertEqual(self.path.read_text(), "# Role\n- dup\n- keep\n")
        archive = Path(result["archive_path"]).read_text()
        self.assertIn("## pruned 2026-07-03T12:00:00Z", archive)
        self.assertIn("- dup", archive)

    def test_apply_with_nothing_to_archive_writes_no_archive(self):
        prune.prune_role(self.repo, "customer", apply=True)
        result = prune.prune_role(self.repo, "customer", apply=True)
        self.assertEqual(result["archived"], 0)

    def test_unknown_role_refused(self):
        with self.assertRaises(council.CouncilError):
            prune.prune_role(self.repo, "intern")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_prune -v`
Expected: FAIL — prune module missing.

- [ ] **Step 3: Implement prune.py**

`scripts/factory/lib/prune.py`:
```python
"""Provenance-preserving prune of council role files.

Invariant: kept + archived == input (nothing silently erased). Only
exact-duplicate claim lines are archived; prose is never touched.
Spec §6.
"""

from . import logs, paths
from .council import ROLES, CouncilError


def propose(lines):
    kept, archived, seen = [], [], set()
    for line in lines:
        if line.startswith("- ") and line in seen:
            archived.append(line)
        else:
            if line.startswith("- "):
                seen.add(line)
            kept.append(line)
    return kept, archived


def prune_role(repo, role, apply=False):
    if role not in ROLES:
        raise CouncilError(f"unknown role {role!r}; one of {ROLES}")
    path = paths.docs_root(repo) / "council" / f"{role}.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    kept, archived = propose(lines)
    archive_path = None
    if apply and archived:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        archive = paths.factory_root(repo) / "pruning" / f"{role}.md"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with archive.open("a", encoding="utf-8") as f:
            f.write(f"## pruned {logs.now_stamp()}\n")
            f.write("\n".join(archived) + "\n")
        archive_path = str(archive)
    return {"role": role, "kept": len(kept), "archived": len(archived),
            "archive_path": archive_path}
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `python3 -m unittest tests.test_prune -v` — Expected: all PASS.
Run: `python3 -m unittest discover -s tests -v` — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/prune.py tests/test_prune.py
git commit -m "feat: provenance-preserving prune with archive trail"
```

---

### Task 5: Council CLI subcommands

**Files:**
- Modify: `scripts/factory/factory.py`
- Test: `tests/test_cli_council.py`

**Interfaces:**
- Consumes: everything above.
- Produces (stable API for Phase 3 skills):
  - `bid AGENT TOPIC CLAIM --evidence E [--evidence E ...] --surface S --severity low|medium|high [--item ID]` — prints the new bid id. CouncilError → stderr, exit 2.
  - `judge BID DECISION --reason R [--surface S --anchor A]` — prints `BID -> DECISION (rep AGENT/TOPIC DELTA)`. CouncilError → exit 2.
  - `reputation` — prints `agent/topic  score` lines sorted by key; `--json` for machine use.
  - `health` — writes `.factory/memory-health.json`, prints `recommendation: ok|prune` + reasons; exit 0 either way.
  - `prune ROLE [--apply]` — prints kept/archived counts; CouncilError → exit 2.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli_council.py`:
```python
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory


class CouncilCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self.run_cli("init")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", self.repo, *args])
        return code, out.getvalue(), err.getvalue()

    def file_bid(self):
        return self.run_cli("bid", "ui-taste", "spacing", "Cards misaligned",
                            "--evidence", "src/cards.css", "--surface",
                            "brain/design-system.md", "--severity", "medium")

    def test_bid_prints_id(self):
        code, out, _ = self.file_bid()
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "bid-0001")

    def test_bid_business_refusal_exit_2(self):
        code, _, err = self.run_cli("bid", "intern", "t", "c", "--evidence", "e",
                                    "--surface", "s", "--severity", "low")
        self.assertEqual(code, 2)
        self.assertIn("intern", err)

    def test_judge_accept_and_reputation(self):
        self.file_bid()
        code, out, _ = self.run_cli("judge", "bid-0001", "accept", "--reason", "ok",
                                    "--surface", "brain/design-system.md",
                                    "--anchor", "## Spacing")
        self.assertEqual(code, 0)
        self.assertIn("bid-0001 -> accept", out)
        code, out, _ = self.run_cli("reputation", "--json")
        self.assertEqual(json.loads(out), {"ui-taste/spacing": 0.05})

    def test_judge_missing_anchor_exit_2(self):
        self.file_bid()
        code, _, err = self.run_cli("judge", "bid-0001", "accept", "--reason", "ok")
        self.assertEqual(code, 2)
        self.assertIn("anchor", err)

    def test_health_command(self):
        code, out, _ = self.run_cli("health")
        self.assertEqual(code, 0)
        self.assertIn("recommendation: ok", out)
        self.assertTrue(Path(self.repo, ".factory/memory-health.json").exists())

    def test_prune_command(self):
        role = Path(self.repo, "docs/factory/council/customer.md")
        role.write_text(role.read_text() + "- d\n- d\n", encoding="utf-8")
        code, out, _ = self.run_cli("prune", "customer")
        self.assertEqual(code, 0)
        self.assertIn("archived: 1", out)
        self.assertIn("- d\n- d", role.read_text())
        code, out, _ = self.run_cli("prune", "customer", "--apply")
        self.assertEqual(code, 0)
        self.assertNotIn("- d\n- d", role.read_text())

    def test_prune_unknown_role_exit_2(self):
        code, _, _ = self.run_cli("prune", "intern")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_cli_council -v`
Expected: FAIL — unknown commands (argparse usage errors → exit 1, not the expected codes).

- [ ] **Step 3: Extend factory.py**

Add imports (`council`, `health` as `health_mod`, `prune` as `prune_mod` — follow the file's existing dual-import block for both branches), then command handlers:

```python
def cmd_bid(args):
    try:
        bid = council.file_bid(args.repo, agent=args.agent, topic=args.topic,
                               claim=args.claim, evidence=args.evidence or [],
                               surface=args.surface, severity=args.severity,
                               item=args.item or "")
    except council.CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(bid["id"])
    return 0


def cmd_judge(args):
    try:
        jdg, rep = council.record_judgement(args.repo, args.bid, args.decision,
                                            args.reason, surface=args.surface,
                                            anchor=args.anchor)
    except council.CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"{args.bid} -> {jdg['decision']} "
          f"(rep {rep['agent']}/{rep['topic']} {rep['delta']:+.2f})")
    return 0


def cmd_reputation(args):
    table = council.reputation_table(args.repo)
    if args.json:
        print(json.dumps(table, indent=2, sort_keys=True))
    else:
        for key in sorted(table):
            print(f"{key:<40} {table[key]:+.2f}")
    return 0


def cmd_health(args):
    path = health_mod.write_health(args.repo)
    report = json.loads(path.read_text(encoding="utf-8"))
    print(f"recommendation: {report['recommendation']}")
    for reason in report["reasons"]:
        print(f"- {reason}")
    return 0


def cmd_prune(args):
    try:
        result = prune_mod.prune_role(args.repo, args.role, apply=args.apply)
    except council.CouncilError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"kept: {result['kept']} archived: {result['archived']}"
          + (f" -> {result['archive_path']}" if result["archive_path"] else ""))
    return 0
```

And the subparser registrations inside `main()` (after the existing ones):

```python
    p = sub.add_parser("bid", help="file an escalation bid")
    p.add_argument("agent")
    p.add_argument("topic")
    p.add_argument("claim")
    p.add_argument("--evidence", action="append", required=True)
    p.add_argument("--surface", required=True)
    p.add_argument("--severity", required=True, choices=["low", "medium", "high"])
    p.add_argument("--item", default="")
    p.set_defaults(func=cmd_bid)

    p = sub.add_parser("judge", help="record the orchestrator judgement for a bid")
    p.add_argument("bid")
    p.add_argument("decision")
    p.add_argument("--reason", required=True)
    p.add_argument("--surface")
    p.add_argument("--anchor")
    p.set_defaults(func=cmd_judge)

    p = sub.add_parser("reputation", help="derived reputation per agent/topic")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_reputation)

    p = sub.add_parser("health", help="write memory-health.json and print recommendation")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("prune", help="propose/apply provenance-preserving prune")
    p.add_argument("role")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_prune)
```

Note `decision` is a plain positional (not `choices=`) so unknown decisions surface as CouncilError exit 2 (business rule), not argparse exit 1 — matching `test_bad_decision_refused` semantics at the lib level and keeping the CLI's refusal channel consistent.

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `python3 -m unittest tests.test_cli_council -v` — Expected: all PASS.
Run: `python3 -m unittest discover -s tests -v` — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/factory.py tests/test_cli_council.py
git commit -m "feat: council CLI - bid, judge, reputation, health, prune"
```

---

### Task 6: Ledger schema validation in validate_tree

**Files:**
- Modify: `scripts/factory/lib/initrepo.py`
- Test: `tests/test_initrepo.py` (add cases)

**Interfaces:**
- Consumes: Task 1 schemas, existing `validate_tree` structure.
- Produces: `validate_tree` now validates every `bids.jsonl` entry against `escalation-bid`, `judgements.jsonl` against `orchestrator-judgement`, and `reputation.jsonl` against `reputation-event` — in addition to the existing JSON-wellformedness check. Error format: `ledgers/<name>.jsonl:<lineno>: <validator message>`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_initrepo.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_initrepo -v`
Expected: the first new test FAILS (0 errors reported — schema not checked); second passes already.

- [ ] **Step 3: Extend validate_tree**

In `scripts/factory/lib/initrepo.py`, add a module-level map and use it inside the existing ledger loop:

```python
LEDGER_SCHEMAS = {"bids": "escalation-bid", "judgements": "orchestrator-judgement",
                  "reputation": "reputation-event"}
```

In the ledger loop, after each successful `json.loads(line)`, validate the parsed entry:

```python
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"ledgers/{name}.jsonl:{lineno}: invalid JSON")
                continue
            for msg in validate(entry, load_schema(LEDGER_SCHEMAS[name]),
                                f"ledgers/{name}.jsonl:{lineno}"):
                errors.append(msg)
```

- [ ] **Step 4: Run tests to verify they pass, then the full suite**

Run: `python3 -m unittest tests.test_initrepo -v` — Expected: all PASS.
Run: `python3 -m unittest discover -s tests -v` — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/factory/lib/initrepo.py tests/test_initrepo.py
git commit -m "feat: schema-validate council ledgers in validate_tree"
```

---

## Plan Self-Review (completed)

- **Spec coverage (Phase 2 scope, spec §6):** bid/judgement firewall as code (Tasks 1-2, `record_judgement` + `is_change_authorized`), wolf-tax reputation derived per agent/topic (Task 2), memory health recommend-only (Task 3), provenance-preserving prune with real CLI (Tasks 4-5, invariant tested), ledgers deterministic/diffable (sorted-keys JSONL throughout), CLI surface for Phase 3 skills (Task 5), corrupt/invalid ledger detection per spec §9 (Task 6). Bounded-protocol *prose* (round 1/synthesis/round 2) is Phase 3 skill content, not engine code — out of scope here.
- **Placeholder scan:** clean — all code steps carry complete code.
- **Type consistency:** `file_bid`/`record_judgement` signatures match CLI handlers; `CouncilError` used across council/prune/CLI; ledger names (`bids/judgements/reputation`) match Phase 1's `LEDGERS` tuple and init-created files; `health.write_health` path matches `cmd_health` reader.
