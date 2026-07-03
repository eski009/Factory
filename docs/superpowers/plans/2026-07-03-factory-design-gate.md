# Factory Design Gate (Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 4 of the Factory spec (`docs/superpowers/specs/2026-07-03-software-factory-design.md` §5, §11 phase 4): the design gate — the factory generates 2–4 UI mockup options, parks the item for the human's pick, records the choice, and resumes — plus the deferred Phase-3 wiring items that belong to this layer.

**Architecture:** The `factory-design` skill authors a self-contained options page (`items/<id>/design/options.html`) from repo-local design tokens, writes a design packet, and pauses the item. A new engine command `factory choice` records the pick deterministically into `design/choice.md` (which `_gate_plan` already validates) — usable by the human in-session, by a skill relaying an async answer, or from the terminal. The dispatcher's existing step-0 resume check then advances the item. DesignSync and artifact hosting remain opportunistic upgrades in the capabilities skill; the degraded path (local HTML + packet) is the contract.

**Tech Stack:** Python 3.11+ stdlib (engine + tests); Claude Code plugin prose (skill + edits to existing skills/commands).

## Global Constraints

- Engine: Python 3 stdlib only; deterministic output; timestamps via `logs.now_stamp()`; CLI exit codes 0/1/2 (2 = refusal).
- Skills: CLI-shorthand convention; frontmatter (`name` matches dir, description starts "Use when"); ≤150 lines; degraded baseline with upgrades only via the capabilities skill.
- `design/choice.md` is written ONLY via `factory choice` (skills and humans both go through it) — one writer, deterministic content.
- Options page: one self-contained HTML file, no external requests (fonts/CDNs/images), 2–4 options as clearly labeled sections with `data-option` ids ("a", "b", "c", "d"); tokens from `docs/factory/brain/design-system.md`.
- Run tests from repo root with: `python3 -m unittest discover -s tests -v`
- Commit after every task; `feat:`/`test:`/`chore:`/`fix:` prefixes.

---

### Task 1: Engine — `factory choice`

**Files:**
- Create: `scripts/factory/lib/design.py`
- Modify: `scripts/factory/factory.py` (new subcommand; imports in both dual-import branches as `design as design_mod`)
- Test: `tests/test_design.py`

**Interfaces:**
- Consumes: `items.load_item/ItemError`, `machine.GateError`, `logs.append_event/now_stamp`, `paths.item_dir`.
- Produces:
  - `design.record_choice(repo, item_id, option, notes=None) -> Path` — validates: item exists; `kind` in (`ui`, `mixed`) else `GateError`; stage is `design`, or `waiting-human` with `paused-from: design`, else `GateError` naming the actual stage. Writes `items/<id>/design/choice.md` (overwrite allowed — changing your mind before resume is legal), appends event `design.choice {"option": option}`, returns the path. File content, exactly:
    ```
    # Design choice

    - option: <option>
    - ts: <now_stamp()>

    <notes or "(no notes)">
    ```
  - CLI: `choice ITEM OPTION [--notes TEXT]` — prints the written path; `GateError`/`ItemError` → stderr `refused: ...`, exit 2.

- [ ] **Step 1: Write the failing tests**

`tests/test_design.py`:
```python
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import design, initrepo, items, logs, machine


def put(repo, stage="design", kind="ui", paused_from=None):
    meta = {"id": "0001-thing", "title": "Thing", "stage": stage, "kind": kind,
            "priority": 1, "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z"}
    if paused_from:
        meta["paused-from"] = paused_from
        meta["paused-reason"] = "pick a design option"
    items.save_item(repo, meta, "# Thing\n")


class TestRecordChoice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_choice_at_design_stage(self):
        put(self.repo)
        path = design.record_choice(self.repo, "0001-thing", "b", notes="darker header")
        text = path.read_text(encoding="utf-8")
        self.assertIn("- option: b", text)
        self.assertIn("- ts: 2026-07-03T12:00:00Z", text)
        self.assertIn("darker header", text)
        events = logs.read_events(self.repo, "0001-thing")
        self.assertEqual(events[-1]["event"], "design.choice")
        self.assertEqual(events[-1]["data"], {"option": "b"})

    def test_choice_while_paused_from_design(self):
        put(self.repo, stage="waiting-human", paused_from="design")
        path = design.record_choice(self.repo, "0001-thing", "a")
        self.assertIn("(no notes)", path.read_text(encoding="utf-8"))

    def test_choice_overwrites(self):
        put(self.repo)
        design.record_choice(self.repo, "0001-thing", "a")
        design.record_choice(self.repo, "0001-thing", "c")
        self.assertIn("- option: c",
                      (self.repo / ".factory/items/0001-thing/design/choice.md").read_text())

    def test_backend_kind_refused(self):
        put(self.repo, kind="backend", stage="plan")
        with self.assertRaises(machine.GateError):
            design.record_choice(self.repo, "0001-thing", "a")

    def test_wrong_stage_refused_with_stage_named(self):
        put(self.repo, stage="implement")
        with self.assertRaises(machine.GateError) as ctx:
            design.record_choice(self.repo, "0001-thing", "a")
        self.assertIn("implement", str(ctx.exception))

    def test_paused_from_other_stage_refused(self):
        put(self.repo, stage="waiting-human", paused_from="review")
        with self.assertRaises(machine.GateError):
            design.record_choice(self.repo, "0001-thing", "a")

    def test_missing_item_raises_item_error(self):
        with self.assertRaises(items.ItemError):
            design.record_choice(self.repo, "0999-nope", "a")


if __name__ == "__main__":
    unittest.main()
```

Plus CLI coverage appended to `tests/test_cli_dispatch.py` (same harness): `choice` on a design-stage ui item prints the choice.md path (exit 0); `choice` on a backend item exits 2 with `refused:` on stderr.

- [ ] **Step 2: Run tests, verify failures** — design module missing.

- [ ] **Step 3: Implement**

`scripts/factory/lib/design.py`:
```python
"""Design-gate support: the single writer of design/choice.md. Spec §5."""

from . import items, logs, paths
from .machine import GateError


def record_choice(repo, item_id, option, notes=None):
    meta, _body = items.load_item(repo, item_id)
    if meta["kind"] not in ("ui", "mixed"):
        raise GateError(f"item kind {meta['kind']!r} has no design stage")
    stage = meta["stage"]
    at_design = stage == "design"
    paused_at_design = stage == "waiting-human" and meta.get("paused-from") == "design"
    if not (at_design or paused_at_design):
        raise GateError(f"choice requires stage design (or paused from it); item is at {stage!r}")
    path = paths.item_dir(repo, item_id) / "design" / "choice.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = notes if notes else "(no notes)"
    path.write_text(
        f"# Design choice\n\n- option: {option}\n- ts: {logs.now_stamp()}\n\n{body}\n",
        encoding="utf-8",
    )
    logs.append_event(repo, item_id, "design.choice", {"option": option})
    return path
```

`factory.py` handler + subparser:
```python
def cmd_choice(args):
    try:
        path = design_mod.record_choice(args.repo, args.item, args.option,
                                        notes=args.notes)
    except (machine.GateError, items.ItemError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0
```
```python
    p = sub.add_parser("choice", help="record the human's design-option pick")
    p.add_argument("item")
    p.add_argument("option")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_choice)
```
(Note `cmd_choice` returns 2 for `ItemError` too — unlike `cmd_packet`'s exit 1 — because `choice` is a refusal-gated write; keep as specified and let the CLI tests pin both.)

- [ ] **Step 4: Run new tests, then full suite** — all PASS.
- [ ] **Step 5: Commit** — `feat: factory choice - deterministic design-choice recording`

---

### Task 2: Integration test — full pipeline walk

**Files:**
- Test: `tests/test_pipeline_walk.py`

**Interfaces:** consumes the whole engine; produces the executable proof that a `ui` item's gate chain works end to end at the CLI/lib level (the prose skills ride on exactly these calls).

- [ ] **Step 1: Write the test** (this task is test-only; it must pass immediately against the existing engine — it is a walk, not TDD for new behavior)

`tests/test_pipeline_walk.py`:
```python
"""End-to-end gate walk for one ui item, engine-level (spec §3, §5).

Simulates exactly what the stage skills do: create artifacts, log
evidence events, advance. Proves the pause -> choice -> resume -> plan
path and every gate refusal/pass in order.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import design, dispatch, initrepo, items, logs, machine, paths


class TestUiPipelineWalk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "root"],
                       cwd=self.repo, check=True, env=env)

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def art(self, rel, text="content\n"):
        p = paths.item_dir(self.repo, self.item) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_full_walk(self):
        # add
        self.item = items.new_item_id(self.repo, "Dark mode")
        now = logs.now_stamp()
        items.save_item(self.repo, {"id": self.item, "title": "Dark mode",
                                    "stage": "idea", "kind": "ui",
                                    "created": now, "updated": now}, "")
        # idea -> triage -> spec (gate: triage.md + priority)
        machine.advance(self.repo, self.item, "triage")
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, self.item, "spec")
        self.art("triage.md")
        meta, body = items.load_item(self.repo, self.item)
        meta["priority"] = 1
        items.save_item(self.repo, meta, body)
        machine.advance(self.repo, self.item, "spec")
        # spec -> design (gate: spec.md)
        self.art("spec.md")
        machine.advance(self.repo, self.item, "design")
        # design pause -> human choice -> resume -> plan
        machine.advance(self.repo, self.item, "waiting-human",
                        reason="pick a design option")
        self.assertIsNone(dispatch.next_item(self.repo))
        self.assertEqual(dispatch.pending_human(self.repo)[0]["id"], self.item)
        design.record_choice(self.repo, self.item, "b")
        machine.advance(self.repo, self.item, "design")   # resume to paused-from
        machine.advance(self.repo, self.item, "plan")     # gate: choice.md present
        # plan -> implement (gate: checkbox)
        self.art("plan.md", "- [ ] Task 1\n")
        machine.advance(self.repo, self.item, "implement")
        # implement -> review (gate: branch + event)
        subprocess.run(["git", "branch", f"factory/{self.item}"],
                       cwd=self.repo, check=True)
        logs.append_event(self.repo, self.item, "implement.completed")
        machine.advance(self.repo, self.item, "review")
        # review -> verify (gate: synthesis + approval)
        self.art("reviews/synthesis.md")
        logs.append_event(self.repo, self.item, "review.approved")
        machine.advance(self.repo, self.item, "verify")
        # verify -> ship -> done
        logs.append_event(self.repo, self.item, "verify.green")
        machine.advance(self.repo, self.item, "ship")
        logs.append_event(self.repo, self.item, "ship.merged")
        meta = machine.advance(self.repo, self.item, "done")
        self.assertEqual(meta["stage"], "done")
        # tree still validates cleanly after the whole journey
        self.assertEqual(initrepo.validate_tree(self.repo), [])
        self.assertIsNone(dispatch.next_item(self.repo))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and the full suite** — all PASS (if the walk exposes an engine bug, STOP and report rather than bending the test).
- [ ] **Step 3: Commit** — `test: end-to-end ui-item pipeline walk`

---

### Task 3: The factory-design skill

**Files:**
- Create: `skills/factory-design/SKILL.md`

**Content requirements (binding contracts; prose is the implementer's craft):**

Frontmatter: `name: factory-design`, `description: Use when a factory item is at stage design - generates 2-4 UI mockup options, parks the item for the human's pick`.

Body must contain:
1. **Contract section:** entry stage `design` (kind ui/mixed only — backend never reaches it); artifacts produced: `items/<id>/design/options.html`, packet `docs/factory/packets/<id>-design.md`; exit: `factory advance ITEM waiting-human --reason "pick a design option: see docs/factory/packets/<id>-design.md"` then `factory packet ITEM`. The choice itself is recorded later via `factory choice` (by the human in-session, or by the orchestrator relaying their pick) — this skill NEVER writes choice.md.
2. **Design context, in order:** read `docs/factory/brain/design-system.md` (always present; the headless fallback) and the item's spec.md acceptance criteria; when DesignSync is available per the capabilities skill (interactive sessions only), pull the linked claude.ai/design project's tokens as the preferred source — never block or fail when absent. If the design-system surface is thin/placeholder, use restrained neutral defaults AND file a bid targeting `brain/design-system.md` (via council-judgement) so the gap becomes durable.
3. **The options page:** one self-contained HTML file at `items/<id>/design/options.html` — no external fonts/CDNs/images/scripts; 2–4 options as labeled sections (`<section data-option="a">` … "Option A — <direction name>"); options must be **genuinely distinct directions** (layout/structure/interaction differences), not palette swaps of one design; each option renders the item's actual UI surface (from the spec), not lorem-ipsum abstractions; respect the design tokens; both light and dark treatment if the design system defines them. When the Artifact tool is present (capabilities skill), additionally publish the same file as an artifact for one-click viewing; the local file remains canonical.
4. **The design packet** (write to `docs/factory/packets/<id>-design.md`, NOT via `factory packet` which stays generic): per-option one-paragraph summary (direction, trade-offs), the skill's single recommendation with one sentence of reasoning, how to answer: `factory choice <id> <option> [--notes ...]` from any session in this repo, or reply in-session; note that the pick can be changed by re-running `choice` any time before the item resumes.
5. **Resume note:** after the human picks, the dispatcher's step-0 resume check advances the item automatically on the next `/factory:run`; this skill does not poll or wait.
6. Item paths are under `.factory/` (the path-shorthand preamble sentence — see Task 4).

- [ ] **Steps:** author the skill; run `python3 -m unittest tests.test_plugin_structure -v` + full suite — green; commit `feat: factory-design skill - the design gate`.

---

### Task 4: Wiring + deferred Phase-3 cleanups

**Files:**
- Modify: `skills/factory-dispatch/SKILL.md`
- Modify: `skills/factory-spec/SKILL.md`
- Modify: `commands/init.md`
- Modify: stage skills' preambles (`factory-triage`, `factory-spec`, `factory-plan`, `factory-implement`, `factory-review`, `factory-verify`, `factory-ship`, `factory-design`)
- Modify: `README.md`
- Test: extend `tests/test_plugin_structure.py`

**Changes (each small and exact):**

1. **factory-dispatch:** (a) stage map: `design → factory-design` plainly; keep the conditional-pause caveat but reword as resilience ("if the factory-design skill is unavailable for any reason…") rather than "[Phase 4]"; (b) step 0: after a successful resume, delete the item's answered packets (`docs/factory/packets/<id>.md` and `<id>-design.md` if present) — the log is the durable record, stale packets mislead the hook's "awaiting review" listing; (c) item mode: track the chosen item explicitly — stop when *that item* leaves the actionable set, not when `next` returns something else; (d) step 2's backlog-empty path: invoke the `council-memory-health` skill (which routes a prune recommendation to `council-pruning`) instead of raw `factory health`.
2. **factory-spec:** add the large-item branch — when the spec would exceed roughly a screen of Behavior bullets or the item's triage notes flag it complex, dispatch `agents/spec-writer.md` with the brain excerpts + triage notes and persist its returned report to `items/<id>/spec.md` (orchestrator-persists convention, same as council rounds).
3. **commands/init.md:** pass the product name through: `... init --product $ARGUMENTS` when arguments are given.
4. **Path-shorthand preamble:** one sentence in each stage skill's preamble (right after the CLI shorthand line): "Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`."
5. **README:** Status → "Phases 1–4"; one Design gate paragraph (options page → packet → `factory choice` → auto-resume).
6. **tests/test_plugin_structure.py:** add assertions — `skills/factory-design/SKILL.md` exists with frontmatter (covered by the existing glob test automatically) and contains both `options.html` and `factory choice`; factory-dispatch contains `factory-design` in its stage map.

- [ ] **Steps:** apply edits; full suite green; commit `feat: wire design gate into dispatcher; close deferred phase-3 items`.

---

## Plan Self-Review (completed)

- **Spec coverage (Phase 4, spec §5):** options generation with token sourcing + DesignSync-as-additive (§5.1-2, §8) → Task 3; review packet with recommendation + choice channel (§5.3) → Tasks 1, 3; choice recording + resume (§5.4) → Task 1 + existing dispatcher step-0 (verified by Task 2's walk); gates config note (§5 end) already engine-side via config.gates (unused by engine, documented — unchanged). Deferred Phase-3 items explicitly listed in the progress ledger → Task 4 (spec-writer wiring, health routing, init --product, item-mode wording, path preamble, stale packets). Evidence-event round-scoping stays deferred (Phase 2 note, machine.py docstring) — not design-gate work.
- **Placeholder scan:** clean; Tasks 1-2 carry complete code, Tasks 3-4 carry exact binding contracts.
- **Type consistency:** `design.record_choice` matches `cmd_choice`; `design.choice` event name is new and gate-neutral (no gate consumes it — the plan gate reads the file, which this writes); choice.md path matches `_gate_plan`'s `design/choice.md`; packet name `<id>-design.md` matches dispatcher deletion list and factory-design contract.
