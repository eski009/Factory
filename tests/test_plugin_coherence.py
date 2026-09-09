"""Coherence guards across the plugin: the dispatcher's stage map, skills,
agents, commands, and plugin metadata must agree. Fails loudly on drift.
Spec §2, §10.
"""

import json
import hashlib
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.factory.lib import (
    config_state, feasibility, initrepo, items, logs, machine, ownership,
    safeio, work)

ROOT = Path(__file__).resolve().parents[1]


def skill_names():
    return {p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")}


def read(p):
    return p.read_text(encoding="utf-8")


FEASIBILITY_ITEM = "0001-feature"


def feasibility_acceptance(spec, plan):
    return {
        "version": 1,
        "item": FEASIBILITY_ITEM,
        "spec_sha256": hashlib.sha256(spec).hexdigest(),
        "plan_structure_sha256": feasibility.plan_structure_sha256(plan),
        "revision": {
            "reason": "Initial complete contract",
            "changed_sections": ["initial"],
        },
        "resume_cursor": {"strategy": "first-unchecked-task"},
        "participants": [{
            "item": FEASIBILITY_ITEM, "owned_paths": ["src"],
        }],
        "dependencies": [],
        "resources": [{
            "id": "code", "kind": "path", "value": "src/feature.py",
            "access": "modify", "provider": FEASIBILITY_ITEM,
            "availability": "available",
        }],
        "interfaces": [],
        "criteria": [{
            "id": "AC-1", "statement": "Feature works",
            "requires": ["code"], "tests": ["unit"],
        }],
        "tests": [{
            "id": "unit", "purpose": "component",
            "command": ["python3", "-m", "unittest"],
            "covers": ["code"],
        }],
        "delivery": {
            "mode": "solo", "participants": [FEASIBILITY_ITEM],
            "merge_order": [FEASIBILITY_ITEM], "shared_gates": [],
        },
        "out_of_scope": ["runtime proof"],
    }


def make_feasibility_repo(repo, *, stage="implement", plan=None,
                          enabled=True):
    plan = plan or b"# Compact plan\n- [ ] implement AC-1\n"
    spec = b"# Spec\n\n## Acceptance criteria\n1. Feature works.\n"
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.test"],
        cwd=repo, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Coherence Test"],
        cwd=repo, check=True)
    (repo / ".gitignore").write_text(".factory/\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src/base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", ".gitignore", "src/base.txt"],
        cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed"], cwd=repo, check=True)
    subprocess.run(
        ["git", "checkout", "-q", "-b", f"factory/{FEASIBILITY_ITEM}"],
        cwd=repo, check=True)
    initrepo.init(repo)
    subprocess.run(
        ["git", "add", "docs/factory"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "factory docs"],
        cwd=repo, check=True)
    config_path = repo / ".factory/config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["gates"] = ["feasibility"] if enabled else ["design"]
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    meta = {
        "id": FEASIBILITY_ITEM, "title": "Feature", "stage": stage,
        "kind": "backend", "created": "2026-09-09T10:00:00Z",
        "updated": "2026-09-09T10:00:00Z",
    }
    if stage == "waiting-human":
        meta["paused-from"] = "implement"
        meta["paused-reason"] = "interrupted"
    items.save_item(repo, meta, "Fixture.")
    item_dir = repo / ".factory/items" / FEASIBILITY_ITEM
    (item_dir / "spec.md").write_bytes(spec)
    (item_dir / "plan.md").write_bytes(plan)
    if enabled:
        (item_dir / "acceptance.json").write_text(
            json.dumps(feasibility_acceptance(spec, plan),
                       indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return item_dir, spec, plan


class PluginCoherenceTest(unittest.TestCase):
    def test_ownership_boundary_has_one_engine_authority(self):
        ownership = read(ROOT / "scripts/factory/lib/ownership.py")
        work = read(ROOT / "scripts/factory/lib/work.py")
        skill = read(ROOT / "skills/factory-implement/SKILL.md")

        self.assertIn("os.O_EXCL", ownership)
        self.assertIn("canonical_worktree", ownership)
        self.assertIn("canonical_worktree", work)

        section_start = skill.index(
            "Otherwise, fall through to the in-process path:")
        section_end = skill.index("\n4. ", section_start)
        in_process = skill[section_start:section_end]
        for required in (
            "factory ownership acquire",
            "factory ownership release",
            "FACTORY_IMPLEMENTATION_OWNER",
            "reviewer",
            "task-evidence finalization",
        ):
            self.assertIn(required, in_process)
        self.assertRegex(
            in_process, r"release failure[^.\n]*fail-closed")
        self.assertNotRegex(
            in_process,
            r"(?i)factory log[^.\n;]*(?:acquir|releas)",
        )
        self.assertNotIn("automatic takeover", skill.lower())

    def test_implement_skill_requires_engine_owned_checkout_claim(self):
        skill = read(ROOT / "skills/factory-implement/SKILL.md")
        for required in (
            "factory ownership acquire",
            "factory ownership release",
            "FACTORY_IMPLEMENTATION_OWNER",
            "fresh independent reviewer",
            "task-evidence finalization",
        ):
            self.assertIn(required, skill)
        self.assertNotIn("one-at-a-time per that skill", skill)


class TestPluginCoherence(unittest.TestCase):
    def test_plan_convergence_corpus_calibrates_every_signal(self):
        corpus = json.loads(read(
            ROOT / "skills/factory-plan/references/approach-convergence-corpus.json"))
        signal_ids = [
            "natural-language-rule-tail",
            "input-variety-task-growth",
            "unconstrained-output-postprocess",
        ]
        self.assertEqual(corpus["signal_ids"], signal_ids)
        cases = corpus["cases"]
        for signal_id in signal_ids:
            self.assertTrue(any(signal_id in case["expected_signals"]
                                for case in cases), signal_id)
            self.assertTrue(any(
                case.get("near_neighbour_for") == signal_id
                and signal_id not in case["expected_signals"]
                for case in cases), signal_id)
        self.assertTrue(any(not case["expected_signals"] for case in cases))
        self.assertTrue(any(len(case["expected_signals"]) > 1 for case in cases))

    def test_plan_skill_owns_semantics_and_uses_one_bounded_reviewer(self):
        text = read(ROOT / "skills/factory-plan/SKILL.md")
        for required in (
            "approach-context", "approach-judgement",
            "approach-convergence-corpus.json", "one fresh independent reviewer",
            "zero signals", "planner invocation", "reviewer invocation",
            "approach.rejected", "approaches/forbidden.md",
        ):
            self.assertIn(required, text)
        block = text.split("## Approach convergence\n", 1)[1].split("\n## ", 1)[0]
        for required in (
            "at most one additional fresh reviewer",
            "never infer a signal by regexing plan prose",
            "engine validates the envelope",
        ):
            self.assertIn(required, block)
        self.assertNotIn("six-seat", block.lower())
        self.assertNotIn("council-review", block)

    def test_engine_comments_cite_symbols_not_source_lines(self):
        citations = []
        source_line = re.compile(r"[A-Za-z0-9_./-]+\.(?:py|md):\d+")
        for path in (ROOT / "scripts/factory/lib").glob("*.py"):
            for match in source_line.finditer(read(path)):
                citations.append(f"{path.name}: {match.group(0)}")
        self.assertEqual(
            citations, [],
            "replace source-line citations with symbol or named-section "
            "references: " + ", ".join(citations))

    def test_fingerprint_recipe_agrees_between_skill_and_engine(self):
        skill = read(ROOT / "skills/factory-assure/SKILL.md")
        engine = read(ROOT / "scripts/factory/lib/assure.py")
        self.assertIn('"<journey id>\\n<scenario id>"', skill)
        self.assertNotIn("normalised failing", engine)

    def test_every_dispatcher_mapped_stage_skill_exists(self):
        # factory-dispatch maps stages to factory-<stage> skills; each must exist.
        dispatch = read(ROOT / "skills/factory-dispatch/SKILL.md")
        mapped = set(re.findall(r"factory-(triage|spec|design|plan|implement|"
                                r"review|verify|assure|ship)", dispatch))
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

    def test_claude_and_codex_manifests_agree(self):
        claude = json.loads(read(ROOT / ".claude-plugin/plugin.json"))
        codex = json.loads(read(ROOT / ".codex-plugin/plugin.json"))
        self.assertEqual(codex["name"], claude["name"])
        self.assertEqual(codex["version"], claude["version"])

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

    def test_council_review_seed_consumes_persona_surfaces(self):
        # the persona/market surfaces factory-research writes must be pulled
        # into council-review's seed (the downstream reasoned-against hook),
        # and research mode must be documented.
        text = read(ROOT / "skills/council-review/SKILL.md")
        self.assertIn("personas", text)
        self.assertIn("market", text)
        self.assertIn("research mode", text.lower())

    def test_factory_design_decision_block_is_surface_adaptive(self):
        # item 0012: the decision block must adapt to the viewing surface — one
        # canonical page branching on window.location.protocol, dropping the inert
        # Record-choice affordance on a hosted Artifact and leading with a
        # reply-to-record path, while the file:// surface keeps the full flow.
        text = read(ROOT / "skills/factory-design/SKILL.md")
        self.assertIn("window.location.protocol", text,
                      "decision block must branch on window.location.protocol")
        self.assertIn("never two HTML variants", text,
                      "must forbid emitting two separately-authored HTML variants")
        self.assertIn("reply with your pick", text.lower(),
                      "hosted surface must lead with a reply-to-record affordance")
        self.assertIn("for terminal use", text.lower(),
                      "hosted surface must demote (not remove) the composed CLI command")

    def test_artifact_hosting_reference_describes_hosted_affordance(self):
        # item 0012: the artifact-hosting reference must state that the hosted
        # surface drops the inert Record-choice control and leads with the
        # reply-to-record affordance, matching factory-design's requirement.
        text = read(ROOT / "skills/capabilities/references/artifact-hosting.md")
        self.assertIn("reply with your pick", text.lower(),
                      "artifact-hosting must describe the hosted reply-to-record affordance")
        self.assertIn("drops the record-choice", text.lower(),
                      "artifact-hosting must state Record-choice is DROPPED on the hosted surface")

    def test_headless_worker_wiring_present(self):
        # the headless-worker capability row, its factory-implement dispatch
        # branch, and its reference doc must all exist together.
        caps = read(ROOT / "skills/capabilities/SKILL.md")
        self.assertIn("Headless worker", caps)
        impl = read(ROOT / "skills/factory-implement/SKILL.md")
        self.assertIn("factory work", impl)
        self.assertTrue(
            (ROOT / "skills/capabilities/references/"
             "headless-workers.md").exists())

    def test_headless_scheduler_wiring_present(self):
        # the Layer-2 pool skill exists, the dispatcher cites it, and the
        # reference doc documents the provisioning verbs.
        self.assertIn("factory-workers", skill_names())
        disp = read(ROOT / "skills/factory-dispatch/SKILL.md")
        self.assertIn("factory-workers", disp)
        ref = read(ROOT / "skills/capabilities/references/headless-workers.md")
        self.assertIn("factory provision", ref)
        self.assertIn("factory cleanup", ref)

    def test_plan_feasibility_skill_wiring_is_complete(self):
        reference = (ROOT / "skills/capabilities/references/"
                     "plan-feasibility.md")
        self.assertTrue(reference.exists())
        plan = read(ROOT / "skills/factory-plan/SKILL.md")
        implement = read(ROOT / "skills/factory-implement/SKILL.md")
        review = read(ROOT / "skills/factory-review/SKILL.md")
        verify = read(ROOT / "skills/factory-verify/SKILL.md")
        assure = read(ROOT / "skills/factory-assure/SKILL.md")
        workers = read(ROOT / "skills/factory-workers/SKILL.md")
        headless = read(
            ROOT / "skills/capabilities/references/headless-workers.md")

        self.assertIn("contract-first branch", plan)
        self.assertIn("factory plan-check", plan)
        self.assertIn("factory plan-dispatch", implement)
        self.assertIn("factory plan-finalize", implement)
        self.assertIn("completed plan is a refusal", implement)
        self.assertIn("never issue a replacement fix ticket", implement)
        self.assertIn("never finalized before the full suite is green",
                      implement)
        for source, text in (("review", review), ("verify", verify),
                             ("assure", assure)):
            self.assertIn(f"factory plan-rework ITEM --source {source}", text)
            self.assertIn("Do not separately", text)
        for text in (workers, headless):
            self.assertIn("concurrent_plan_change", text)
            self.assertIn("do not auto-retry", text.lower())
        reference_text = read(reference)
        self.assertIn("not runtime proof", reference_text)
        self.assertIn("first-unchecked-task", reference_text)
        self.assertIn("exactly one unchecked task per accepted finding",
                      reference_text)
        self.assertIn("not automatically a rework-cap refusal",
                      reference_text)
        self.assertIn("review rejected too many times", review)

    def test_compact_dispatch_resume_completed_and_disabled_journeys(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _item_dir, _spec, plan = make_feasibility_repo(repo)
            claim = ownership.acquire(repo, FEASIBILITY_ITEM)
            try:
                dispatch = feasibility.prepare_dispatch(
                    repo, FEASIBILITY_ITEM,
                    config=config_state.capture(repo),
                    owner_token=claim.token, tasks=1)
                self.assertEqual(dispatch.tasks, ("implement AC-1",))
                self.assertEqual(
                    json.loads(dispatch.handoff)["cursor"], "implement AC-1")
            finally:
                claim.release()
            self.assertEqual(
                (repo / ".factory/items" / FEASIBILITY_ITEM /
                 "plan.md").read_bytes(), plan)

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            item_dir, _spec, plan = make_feasibility_repo(
                repo, stage="waiting-human")
            machine.advance(repo, FEASIBILITY_ITEM, "implement")
            self.assertEqual((item_dir / "plan.md").read_bytes(), plan)
            self.assertEqual(
                items.load_item(repo, FEASIBILITY_ITEM)[0]["stage"],
                "implement")

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            complete = b"# Compact plan\n- [x] implement AC-1\n"
            item_dir, _spec, _plan = make_feasibility_repo(
                repo, plan=complete)
            code, result = work.run_work(
                repo, FEASIBILITY_ITEM, backend="stub")
            self.assertEqual(code, 2, result)
            self.assertIn("unchecked task", result["error"])
            self.assertFalse((item_dir / "worker").exists())

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            item_dir, _spec, plan = make_feasibility_repo(
                repo, stage="plan", enabled=False)
            machine.advance(repo, FEASIBILITY_ITEM, "implement")
            self.assertEqual((item_dir / "plan.md").read_bytes(), plan)
            self.assertEqual(
                list((item_dir / "control").glob("operations/*/commit.json")),
                [])

    def test_rejecting_stages_install_source_linked_rework_atomically(self):
        source_names = {
            "review": "reviews/synthesis.md",
            "verify": "verify.md",
            "assure": "assurance/verdicts.json",
        }
        event_names = {
            "review": "review.rejected",
            "verify": "verify.rejected",
            "assure": "assure.rejected",
        }
        for source in ("review", "verify", "assure"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory)
                old_plan = b"# Plan\n- [x] original implementation\n"
                item_dir, spec, _plan = make_feasibility_repo(
                    repo, stage=source, plan=old_plan)
                finding = f"{source.upper()}-1"
                source_path = item_dir / source_names[source]
                source_path.parent.mkdir(parents=True, exist_ok=True)
                if source == "assure":
                    source_path.write_text(json.dumps({
                        "item": FEASIBILITY_ITEM,
                        "journeys": [{
                            "id": "J-001", "surface": "cli",
                            "scenarios": [{
                                "id": finding, "verdict": "fail",
                                "expected": "works", "actual": "broken",
                                "attribution": "regression",
                            }],
                        }],
                    }), encoding="utf-8")
                else:
                    source_path.write_text(
                        f"# Blocking findings\n- {finding}: broken\n",
                        encoding="utf-8")
                proposals = repo / "proposals"
                proposals.mkdir()
                proposal_plan = old_plan + (
                    f"- [ ] Fix {finding} from {source_names[source]}\n"
                    .encode("utf-8"))
                plan_path = proposals / "plan.md"
                plan_path.write_bytes(proposal_plan)
                source_snapshot = safeio.snapshot_path(
                    repo, source_path.relative_to(repo))
                proposed = feasibility_acceptance(spec, proposal_plan)
                proposed["revision"] = {
                    "reason": f"{source} rejection {source_snapshot.sha256}",
                    "changed_sections": ["tasks"],
                }
                acceptance_path = proposals / "acceptance.json"
                acceptance_path.write_text(
                    json.dumps(proposed), encoding="utf-8")
                prepared = feasibility.prepare_rework_entry(
                    repo, FEASIBILITY_ITEM,
                    config=config_state.capture(repo), source=source,
                    source_snapshot=source_snapshot,
                    finding_ids=[finding],
                    plan_proposal=safeio.snapshot_path(
                        repo, plan_path.relative_to(repo)),
                    acceptance_proposal=safeio.snapshot_path(
                        repo, acceptance_path.relative_to(repo)))
                meta, _verdict, receipt = machine.commit_implement_entry(
                    prepared)
                self.assertEqual(meta["stage"], "implement")
                self.assertEqual(
                    (item_dir / "plan.md").read_bytes(), proposal_plan)
                events = [
                    event["event"] for event in logs.read_events(
                        repo, FEASIBILITY_ITEM)
                    if event.get("operation_id") == receipt.operation_id]
                self.assertEqual(
                    events, [event_names[source], "stage.advance"])

    def test_decision_page_wiring_present(self):
        ref = ROOT / "skills/capabilities/references/decision-pages.md"
        self.assertTrue(ref.exists())
        dispatch = read(ROOT / "skills/factory-dispatch/SKILL.md")
        self.assertIn("packets/", dispatch)
        self.assertIn(".html", dispatch)

    def test_tier_set_wiring_present(self):
        triage = read(ROOT / "skills/factory-triage/SKILL.md")
        self.assertIn("factory tier", triage)
        bug = read(ROOT / "skills/factory-bug/SKILL.md")
        self.assertIn("factory tier", bug)
        roadmap = read(ROOT / "skills/factory-roadmap/SKILL.md")
        self.assertIn("tier", roadmap)

    def test_interview_reachable_only_from_init(self):
        # the interview must be reachable only through the human-invoked
        # /factory:init flow — never from autopilot, the dispatcher, or any
        # other skill or command that can run unattended.
        self.assertIn("factory-interview", skill_names())
        self.assertIn("factory-interview", read(ROOT / "commands/init.md"))
        for skill in (ROOT / "skills").glob("*/SKILL.md"):
            if skill.parent.name != "factory-interview":
                self.assertNotIn("factory-interview", read(skill),
                                 f"{skill.parent.name} must not invoke the interview")
        for cmd in (ROOT / "commands").glob("*.md"):
            if cmd.name != "init.md":
                self.assertNotIn("factory-interview", read(cmd),
                                 f"{cmd.name} must not invoke the interview")

    def test_tier_consume_wiring_present(self):
        review = read(ROOT / "skills/factory-review/SKILL.md")
        self.assertIn("Review depth by tier", review)
        council = read(ROOT / "skills/council-review/SKILL.md")
        self.assertIn("light", council)
        research = read(ROOT / "skills/factory-research/SKILL.md")
        self.assertIn("epic", research)

    def test_spec_section_lists_stay_synced(self):
        # the spec.md section order is defined in two places; Journey impact
        # must sit between Behavior and Non-goals in BOTH.
        for rel in ("skills/factory-spec/SKILL.md", "agents/spec-writer.md"):
            text = read(ROOT / rel)
            # anchor on the dash-bullet form so prose mentions of the section
            # names elsewhere in the file cannot satisfy the ordering check
            b = text.index("- `## Behavior`")
            j = text.index("- `## Journey impact`")
            n = text.index("- `## Non-goals`")
            self.assertTrue(b < j < n, f"{rel}: Journey impact must sit between Behavior and Non-goals")

    def test_dispatch_maps_assure_between_verify_and_ship(self):
        dispatch = read(ROOT / "skills/factory-dispatch/SKILL.md")
        self.assertIn("| assure | factory-assure |", dispatch)
        self.assertLess(dispatch.index("| verify | factory-verify |"),
                        dispatch.index("| assure | factory-assure |"))
        self.assertLess(dispatch.index("| assure | factory-assure |"),
                        dispatch.index("| ship | factory-ship |"))

    def test_dispatcher_parks_and_resumes_on_the_cost_breaker(self):
        """AC24: the park rule, the loop/item-step split, and the
        recorded-option routing all live in dispatcher prose — the engine
        never routes on which answer was recorded."""
        text = read(ROOT / "skills/factory-dispatch/SKILL.md")
        self.assertIn("cost breaker:", text)
        self.assertIn("factory cost-answer", text)
        self.assertIn("cost/answer.md", text)
        self.assertIn("- answer: continue", text)
        self.assertIn(
            'factory advance ITEM waiting-human --reason "cost breaker:',
            text)
        park = text.split("cost breaker: <n> rework edges", 1)[1]
        self.assertIn("loop", park)
        self.assertIn("item", park)
        self.assertIn("step", park)

    def test_autopilot_run_summary_carries_no_cross_item_total(self):
        """0016 global constraint: no total, sum, mean or median across
        items appears in any text output, anywhere — the run-summary
        packet's Spend section is per-item only."""
        text = read(ROOT / "skills/factory-autopilot/SKILL.md")
        self.assertNotIn("run total", text)
        self.assertIn("no run-total line", text)

    def test_assure_base_walk_contract_is_stated(self):
        # AC11: the base walk's four load-bearing properties must be
        # written down in the skill, not left to the orchestrator's memory.
        text = read(ROOT / "skills/factory-assure/SKILL.md")
        # (a) conditional fresh-round exemption
        self.assertIn("assurance/base/<sha>/", text)
        self.assertIn("conditional on `<sha>` still equalling the current "
                      "merge base", text)
        self.assertIn("deleted at the start of a fresh round", text)
        # (b) the allowlist exclusion
        self.assertIn("never the branch walk's verdicts, expectations, "
                      "evidence, or any attribution", text)
        # (c) journey-scoped, once per round, config-gated trigger
        self.assertIn("exactly **one** base walk per assure round", text)
        self.assertIn("journey-scoped", text)
        self.assertIn("`assure_attribution: true`", text)
        # (d) its own spend event
        self.assertIn("factory-assure-base", text)
        self.assertIn('"stage":"assure"', text)

    def test_assure_skill_routes_non_blocking_fails_to_real_items(self):
        text = read(ROOT / "skills/factory-assure/SKILL.md")
        self.assertIn("factory file-base-defect", text)
        self.assertIn("Factory never ignores a failure; it files it.", text)
        self.assertIn("packets/reports", text)

    def test_dispatcher_parks_and_resumes_on_the_approach_cap(self):
        """Item 0015 AC16.4: the park rule, the loop/item-step split,
        and the recorded-option routing live in dispatcher prose - the
        engine never routes on which answer was recorded."""
        text = read(ROOT / "skills/factory-dispatch/SKILL.md")
        self.assertIn("approach cap:", text)
        self.assertIn("factory approach-answer", text)
        self.assertIn("approaches/answer.md", text)
        self.assertIn("- answer: continue", text)
        self.assertIn(
            'factory advance ITEM waiting-human --reason "approach cap:',
            text)
        park = text.split("approach cap: <n> redesign", 1)[1]
        self.assertIn("loop", park)
        self.assertIn("item", park)
        self.assertIn("step", park)

    def test_verify_failures_route_to_a_remedy_not_a_park(self):
        """Item 0015 AC13: a verify failure with a named remedy routes
        factory advance ITEM implement; a non-convergent design writes
        the graveyard and routes the redesign edge."""
        dispatch_text = read(ROOT / "skills/factory-dispatch/SKILL.md")
        verify_text = read(ROOT / "skills/factory-verify/SKILL.md")
        self.assertIn("factory advance ITEM implement", dispatch_text)
        self.assertIn("approaches/forbidden.md", verify_text)
        self.assertIn("approach.rejected", verify_text)
        self.assertIn("factory advance ITEM implement", verify_text)

    def test_spec_skill_reads_graveyard_and_logs_spec_revised(self):
        """Item 0015 SS4 residual: the required read is skill prose plus
        the fail-closed spec.revised token - nothing engine-side can
        verify comprehension, so the prose must exist."""
        text = read(ROOT / "skills/factory-spec/SKILL.md")
        self.assertIn("approaches/forbidden.md", text)
        self.assertIn("spec.revised", text)


if __name__ == "__main__":
    unittest.main()
