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
                         ["add", "autopilot", "init", "packet", "research", "roadmap", "run", "status"])
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
        for name in ("workflow-fanout", "artifact-hosting", "scheduling", "designsync", "orchestration-patterns", "model-tiering"):
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


if __name__ == "__main__":
    unittest.main()
