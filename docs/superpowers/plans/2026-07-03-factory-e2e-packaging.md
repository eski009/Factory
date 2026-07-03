# Factory E2E + Packaging (Phase 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 6 of the Factory spec (`docs/superpowers/specs/2026-07-03-software-factory-design.md` §10, §11 phase 6): the end-to-end proof and the packaging polish that make Factory installable and trustworthy — a subprocess-level CLI walk over a real fixture repo, a plugin-coherence test, and the release scaffolding (LICENSE, CHANGELOG, getting-started docs, final README).

**Architecture:** The existing walk test (`test_pipeline_walk.py`) drives the engine at the *library* level. Phase 6 adds a higher-fidelity walk that shells out to `factory.py` exactly as a skill would (`python3 scripts/factory/factory.py --repo <fixture> <cmd>`), proving the CLI contract end to end in a real temp git repo. A plugin-coherence test asserts the plugin's parts agree (every stage the dispatcher maps has a skill; every agent the skills name exists; plugin.json/marketplace.json/hooks cohere). Packaging tasks add the files a public GitHub project needs. No product-code changes — this phase is verification + release scaffolding.

**Tech Stack:** Python 3.11+ stdlib (subprocess-driven tests); Markdown/text (docs, LICENSE, CHANGELOG).

## Global Constraints

- Tests: Python 3 stdlib only; deterministic (`FACTORY_NOW`, git author env pinned); each test self-contained in a `tempfile.TemporaryDirectory`.
- The e2e test shells out to the real `factory.py` via `subprocess` — it exercises the CLI surface skills depend on, so it must use only documented subcommands/flags and assert on exit codes + stdout/stderr + resulting files.
- Packaging: LICENSE is MIT (attribution "Steve Coulson"); CHANGELOG follows Keep-a-Changelog headings; docs are accurate to the shipped code (no aspirational claims).
- Plugin-coherence test must fail loudly if a dispatcher-mapped stage has no skill dir, or a skill/agent references a sibling that doesn't exist — this is the guard against skill/agent drift as the project grows.
- Run tests from repo root with: `python3 -m unittest discover -s tests -v`
- Commit after every task; `feat:`/`test:`/`chore:`/`docs:` prefixes.

---

### Task 1: End-to-end CLI walk over a fixture repo

**Files:**
- Test: `tests/test_e2e_cli.py`

**Interfaces:** consumes the whole shipped CLI via subprocess; produces the executable proof that `init → add → advance (with gate refusals) → choice → … → done` works exactly as a skill would drive it.

- [ ] **Step 1: Write the test** (test-only; must pass against the shipped CLI immediately — it's a walk, not TDD for new behavior; if it exposes a real CLI bug, STOP and report)

`tests/test_e2e_cli.py`:
```python
"""End-to-end CLI walk: drive the real factory.py via subprocess exactly
as a stage skill would, over a fresh fixture repo. Proves the CLI contract
(exit codes, stdout, resulting files) for a full ui-item lifecycle. Spec §10.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "factory" / "factory.py"


class TestE2ECli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name)
        self.env = dict(os.environ, FACTORY_NOW="2026-07-03T12:00:00Z",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        subprocess.run(["git", "init", "-q"], cwd=self.target, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "root"],
                       cwd=self.target, check=True, env=self.env)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, expect=0):
        result = subprocess.run(
            ["python3", str(CLI), "--repo", str(self.target), *args],
            capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, expect,
                         msg=f"args={args}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result

    def art(self, item, rel, text="content\n"):
        p = self.target / ".factory" / "items" / item / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_full_cli_lifecycle(self):
        # init + validate
        self.cli("init", "--product", "demo")
        self.cli("validate")
        self.assertEqual(self.cli("doctor", "--json").returncode, 0)
        # add a ui item; it becomes 0001-dark-mode
        out = self.cli("add", "Dark mode", "--kind", "ui").stdout.strip()
        self.assertEqual(out, "0001-dark-mode")
        item = "0001-dark-mode"
        # next selects it
        self.assertIn(item, self.cli("next").stdout)
        # idea -> triage
        self.cli("advance", item, "triage")
        # spec gate refuses without triage.md + priority
        self.cli("advance", item, "spec", expect=2)
        self.art(item, "triage.md")
        # set priority via edited item.md through... there's no CLI for priority;
        # skills edit frontmatter directly, so do the same here:
        item_md = self.target / ".factory/items" / item / "item.md"
        item_md.write_text(item_md.read_text().replace(
            "kind: ui", "kind: ui\npriority: 1"), encoding="utf-8")
        self.cli("advance", item, "spec")
        # spec -> design
        self.art(item, "spec.md")
        self.cli("advance", item, "design")
        # design gate: pause, choice, resume
        self.cli("advance", item, "waiting-human", "--reason", "pick a design")
        self.assertIn(item, self.cli("packet", item).stdout)  # packet path printed
        self.cli("choice", item, "b", "--notes", "darker header")
        self.assertTrue((self.target / ".factory/items" / item / "design/choice.md").exists())
        self.cli("advance", item, "design")   # resume to paused-from
        self.cli("advance", item, "plan")     # gate: choice.md present
        # plan -> implement
        self.art(item, "plan.md", "- [ ] Task 1\n")
        self.cli("advance", item, "implement")
        # implement -> review (branch + event)
        subprocess.run(["git", "branch", f"factory/{item}"], cwd=self.target, check=True)
        self.cli("log", item, "implement.completed")
        self.cli("advance", item, "review")
        # review -> verify
        self.art(item, "reviews/synthesis.md")
        self.cli("log", item, "review.approved")
        self.cli("advance", item, "verify")
        # verify -> ship -> done
        self.cli("log", item, "verify.green")
        self.cli("advance", item, "ship")
        self.cli("log", item, "ship.merged")
        self.cli("advance", item, "done")
        # final state: done, tree valid, nothing actionable, council usable
        rows = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(rows[0]["stage"], "done")
        self.cli("validate")
        self.assertIn("nothing actionable", self.cli("next").stdout)
        # council firewall end to end via CLI
        bid = self.cli("bid", "product", "onboarding", "Users drop at step 2",
                       "--evidence", "docs/factory/brain/users.md",
                       "--surface", "brain/vision.md", "--severity", "medium").stdout.strip()
        self.assertEqual(bid, "bid-0001")
        self.cli("bid", "product", "onboarding", "bad", "--evidence", "x",
                 "--surface", "s", "--severity", "nope", expect=2)   # schema refusal
        self.cli("judge", "bid-0001", "accept", "--reason", "clear signal",
                 "--surface", "brain/vision.md", "--anchor", "## Onboarding")
        rep = json.loads(self.cli("reputation", "--json").stdout)
        self.assertEqual(rep["product/onboarding"], 0.05)
        self.cli("validate")   # ledgers consistent after a real bid+judge

    def test_backend_item_skips_design(self):
        self.cli("init")
        item = self.cli("add", "Add index", "--kind", "backend").stdout.strip()
        self.cli("advance", item, "triage")
        self.art(item, "triage.md")
        item_md = self.target / ".factory/items" / item / "item.md"
        item_md.write_text(item_md.read_text().replace(
            "kind: backend", "kind: backend\npriority: 1"), encoding="utf-8")
        self.cli("advance", item, "spec")
        self.art(item, "spec.md")
        # backend jumps spec -> plan (no design); design is an illegal transition
        self.cli("advance", item, "design", expect=2)
        self.cli("advance", item, "plan")
        # choice refused for a backend item
        self.cli("choice", item, "a", expect=2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and the full suite.** Run `python3 -m unittest tests.test_e2e_cli -v` then the whole suite. All PASS. If the CLI walk reveals a real bug (e.g. a gate or exit code differs from the library walk), STOP and report it — do not weaken the assertions.
- [ ] **Step 3: Commit** — `test: end-to-end CLI walk over a fixture repo`

---

### Task 2: Plugin-coherence test

**Files:**
- Test: `tests/test_plugin_coherence.py`

**Interfaces:** consumes the plugin tree; produces the guard that skills, agents, commands, dispatcher map, and plugin metadata stay mutually consistent as the project grows.

- [ ] **Step 1: Write the test** (test-only; must pass against the shipped plugin)

`tests/test_plugin_coherence.py`:
```python
"""Coherence guards across the plugin: the dispatcher's stage map, skills,
agents, commands, and plugin metadata must agree. Fails loudly on drift.
Spec §2, §10.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def skill_names():
    return {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}


def read(p):
    return p.read_text(encoding="utf-8")


class TestPluginCoherence(unittest.TestCase):
    def test_every_dispatcher_mapped_stage_skill_exists(self):
        # factory-dispatch maps stages to factory-<stage> skills; each must exist.
        dispatch = read(ROOT / "skills/factory-dispatch/SKILL.md")
        mapped = set(re.findall(r"factory-(triage|spec|design|plan|implement|"
                                r"review|verify|ship)", dispatch))
        skills = skill_names()
        for stage in mapped:
            self.assertIn(f"factory-{stage}", skills,
                          f"dispatcher maps factory-{stage} but the skill is missing")

    def test_every_referenced_agent_exists(self):
        agents = {p.stem for p in (ROOT / "agents").glob("*.md")}
        for skill in (ROOT / "skills").glob("*/SKILL.md"):
            for ref in re.findall(r"agents/([a-z0-9-]+)\.md", read(skill)):
                self.assertIn(ref, agents,
                              f"{skill.parent.name} references agents/{ref}.md which is missing")

    def test_every_reference_doc_link_resolves(self):
        refs_dir = ROOT / "skills/capabilities/references"
        for skill in (ROOT / "skills").glob("*/SKILL.md"):
            for ref in re.findall(r"references/([a-z0-9-]+\.md)", read(skill)):
                self.assertTrue((refs_dir / ref).exists(),
                                f"{skill.parent.name} links references/{ref} which is missing")

    def test_council_roles_match_agents_and_templates(self):
        # the six council roles must exist as agents AND as role templates.
        roles = ["product", "ui-taste", "architecture", "engineering-quality",
                 "customer", "commercial"]
        for role in roles:
            self.assertTrue((ROOT / f"agents/council-{role}.md").exists(),
                            f"missing agents/council-{role}.md")
            self.assertTrue((ROOT / f"templates/docs-factory/council/{role}.md").exists(),
                            f"missing role template for {role}")

    def test_plugin_and_marketplace_agree(self):
        plugin = json.loads(read(ROOT / ".claude-plugin/plugin.json"))
        market = json.loads(read(ROOT / ".claude-plugin/marketplace.json"))
        self.assertEqual(plugin["name"], "factory")
        names = {p["name"] for p in market["plugins"]}
        self.assertIn("factory", names)

    def test_every_command_names_a_real_skill_or_cli(self):
        # each command body references either a skill (…-skill / factory-…) or the CLI.
        for cmd in (ROOT / "commands").glob("*.md"):
            body = read(cmd)
            self.assertTrue(
                "factory.py" in body or re.search(r"factory-[a-z]+", body)
                or "factory-intake" in body,
                f"{cmd.name} neither invokes the CLI nor names a skill")

    def test_hook_script_referenced_by_hooks_json_exists(self):
        hooks = json.loads(read(ROOT / "hooks/hooks.json"))
        blob = json.dumps(hooks)
        self.assertIn("session-start.sh", blob)
        self.assertTrue((ROOT / "hooks/session-start.sh").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it + full suite.** All PASS. If a coherence check fails, that's a REAL drift bug — STOP and report which skill/agent/command is inconsistent rather than loosening the assertion.
- [ ] **Step 3: Commit** — `test: plugin-coherence guards (dispatcher map, agents, references, metadata)`

---

### Task 3: Release scaffolding — LICENSE, CHANGELOG, getting-started, README finalize

**Files:**
- Create: `LICENSE`
- Create: `CHANGELOG.md`
- Create: `docs/getting-started.md`
- Modify: `README.md`

**Content requirements:**

`LICENSE` — MIT License, year 2026, copyright holder "Steve Coulson". Standard MIT text.

`CHANGELOG.md` — Keep-a-Changelog format. One `## [0.1.0] - 2026-07-03` entry under `### Added` summarizing what exists: engine (state machine, gates, ledgers, reputation, health, prune, doctor); plugin (dispatcher + stage skills + council protocol + design gate + autopilot); install (plugin.json/marketplace.json/hook/commands). Keep it factual and terse — one bullet per subsystem, no aspirational items.

`docs/getting-started.md` — a real walkthrough for a first-time user: (1) install (marketplace add the repo git URL, `/plugin install factory`; or `--plugin-dir`; Superpowers as companion); (2) `/factory:init` in a target repo → what it scaffolds → the intake hard gate (human reviews the seeded brain); (3) `/factory:add "…"` then `/factory:run` → what each stage does, where the design gate stops for you, how you answer with `factory choice`; (4) the autonomy dial: gates config, merge policy, `/factory:autopilot`; (5) where state lives (`.factory/` machine state, `docs/factory/` human-readable brain + packets) and how to inspect it (`/factory:status`, `factory doctor`). Accurate to the shipped commands only.

`README.md` — finalize: Status → "Phases 1–6 complete"; a concise feature list (product-brain pipeline, bounded council with memory firewall, design gate, autopilot, works on any Claude model); link to `docs/getting-started.md` and the spec; keep the existing install + CLI sections, correcting anything now stale (e.g. the CLI surface now includes `next`, `packet`, `choice`, `doctor`, `bid`, `judge`, `reputation`, `health`, `prune`, `autopilot`).

- [ ] **Steps:** author the four files; run the full suite (docs don't affect it, but confirm nothing regressed) — green; commit `docs: LICENSE, CHANGELOG, getting-started, finalized README`.

---

## Plan Self-Review (completed)

- **Spec coverage (Phase 6, §10 testing + build-order phase 6):** e2e fixture that runs init + a scripted item through every stage at the CLI level (Task 1 — higher fidelity than the existing lib walk, includes the council firewall and backend-skips-design paths); plugin-coherence guard against skill/agent/reference/metadata drift (Task 2 — the "no silent drift" net as the project grows); packaging + docs polish for a public install (Task 3). The lib-level walk (Phase 4) and the CLI walk (Task 1) are complementary, not redundant: one pins engine internals, the other pins the subprocess CLI contract skills actually use.
- **Placeholder scan:** Tasks 1-2 carry complete test code; Task 3 carries exact content contracts (MIT/Keep-a-Changelog/five-section walkthrough) with the prose as craft — no TBDs.
- **Type consistency:** e2e test uses only real subcommands/flags (`init/validate/doctor/add/next/advance/packet/choice/log/status/bid/judge/reputation`), verified against the shipped `factory.py` argparse; coherence test's stage regex matches the eight `factory-<stage>` skills that exist; `factory choice … b` uses a valid a–d option (matches Phase 4's validation); reputation key `product/onboarding` matches the bid's agent/topic.
