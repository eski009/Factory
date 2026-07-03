# Factory Capability Upgrades (Phase 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 5 of the Factory spec (`docs/superpowers/specs/2026-07-03-software-factory-design.md` §8, §11 phase 5): make the capability adapter's opportunistic upgrades concrete — Workflow-based council/plan fan-out, artifact hosting of design options and status, and scheduled continuous operation — without ever making them requirements. The degraded baseline (subagents + files) stays the contract; upgrades are additive reference material plus one autopilot skill/command.

**Architecture:** The `capabilities` skill already names four upgrade rows as one-liners. Phase 5 turns each into a concrete reference doc under `skills/capabilities/references/` describing exactly how a session THAT HAS the tool should use it for the factory's purpose — written so a model without the tool simply never reads it. Stage skills that can fan out gain a single pointer line to the relevant reference. A new `factory-autopilot` skill + `/factory:autopilot` command document safe continuous/scheduled operation (bounds: respects gates, halts on validate errors, budget-aware). No engine code changes except a tiny `factory doctor` command that reports which optional integrations the *repo* is configured for (design-system tokens present? DesignSync project linked in config? schedule configured?) — a deterministic, testable readout.

**Tech Stack:** Python 3.11+ stdlib (the one small command + tests); Claude Code plugin prose (references, skill, command, edits).

## Global Constraints

- Engine: Python 3 stdlib only; deterministic; exit codes 0/1/2.
- **Upgrades never become requirements.** Every reference doc opens with a one-line "You only need this if you have <tool>; the degraded path in the capabilities skill is always sufficient." No stage skill may hard-depend on a reference.
- Reference docs describe factory-specific *usage* of a tool, at the altitude of "what to do," not fabricated exact tool signatures — the orchestrating model knows its own tool schemas.
- Skills: CLI-shorthand convention; frontmatter (`name` matches dir, description "Use when …"); ≤150 lines. Reference docs have no frontmatter requirement but must be linked from `capabilities/SKILL.md`.
- Autopilot safety bounds are binding (see Task 3) — an autonomous loop must halt on `factory validate` errors and never bypass a configured gate.
- Run tests from repo root with: `python3 -m unittest discover -s tests -v`
- Commit after every task; `feat:`/`test:`/`chore:` prefixes.

---

### Task 1: `factory doctor` — capability/integration readout

**Files:**
- Create: `scripts/factory/lib/doctor.py`
- Modify: `scripts/factory/factory.py` (subcommand; import `doctor as doctor_mod` in both branches)
- Test: `tests/test_doctor.py`, CLI coverage in `tests/test_cli_dispatch.py`-style additions

**Interfaces:**
- Consumes: `paths.config_path/docs_root/factory_root`, `initrepo.validate_tree`.
- Produces:
  - `doctor.report(repo) -> dict` — deterministic readout of REPO-side integration state (not model tool availability, which the engine can't see):
    ```
    {
      "tree_valid": bool,                 # validate_tree() == []
      "design_system_present": bool,      # docs/factory/brain/design-system.md non-placeholder
      "designsync_project": str|None,     # config.get("designsync_project")
      "schedule_configured": bool,        # config.get("autopilot", {}).get("schedule") truthy
      "merge_policy": str,                # config["merge"]
      "gates": [str],                     # config["gates"]
      "open_items": int,                  # items not done/blocked
      "pending_human": int,               # waiting-human items
    }
    ```
    "non-placeholder" = the design-system.md file does not contain the seeded sentinel line "_Not yet written." (intake replaces it). Missing config keys default sensibly (None/False).
  - `doctor.render(report) -> str` — human-readable lines, one per key, deterministic order.
  - CLI: `doctor [--json]` — prints render() or JSON; exit 0 always (it's a readout, not a gate). `config.schema.json` gains OPTIONAL `designsync_project` (string) and `autopilot` (object with optional `schedule` string) properties so a configured repo still validates.

- [ ] **Step 1: Write failing tests**

`tests/test_doctor.py`:
```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import doctor, initrepo, items, paths


class TestDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo, product="demo")

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_repo_report(self):
        r = doctor.report(self.repo)
        self.assertTrue(r["tree_valid"])
        self.assertFalse(r["design_system_present"])   # still placeholder
        self.assertIsNone(r["designsync_project"])
        self.assertFalse(r["schedule_configured"])
        self.assertEqual(r["merge_policy"], "auto")
        self.assertEqual(r["gates"], ["design"])
        self.assertEqual(r["open_items"], 0)
        self.assertEqual(r["pending_human"], 0)

    def test_design_system_present_when_edited(self):
        (self.repo / "docs/factory/brain/design-system.md").write_text(
            "# Design System\n\nPrimary: #101010 (source: brand.md)\n", encoding="utf-8")
        self.assertTrue(doctor.report(self.repo)["design_system_present"])

    def test_config_integrations_surface(self):
        cfg = json.loads(paths.config_path(self.repo).read_text())
        cfg["designsync_project"] = "proj-123"
        cfg["autopilot"] = {"schedule": "0 * * * *"}
        paths.config_path(self.repo).write_text(json.dumps(cfg, sort_keys=True, indent=2) + "\n")
        r = doctor.report(self.repo)
        self.assertEqual(r["designsync_project"], "proj-123")
        self.assertTrue(r["schedule_configured"])
        self.assertEqual(initrepo.validate_tree(self.repo), [])   # still schema-valid

    def test_item_counts(self):
        for i, stage in enumerate(("idea", "done", "waiting-human"), 1):
            items.save_item(self.repo, {"id": f"000{i}-x{i}", "title": "x", "stage": stage,
                                        "kind": "ui", "created": "2026-07-03T10:00:00Z",
                                        "updated": "2026-07-03T10:00:00Z"}, "")
        r = doctor.report(self.repo)
        self.assertEqual(r["open_items"], 2)      # idea + waiting-human (not done)
        self.assertEqual(r["pending_human"], 1)

    def test_render_deterministic(self):
        text = doctor.render(doctor.report(self.repo))
        self.assertIn("tree_valid:", text)
        self.assertEqual(text, doctor.render(doctor.report(self.repo)))


if __name__ == "__main__":
    unittest.main()
```
CLI additions: `doctor` prints lines exit 0; `doctor --json` parses and has key `tree_valid`.

- [ ] **Step 2: Run tests, verify failures.**

- [ ] **Step 3: Implement**

`scripts/factory/lib/doctor.py`:
```python
"""Deterministic readout of a repo's factory integration state. Spec §8.

Reports REPO-side configuration only (design tokens, linked DesignSync
project, schedule, gates, item counts) — never model tool availability,
which the engine cannot observe. A readout, never a gate.
"""

import json

from . import dispatch, initrepo, items, paths

REPORT_KEYS = ("tree_valid", "design_system_present", "designsync_project",
               "schedule_configured", "merge_policy", "gates",
               "open_items", "pending_human")
_PLACEHOLDER = "_Not yet written."


def _config(repo):
    path = paths.config_path(repo)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def report(repo):
    config = _config(repo)
    ds_path = paths.docs_root(repo) / "brain" / "design-system.md"
    ds_present = ds_path.exists() and _PLACEHOLDER not in ds_path.read_text(encoding="utf-8")
    metas, _errors = items.list_items_safe(repo)
    return {
        "tree_valid": initrepo.validate_tree(repo) == [],
        "design_system_present": ds_present,
        "designsync_project": config.get("designsync_project"),
        "schedule_configured": bool(config.get("autopilot", {}).get("schedule")),
        "merge_policy": config.get("merge", "auto"),
        "gates": config.get("gates", []),
        "open_items": sum(1 for m in metas if m["stage"] not in ("done", "blocked")),
        "pending_human": len(dispatch.pending_human(repo)),
    }


def render(report_dict):
    return "\n".join(f"{key}: {report_dict[key]}" for key in REPORT_KEYS)
```

`config.schema.json`: add to `properties` (keep `additionalProperties: false`):
```json
    "designsync_project": {"type": "string", "minLength": 1},
    "autopilot": {
      "type": "object",
      "additionalProperties": false,
      "properties": {"schedule": {"type": "string", "minLength": 1}}
    }
```

`factory.py`: `cmd_doctor` (json or render, always exit 0) + subparser `doctor` with `--json`.

- [ ] **Step 4: Run new tests + full suite** — green.
- [ ] **Step 5: Commit** — `feat: factory doctor - repo integration readout`

---

### Task 2: Capability upgrade reference docs

**Files:**
- Create: `skills/capabilities/references/workflow-fanout.md`
- Create: `skills/capabilities/references/artifact-hosting.md`
- Create: `skills/capabilities/references/scheduling.md`
- Create: `skills/capabilities/references/designsync.md`
- Modify: `skills/capabilities/SKILL.md` (link the four references from their table rows)
- Test: extend `tests/test_plugin_structure.py`

**Content requirements (each reference opens with the "only if you have <tool>; degraded path is sufficient" line):**

`workflow-fanout.md` — when the Workflow tool is available: run council Round 1 as a parallel fan-out (one stage per seat, structured output = each seat's findings), the orchestrator synthesis as the reduce step, Round 2 as a second conditional fan-out over only the selected seats; and run independent plan tasks (factory-implement) as a pipeline with per-task verify. State the mapping to the degraded path (parallel Task subagents in one message) so behavior is identical, only faster/more parallel. Emphasize: same artifacts written (`reviews/round-1/<role>.md` etc.), same firewall (orchestrator still persists + judges) — Workflow changes execution, never the protocol or the memory rules.

`artifact-hosting.md` — when the Artifact tool is available: publish `items/<id>/design/options.html` as an artifact for one-click viewing and richer interaction; also publish a status dashboard from `factory status --json` + `factory doctor --json`. Canonical copy stays the repo file; the artifact is a view. Never require it — headless runs open the local HTML.

`scheduling.md` — when scheduled-agent/cron tooling is available: run `/factory:autopilot` (Task 3) on a schedule for continuous operation; recommended cadence and the safety bounds (autopilot halts on validate errors, respects gates). Degraded path: the user runs `/factory:run loop` manually.

`designsync.md` — when DesignSync + an interactive claude.ai login are available: link a design-system project id into `.factory/config.json` as `designsync_project`; factory-design pulls its tokens as the preferred source and can push built components back; `factory doctor` surfaces whether it's linked. Degraded path: repo-local `design-system.md` tokens. Interactive-only — never attempted in headless/scheduled runs.

`capabilities/SKILL.md`: in each of the four table rows' "With it" cell, add "→ see references/<file>.md".

- [ ] **Steps:** author four references; link them; structural test asserts each of the four reference files exists and is linked from SKILL.md (`references/<name>.md` string present). Full suite green. Commit `feat: capability upgrade reference docs`.

---

### Task 3: factory-autopilot skill + command; fan-out pointers

**Files:**
- Create: `skills/factory-autopilot/SKILL.md`
- Create: `commands/autopilot.md`
- Modify: `skills/council-review/SKILL.md`, `skills/factory-implement/SKILL.md`, `skills/factory-design/SKILL.md` (one pointer line each to the relevant reference)
- Test: extend `tests/test_plugin_structure.py`

**Content requirements:**

`factory-autopilot/SKILL.md` — `name: factory-autopilot`, `description: Use when running the factory continuously or on a schedule - a bounded autonomous loop with explicit safety stops`. Body (binding safety bounds):
1. Preflight: run `factory doctor`; if `tree_valid` is false, STOP and write a packet — never operate on a corrupt tree.
2. Run `factory-dispatch` in loop mode. The loop's own rules (validate each pass, stop on error, pause at gates) are the safety net; autopilot adds:
3. **Gate respect:** never records a design `choice`, never merges outside the configured `merge` policy, never edits the brain except through the judgement firewall. Autopilot NEVER answers its own human gates — items at `waiting-human` stay parked with packets for the human.
4. **Budget/termination:** stop after the backlog is drained (dispatch returns nothing actionable) OR a caller-provided budget is exhausted; emit a run summary (items advanced, items parked at gates, blocks) as a packet in `docs/factory/packets/`.
5. **Scheduling:** reference `references/scheduling.md` for running this on a schedule; the skill itself is schedule-agnostic (one invocation = one drain-or-budget run).

`commands/autopilot.md` — `description: Run the factory autonomously until the backlog drains or the budget is spent ($ARGUMENTS = optional budget hint)`; body: invoke the factory-autopilot skill.

Pointer lines: council-review → "For Workflow-based fan-out of the rounds, see the capabilities skill's references/workflow-fanout.md (degraded path — parallel subagents — is the default)."; factory-implement → same pointer for parallel plan tasks; factory-design → references/artifact-hosting.md for publishing the options page.

- [ ] **Steps:** author skill + command + pointers; structural test asserts factory-autopilot exists with frontmatter and the autopilot command exists. Full suite green. Commit `feat: factory-autopilot skill and command; fan-out pointers`.

---

## Plan Self-Review (completed)

- **Spec coverage (Phase 5, §8):** Workflow fan-out (Task 2 workflow-fanout.md + Task 3 pointers), artifact hosting (Task 2 artifact-hosting.md + factory-design pointer), scheduling/continuous op (Task 3 autopilot + Task 2 scheduling.md), DesignSync (Task 2 designsync.md + config `designsync_project` surfaced by `factory doctor` in Task 1). Degraded-baseline-stays-contract enforced by the mandatory opening line on every reference + autopilot preflight. The one engine addition (`doctor`) is deterministic and testable, unlike the prose upgrades — it gives the autopilot/scheduling story a real, checkable readout.
- **Placeholder scan:** Task 1 carries complete code; Tasks 2-3 carry binding content contracts (opening line, per-file purpose, the four autopilot safety bounds) with prose as craft.
- **Type consistency:** `doctor.report` keys match the test + `render`; new config properties are optional so existing repos validate; `designsync_project` name consistent across doctor, designsync.md, config schema; autopilot references scheduling.md which references the autopilot command — no dangling links.
