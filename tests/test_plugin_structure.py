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
                         ["add", "autopilot", "bug", "init", "packet", "research", "roadmap", "run", "status"])
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
        for name in ("workflow-fanout", "artifact-hosting", "scheduling", "designsync", "orchestration-patterns", "model-tiering", "browser-read"):
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
            "in tool list |", text)
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


if __name__ == "__main__":
    unittest.main()
