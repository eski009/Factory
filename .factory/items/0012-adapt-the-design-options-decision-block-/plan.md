# Surface-adaptive decision block (Option A) — Implementation Plan

> **For agentic workers:** Executed by the factory-implement skill — one fresh subagent per task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the factory-design decision-block template render honestly on both viewing surfaces — one canonical `options.html` that branches on `window.location.protocol`, dropping the inert Record-choice affordance on a hosted Artifact and leading with a reply-to-record path, while the local `file://` page keeps the full clickable flow.

**Architecture:** This is a skill-prose change, not engine code. The factory has no HTML-generator function — the orchestrator authors each `options.html` by following the binding requirements in `skills/factory-design/SKILL.md` §"The decision block". So the deliverable is (1) a new binding requirement in that section, and (2) consistency in the two capability references that describe the same surfaces. Both are guarded by grep-over-skill-prose tests in `tests/test_plugin_coherence.py`, the same style as the existing `test_council_review_seed_consumes_persona_surfaces` — this is what makes the requirement machine-checked rather than reviewer-opinion.

**Tech Stack:** Python 3 stdlib `unittest` (repo test convention); markdown skill files. No third-party deps.

## Global Constraints

- Engine is Python 3 stdlib only; no third-party deps. Tests use `unittest`.
- Single-writer invariant: every design-pick capture path terminates in `factory choice` / `design.record_choice`. This item adds NO new writer and NO engine (`scripts/factory/`) change.
- Zero-network: the options page makes no request; a `window.location.protocol` read is not a network call. No server, daemon, or listener — ever.
- One canonical `options.html`, one runtime branch — never two separately-authored HTML variants.
- Out of scope (item 0005's, do NOT touch here): fixed-bar bottom clearance on phones, none-cost cue, `OPTION_RE` `re.fullmatch`, the `_gate_plan` option check.
- Run tests from the repo root. Full suite: `python3 -m unittest discover -s tests -v`.

---

### Task 1: Encode the surface-adaptive requirement in factory-design's decision block

**Files:**
- Modify: `skills/factory-design/SKILL.md` (insert one binding bullet in §"The decision block", after the Record-choice-finalization bullet at line 57, before the Degradation bullet at line 58)
- Test: `tests/test_plugin_coherence.py` (add one method to `class TestPluginCoherence`)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the phrases `window.location.protocol`, `never two HTML variants`, `reply with your pick`, and `for terminal use` present verbatim in `skills/factory-design/SKILL.md` — Task 2's reference edits align with the same vocabulary.

**Covers acceptance criteria:** 1, 2, 3, 4, 5, 6, 7 (and honors the criterion-8 exclusion by adding no phone-ergonomics changes).

- [x] **Step 1: Write the failing test**

Add this method inside `class TestPluginCoherence` in `tests/test_plugin_coherence.py` (place it directly after `test_council_review_seed_consumes_persona_surfaces`):

```python
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
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_factory_design_decision_block_is_surface_adaptive -v`
Expected: FAIL — `AssertionError: decision block must branch on window.location.protocol` (the phrases are not yet in SKILL.md).

- [x] **Step 3: Implement — add the binding bullet to SKILL.md**

In `skills/factory-design/SKILL.md`, insert the following bullet between the `- **Record-choice finalization …**` bullet (line 57) and the `- **Degradation:** …` bullet (line 58), as a new list item at the same indent:

```markdown
- **Surface-adaptive affordances (Option A, item 0012 — one canonical file, runtime branch):** the page branches on `window.location.protocol` at load; author ONE `options.html`, never two HTML variants. On the local `file:` surface, render the full block above — the sticky command bar with the composed command, Copy, and the Record-choice control — unchanged. On a hosted surface (an Artifact opened over `http`/`https`, where no in-session browser reads the page and no terminal is present), the Record-choice control is **not rendered** — it is the one affordance that is genuinely inert there — and instead a mode banner leads with "reply with your pick and I'll record it" (the ratified reply-in-session capture path), each option carries a copyable "reply: pick `<opt>`" chip, and the composed `factory choice` command folds into a demoted "for terminal use" disclosure rather than being removed. Every other element — the options, per-option commentary, `<meta viewport>`, and the `<noscript>` line — renders identically on both surfaces. The `file:` surface keeps `<output id="factory-choice">`, the `FACTORY_CHOICE` console line, and the `<noscript>` fallback fully intact, so browser read-back (`references/browser-read.md`, which reads only the local `file://` DOM/console) is unaffected. A `window.location.protocol` read is not a network request; zero-network holds on both surfaces. Worked reference illustrating the branch: `.factory/items/0012-adapt-the-design-options-decision-block-/design/options.html`.
```

- [x] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_factory_design_decision_block_is_surface_adaptive -v`
Expected: PASS (OK).

- [x] **Step 5: Run the full suite to confirm no regression**

Run: `python3 -m unittest discover -s tests -v`
Expected: OK — all tests pass (the added test included; nothing else affected since no engine code changed).

- [x] **Step 6: Commit**

```bash
git add skills/factory-design/SKILL.md tests/test_plugin_coherence.py
git commit -m "feat(0012): surface-adaptive decision block in factory-design"
```

---

### Task 2: Align the capability references with the surface-adaptive block

**Files:**
- Modify: `skills/capabilities/references/artifact-hosting.md` (the "Design options" section)
- Modify: `skills/capabilities/references/browser-read.md` (the "Session-live only" / degradation note — reinforce that read-back is `file://`-only, which the surface branch relies on)
- Test: `tests/test_plugin_coherence.py` (add one method to `class TestPluginCoherence`)

**Interfaces:**
- Consumes: the vocabulary produced by Task 1 (`reply with your pick`).
- Produces: nothing later tasks depend on.

**Covers acceptance criteria:** 9.

- [x] **Step 1: Write the failing test**

Add this method inside `class TestPluginCoherence` in `tests/test_plugin_coherence.py` (directly after the Task 1 method):

```python
    def test_artifact_hosting_reference_describes_hosted_affordance(self):
        # item 0012: the artifact-hosting reference must state that the hosted
        # surface drops the inert Record-choice control and leads with the
        # reply-to-record affordance, matching factory-design's requirement.
        text = read(ROOT / "skills/capabilities/references/artifact-hosting.md")
        self.assertIn("reply with your pick", text.lower(),
                      "artifact-hosting must describe the hosted reply-to-record affordance")
        self.assertIn("record-choice", text.lower(),
                      "artifact-hosting must state Record-choice is dropped on the hosted surface")
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_artifact_hosting_reference_describes_hosted_affordance -v`
Expected: FAIL — `AssertionError: artifact-hosting must describe the hosted reply-to-record affordance`.

- [x] **Step 3: Implement — add a consistency paragraph to artifact-hosting.md**

In `skills/capabilities/references/artifact-hosting.md`, under the `## Design options` heading, append this paragraph immediately after the "Publishing mechanics" subsection (i.e. at the end of the Design options section, before `## Status dashboard`):

```markdown
### Hosted surface is view-only for the pick

An Artifact is sandboxed and view-only: nothing in-session reads its console and no terminal runs its composed command, so the decision block's Record-choice control is genuinely inert there. Per factory-design's surface-adaptive requirement, the page branches on `window.location.protocol` and, on the hosted surface, **drops the Record-choice control** and leads with "reply with your pick and I'll record it" (the reply-in-session capture path, which the orchestrator relays to `factory choice`). The local `file://` page keeps the full clickable flow. This is one canonical page with a runtime branch — never a second authored HTML variant.
```

- [x] **Step 4: Reinforce the file://-only read-back note in browser-read.md**

In `skills/capabilities/references/browser-read.md`, in the `## Session-live only` section, append this sentence to the end of that paragraph:

```markdown
Browser read-back therefore targets the local `file://` page only; the hosted Artifact drops the Record-choice control entirely (factory-design's surface-adaptive requirement), so there is no inert read-back affordance to mislead a phone viewer — they use the reply-in-session path instead.
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_plugin_coherence.TestPluginCoherence.test_artifact_hosting_reference_describes_hosted_affordance -v`
Expected: PASS (OK).

- [x] **Step 6: Run the full suite to confirm no regression**

Run: `python3 -m unittest discover -s tests -v`
Expected: OK — all tests pass, including both methods added in Tasks 1 and 2.

- [x] **Step 7: Commit**

```bash
git add skills/capabilities/references/artifact-hosting.md skills/capabilities/references/browser-read.md tests/test_plugin_coherence.py
git commit -m "feat(0012): align capability references with surface-adaptive block"
```
