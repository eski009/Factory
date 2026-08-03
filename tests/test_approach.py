"""Item 0015: the redesign loop - approach.rejected edges, caps,
spec-exit gate, answer verb, and packet surfaces.

Guard-test discipline (bid-0076/0082): every fixture that exercises a
cap or a gate reaches its state through machine.advance() - the
production path - never by writing a stage into item.md with
items.save_item. Render-only fixtures (packet/cost aggregation) seed
log events directly and say so in a comment: they test aggregation of
log shape, not gate admission.
"""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import (
    approach, breaker, cost, initrepo, items, logs, machine, packet, paths)

ITEM = "0001-thing"
GIT_ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


class ApproachTest(unittest.TestCase):
    """Base harness: a backend item driven only by machine.advance()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        initrepo.init(self.repo)
        os.environ["FACTORY_NOW"] = "2026-07-03T12:00:00Z"
        self._branched = False

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def reset(self):
        """Fresh repo mid-test, for subTest parameterization."""
        self.tearDown()
        self.setUp()

    def art(self, rel, text="content\n"):
        p = paths.item_dir(self.repo, ITEM) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def make_item(self, kind="backend"):
        now = logs.now_stamp()
        items.save_item(self.repo, {
            "id": ITEM, "title": "Thing", "stage": "idea", "kind": kind,
            "created": now, "updated": now}, "# Thing\n")

    def _branch(self):
        if self._branched:
            return
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "x"],
                       cwd=self.repo, check=True,
                       env=dict(os.environ, **GIT_ENV))
        subprocess.run(["git", "branch", f"factory/{ITEM}"],
                       cwd=self.repo, check=True)
        self._branched = True

    def _prep(self, to):
        """Write exactly what each gate requires, the way the stage
        skills write it, before advancing to `to`."""
        if to == "spec":
            self.art("triage.md")
            items.set_priority(self.repo, ITEM, 1)
        elif to == "plan":
            self.art("spec.md", "# Spec\n\n## Journey impact\nJ-001.\n")
            meta, _ = items.load_item(self.repo, ITEM)
            if "journeys" not in meta:
                items.set_journeys(self.repo, ITEM, "J-001")
            # On a redesign round factory-spec logs the freshness token
            # after rewriting spec.md (item 0015 SS4).
            if machine._approach_edges(
                    logs.read_events(self.repo, ITEM))[0]:
                logs.append_event(self.repo, ITEM, "spec.revised")
        elif to == "implement":
            self.art("plan.md", "- [ ] task\n")
        elif to == "review":
            self._branch()
            logs.append_event(self.repo, ITEM, "implement.completed")
        elif to == "verify":
            self.art("reviews/synthesis.md")
            logs.append_event(self.repo, ITEM, "review.approved")
        elif to == "assure":
            logs.append_event(self.repo, ITEM, "verify.green")

    def walk_to(self, target):
        """Advance ITEM from its current stage to `target`, production
        path only."""
        seq = machine.stage_sequence("backend")
        meta, _ = items.load_item(self.repo, ITEM)
        idx = seq.index(meta["stage"])
        for stage in seq[idx + 1:seq.index(target) + 1]:
            self._prep(stage)
            machine.advance(self.repo, ITEM, stage)

    def forbid(self, frm, entry=1):
        """Append one dated graveyard entry, the way a rejecting stage
        writes it (append-only, gap G4/G5)."""
        p = paths.item_dir(self.repo, ITEM) / "approaches" / "forbidden.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"## 2026-07-03T12:00:00Z - rejected at {frm} "
                    f"(entry {entry})\n\nTried approach {entry}; the "
                    "evidence shows it cannot converge. Evidence: "
                    "reviews/synthesis.md\n\n")

    def redesign(self, frm="review", entry=1):
        """Walk to `frm`, write the graveyard, take the edge."""
        self.walk_to(frm)
        self.forbid(frm, entry)
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: cannot converge")


class TestApproachEdge(ApproachTest):
    """AC1/AC3/AC10/AC15: the edge, its firing set, its artifact gate,
    its lifetime cap."""

    def test_constants_declared_once_in_machine(self):
        self.assertEqual(machine.APPROACH_FROM,
                         frozenset({"review", "verify", "assure"}))
        self.assertEqual(machine.APPROACH_TO, "spec")
        self.assertEqual(machine.MAX_APPROACH_REJECTIONS, 1)
        # aliased, not re-declared (import graph: cost imports machine)
        self.assertIs(cost.APPROACH_FROM, machine.APPROACH_FROM)
        self.assertIs(cost.APPROACH_TO, machine.APPROACH_TO)

    def test_edge_from_each_firing_stage(self):
        # AC1/AC15: parameterized over the set - a membership change is
        # a one-line change in machine.py plus nothing here.
        for frm in sorted(machine.APPROACH_FROM):
            with self.subTest(frm=frm):
                self.reset()
                self.make_item()
                self.redesign(frm=frm)
                meta, _ = items.load_item(self.repo, ITEM)
                self.assertEqual(meta["stage"], "spec")
                last = logs.read_events(self.repo, ITEM)[-1]
                self.assertEqual(last["event"], "stage.advance")
                self.assertEqual(last["data"]["from"], frm)
                self.assertEqual(last["data"]["to"], "spec")

    def test_edge_refused_without_forbidden_artifact(self):
        # AC10: missing, then empty - both refused naming the path.
        self.make_item()
        self.walk_to("review")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: x")
        self.assertIn("approaches/forbidden.md", str(ctx.exception))
        self.art("approaches/forbidden.md", "   \n")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: x")
        self.assertIn("approaches/forbidden.md", str(ctx.exception))
        # still at review: the refusal changed nothing
        self.assertEqual(items.load_item(self.repo, ITEM)[0]["stage"],
                         "review")

    def test_cap_refusal_names_the_answer_verb(self):
        # AC1: at MAX_APPROACH_REJECTIONS engine-counted edges with no
        # covering answer, exit path is a GateError naming the verb.
        self.make_item()
        self.redesign(frm="review", entry=1)
        self.walk_to("review")
        self.forbid("review", entry=2)
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: y")
        msg = str(ctx.exception)
        self.assertIn("approach cap: 1 redesign(s) used (cap 1)", msg)
        self.assertIn(f"factory approach-answer {ITEM}", msg)
        self.assertIn("<continue|narrow|defer>", msg)

    def test_forward_and_resume_entries_never_count(self):
        # AC3: triage->spec and waiting-human->spec are outside the
        # firing set - resumes never inflate the count (cost.py:25
        # waiting-human exclusion, mirrored).
        self.make_item()
        self.walk_to("spec")
        machine.advance(self.repo, ITEM, "waiting-human", reason="hold")
        machine.advance(self.repo, ITEM, "spec")  # resume
        events = logs.read_events(self.repo, ITEM)
        self.assertEqual(machine._approach_edges(events)[0], 0)
        # and a real redesign afterwards counts exactly one
        self.redesign(frm="review")
        events = logs.read_events(self.repo, ITEM)
        self.assertEqual(machine._approach_edges(events)[0], 1)

    def test_outside_firing_set_to_spec_stays_illegal(self):
        self.make_item()
        self.walk_to("plan")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec")
        self.assertIn("illegal transition", str(ctx.exception))

    def test_cap_counts_engine_edges_only(self):
        # AC2, the parameterized invariance: (a) edges only and
        # (b) edges + skill-logged noise events agree; (c) noise events
        # with no edges count zero and the edge is admitted.
        for frm in sorted(machine.APPROACH_FROM):
            with self.subTest(frm=frm):
                # (a) one engine edge
                self.reset()
                self.make_item()
                self.redesign(frm=frm)
                a = machine._approach_edges(
                    logs.read_events(self.repo, ITEM))[0]
                # (b) same walk plus skill-logged event noise
                for noise in ("approach.rejected", "review.rejected",
                              "assure.rejected"):
                    logs.append_event(self.repo, ITEM, noise)
                b = machine._approach_edges(
                    logs.read_events(self.repo, ITEM))[0]
                self.assertEqual(a, 1)
                self.assertEqual(a, b)
                # (c) events only, no edges: count zero, edge admitted
                self.reset()
                self.make_item()
                self.walk_to(frm)
                for noise in ("approach.rejected", "review.rejected",
                              "assure.rejected"):
                    logs.append_event(self.repo, ITEM, noise)
                self.assertEqual(machine._approach_edges(
                    logs.read_events(self.repo, ITEM))[0], 0)
                self.forbid(frm)
                meta, _ = machine.advance(self.repo, ITEM, "spec",
                                          reason="approach.rejected: z")
                self.assertEqual(meta["stage"], "spec")

    def test_ui_redesign_passes_back_through_design(self):
        # item 0015 SS1: the redesign path for ui/mixed re-enters design;
        # the round-1 design/choice.md satisfies _gate_plan unchanged
        # (fresh choice is a named non-goal, gap G7 residual).
        self.make_item(kind="ui")
        machine.advance(self.repo, ITEM, "triage")
        self._prep("spec")
        machine.advance(self.repo, ITEM, "spec")
        self.art("spec.md", "# Spec\n\n## Journey impact\nJ-001.\n")
        items.set_journeys(self.repo, ITEM, "J-001")
        machine.advance(self.repo, ITEM, "design")
        self.art("design/choice.md", "- option: b\n")
        self._prep("plan")  # spec.md exists; logs nothing (no edges yet)
        machine.advance(self.repo, ITEM, "plan")
        self._prep("implement")
        machine.advance(self.repo, ITEM, "implement")
        self._prep("review")
        machine.advance(self.repo, ITEM, "review")
        self.forbid("review")
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: wrong shape")
        logs.append_event(self.repo, ITEM, "spec.revised")
        meta, _ = machine.advance(self.repo, ITEM, "design")
        self.assertEqual(meta["stage"], "design")
        meta, _ = machine.advance(self.repo, ITEM, "plan")
        self.assertEqual(meta["stage"], "plan")


class TestApproachAnswer(ApproachTest):
    """AC6/AC16/AC17/AC18: the five-part pause contract's artifact side."""

    def test_record_below_cap_refused(self):
        self.make_item()
        self.walk_to("review")
        with self.assertRaises(machine.GateError) as ctx:
            approach.record_answer(self.repo, ITEM, "continue")
        self.assertIn("nothing to answer", str(ctx.exception))

    def test_out_of_enum_refused(self):
        self.make_item()
        self.redesign()
        with self.assertRaises(machine.GateError) as ctx:
            approach.record_answer(self.repo, ITEM, "later")
        self.assertIn("must be one of", str(ctx.exception))

    def test_record_writes_artifact_and_logs_event(self):
        self.make_item()
        self.redesign()
        path = approach.record_answer(self.repo, ITEM, "continue",
                                      notes="one more try")
        text = path.read_text(encoding="utf-8")
        self.assertIn("- answer: continue", text)
        self.assertIn("- redesigns: 1", text)
        self.assertIn("- ts: 2026-07-03T12:00:00Z", text)
        self.assertIn("one more try", text)
        last = logs.read_events(self.repo, ITEM)[-1]
        self.assertEqual(last["event"], "approach.answered")
        self.assertEqual(last["data"], {"answer": "continue",
                                        "redesigns": 1})

    def test_watermark_admits_exactly_one_more_edge(self):
        # AC18: an answer at redesigns 1 admits the second edge and does
        # not admit a third; the stale refusal names recorded vs now.
        self.make_item()
        self.redesign(frm="review", entry=1)
        approach.record_answer(self.repo, ITEM, "continue")
        self.walk_to("review")
        self.forbid("review", entry=2)
        meta, _ = machine.advance(self.repo, ITEM, "spec",
                                  reason="approach.rejected: second try")
        self.assertEqual(meta["stage"], "spec")  # admitted exactly once
        self.walk_to("review")
        self.forbid("review", entry=3)
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: third try")
        msg = str(ctx.exception)
        self.assertIn("stale", msg)
        self.assertIn("recorded at 1", msg)
        self.assertIn("now 2", msg)

    def test_malformed_artifacts_get_distinct_refusals(self):
        # AC18: malformed option vs missing watermark line - distinct
        # messages, both different from the stale message.
        self.make_item()
        self.redesign()
        self.walk_to("review")
        self.forbid("review", entry=2)
        p = approach.answer_path(self.repo, ITEM)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("- answer: maybe\n- redesigns: 1\n", encoding="utf-8")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: x")
        self.assertIn("recorded option 'maybe'", str(ctx.exception))
        p.write_text("- answer: continue\n", encoding="utf-8")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: x")
        self.assertIn("no '- redesigns: N' line", str(ctx.exception))

    def test_absent_answer_line_named_as_a_missing_field(self):
        # AC18 (assure round 1, J-003/S6 arm A): an answer.md with no
        # '- answer:' line at all is a MISSING FIELD, named the way the
        # sibling watermark line is - never by interpolating the parsed
        # value, which leaked a Python None repr to the operator. The
        # out-of-enum arm still names the recorded value, and the two
        # stay pairwise distinct.
        #
        # bid-0127: the field is named with the house `<option>` metavar
        # (packet.py's `factory choice <id> <option>`), not a second copy
        # of the enum the retry clause already spells out ~20 chars
        # later. `<option>` and not a bare `- answer:` - a literal paste
        # of `- answer:` fails the value regex and re-fires THIS arm with
        # a byte-identical message, an unbreaking loop; `<option>` moves
        # the operator on to a distinct arm.
        self.make_item()
        self.redesign()
        self.walk_to("review")
        self.forbid("review", entry=2)
        p = approach.answer_path(self.repo, ITEM)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("I said yes go ahead\n", encoding="utf-8")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: x")
        missing = str(ctx.exception)
        self.assertIn("no '- answer: <option>' line", missing)
        self.assertNotIn("None", missing)
        # The enum is spelled out exactly once on the line - in the retry
        # clause - never twice.
        self.assertEqual(1, missing.count("continue|narrow|defer"))
        p.write_text("- answer: yolo\n- redesigns: 1\n", encoding="utf-8")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: x")
        enum = str(ctx.exception)
        self.assertIn("recorded option 'yolo'", enum)
        p.write_text("- answer: continue\n", encoding="utf-8")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "spec",
                            reason="approach.rejected: x")
        watermark = str(ctx.exception)
        self.assertIn("no '- redesigns: N' line", watermark)
        self.assertEqual(3, len({missing, enum, watermark}))

    def test_narrow_and_defer_delete_packet_at_record_time(self):
        # bid-0078/AC17: keyed on answer-record time, never on "no
        # longer waiting-human". continue keeps the packet.
        self.make_item()
        self.redesign()
        pdir = paths.docs_root(self.repo) / "packets"
        pdir.mkdir(parents=True, exist_ok=True)
        for answer, expect_gone in (("continue", False), ("narrow", True),
                                    ("defer", True)):
            with self.subTest(answer=answer):
                md = pdir / f"{ITEM}.md"
                html = pdir / f"{ITEM}.html"
                md.write_text("packet\n", encoding="utf-8")
                html.write_text("packet\n", encoding="utf-8")
                approach.record_answer(self.repo, ITEM, answer)
                self.assertEqual(not md.exists(), expect_gone)
                self.assertEqual(not html.exists(), expect_gone)

    def test_no_engine_transition_writes_any_answer(self):
        # AC6/bid-0098: a full production-path redesign fixture ends
        # with BOTH answer artifacts absent.
        self.make_item()
        self.redesign()
        self.assertFalse(approach.answer_path(self.repo, ITEM).exists())
        self.assertFalse(breaker.answer_path(self.repo, ITEM).exists())


class TestApproachCli(ApproachTest):
    """AC16 part 1 + AC6: the verb and the log-verb refusals."""

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = factory.main(["--repo", str(self.repo), *args])
        return code, out.getvalue(), err.getvalue()

    def test_approach_answer_records_and_prints_path(self):
        self.make_item()
        self.redesign()
        code, out, _ = self.run_cli("approach-answer", ITEM, "continue")
        self.assertEqual(code, 0)
        self.assertIn("approaches/answer.md", out)

    def test_approach_answer_refusal_exits_2(self):
        self.make_item()
        self.walk_to("review")
        code, _, err = self.run_cli("approach-answer", ITEM, "continue")
        self.assertEqual(code, 2)
        self.assertIn("nothing to answer", err)

    def test_factory_log_refuses_single_writer_events(self):
        self.make_item()
        for event in ("approach.answered", "cost.answered"):
            with self.subTest(event=event):
                code, _, err = self.run_cli("log", ITEM, event)
                self.assertEqual(code, 1)
                self.assertIn("written only by its human verb", err)
        self.assertIn(
            "factory approach-answer",
            self.run_cli("log", ITEM, "approach.answered")[2])


class TestVerifyReworkAndRoundScoping(ApproachTest):
    """AC4/AC5/AC11/AC12: the verify edge and the round-scoped counts."""

    def verify_rework(self):
        """One verify -> implement round trip, production path."""
        self.walk_to("verify")
        meta, _ = machine.advance(self.repo, ITEM, "implement",
                                  reason="verify rework: fix the prose")
        return meta

    def test_verify_to_implement_capped_names_redesign_route(self):
        # AC11: mirrors review -> implement in edge shape; the cap
        # refusal names the redesign route, never bare blocked.
        self.assertEqual(machine.MAX_VERIFY_REWORKS, 2)
        self.make_item()
        self.assertEqual(self.verify_rework()["stage"], "implement")
        self.assertEqual(self.verify_rework()["stage"], "implement")
        self.walk_to("verify")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "implement",
                            reason="verify rework: again")
        msg = str(ctx.exception)
        self.assertIn("approaches/forbidden.md", msg)
        self.assertIn(f"factory advance {ITEM} spec", msg)
        self.assertNotIn("move item to blocked", msg)

    def test_verify_cap_round_scoped_to_latest_redesign(self):
        # AC4: the verify cap counts only edges after the latest
        # approach.rejected edge; the approach cap still counts the
        # pre-redesign edge (lifetime).
        self.make_item()
        self.verify_rework()
        self.verify_rework()          # at cap, pre-redesign
        self.redesign(frm="verify")   # walks to verify, takes the edge
        self.walk_to("verify")
        meta, _ = machine.advance(self.repo, ITEM, "implement",
                                  reason="verify rework: fresh round")
        self.assertEqual(meta["stage"], "implement")  # admitted again
        self.assertEqual(machine._approach_edges(
            logs.read_events(self.repo, ITEM))[0], 1)  # still counted

    def test_review_and_assure_caps_round_scoped(self):
        # AC4: substrate unchanged (review.rejected/assure.rejected
        # EVENTS - the machine.py:459,462 defect stays named, not
        # migrated), scoping added: only events after the latest
        # approach.rejected edge count.
        for frm, event in (("review", "review.rejected"),
                           ("assure", "assure.rejected")):
            with self.subTest(frm=frm):
                self.reset()
                self.make_item()
                self.walk_to(frm)
                for _ in range(3):
                    logs.append_event(self.repo, ITEM, event)
                with self.assertRaises(machine.GateError):
                    machine.advance(self.repo, ITEM, "implement")
                # redesign clears the round: over-cap before, admitted after
                self.forbid(frm)
                machine.advance(self.repo, ITEM, "spec",
                                reason="approach.rejected: wrong design")
                self.walk_to(frm)
                logs.append_event(self.repo, ITEM, event)
                meta, _ = machine.advance(self.repo, ITEM, "implement")
                self.assertEqual(meta["stage"], "implement")

    def test_verify_edge_counts_in_breaker_substrate_unchanged(self):
        # AC12: cost.py:26 pre-listed verify, so summarize and the 0016
        # breaker count the new edge with ZERO breaker change.
        self.assertIs(breaker.REWORK_FROM, cost.REWORK_FROM)
        self.assertIn("verify", cost.REWORK_FROM)
        self.make_item()
        self.verify_rework()
        self.assertEqual(
            cost.summarize(self.repo, ITEM)["rework_edges"], 1)
        self.assertEqual(breaker.rework_edges(self.repo, ITEM), 1)


class TestSpecExitGate(ApproachTest):
    """AC7/AC8/AC9/AC10: leaving spec after a redesign requires fresh
    evidence; the gate proves freshness and existence, not
    comprehension."""

    def test_exit_requires_spec_revised_postdating_the_edge(self):
        # AC8: a spec.revised logged BEFORE the edge does not satisfy;
        # one logged after does. Note _prep("plan") logs spec.revised
        # itself, so this test advances by hand.
        self.make_item()
        self.walk_to("review")
        logs.append_event(self.repo, ITEM, "spec.revised")  # stale
        self.forbid("review")
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: x")
        self.art("spec.md", "# Spec v2\n\n## Journey impact\nJ-001.\n")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "plan")
        self.assertIn("spec.revised", str(ctx.exception))
        logs.append_event(self.repo, ITEM, "spec.revised")
        meta, _ = machine.advance(self.repo, ITEM, "plan")
        self.assertEqual(meta["stage"], "plan")

    def test_refusal_names_both_missing_pieces(self):
        # AC8: (a) and (b) both named. The edge required a non-empty
        # graveyard, so simulate a bad cleanup truncating it afterwards.
        self.make_item()
        self.redesign()
        self.art("approaches/forbidden.md", "")  # truncated post-edge
        self.art("spec.md", "# Spec v2\n\n## Journey impact\nJ-001.\n")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "plan")
        msg = str(ctx.exception)
        self.assertIn("approaches/forbidden.md", msg)
        self.assertIn("spec.revised", msg)

    def test_both_unmet_is_one_refusal_naming_both(self):
        # AC8 (assure round 1, J-003/S5): the operator failing BOTH
        # requirements is not drip-fed two refusals across two stage
        # re-entries - the gate evaluates both conditions and names both
        # in ONE message under a single `redesign spec-exit:` prefix.
        # The single-requirement wordings (arms 2 and 3 of the walk) are
        # exactly the two clauses joined here.
        self.make_item()
        self.redesign()
        self.art("approaches/forbidden.md", "")  # truncated post-edge
        self.art("spec.md", "# Spec v2\n\n## Journey impact\nJ-001.\n")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "plan")
        self.assertEqual(
            str(ctx.exception),
            "redesign spec-exit: approaches/forbidden.md missing or "
            "empty; no spec.revised event after the latest "
            "approach.rejected edge (factory-spec logs it after "
            "rewriting spec.md)")

    def test_zero_redesign_items_gate_inert(self):
        # AC8: no approach edge - no spec.revised required, byte-
        # identical behavior (the walk in every other test also proves
        # this transitively).
        self.make_item()
        self.walk_to("plan")
        self.assertEqual(items.load_item(self.repo, ITEM)[0]["stage"],
                         "plan")
        self.assertNotIn("spec.revised",
                         [e["event"] for e in
                          logs.read_events(self.repo, ITEM)])

    def test_honest_residual_stated_in_docstring(self):
        # AC9, verified by inspection-as-test: freshness and existence,
        # not comprehension.
        doc = machine._require_fresh_redesign_spec.__doc__ or ""
        self.assertIn("not comprehension", doc)

    def test_forbidden_is_append_only_across_redesigns(self):
        # AC10: a two-redesign fixture retains entry 1 intact.
        self.make_item()
        self.redesign(frm="review", entry=1)
        approach.record_answer(self.repo, ITEM, "continue")
        self.walk_to("review")
        self.forbid("review", entry=2)
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: y")
        text = approach.forbidden_path(self.repo, ITEM).read_text(
            encoding="utf-8")
        self.assertIn("(entry 1)", text)
        self.assertIn("(entry 2)", text)

    def test_owed_cost_pause_surfaces_post_redesign(self):
        # AC7/bid-0098: with "cost" gated and cumulative rework at the
        # threshold, the post-redesign plan -> implement entry is
        # refused by breaker.precondition naming factory cost-answer -
        # the redesign edge consumed nothing.
        config_path = paths.config_path(self.repo)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["gates"] = ["cost"]
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True)
                               + "\n", encoding="utf-8")
        self.make_item()
        # two rework edges, production path (no review.rejected events,
        # so the review cap never trips)
        self.walk_to("review")
        machine.advance(self.repo, ITEM, "implement")
        self.walk_to("review")
        machine.advance(self.repo, ITEM, "implement")
        # redesign from review
        self.walk_to("review")
        self.forbid("review")
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: x")
        self.art("spec.md", "# Spec v2\n\n## Journey impact\nJ-001.\n")
        logs.append_event(self.repo, ITEM, "spec.revised")
        machine.advance(self.repo, ITEM, "plan")
        self.art("plan.md", "- [ ] task v2\n")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "implement")
        self.assertIn("factory cost-answer", str(ctx.exception))
        # a stale pre-redesign answer does not admit it either
        breaker_path = breaker.answer_path(self.repo, ITEM)
        breaker_path.parent.mkdir(parents=True, exist_ok=True)
        breaker_path.write_text("- answer: continue\n- rework-edges: 1\n",
                                encoding="utf-8")
        with self.assertRaises(machine.GateError) as ctx:
            machine.advance(self.repo, ITEM, "implement")
        self.assertIn("stale", str(ctx.exception))


class TestCostApproachKeys(ApproachTest):
    """AC5/AC19/AC20: one summarize read feeds every renderer; zero-
    approach items are byte-identical to the pre-change engine."""

    def test_summarize_counts_both_populations(self):
        # Production-path walk: one pre-redesign rework edge, the
        # redesign, one post-redesign rework edge.
        self.make_item()
        self.walk_to("review")
        machine.advance(self.repo, ITEM, "implement")   # rework 1
        self.walk_to("verify")
        machine.advance(self.repo, ITEM, "implement",
                        reason="verify rework: x")      # rework 2
        self.walk_to("verify")
        self.forbid("verify")
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: x")  # redesign
        self.walk_to("review")
        machine.advance(self.repo, ITEM, "implement")   # rework 3
        summary = cost.summarize(self.repo, ITEM)
        self.assertEqual(summary["approach_edges"], 1)
        self.assertEqual(summary["rework_edges_since_last_redesign"], 1)
        # AC5: cumulative, redesigns included, NEVER reset
        self.assertEqual(summary["rework_edges"], 3)
        self.assertEqual(breaker.rework_edges(self.repo, ITEM), 3)

    def test_zero_approach_items_have_no_new_keys(self):
        # AC20: the keys are absent, not zero - so status --json and
        # cost --json bytes cannot change for un-redesigned items.
        self.make_item()
        self.walk_to("implement")
        summary = cost.summarize(self.repo, ITEM)
        self.assertNotIn("approach_edges", summary)
        self.assertNotIn("rework_edges_since_last_redesign", summary)


class TestPacketPopulations(ApproachTest):
    """AC16.5/AC20: dual populations on every redesigned packet; the
    derived waiting line; the respond verb. Render-only fixtures:
    these seed log events directly (aggregation of log shape, not gate
    admission - the bid-0076/0082 rule binds cap/gate guards)."""

    def seed_redesigned(self, stage="waiting-human",
                        reason="approach cap: 1 redesign(s) used (cap 1)",
                        paused_from="review"):
        now = logs.now_stamp()
        meta = {"id": ITEM, "title": "Thing", "stage": stage,
                "kind": "backend", "priority": 1,
                "created": now, "updated": now}
        if stage == "waiting-human":
            meta["paused-from"] = paused_from
            meta["paused-reason"] = reason
        items.save_item(self.repo, meta, "# Thing\n")
        for frm in ("review", "review"):
            logs.append_event(self.repo, ITEM, "stage.advance",
                              {"from": frm, "to": "implement"})
        logs.append_event(self.repo, ITEM, "stage.advance",
                          {"from": "review", "to": "spec"})
        self.forbid("review")

    def test_redesigned_packet_renders_both_labelled_populations(self):
        self.seed_redesigned(stage="spec")
        md = packet.render_packet(self.repo, ITEM)
        html = packet.render_packet_html(self.repo, ITEM)
        pop1 = ("- [proxy] redesigns: 1 of 1 (engine-counted "
                "approach.rejected edges; lifetime, never reset)")
        pop2 = ("- [proxy] rework edges since last redesign: 0 "
                "(cumulative 2 — the breaker counts the cumulative "
                "figure)")
        self.assertIn(pop1, md)
        self.assertIn(pop2, md)
        self.assertIn("redesigns: 1 of 1", html)
        self.assertIn("rework edges since last redesign: 0", html)
        # the cumulative echo agrees numerically with the receipt line
        self.assertIn("2 rework edges", md)

    def test_zero_approach_packet_carries_no_population_lines(self):
        # AC20's other half (full byte-identity is the default-path
        # golden's job - Task 5 step 5).
        now = logs.now_stamp()
        items.save_item(self.repo, {
            "id": ITEM, "title": "Thing", "stage": "implement",
            "kind": "backend", "priority": 1,
            "created": now, "updated": now}, "# Thing\n")
        md = packet.render_packet(self.repo, ITEM)
        self.assertNotIn("redesigns:", md)
        self.assertNotIn("since last redesign", md)

    def test_waiting_line_derived_from_summary_not_free_text(self):
        # A typo in the hand-copied park reason must not reach the
        # operator as a figure (the B3/F4 cost-breaker precedent).
        self.seed_redesigned(
            reason="approach cap: 9999 redesign(s) used (cap 7)")
        md = packet.render_packet(self.repo, ITEM)
        self.assertIn("approach cap: 1 redesign(s) used (cap 1)", md)
        self.assertNotIn("9999", md)

    def test_respond_names_approach_answer_even_when_paused_from_assure(self):
        # The approach branch must be checked BEFORE the paused_from
        # branches: an approach park from assure is not a confirm/waive
        # pause.
        self.seed_redesigned(paused_from="assure")
        meta, _ = items.load_item(self.repo, ITEM)
        lines = packet.respond_action_lines(self.repo, ITEM, meta)
        self.assertEqual(len(lines), 1)
        self.assertIn(f"factory approach-answer {ITEM}", lines[0])
        self.assertNotIn("factory confirm", lines[0])


class TestRedesignDecisionBlock(ApproachTest):
    """AC19: the tradeoff packet. Render-only fixtures seed log events
    directly (see TestPacketPopulations)."""

    def park(self, priority=1, others=0):
        now = logs.now_stamp()
        meta = {"id": ITEM, "title": "Thing", "stage": "waiting-human",
                "kind": "backend", "created": now, "updated": now,
                "paused-from": "review",
                "paused-reason": "approach cap: 1 redesign(s) used (cap 1)"}
        if priority is not None:
            meta["priority"] = priority
        items.save_item(self.repo, meta, "# Thing\n")
        logs.append_event(self.repo, ITEM, "stage.advance",
                          {"from": "review", "to": "implement"})
        logs.append_event(self.repo, ITEM, "stage.advance",
                          {"from": "review", "to": "spec"})
        self.forbid("review")
        for i in range(others):
            oid = f"000{i + 2}-other"
            items.save_item(self.repo, {
                "id": oid, "title": "Other", "stage": "idea",
                "kind": "backend", "priority": 1,
                "created": now, "updated": now}, "# Other\n")

    def test_block_leads_with_populations_and_ends_with_one_action(self):
        self.park(others=1)
        md = packet.render_packet(self.repo, ITEM)
        self.assertIn("## Redesign decision", md)
        block = md.split("## Redesign decision", 1)[1].split("## View", 1)[0]
        lines = [l for l in block.splitlines() if l.strip()]
        self.assertTrue(lines[0].startswith("- [proxy] redesigns: 1 of 1"))
        self.assertTrue(lines[1].startswith(
            "- [proxy] rework edges since last redesign: 0 (cumulative 1"))
        # measured tokens only as a labelled LOWER BOUND or a loud
        # UNMEASURED (this fixture has no spend events -> UNMEASURED)
        self.assertTrue("LOWER BOUND" in block or "UNMEASURED" in block)
        self.assertTrue("[measured]" in block or "[unmeasured]" in block)
        self.assertIn("- backlog: 1 actionable item at priority ≤ 1", block)
        self.assertIn("forbidden approaches (authored text, "
                      "approaches/forbidden.md):", block)
        self.assertIn("rejected at review (entry 1)", block)
        # one consequence line per option
        for option in ("continue —", "narrow —", "defer —"):
            self.assertEqual(block.count(f"- {option}"), 1)
        # exactly one action under ## Respond, naming the verb
        respond = md.split("## Respond", 1)[1]
        actions = [l for l in respond.splitlines()
                   if l.startswith("- `")]
        self.assertEqual(len(actions), 1)
        self.assertIn(f"factory approach-answer {ITEM}", actions[0])

    def test_recommended_defer_when_backlog_waiting_never_continue(self):
        self.park(others=1)
        md = packet.render_packet(self.repo, ITEM)
        self.assertIn("Recommended: defer", md)
        self.assertNotIn("Recommended: continue", md)

    def test_recommended_narrow_when_backlog_empty(self):
        self.park(others=0)
        md = packet.render_packet(self.repo, ITEM)
        self.assertIn("Recommended: narrow", md)

    def test_no_priority_renders_comparison_unavailable(self):
        # bid-0066/0077: None is never rendered as 0.
        self.park(priority=None)
        md = packet.render_packet(self.repo, ITEM)
        self.assertIn("comparison unavailable", md)
        self.assertIn("Recommended: set a priority first", md)
        self.assertNotIn("0 actionable items at priority", md)

    def test_html_carries_the_block_and_cost_section_id_is_intact(self):
        self.park()
        html = packet.render_packet_html(self.repo, ITEM)
        self.assertIn('<section id="redesign-decision">', html)
        self.assertIn("Redesign decision", html)
        # the extraction must not perturb the cost-decision contract
        self.assertIn("#cost-decision", html)  # stylesheet selector
        # Deviation coverage (task review finding): the stylesheet
        # selectors are spliced in only when the redesign section
        # renders, and str.replace would no-op silently if the head
        # literals drifted — assert the splice's ACTIVE path.
        self.assertIn("#redesign-decision {", html)
        self.assertIn("#redesign-decision h2", html)


class TestInheritance0025(ApproachTest):
    """AC14 (B1): the redesign path inherits 0025's forward-gate
    re-scoping with ZERO 0015-side mechanism - spec -> plan -> implement
    is a fresh entry into implement under 0025's key. These tests
    require 0025 merged; this item's diff touches no forward-gate
    scoping code (inspection, step 3)."""

    def test_stale_implement_completed_refused_after_redesign(self):
        self.make_item()
        self.redesign(frm="review")   # pre-redesign implement.completed
        self.walk_to("implement")     # fresh entry into implement
        # only PRE-redesign implement.completed exists; 0025 scopes the
        # review entry gate to evidence after this implement entry.
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, ITEM, "review")
        logs.append_event(self.repo, ITEM, "implement.completed")
        meta, _ = machine.advance(self.repo, ITEM, "review")
        self.assertEqual(meta["stage"], "review")

    def test_stale_review_approved_refused_after_redesign(self):
        self.make_item()
        self.walk_to("verify")        # pre-redesign review.approved
        self.forbid("verify")
        machine.advance(self.repo, ITEM, "spec",
                        reason="approach.rejected: x")
        self.walk_to("review")        # logs a fresh implement.completed
        # only PRE-redesign review.approved exists
        with self.assertRaises(machine.GateError):
            machine.advance(self.repo, ITEM, "verify")
        self.art("reviews/synthesis.md")
        logs.append_event(self.repo, ITEM, "review.approved")
        meta, _ = machine.advance(self.repo, ITEM, "verify")
        self.assertEqual(meta["stage"], "verify")
