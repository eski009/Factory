# Factory Skills Layer (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 3 of the Factory spec (`docs/superpowers/specs/2026-07-03-software-factory-design.md` §2, §4, §6, §11 phase 3): the Claude Code plugin layer — dispatcher + stage skills written against the degraded baseline (subagents + files, no Fable-only tools), agent definitions, slash commands, SessionStart hook — plus two small engine additions (`next`, `packet`) the dispatcher needs.

**Architecture:** Skills do the thinking; every state mutation goes through the Phase 1/2 CLI (`factory.py advance/log/bid/judge/...`), which enforces the gates. The dispatcher skill picks work via `factory.py next`, runs the current stage's skill, and repeats. Stage skills dispatch subagents for heavy work and log evidence events the gates require. A single capabilities reference defines probe-and-upgrade behavior (Workflow/Artifacts/DesignSync/scheduling) so no skill forks on model.

**Tech Stack:** Claude Code plugin conventions (`.claude-plugin/plugin.json`, `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md`, `hooks/hooks.json`); Python 3.11+ stdlib for engine additions and the plugin-structure test.

## Global Constraints

- Engine changes: Python 3 stdlib only; deterministic output; CLI exit codes 0/1/2 as established.
- **Every skill and command references the CLI as** `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . <cmd>` — never a bare relative path (the plugin is installed outside the target repo). In prose below this is abbreviated `factory <cmd>`.
- Skills are written against the **degraded baseline** (Task subagents + files). Fable-only upgrades appear ONLY in `skills/capabilities/SKILL.md`; stage skills say "dispatch per capabilities skill" and never name Workflow/fork mechanics inline.
- Skill frontmatter: `name` (kebab-case, matches dir) and `description` starting "Use when ..." — both required. Body ≤ 150 lines per skill.
- Stage skills MUST state their entry precondition and exit action in a `## Contract` section: which stage the item must be in, what artifacts they produce, which evidence event they log, and the exact `advance` call they end with. These must match the spec §3 gate table exactly (events: `implement.completed`, `review.approved`, `review.rejected`, `verify.green`, `ship.merged`).
- Council protocol constants (spec §6): round 1 independent, max 3 new claims/agent; orchestrator synthesis; round 2 delta-only; hard stop at 2 rounds (3rd requires written reason). Six roles exactly: `product, ui-taste, architecture, engineering-quality, customer, commercial`.
- Item kinds: an item is `ui`/`mixed` if it touches user-facing interface; `backend` otherwise. Backend items skip the design stage (engine enforces).
- Plugin name: `factory` (commands surface as `/factory:run` etc.).
- Run tests from repo root with: `python3 -m unittest discover -s tests -v`
- Commit after every task; `feat:`/`test:`/`chore:` prefixes.

---

### Task 1: Engine additions — `next` and `packet`

**Files:**
- Create: `scripts/factory/lib/dispatch.py`
- Create: `scripts/factory/lib/packet.py`
- Modify: `scripts/factory/factory.py` (two new subcommands)
- Test: `tests/test_dispatch.py`, `tests/test_packet.py`, extend `tests/test_cli_council.py`-style CLI coverage in `tests/test_cli_dispatch.py`

**Interfaces:**
- Consumes: `items.list_items_safe`, `machine.SPECIAL`, `machine.stage_sequence`, `logs.read_events`, `paths.*`.
- Produces:
  - `dispatch.next_item(repo) -> dict | None` — highest-priority actionable item meta. Actionable = stage not in `("done", "blocked", "waiting-human")`. Sort key `(priority or 9999, id)`. Returns None when nothing is actionable.
  - `dispatch.pending_human(repo) -> list[dict]` — items at `waiting-human`, same sort.
  - `packet.render_packet(repo, item_id) -> str` and `packet.write_packet(repo, item_id) -> Path` — human-readable markdown: title/id/stage/kind/priority header, `paused-reason` if paused, artifact checklist (which of triage.md/spec.md/plan.md/design/choice.md/reviews/synthesis.md exist), last 5 log events, and a `## Respond` section ("Reply in session, or edit this file"). Written to `docs/factory/packets/<item-id>.md` (overwrite; deterministic given state).
  - CLI: `next [--json]` — prints `<id> <stage>` or JSON meta; prints `nothing actionable` + exit 0 with `--json` printing `null` when none. `packet ITEM` — writes packet, prints its path; unknown item → ItemError → stderr, exit 1.

- [ ] **Step 1: Write failing tests**

`tests/test_dispatch.py` (build items via `items.save_item` as in `tests/test_machine.py`; use `make_item`-style helper with distinct ids/priorities):
```python
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import dispatch, initrepo, items


def put(repo, item_id, stage, priority=None, kind="mixed"):
    meta = {"id": item_id, "title": item_id, "stage": stage, "kind": kind,
            "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
    if priority:
        meta["priority"] = priority
    items.save_item(repo, meta, "")


class TestNextItem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_repo_returns_none(self):
        self.assertIsNone(dispatch.next_item(self.repo))

    def test_priority_order_wins(self):
        put(self.repo, "0001-low", "spec", priority=5)
        put(self.repo, "0002-high", "idea", priority=1)
        self.assertEqual(dispatch.next_item(self.repo)["id"], "0002-high")

    def test_missing_priority_sorts_last_then_id(self):
        put(self.repo, "0001-a", "idea")
        put(self.repo, "0002-b", "idea", priority=3)
        self.assertEqual(dispatch.next_item(self.repo)["id"], "0002-b")

    def test_done_blocked_waiting_not_actionable(self):
        for i, stage in enumerate(("done", "blocked", "waiting-human"), 1):
            put(self.repo, f"000{i}-x{i}", stage, priority=1)
        self.assertIsNone(dispatch.next_item(self.repo))

    def test_pending_human_lists_waiting(self):
        put(self.repo, "0001-w", "waiting-human", priority=1)
        put(self.repo, "0002-n", "idea", priority=2)
        pending = dispatch.pending_human(self.repo)
        self.assertEqual([m["id"] for m in pending], ["0001-w"])


if __name__ == "__main__":
    unittest.main()
```

`tests/test_packet.py`:
```python
import os
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import initrepo, items, logs, packet


class TestPacket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        meta = {"id": "0001-thing", "title": "Thing", "stage": "waiting-human",
                "kind": "ui", "priority": 1, "paused-from": "design",
                "paused-reason": "pick a design option",
                "created": "2026-07-03T10:00:00Z", "updated": "2026-07-03T10:00:00Z"}
        items.save_item(self.repo, meta, "# Thing\n")
        (self.repo / ".factory/items/0001-thing/spec.md").write_text("spec\n")
        logs.append_event(self.repo, "0001-thing", "stage.advance",
                          {"from": "spec", "to": "design"})

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def test_render_contains_state_and_reason(self):
        text = packet.render_packet(self.repo, "0001-thing")
        self.assertIn("# Thing", text)
        self.assertIn("waiting-human", text)
        self.assertIn("pick a design option", text)
        self.assertIn("spec.md: yes", text)
        self.assertIn("plan.md: no", text)
        self.assertIn("stage.advance", text)
        self.assertIn("## Respond", text)

    def test_write_packet_path_and_determinism(self):
        path = packet.write_packet(self.repo, "0001-thing")
        self.assertEqual(path, self.repo / "docs/factory/packets/0001-thing.md")
        first = path.read_text()
        packet.write_packet(self.repo, "0001-thing")
        self.assertEqual(path.read_text(), first)


if __name__ == "__main__":
    unittest.main()
```

`tests/test_cli_dispatch.py` (same run_cli harness style as tests/test_cli.py): `next` on empty repo → exit 0, stdout `nothing actionable`; `next --json` → `null`; after `add` + priority-less item → `next` prints `0001-... idea`; `packet 0001-...` → prints path, file exists; `packet 0999-nope` → exit 1.

- [ ] **Step 2: Run tests, verify failures** — `python3 -m unittest tests.test_dispatch tests.test_packet tests.test_cli_dispatch -v` → import errors.

- [ ] **Step 3: Implement**

`scripts/factory/lib/dispatch.py`:
```python
"""Deterministic work selection for the dispatcher skill. Spec §4."""

from . import items

NOT_ACTIONABLE = ("done", "blocked", "waiting-human")


def _by_priority(metas):
    return sorted(metas, key=lambda m: (m.get("priority", 9999), m["id"]))


def next_item(repo):
    metas, _errors = items.list_items_safe(repo)
    actionable = [m for m in metas if m["stage"] not in NOT_ACTIONABLE]
    ordered = _by_priority(actionable)
    return ordered[0] if ordered else None


def pending_human(repo):
    metas, _errors = items.list_items_safe(repo)
    return _by_priority([m for m in metas if m["stage"] == "waiting-human"])
```

`scripts/factory/lib/packet.py`:
```python
"""Render mobile-legible review packets for humans. Spec §5, §9."""

from . import items, logs, paths

ARTIFACTS = ("triage.md", "spec.md", "plan.md", "design/choice.md",
             "reviews/synthesis.md")


def render_packet(repo, item_id):
    meta, _body = items.load_item(repo, item_id)
    item_dir = paths.item_dir(repo, item_id)
    lines = [f"# {meta['title']}", ""]
    lines.append(f"- id: {meta['id']}")
    lines.append(f"- stage: {meta['stage']}")
    lines.append(f"- kind: {meta['kind']}")
    lines.append(f"- priority: {meta.get('priority', '-')}")
    if meta.get("paused-reason"):
        lines.append(f"- waiting on you: {meta['paused-reason']}")
    lines += ["", "## Artifacts"]
    for rel in ARTIFACTS:
        exists = (item_dir / rel).exists()
        lines.append(f"- {rel}: {'yes' if exists else 'no'}")
    lines += ["", "## Recent events"]
    for event in logs.read_events(repo, item_id)[-5:]:
        lines.append(f"- {event['ts']} {event['event']}"
                     + (f" {event['data']}" if "data" in event else ""))
    lines += ["", "## Respond",
              "Reply in session, or edit this file with your decision and",
              "run `/factory:run` to resume.", ""]
    return "\n".join(lines)


def write_packet(repo, item_id):
    path = paths.docs_root(repo) / "packets" / f"{item_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_packet(repo, item_id), encoding="utf-8")
    return path
```

`factory.py`: add `dispatch` and `packet` (as `packet_mod`) to both import branches; handlers:
```python
def cmd_next(args):
    meta = dispatch.next_item(args.repo)
    if args.json:
        print(json.dumps(meta, indent=2, sort_keys=True))
    elif meta is None:
        print("nothing actionable")
    else:
        print(f"{meta['id']} {meta['stage']}")
    return 0


def cmd_packet(args):
    try:
        path = packet_mod.write_packet(args.repo, args.item)
    except items.ItemError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(path)
    return 0
```
Subparsers: `next` with `--json` flag; `packet` with `item` positional.

- [ ] **Step 4: Run new tests, then full suite** — all PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: dispatcher selection and review-packet rendering"`

---

### Task 2: Plugin scaffold — plugin.json, hook, commands

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `hooks/hooks.json`, `hooks/session-start.sh`
- Create: `commands/init.md`, `commands/add.md`, `commands/status.md`, `commands/run.md`, `commands/packet.md`
- Test: `tests/test_plugin_structure.py`

**Interfaces:**
- Produces: installable plugin skeleton; `/factory:init|add|status|run|packet` commands; SessionStart hook that surfaces factory state.

- [ ] **Step 1: Write the structural test**

`tests/test_plugin_structure.py`:
```python
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


class TestPluginStructure(unittest.TestCase):
    def test_plugin_json_valid(self):
        data = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual(data["name"], "factory")

    def test_hooks_json_references_existing_executable(self):
        data = json.loads((ROOT / "hooks/hooks.json").read_text())
        self.assertIn("SessionStart", json.dumps(data))
        script = ROOT / "hooks/session-start.sh"
        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111, "hook must be executable")

    def test_commands_have_frontmatter(self):
        commands = sorted((ROOT / "commands").glob("*.md"))
        self.assertEqual([p.stem for p in commands],
                         ["add", "init", "packet", "run", "status"])
        for path in commands:
            self.assertRegex(path.read_text(), FRONTMATTER, path.name)

    def test_skills_have_frontmatter_and_matching_names(self):
        for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
            text = skill.read_text()
            self.assertRegex(text, FRONTMATTER, str(skill))
            self.assertIn(f"name: {skill.parent.name}", text, str(skill))
            self.assertIn("description: Use when", text, str(skill))

    def test_agents_have_frontmatter(self):
        agents = sorted((ROOT / "agents").glob("*.md"))
        self.assertTrue(len(agents) >= 1)
        for path in agents:
            self.assertRegex(path.read_text(), FRONTMATTER, path.name)


if __name__ == "__main__":
    unittest.main()
```
(Skills/agents dirs are created by Tasks 3-8; create `skills/.gitkeep`-free empty dirs is unnecessary — glob on a missing dir yields nothing, and the agents assertion `>= 1` will pass once Task 7 lands. Run this test file at the END of each remaining task.)

- [ ] **Step 2: Write plugin.json**

`.claude-plugin/plugin.json`:
```json
{
  "name": "factory",
  "version": "0.1.0",
  "description": "Autonomous software factory: product brain, pipeline state machine, council review. Requires the superpowers plugin for execution discipline.",
  "author": {"name": "Steve Coulson"}
}
```

- [ ] **Step 3: Write the hook**

`hooks/hooks.json`:
```json
{
  "hooks": {
    "SessionStart": [
      {"matcher": "startup|resume|clear",
       "hooks": [{"type": "command",
                  "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh\""}]}
    ]
  }
}
```

`hooks/session-start.sh` (chmod +x):
```bash
#!/usr/bin/env bash
# Surface factory state at session start; silent when repo has no .factory/.
set -euo pipefail
[ -d ".factory" ] || exit 0
CLI="${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py"
echo "This repo is a Factory target. Pipeline state:"
python3 "$CLI" --repo . status 2>/dev/null || echo "(factory state unreadable - run: factory validate)"
NEXT=$(python3 "$CLI" --repo . next 2>/dev/null || true)
echo "Next actionable: ${NEXT:-none}"
if ls docs/factory/packets/*.md >/dev/null 2>&1; then
  echo "Packets awaiting human review: $(ls docs/factory/packets/*.md | tr '\n' ' ')"
fi
echo "Use /factory:run to advance the pipeline. Skills: factory-dispatch."
```

- [ ] **Step 4: Write the five commands**

Each command file: frontmatter `description:` + body instructions. Exact contents:

`commands/init.md`:
```markdown
---
description: Initialize this repo as a Factory target (scaffolds .factory/ and docs/factory/)
---
Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . init` then `... validate`.
Show the created paths. Then invoke the factory-intake skill to seed
docs/factory/brain/ from real sources ($ARGUMENTS names the product if given).
If the brain templates are still placeholders, tell the user triage will treat
empty surfaces as open questions.
```

`commands/add.md`:
```markdown
---
description: Add a work item to the factory backlog ($ARGUMENTS = title, optionally "kind:ui|backend|mixed")
---
Parse $ARGUMENTS into TITLE and optional kind (default mixed; use ui/mixed when
the work touches user-facing interface). Run
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . add "TITLE" --kind KIND`.
Report the new item id. Do not start work on it — /factory:run does that.
```

`commands/status.md`:
```markdown
---
description: Show the factory pipeline - items by priority, waiting packets, reputation
---
Run these and summarize compactly (one table, then one line each for packets
and anything needing the user):
- `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . status`
- `... next`
- `... health`
- list docs/factory/packets/*.md if any exist
```

`commands/run.md`:
```markdown
---
description: Run the factory - advance the pipeline ($ARGUMENTS = step | item | loop, default item)
---
Invoke the factory-dispatch skill with mode from $ARGUMENTS (default: item).
Follow it exactly; it owns work selection, stage execution, and stopping rules.
```

`commands/packet.md`:
```markdown
---
description: Render the review packet for a work item ($ARGUMENTS = item id)
---
Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . packet $ARGUMENTS`,
read the file it prints, and relay its contents to the user with a one-line
recommendation of what to decide.
```

- [ ] **Step 5: Run the structural test** (skills/agents assertions will be vacuous-or-partial until later tasks; the command/hook/plugin assertions must pass): `python3 -m unittest tests.test_plugin_structure -v`. Full suite must stay green.
- [ ] **Step 6: Commit** — `chore: plugin scaffold - plugin.json, session hook, commands`

---

### Task 3: Skills — capabilities reference + factory-dispatch

**Files:**
- Create: `skills/capabilities/SKILL.md`
- Create: `skills/factory-dispatch/SKILL.md`

**Content requirements (author following superpowers:writing-skills; complete prose is the implementer's craft, contracts below are verbatim requirements):**

`skills/capabilities/SKILL.md` — frontmatter `name: capabilities`, `description: Use when a factory skill needs to fan out work, render design options, or schedule runs - defines probe-and-upgrade for optional tools`. Body: a table with rows Workflow tool / Artifact tool / DesignSync / scheduled agents; columns Probe (how to detect: tool present in tool list), With it (fan out council rounds & independent plan tasks via Workflow; host options page as artifact; pull/push claude.ai/design tokens; loop mode on schedule), Without it (parallel Task subagent dispatches in one message; write HTML to `items/<id>/design/options.html` and tell the user to open it; use `docs/factory/brain/design-system.md` tokens; user runs `/factory:run loop` manually). Rule stated verbatim: "Probe by attempting nothing: check the tool list. Never let a missing optional tool fail a stage — the degraded path is the contract, upgrades are opportunistic."

`skills/factory-dispatch/SKILL.md` — frontmatter `name: factory-dispatch`, `description: Use when running the factory pipeline (via /factory:run or autonomously) - picks the next actionable item, executes its current stage, advances`. Body must contain:
1. **Modes**: step (one stage of one item), item (one item until done/blocked/waiting-human), loop (repeat item-mode across backlog until `next` returns nothing actionable; between items, if a packet answer is found — `design/choice.md` newly filled — resume that item first).
2. **The loop, exactly**: (a) run `factory validate` — on errors, STOP and write/refresh packets for the user (never guess at corrupt state); (b) `factory next --json` — if null, run `factory health`, report, stop; (c) map stage → skill table (idea→factory-triage — triage covers idea→triage→spec transitions; spec→factory-spec; design→factory-design [Phase 4 — if the skill is absent, pause the item to waiting-human with reason "design stage requires Phase 4 design skill" via `factory advance ITEM waiting-human --reason ...`]; plan→factory-plan; implement→factory-implement; review→factory-review; verify→factory-verify; ship→factory-ship); (d) invoke that skill for the item; (e) re-check mode: step stops here, item continues same item, loop continues backlog.
3. **Stopping rules**: any stage skill failing twice on the same item → `factory advance ITEM blocked --reason "<what failed>"` + `factory packet ITEM` + move on (loop) or stop (step/item). Items entering waiting-human always get `factory packet ITEM`.
4. **Capabilities**: one line — "For any fan-out or design rendering, follow the capabilities skill."
5. **Context hygiene**: stage skills dispatch subagents for heavy work; the dispatcher itself never reads item artifacts beyond metas and skill results.

- [ ] **Steps**: author both skills; run `python3 -m unittest tests.test_plugin_structure -v` (skills assertions now bind); full suite green; commit `feat: capabilities reference and factory-dispatch skill`.

---

### Task 4: Skills — factory-triage + council protocol skills

**Files:**
- Create: `skills/factory-triage/SKILL.md`
- Create: `skills/council-review/SKILL.md`
- Create: `skills/council-judgement/SKILL.md`

**Content requirements:**

`skills/council-review/SKILL.md` — `name: council-review`, `description: Use when a factory stage needs the council's bounded multi-agent review (triage or code review) - runs the two-round protocol without group-chat drift`. Body: the protocol verbatim from spec §6: (1) write `seed-context.md` into `items/<id>/reviews/` (triage: item body + relevant brain surfaces; review: diff summary + spec); (2) Round 1 — dispatch the six council agents (agents/council-*.md) in parallel, each receives ONLY the seed + its own `docs/factory/council/<role>.md`, writes `reviews/round-1/<role>.md`, max 3 new claims, cite evidence or mark unsourced; (3) Orchestrator synthesis — the invoking session dedupes/groups/conflict-detects into `reviews/synthesis-1.md`, selects which agents (if any) need round 2; (4) Round 2 delta-only — selected agents read synthesis (never each other's raw notes), answer agree/disagree/withdraw/refine only, into `reviews/round-2/<role>.md`; (5) hard stop — max 2 rounds, a 3rd requires a written reason line in the synthesis; final synthesis in `reviews/synthesis.md`. Material findings → `council-judgement` skill for bids. Reputation ranks attention: read `factory reputation --json` and order round-1 reading by score, never suppress a claim.

`skills/council-judgement/SKILL.md` — `name: council-judgement`, `description: Use when council findings need to become durable product memory - files bids and records orchestrator judgements through the ledger firewall`. Body: specialists never edit `docs/factory/brain/`; for each material finding run `factory bid ROLE TOPIC "CLAIM" --evidence PATH --surface brain/<file>.md --severity ...` (evidence must be real paths/URLs; unsourced claims go to `brain/open-questions.md` via a bid targeting that surface); the orchestrator (main session) judges each bid with `factory judge BID decision --reason ... [--surface --anchor]`; ONLY after an accept/merge judgement may the brain surface named be edited, at the anchor named; then note the edit in `brain/decisions.md`. Never `judge` your own just-filed bid without re-reading the evidence. Deltas table included verbatim (+0.05/0.0/−0.05/−0.10).

`skills/factory-triage/SKILL.md` — `name: factory-triage`, `description: Use when a factory item is at stage idea or triage - council decides build/priority/scope and writes the roadmap`. Contract section: entry stage `idea` (advance to `triage` first: `factory advance ITEM triage`); run council-review in triage mode; output `items/<id>/triage.md` (decision, priority N, scope cuts, kind confirmation — fix `kind` in item.md frontmatter if council disagrees); set priority by editing item.md frontmatter `priority: N`; update `docs/factory/roadmap.md` (one line per item, priority order); file bids for durable learnings via council-judgement; exit: `factory advance ITEM spec` (gate needs triage.md + priority) — or, if council decides "don't build", `factory advance ITEM blocked --reason "triage: rejected - <why>"` + packet.

- [ ] **Steps**: author three skills; structural test + full suite green; commit `feat: triage and council protocol skills`.

---

### Task 5: Skills — factory-spec + factory-plan

**Files:**
- Create: `skills/factory-spec/SKILL.md`
- Create: `skills/factory-plan/SKILL.md`

**Content requirements:**

`skills/factory-spec/SKILL.md` — `name: factory-spec`, `description: Use when a factory item is at stage spec - writes the item's spec from the product brain without human back-and-forth`. Body: read the brain surfaces + triage.md; the *autonomous substitute for brainstorming's dialogue* is: enumerate the 3-5 key design questions the item raises, answer each FROM the brain (vision/users/constraints/design-system), and for any question the brain cannot answer, choose the most reversible option and record it in the spec under `## Assumptions (brain gaps)` AND file a bid targeting `brain/open-questions.md` (via council-judgement skill) so the gap becomes durable memory. Spec structure: Purpose / Behavior / Non-goals / Assumptions / Acceptance criteria (testable). Write to `items/<id>/spec.md`. Exit: `factory advance ITEM design` for ui/mixed (design is Phase 4 — the dispatcher handles pausing), else `factory advance ITEM plan` — the engine picks the legal next stage; attempt design first for ui/mixed, plan otherwise, and report the gate message verbatim if refused.

`skills/factory-plan/SKILL.md` — `name: factory-plan`, `description: Use when a factory item is at stage plan - produces the TDD implementation plan the implement stage executes`. Body: REQUIRED SUB-SKILL superpowers:writing-plans, adapted: plan documents live at `items/<id>/plan.md`; tasks must be checkbox `- [ ]` items (the implement gate requires at least one); every task names files, tests, and the exact test command; plans reference the item spec's acceptance criteria by number; keep tasks sized for one subagent dispatch each. Exit: `factory advance ITEM implement`.

- [ ] **Steps**: author both; structural test + suite green; commit `feat: spec and plan stage skills`.

---

### Task 6: Skills — factory-implement, factory-review, factory-verify, factory-ship

**Files:**
- Create: `skills/factory-implement/SKILL.md`, `skills/factory-review/SKILL.md`, `skills/factory-verify/SKILL.md`, `skills/factory-ship/SKILL.md`

**Content requirements:**

`factory-implement` — `description: Use when a factory item is at stage implement - executes the plan task-by-task in an isolated branch`. Body: create branch `factory/<item-id>` from the repo's default branch (worktree via superpowers:using-git-worktrees when available, plain branch otherwise); execute `items/<id>/plan.md` with superpowers:subagent-driven-development (fresh implementer subagent per task — use `agents/implementer.md` — with task reviews per `agents/reviewer.md`); tick checkboxes in plan.md as tasks land; when all tasks complete and the item's full test suite passes: `factory log ITEM implement.completed --data '{"tasks": N, "tests": "<summary>"}'` then `factory advance ITEM review`. On a task failing twice: leave the branch intact, log `implement.failed`, and report failure to the dispatcher (which blocks the item).

`factory-review` — `description: Use when a factory item is at stage review - council reviews the diff against spec and brain before verification`. Body: generate the branch diff vs base; run council-review in review mode (seed = diff summary + spec.md + acceptance criteria); blocking findings = anything council marks severity high that contradicts spec/brain/tests; if blocking: `factory log ITEM review.rejected --data '{"round": N}'`, write findings into `reviews/synthesis.md`, `factory advance ITEM implement` (engine enforces the 2-rework cap — on GateError, block the item instead), and hand back to dispatcher; if clean: ensure `reviews/synthesis.md` exists, `factory log ITEM review.approved`, `factory advance ITEM verify`. File durable learnings as bids.

`factory-verify` — `description: Use when a factory item is at stage verify - proves the change works end-to-end before shipping`. Body: REQUIRED SUB-SKILL superpowers:verification-before-completion; run the full test suite AND exercise the changed behavior directly (run the app/CLI path the spec's acceptance criteria name); every acceptance criterion gets a line: criterion → command run → observed result; write to `items/<id>/verify.md`; only when ALL pass: `factory log ITEM verify.green --data '{"tests": "<counts>", "criteria": "<n>/<n>"}'` then `factory advance ITEM ship`. Any failure → back to dispatcher as a stage failure (never log verify.green on partial evidence — evidence before assertions).

`factory-ship` — `description: Use when a factory item is at stage ship - merges per policy and closes the loop on the brain`. Body: read `merge` from `.factory/config.json`: auto → merge `factory/<id>` into the default branch, run the suite on the merged result, delete the branch; queue → push and open a PR (gh pr create), leave branch; tiered → auto for kind backend + severity of change low (docs/fixes/refactors), queue otherwise. After merge/PR: `factory log ITEM ship.merged --data '{"mode": "<auto|queue|tiered>", "ref": "<sha-or-pr>"}'`; `factory advance ITEM done`; update `docs/factory/roadmap.md` (move to Shipped); append outcome line to `docs/factory/brain/decisions.md` (this file is the ship-log exception to the bid firewall — factual ship records only, judgements still own beliefs); `factory packet ITEM` as the shipped report. If merge conflicts or the merged suite fails: revert the merge, log `ship.failed`, report to dispatcher.

- [ ] **Steps**: author all four; structural test + suite green; commit `feat: implement, review, verify, ship stage skills`.

---

### Task 7: Agent definitions

**Files:**
- Create: `agents/council-product.md`, `agents/council-ui-taste.md`, `agents/council-architecture.md`, `agents/council-engineering-quality.md`, `agents/council-customer.md`, `agents/council-commercial.md`
- Create: `agents/implementer.md`, `agents/reviewer.md`, `agents/spec-writer.md`

**Content requirements:**

Council agents — frontmatter `name: council-<role>`, `description: <Role> seat on the factory council - dispatched for bounded review rounds`, `tools: Read, Grep, Glob` (read-only). Body (per role, ~30 lines): "You are the <role> specialist on a bounded council. Read the seed context file you are given and your role memory at docs/factory/council/<role>.md. Round 1: write your findings to the round-1 file path you are given — max 3 new claims, each with evidence (file path, url, or brain citation) or explicitly marked UNSOURCED; end with your single highest-priority concern. Round 2 (only if dispatched again): read the synthesis you are given; respond delta-only — agree/disagree/withdraw/refine per claim; no restatement. Never edit any file outside the path you are given. Never edit docs/factory/brain/ or docs/factory/council/." Plus 3-4 role-specific lines lifted from the role's scope/evidence-standards/blind-spots in `templates/docs-factory/council/<role>.md` (keep the two in sync).

`implementer.md` — `name: implementer`, description for factory-implement dispatches; body: TDD contract (failing test → implement → pass → commit), report format (status DONE/BLOCKED, commits, test summary), escalate-don't-guess.
`reviewer.md` — `name: reviewer`, read-only tools; body: two verdicts (spec compliance vs plan task + code quality), severity calibration, cite file:line.
`spec-writer.md` — `name: spec-writer`, used by factory-spec for large items; body: produce the spec structure from Task 5 given brain excerpts + triage notes; mark brain gaps explicitly.

- [ ] **Steps**: author all nine; structural test + suite green; commit `feat: council and worker agent definitions`.

---

### Task 8: Hygiene skills + intake + final wiring

**Files:**
- Create: `skills/council-memory-health/SKILL.md`, `skills/council-pruning/SKILL.md`, `skills/factory-intake/SKILL.md`
- Modify: `README.md` (Status section + plugin install instructions)

**Content requirements:**

`council-memory-health` — `description: Use when a factory loop run ends or /factory:status is invoked - checks memory health and recommends pruning`. Body: run `factory health`; if recommendation is prune, invoke council-pruning; report reasons verbatim; never prune without the health recommendation.

`council-pruning` — `description: Use when memory-health recommends pruning - runs the provenance-preserving prune per role`. Body: for each role named in the health reasons: `factory prune ROLE` (dry-run) → show counts → `factory prune ROLE --apply`; archived lines live in `.factory/pruning/<role>.md` — never delete them; report kept/archived per role.

`factory-intake` — `description: Use when initializing a factory target or refreshing the product brain - seeds brain surfaces from real sources, evidence only`. Body: inventory real sources (README, docs/, package metadata, recent git log, linked issue tracker); fill each `docs/factory/brain/*.md` surface only with claims traceable to a source, cited inline `(source: <path-or-url>)`; unanswerable sections get an entry in `open-questions.md` instead of invention; NEVER touch product code or CLAUDE.md; end by listing the surfaces still thin so the user knows what triage will treat as open questions. Hard gate verbatim: "A human reviews the seeded brain before the first council run treats it as ground truth — say so when you finish."

README: update Status to "Phases 1-3: engine, council, plugin skills layer"; add "Install as plugin" section (marketplace add from git URL or `claude --plugin-dir`), note Superpowers as required companion plugin, and the `/factory:init → /factory:add → /factory:run` quickstart.

- [ ] **Steps**: author files; `python3 -m unittest discover -s tests -v` green (structural test now fully binding); commit `feat: hygiene and intake skills; README plugin docs`.

---

## Plan Self-Review (completed)

- **Spec coverage (Phase 3 scope):** dispatcher three modes + actionable selection + corrupt-halt (spec §4, §9) → Tasks 1, 3; stage skills with gate-matching contracts (§3) → Tasks 4-6; bounded council protocol + firewall usage (§6) → Task 4; packets (§5, §9) → Task 1 + skill wiring; capability adapter as one reference (§8) → Task 3; plugin/commands/hook (§2) → Task 2; agents (§2) → Task 7; intake hard gate (predecessor's) → Task 8. Design stage is Phase 4: dispatcher pauses ui items at design with a packet (Task 3 rule), spec-stage exit tries the legal next stage (Task 5) — consistent.
- **Placeholder scan:** engine code complete; skill/command/agent content specified by verbatim contracts (frontmatter, CLI calls, event names, protocol constants) with prose left to writing-skills craft — no TBDs.
- **Type consistency:** `next`/`packet` CLI names match dispatcher skill references; event names match Phase 1 gates; `factory/<item-id>` branch matches machine's `_gate_review` expectation; packet path `docs/factory/packets/<id>.md` matches hook glob and Phase 1 template dir.
