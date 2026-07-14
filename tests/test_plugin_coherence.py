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

    def test_tier_consume_wiring_present(self):
        review = read(ROOT / "skills/factory-review/SKILL.md")
        self.assertIn("Review depth by tier", review)
        council = read(ROOT / "skills/council-review/SKILL.md")
        self.assertIn("light", council)
        research = read(ROOT / "skills/factory-research/SKILL.md")
        self.assertIn("epic", research)


if __name__ == "__main__":
    unittest.main()
