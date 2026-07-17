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

    def test_marketplace_json_valid(self):
        data = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(data["name"], "factory-marketplace")
        self.assertEqual(len(data["plugins"]), 1)
        self.assertEqual(data["plugins"][0]["name"], "factory")

    def test_hooks_json_references_existing_executable(self):
        data = json.loads((ROOT / "hooks/hooks.json").read_text())
        self.assertIn("SessionStart", json.dumps(data))
        script = ROOT / "hooks/session-start.sh"
        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111, "hook must be executable")

    def test_commands_have_frontmatter(self):
        commands = sorted((ROOT / "commands").glob("*.md"))
        self.assertEqual([p.stem for p in commands],
                         ["add", "autopilot", "bug", "do", "escape", "init", "packet", "research", "roadmap", "run", "status"])
        for path in commands:
            self.assertRegex(path.read_text(), FRONTMATTER, path.name)

    @unittest.skipUnless((ROOT / "skills").is_dir(), "skills arrive in Task 3")
    def test_skills_have_frontmatter_and_matching_names(self):
        for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
            text = skill.read_text()
            self.assertRegex(text, FRONTMATTER, str(skill))
            self.assertIn(f"name: {skill.parent.name}", text, str(skill))
            self.assertIn("description: Use when", text, str(skill))

    @unittest.skipUnless((ROOT / "agents").is_dir(), "agents arrive in Task 7")
    def test_agents_have_frontmatter(self):
        agents = sorted((ROOT / "agents").glob("*.md"))
        self.assertTrue(len(agents) >= 1)
        for path in agents:
            self.assertRegex(path.read_text(), FRONTMATTER, path.name)

    def test_dispatch_conditional_pause_mentions_design_choice(self):
        text = (ROOT / "skills/factory-dispatch/SKILL.md").read_text()
        self.assertIn("design/choice.md", text)

    def test_dispatch_stage_map_includes_factory_design(self):
        text = (ROOT / "skills/factory-dispatch/SKILL.md").read_text()
        self.assertIn("factory-design", text)

    def test_factory_design_skill_exists_and_covers_options_and_choice(self):
        skill = ROOT / "skills/factory-design/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("options.html", text)
        self.assertIn("factory choice", text)

    def test_autopilot_command_exists(self):
        cmd = ROOT / "commands/autopilot.md"
        self.assertTrue(cmd.exists())
        text = cmd.read_text()
        self.assertRegex(text, FRONTMATTER, str(cmd))
        self.assertIn("factory-autopilot", text)

    def test_autopilot_skill_never_answers_its_own_human_gates(self):
        skill = ROOT / "skills/factory-autopilot/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("never answers its own human gates", text.lower())
        self.assertIn("never waives or confirms assurance", text.lower())
        self.assertIn("never files or promotes escapes", text.lower())

    def test_do_command_routes_to_owning_surfaces(self):
        cmd = ROOT / "commands/do.md"
        self.assertTrue(cmd.exists())
        text = cmd.read_text()
        self.assertRegex(text, FRONTMATTER, str(cmd))
        # a router, not a new pipeline: every route lands on an existing owner
        for owner in ("factory-bug", "factory-roadmap", "factory-research",
                      "factory-dispatch", "factory-autopilot",
                      "factory add", "commands/escape.md"):
            self.assertIn(owner, text, owner)
        # it never advances stages itself
        self.assertIn("never run `factory advance` yourself", text)
        # human verbs are relays of an expressed decision, never guesses
        self.assertIn("ONLY when the human's own words carry the decision",
                      text)
        for verb in ("factory choice", "factory waive", "factory confirm"):
            self.assertIn(verb, text, verb)
        self.assertIn("never invented", text)
        # ambiguity goes to the present human, not the nearest match
        self.assertIn("ask ONE clarifying question", text)
        # unattended runs never route through it
        self.assertIn("never invoke it at all", text)

    def test_escape_command_wraps_cli_and_links_bugs(self):
        cmd = ROOT / "commands/escape.md"
        self.assertTrue(cmd.exists())
        text = cmd.read_text()
        self.assertRegex(text, FRONTMATTER, str(cmd))
        self.assertIn("factory escape", text)
        self.assertIn("factory promote", text)
        self.assertIn("factory-bug", text)
        self.assertIn("miss", text)
        self.assertIn("missing-journey", text)

    def test_roadmap_skill_mentions_factory_add_and_priority(self):
        skill = ROOT / "skills/factory-roadmap/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("factory add", text)
        self.assertIn("factory priority", text)

    def test_roadmap_command_names_its_skill(self):
        cmd = ROOT / "commands/roadmap.md"
        self.assertTrue(cmd.exists())
        text = cmd.read_text()
        self.assertRegex(text, FRONTMATTER, str(cmd))
        self.assertIn("factory-roadmap", text)

    def test_intake_skill_covers_brownfield_and_taste_packet(self):
        text = (ROOT / "skills/factory-intake/SKILL.md").read_text()
        self.assertIn("taste.md", text)
        self.assertIn("brownfield", text)

    def test_capability_upgrade_references_exist_and_are_linked(self):
        skill_text = (ROOT / "skills/capabilities/SKILL.md").read_text()
        for name in ("workflow-fanout", "artifact-hosting", "scheduling", "designsync", "orchestration-patterns", "model-tiering", "browser-read", "browser-drive"):
            ref = ROOT / f"skills/capabilities/references/{name}.md"
            self.assertTrue(ref.exists(), str(ref))
            self.assertIn(f"references/{name}.md", skill_text, name)

    def test_research_command_names_its_skill(self):
        cmd = ROOT / "commands/research.md"
        self.assertTrue(cmd.exists())
        text = cmd.read_text()
        self.assertRegex(text, FRONTMATTER, str(cmd))
        self.assertIn("factory-research", text)

    def test_research_skill_covers_persona_market_depth_and_gate(self):
        skill = ROOT / "skills/factory-research/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("personas.md", text)
        self.assertIn("market.md", text)
        self.assertIn("research.depth", text)
        self.assertIn("research mode", text.lower())
        self.assertIn(
            "A human reviews the seeded brain before the first council run "
            "treats it as ground truth", text)

    def test_init_command_invokes_research(self):
        text = (ROOT / "commands/init.md").read_text()
        self.assertIn("factory-research", text)

    def test_init_command_invokes_interview_after_research(self):
        text = (ROOT / "commands/init.md").read_text()
        self.assertIn("factory-interview", text)
        self.assertLess(text.index("factory-research"),
                        text.index("factory-interview"))
        flat = " ".join(text.split())
        self.assertIn("once after the interview rather than repeating it", flat)
        self.assertIn("never runs unattended", flat)

    def test_interview_skill_guards_unattended_and_folds_cited_answers(self):
        skill = ROOT / "skills/factory-interview/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("only from the human-invoked `/factory:init` flow", text)
        self.assertIn("(source: intake interview, <YYYY-MM-DD>)", text)
        self.assertIn("## Resolved", text)
        self.assertIn("park the rest", text)
        self.assertIn('never mark "Persona validation" resolved', text)
        self.assertIn(
            "A human reviews the seeded brain before the first council run "
            "treats it as ground truth", text)
        self.assertIn("journeys/inventory.md", text)

    def test_spec_and_design_reason_against_persona(self):
        self.assertIn("personas.md", (ROOT / "skills/factory-spec/SKILL.md").read_text())
        self.assertIn("personas.md", (ROOT / "skills/factory-design/SKILL.md").read_text())

    def test_focus_group_reference_has_templates_and_caps(self):
        ref = ROOT / "skills/factory-research/references/focus-group.md"
        self.assertTrue(ref.exists(), str(ref))
        text = ref.read_text()
        # four templates present (AC 5)
        for heading in ("## Roster template", "## Interview guide template",
                        "## Transcript template", "## Findings template",
                        "## Spend log template"):
            self.assertIn(heading, text, heading)
        # numeric caps stated (AC 5)
        self.assertIn("4–6 personas", text)
        self.assertIn("≤500 words", text)
        self.assertIn("≤10 questions", text)
        self.assertIn("≤5 bullets per persona", text)
        self.assertIn("exactly one `## Synthesis` paragraph", text)
        self.assertIn("one `## Next action` line", text)
        # roster fields and classes (AC 6)
        for field in ("Label", "Class", "Relationship",
                      "Can credibly inform", "Cannot credibly inform"):
            self.assertIn(field, text, field)
        self.assertIn("sme | customer | buyer | decision-maker | influencer",
                      text)
        self.assertIn("at least two distinct classes", text)
        # banners (AC 7)
        self.assertIn(
            "This transcript is an AI-roleplayed simulation, not user "
            "evidence.", text)
        self.assertIn("docs/factory/brain/constraints.md", text)
        # spend contract (AC 10)
        for field in ("run date", "trigger", "persona count",
                      "subagent count", "timestamps",
                      "UNMEASURED"):
            self.assertIn(field, text, field)

    def test_focus_group_guide_template_is_human_usable(self):
        text = (ROOT /
                "skills/factory-research/references/focus-group.md").read_text()
        self.assertIn("human-usable as-is", text)
        self.assertIn("no AI, roleplay, or meta instructions", text)

    def test_research_skill_focus_group_section(self):
        text = (ROOT / "skills/factory-research/SKILL.md").read_text()
        # section exists between §3 and §4 (AC 1)
        i3 = text.index("## 3. Council research mode")
        i3b = text.index("## 3b. Focus group (opt-in)")
        i4 = text.index("## 4. Seed the surfaces")
        self.assertTrue(i3 < i3b < i4, "3b must sit between 3 and 4")
        section = text[i3b:i4]
        # run root, artifact set, citation class (AC 1)
        self.assertIn(".factory/runs/research/focus-group/", section)
        for artifact in ("roster.md", "guides/", "transcripts/",
                         "findings.md", "spend.md"):
            self.assertIn(artifact, section, artifact)
        self.assertIn("(simulated: focus-group run", section)
        # trigger rule (AC 2)
        self.assertIn("--focus-group", text)
        self.assertIn("--no-focus-group", text)
        self.assertIn("never runs on the default `web` path", text)
        # hard gate untouched (AC 3)
        self.assertIn(
            "A human reviews the seeded brain before the first council run "
            "treats it as ground truth", text)
        # firewall rules (AC 4)
        self.assertIn("never fact-grade `(source:)`", section)
        self.assertIn("open-questions.md", section)
        self.assertIn("Persona validation", section)
        # interview mechanics (AC 9)
        self.assertIn("one subagent per persona", section)
        self.assertIn("one interview round", section)
        self.assertIn("sequential", section)
        self.assertIn("no cross-persona debate", section)
        # autopilot rule (AC 11)
        self.assertIn("autopilot", section.lower())
        self.assertIn("never", section.lower())
        # reference file linked (Task 1 interface)
        self.assertIn("focus-group.md", section)

    def test_research_command_documents_focus_group_flags(self):
        text = (ROOT / "commands/research.md").read_text()
        self.assertIn("--focus-group", text)
        self.assertIn("--no-focus-group", text)
        self.assertIn("factory-research", text)

    def test_designsync_reference_names_tool_family_and_mechanics(self):
        ref = ROOT / "skills/capabilities/references/designsync.md"
        self.assertTrue(ref.exists(), str(ref))
        text = ref.read_text()
        # tool family + probe (AC 4)
        self.assertIn("mcp__claude-design__", text)
        for tool in ("get_project", "list_files", "read_file",
                     "write_files", "render_preview"):
            self.assertIn(f"mcp__claude-design__{tool}", text, tool)
        self.assertIn("presence of any tool in the family", text)
        # built-in variant satisfies the same probe; writes are plan-locked
        self.assertIn("Built-in variant.", text)
        self.assertIn("`finalize_plan`", text)
        self.assertIn("the built-in `DesignSync` tool counts", text)
        # canonical-mirror rule; interactive-only survives (AC 5)
        self.assertIn("never a second source of truth", text)
        self.assertIn("items/<id>/design/", text)
        self.assertIn("## Interactive-only", text)
        self.assertIn(
            "the degraded path is the tested contract, not an error state",
            text)
        # pull + firewall mirror mechanics (AC 6)
        self.assertIn("items/<id>/design/claude-design-pull.md", text)
        self.assertIn("bid targeting `brain/design-system.md`", text)
        self.assertIn("council-judgement", text)
        self.assertIn("accepted judgement", text)
        self.assertIn("never edits `design-system.md` directly", text)
        # single-writer rule (AC 7)
        self.assertIn("factory choice", text)
        self.assertIn("design.record_choice", text)
        self.assertIn("never write `design/choice.md`", text)
        # spend convention (AC 9)
        self.assertIn("factory log", text)
        self.assertIn('"provenance":"proxy"', text)
        self.assertIn("no `tokens` key", text)
        self.assertIn("Never estimate", text)
        # linking = reuse of designsync_project, no new surface (AC 10)
        self.assertIn("designsync_project", text)
        self.assertIn("no new key, no new command, and no schema diff",
                      text)
        self.assertIn("open-questions.md", text)

    def test_designsync_capability_row_names_tool_family(self):
        text = (ROOT / "skills/capabilities/SKILL.md").read_text()
        self.assertIn(
            "| DesignSync | any `mcp__claude-design__*` tool present "
            "in tool list, or the built-in `DesignSync` tool |", text)
        self.assertIn("references/designsync.md", text)
        self.assertIn("Never let a missing optional tool fail a stage",
                      text)

    def test_designsync_surfaces_never_say_single_source_of_truth(self):
        for rel in ("skills/capabilities/SKILL.md",
                    "skills/capabilities/references/designsync.md",
                    "skills/factory-design/SKILL.md",
                    "skills/factory-ship/SKILL.md"):
            text = (ROOT / rel).read_text().lower()
            self.assertNotIn("single source of truth", text, rel)

    def test_factory_design_designsync_pull_and_push_hooks(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        # concrete pull + firewall mirror (AC 6)
        self.assertIn("mcp__claude-design__list_files", text)
        self.assertIn("mcp__claude-design__read_file", text)
        self.assertIn("items/<id>/design/claude-design-pull.md", text)
        self.assertIn("council-judgement", text)
        self.assertIn("never edits `design-system.md` directly", text)
        # push points (AC 8)
        self.assertIn("mcp__claude-design__write_files", text)
        self.assertIn("chosen-direction note", text)
        self.assertIn("never blocks `factory advance ITEM plan`", text)
        # spend convention (AC 9)
        self.assertIn('"provenance":"proxy"', text)
        self.assertIn("no `tokens` key", text)
        # degraded contract survives verbatim (AC 2)
        self.assertIn("never block or fail when it's absent", text)
        self.assertIn("the design-system.md fallback is the contract",
                      text)
        self.assertIn("This skill never writes `design/choice.md`", text)

    def test_factory_ship_claude_design_push_is_non_blocking(self):
        text = (ROOT / "skills/factory-ship/SKILL.md").read_text()
        self.assertIn("mcp__claude-design__", text)
        self.assertIn("mcp__claude-design__write_files", text)
        self.assertIn("never grounds for `ship.failed`", text)
        self.assertIn("never delays `factory advance ITEM done`", text)
        self.assertIn('"provenance":"proxy"', text)
        self.assertIn("Headless ship runs skip it entirely", text)

    def test_designsync_pull_bid_divergence_guard(self):
        ref = (ROOT / "skills/capabilities/references/designsync.md").read_text()
        self.assertIn("file the bid only when the snapshot differs", ref)
        self.assertIn("tokens unchanged", ref)
        skill = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn("only when the snapshot differs", skill)

    def test_design_packet_discloses_token_provenance(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn("token source", text)
        self.assertIn("mirror bid", text)
        self.assertIn("rejected", text)

    def test_designsync_mirror_supersedes_fallback_tokens(self):
        ref = (ROOT / "skills/capabilities/references/designsync.md").read_text()
        self.assertIn("replaces", ref)
        self.assertIn("fallback tokens", ref)

    def test_designsync_journeys_section(self):
        ref = (ROOT / "skills/capabilities/references/designsync.md").read_text()
        self.assertIn("## Journeys", ref)
        self.assertIn("factory-journeys.html", ref)
        self.assertIn("(source: claude-design", ref)
        self.assertIn("never contracts/", ref)
        self.assertIn("never a second source of truth", ref)

    def test_intake_greenfield_frame_pull(self):
        text = (ROOT / "skills/factory-intake/SKILL.md").read_text()
        self.assertIn("designsync_project", text)
        self.assertIn("(source: claude-design", text)
        self.assertIn("factory-journeys.html", text)

    def test_factory_design_entry_check_three_way_branch(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn("Absent or empty", text)
        self.assertIn("- option: none", text)
        self.assertIn("design/feedback/round-<N+1>.md", text)
        self.assertIn("then delete `design/choice.md`", text)
        self.assertIn(
            "every `items/<id>/design/feedback/round-*.md` file as required "
            "input", text)
        self.assertIn("the cap: 2 regeneration rounds", text)
        self.assertIn("human-authored steer", text)
        self.assertIn("amend `spec.md`'s UI acceptance criteria", text)

    def test_factory_design_options_page_decision_block(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn('<button data-pick="none">', text)
        self.assertIn('exactly one "None of these" block', text)
        self.assertIn('maxlength="500"', text)
        self.assertIn("before the first pick button", text)
        self.assertIn("changed any time before the item resumes", text)
        self.assertIn("'\\''", text)
        self.assertIn('<output id="factory-choice" data-final="true">', text)
        self.assertIn("FACTORY_CHOICE", text)
        self.assertIn("<noscript>", text)
        self.assertIn("viewport", text)
        self.assertIn("never writes files and never makes a request", text)

    def test_factory_design_packet_notes_convention_and_none_routing(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn('factory choice <id> <option> [--notes "..."]', text)
        self.assertIn("[opt] text | …", text)
        self.assertIn("back to design regeneration", text)
        self.assertIn("never advances the item toward plan", text)
        self.assertIn("what changed in answer to the round-N commentary", text)

    def test_factory_design_never_authors_a_pick(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn("This skill never writes `design/choice.md`", text)
        self.assertIn("never *authors a pick*", text)
        self.assertIn("move-and-delete", text)

    def test_dispatch_resume_never_routes_on_choice_content(self):
        text = (ROOT / "skills/factory-dispatch/SKILL.md").read_text()
        self.assertIn("regardless of which option `choice.md` records", text)
        self.assertIn(
            "never advances a design item toward `plan` based on "
            "`choice.md` content", text)
        self.assertIn("belongs exclusively to factory-design's entry check",
                      text)

    def test_dispatch_short_circuit_guarded_against_none(self):
        text = (ROOT / "skills/factory-dispatch/SKILL.md").read_text()
        self.assertIn("records an option a–d", text)
        self.assertIn("`- option: none` is not a satisfied artifact", text)
        self.assertIn("take the pause branch below for it instead", text)

    def test_browser_read_capability_row_and_reference(self):
        skill = (ROOT / "skills/capabilities/SKILL.md").read_text()
        self.assertIn(
            "| Browser read-back | a browser-automation tool that can read "
            "page DOM/console is present in the tool list |", skill)
        self.assertIn("references/browser-read.md", skill)
        ref = (ROOT /
               "skills/capabilities/references/browser-read.md").read_text()
        self.assertIn("Session-live only", ref)
        self.assertIn("the *session*, not the page, invokes the engine", ref)
        self.assertIn("never required, never blocks", ref)
        self.assertIn("no server, no daemon", ref)
        self.assertIn(
            "requires a judgement amending the zero-network rule first", ref)

    def test_journeys_templates_exist_and_validate(self):
        inv = ROOT / "templates/docs-factory/journeys/inventory.md"
        graph = ROOT / "templates/docs-factory/journeys/graph.json"
        self.assertTrue(inv.exists())
        self.assertTrue(graph.exists())
        self.assertIn("_Not yet written.", inv.read_text())
        import json as _json
        from scripts.factory.lib.initrepo import load_schema
        from scripts.factory.lib.validate import validate
        data = _json.loads(graph.read_text())
        self.assertEqual(validate(data, load_schema("journey-graph"), "graph"), [])

    def test_intake_journeys_collector_and_license(self):
        text = (ROOT / "skills/factory-intake/SKILL.md").read_text()
        self.assertIn("journeys/inventory.md", text)
        self.assertIn("graph.json", text)
        self.assertIn("(assumption)", text)
        self.assertIn("never contracts/", text)
        self.assertIn("docs/factory/journeys/", text)

    def test_spec_skill_journey_impact_duties(self):
        text = (ROOT / "skills/factory-spec/SKILL.md").read_text()
        self.assertIn("## Journey impact", text)
        self.assertIn("assurance/impact.json", text)
        self.assertIn("factory journeys", text)
        self.assertIn("None — no customer journey affected.", text)
        self.assertIn("status: draft", text)
        self.assertIn("Run & fixtures", text)

    def test_bug_intake_seeds_journey_impact(self):
        text = (ROOT / "skills/factory-bug/SKILL.md").read_text()
        self.assertIn("## Journey impact (seeded at bug intake — carry into spec.md verbatim)", text)
        self.assertIn("immediate transition", text)

    def test_assure_skill_contract_and_discipline(self):
        skill = ROOT / "skills/factory-assure/SKILL.md"
        self.assertTrue(skill.exists())
        text = skill.read_text()
        self.assertRegex(text, FRONTMATTER, str(skill))
        self.assertIn("never the implementer transcript", text)
        self.assertIn("expectations.md", text)
        self.assertIn("run-manifest.json", text)
        self.assertIn("pass | fail | ambiguity | blocker", text)
        self.assertIn("assure.passed", text)
        self.assertIn("assure.rejected", text)
        self.assertIn("never runs `factory waive` or `factory confirm`", text)
        self.assertIn("Browser drive", text)
        self.assertIn("never a silent pass", text)
        self.assertIn("one fresh journey-reviewer subagent per affected journey", text)
        self.assertIn("agents/journey-reviewer.md", text)
        self.assertIn("-assure.md", text)
        self.assertIn("Fresh round", text)
        self.assertIn("journey impact undeclared", text)

    def test_journey_reviewer_agent_discipline(self):
        agent = ROOT / "agents/journey-reviewer.md"
        self.assertTrue(agent.exists())
        text = agent.read_text()
        self.assertRegex(text, FRONTMATTER, str(agent))
        self.assertIn("pass | fail | ambiguity | blocker", text)
        self.assertIn("before acting", text.lower())
        self.assertIn("only under `.factory/items/<id>/assurance/`", text)
        self.assertIn("never edit product code", text.lower())
        self.assertIn("not told this feature is complete", text.lower())
        self.assertIn("expectations.md", text)
        self.assertIn("APPEND it to `assurance/expectations.md` BEFORE acting", text)

    def test_verify_exit_routes_to_assure(self):
        text = (ROOT / "skills/factory-verify/SKILL.md").read_text()
        self.assertIn("factory advance ITEM assure", text)
        self.assertIn("journeys: none", text)

    def test_dispatch_recognizes_assure_pauses(self):
        text = (ROOT / "skills/factory-dispatch/SKILL.md").read_text()
        self.assertIn("assurance/waiver.md", text)
        self.assertIn("assurance/human-confirmation.md", text)

    def test_assure_skill_entry_check_short_circuits(self):
        text = (ROOT / "skills/factory-assure/SKILL.md").read_text()
        self.assertIn("## Entry check", text)
        self.assertIn("waiver.md", text)
        self.assertIn("do not re-walk", text)

    def test_ship_entry_names_assurance(self):
        text = (ROOT / "skills/factory-ship/SKILL.md").read_text()
        self.assertIn("assure.passed", text)
        self.assertIn("journeys: none", text)

    def test_browser_drive_capability_row_and_reference(self):
        skill = (ROOT / "skills/capabilities/SKILL.md").read_text()
        self.assertIn("| Browser drive |", skill)
        self.assertIn("references/browser-drive.md", skill)
        ref = (ROOT / "skills/capabilities/references/browser-drive.md").read_text()
        self.assertIn("navigate, click, type, screenshot, and read console/network", ref)
        self.assertIn("park", ref)
        self.assertIn("silent pass", ref)
        self.assertIn("factory waive", ref)
        self.assertIn("Parking is not failing", ref)

    def test_factory_workers_skill_auth_reason_carve_out(self):
        text = (ROOT / "skills/factory-workers/SKILL.md").read_text()
        self.assertIn("a provision refusal with reason `auth`", text)
        self.assertIn(
            "Unless the result's reason is `auth` (a chatgpt-mode login "
            "refusal): that is a setup fault for the whole pool", text)

    def test_headless_workers_reference_documents_auth_modes(self):
        ref = (ROOT / "skills/capabilities/references/headless-workers.md").read_text()
        self.assertIn('workers.codex.auth', ref)
        self.assertIn('"chatgpt"', ref)
        self.assertIn("refresh token", ref)
        self.assertIn("never writes", ref)
        self.assertIn("plan rate limits", ref)
        self.assertIn("factory work` without provisioning", ref)

    def test_spec_and_escape_push_journey_map(self):
        spec = (ROOT / "skills/factory-spec/SKILL.md").read_text()
        self.assertIn("factory-journeys.html", spec)
        esc = (ROOT / "commands/escape.md").read_text()
        self.assertIn("factory-journeys.html", esc)

    def test_design_gate_journey_annotations(self):
        text = (ROOT / "skills/factory-design/SKILL.md").read_text()
        self.assertIn("impact.json", text)
        self.assertIn("journey node", text)
        self.assertIn("still-draft contract", text)
        self.assertIn("never an approved contract", text)


if __name__ == "__main__":
    unittest.main()
