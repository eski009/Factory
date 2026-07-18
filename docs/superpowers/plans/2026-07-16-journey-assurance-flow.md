# Journey Assurance — Plan 4: Confirmation, Escapes + Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop: dispatch resume for assure pauses, single-writer enforcement for the human verbs, the `/factory:escape` command, autopilot gate-respect, ship-entry correction, and the full docs sweep (README, getting-started, CHANGELOG 0.7.0, version bump).

**Architecture:** One small engine hardening task; the rest is prose wiring + docs. After this plan the whole capability is operable end-to-end and documented.

**Tech Stack:** Python stdlib + Markdown. Tests: stdlib unittest.

**Spec:** `docs/superpowers/specs/2026-07-15-journey-assurance-design.md` (Human confirmation and the escape loop + Edge cases + Files touched).

## Global Constraints

- `factory waive` / `factory confirm` are the ONLY writers of `assure.waived` / `assure.confirmed` — after this plan that is engine-enforced (`factory log` refuses those event names), not just prose.
- Dispatch's resume check stays artifact-based (it reads files, never log.jsonl): assure pauses answer via `assurance/waiver.md` or `assurance/human-confirmation.md`.
- Autopilot never waives, confirms, promotes, or files escapes — escapes are human discoveries.
- The stage line everywhere user-facing becomes `idea → triage → spec → design → plan → implement → review → verify → assure → ship → done`. Historical docs (docs/superpowers/specs+plans, .superpowers/) are NEVER edited in the sweep.
- CHANGELOG gets a dated `[0.7.0]` entry; `plugin.json` bumps 0.6.0 → 0.7.0; the migration note documents: mid-flight items arriving at assure undeclared park; `factory journeys <id> none` (works even while parked at assure) or `factory waive` unblocks.
- `tests/test_plugin_structure.py::test_commands_have_frontmatter` pins the exact command stem list — adding `/factory:escape` means updating that list in the same commit.
- Run the FULL suite before every commit. Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Engine — single-writer enforcement + waiver artifact

**Files:**
- Modify: `scripts/factory/factory.py` (`cmd_log`), `scripts/factory/lib/assure.py` (`record_waiver`)
- Test: `tests/test_cli.py` (or the file holding cmd_log tests — grep first), `tests/test_assure_verbs.py`

**Interfaces:**
- Produces: `factory log ITEM assure.waived|assure.confirmed` refuses with exit 1 and a message naming the real verbs; `record_waiver` also writes `items/<id>/assurance/waiver.md` (reason + ts) so dispatch can artifact-detect an answered pause.

- [ ] **Step 1: Write the failing tests**

In `tests/test_assure_verbs.py`:

```python
    def test_waiver_writes_artifact_file(self):
        make_item(self.repo)
        assure.record_waiver(self.repo, "0001-a", "no browser here")
        path = Path(self.repo) / ".factory" / "items" / "0001-a" / "assurance" / "waiver.md"
        self.assertTrue(path.exists())
        self.assertIn("no browser here", path.read_text(encoding="utf-8"))

    def test_cmd_log_refuses_human_only_events(self):
        from scripts.factory.lib import initrepo
        initrepo.init(self.repo)
        for event in ("assure.waived", "assure.confirmed"):
            with patch("sys.stderr", new_callable=StringIO) as err:
                code = factory.main(["--repo", str(self.repo), "log", "0001-a", event])
            self.assertEqual(code, 1)
            self.assertIn("factory waive", err.getvalue() + " factory confirm")
```

(The second assertion just needs the error text to name the real verb; adapt to taste but keep exit 1. `make_item(self.repo)` must run before the log calls.)

- [ ] **Step 2: Run to verify RED**, then implement:

`factory.py` `cmd_log` — after the JSON parse, before `items.load_item`:

```python
    if args.event in ("assure.waived", "assure.confirmed"):
        print(f"{args.event} is written only by its human verb "
              "(factory waive / factory confirm)", file=sys.stderr)
        return 1
```

`lib/assure.py` `record_waiver` — after `_require_assure_context(meta)`, before the event append:

```python
    path = paths.item_dir(repo, item_id) / "assurance" / "waiver.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Assurance waiver\n\n- ts: {logs.now_stamp()}\n\n{reason.strip()}\n",
        encoding="utf-8")
```

(Return value and event append unchanged.)

- [ ] **Step 3: FULL suite green; commit**

```bash
git add scripts/factory/factory.py scripts/factory/lib/assure.py tests/test_assure_verbs.py
git commit -m "feat(engine): factory log refuses human-only assure events; waiver writes waiver.md

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Dispatch resume for assure pauses + factory-assure entry check + autopilot + ship entry

**Files:**
- Modify: `skills/factory-dispatch/SKILL.md` (step 0 + skill-unavailable short-circuit), `skills/factory-assure/SKILL.md` (entry check), `skills/factory-autopilot/SKILL.md` (§3 gate respect), `skills/factory-ship/SKILL.md` (entry gate line)
- Test: `tests/test_plugin_structure.py`, `tests/test_plugin_coherence.py`

**Interfaces:**
- Produces: dispatch recognizes a second answered-pause type (paused-from `assure` + `assurance/waiver.md` or `assurance/human-confirmation.md` non-empty → resume); factory-assure short-circuits on a recorded waiver/confirmation instead of re-walking; autopilot's never-list grows; ship's entry text matches the real gate.

- [ ] **Step 1: Write the failing pins**

`tests/test_plugin_structure.py`:

```python
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
```

`tests/test_plugin_coherence.py` — extend `test_autopilot_skill_never_answers_its_own_human_gates`-adjacent coverage (the autopilot pin lives in test_plugin_structure — extend THAT test):

```python
        self.assertIn("never waives or confirms assurance", text.lower())
        self.assertIn("never files or promotes escapes", text.lower())
```

(Add those two lines inside the existing `test_autopilot_skill_never_answers_its_own_human_gates`.)

- [ ] **Step 2: Make the prose edits** (read each file for anchors first)

1. **factory-dispatch step 0** — the sentence "today that means items paused from `design` …" becomes an enumeration of the two answered-pause types:

```markdown
   Today that means: items paused from `design` (`meta["paused-from"] == "design"`) whose `.factory/items/<id>/design/choice.md` is now present and non-empty; and items paused from `assure` whose `.factory/items/<id>/assurance/waiver.md` or `.factory/items/<id>/assurance/human-confirmation.md` is now present and non-empty (the human ran `factory waive` or `factory confirm`).
```

   And extend the resume-packet cleanup list with `docs/factory/packets/<id>-assure.md` alongside the design packet name (harmless if absent). Also, in step 3's skill-unavailable short-circuit sentence, after the design-artifact rule, add: `For an assure item the awaited artifact counts as satisfied when assurance/waiver.md or assurance/human-confirmation.md is present and non-empty.`

2. **factory-assure** — insert a new section immediately after `## Contract`:

```markdown
## Entry check

Before dispatching any reviewer, check for an already-answered stage: if
`items/<id>/assurance/waiver.md` exists (a human ran `factory waive`), or
`human-confirmation.md` exists with `assure.confirmed` logged, and the
recorded answer postdates the latest implementation round, do not re-walk —
take the matching Exit branch directly (`factory advance ITEM ship`; the
engine's round-scoped gate is the authority and will refuse a stale answer).
This mirrors factory-design's entry check: the stage never re-asks a
question a human already answered.
```

3. **factory-autopilot §3** — add two bullets in its never-list:

```markdown
- Never waives or confirms assurance: `factory waive` and `factory confirm` are the human's verbs; items parked at assure (blockers, ambiguities, gated confirmation) stay parked with their packets until a real human acts.
- Never files or promotes escapes: escapes are the human's post-assurance discoveries; promotion routes through the human/judgement paths.
```

4. **factory-ship** — the Contract entry line becomes:

```markdown
- **Entry gate:** for journey-affecting items, `assure.passed` (or a recorded human waiver) after the latest implementation round — plus `assure.confirmed` when the repo's config gates include `assure`; for `journeys: none` items, `verify.green`. The engine's `_gate_ship` is the authority.
```

- [ ] **Step 3: FULL suite green; commit**

```bash
git add skills/factory-dispatch/SKILL.md skills/factory-assure/SKILL.md skills/factory-autopilot/SKILL.md skills/factory-ship/SKILL.md tests/test_plugin_structure.py
git commit -m "feat(assure): dispatch resume + entry short-circuit, autopilot never-list, ship entry

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: /factory:escape command

**Files:**
- Create: `commands/escape.md`
- Modify: `tests/test_plugin_structure.py` (`test_commands_have_frontmatter` stem list + new pin)

**Interfaces:**
- Produces: the human-facing escape intake flow wrapping the `factory escape` CLI.

- [ ] **Step 1: Failing pins** — add `"escape"` to the stem list in `test_commands_have_frontmatter` (alphabetical position: after `bug`, before `init`), plus:

```python
    def test_escape_command_wraps_cli_and_links_bugs(self):
        cmd = ROOT / "commands/escape.md"
        self.assertTrue(cmd.exists())
        text = cmd.read_text()
        self.assertRegex(text, FRONTMATTER, str(cmd))
        self.assertIn("factory escape", text)
        self.assertIn("factory promote", text)
        self.assertIn("factory-bug", text)
        self.assertIn("miss", text)
```

- [ ] **Step 2: Create `commands/escape.md`**

```markdown
---
description: File a post-assurance escape - something a human still found after the factory said done ($ARGUMENTS = the finding, in your own words)
---
Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

$ARGUMENTS is the finding. Identify the journey and node from
docs/factory/journeys/graph.json and inventory.md (ask the human one
clarifying question if genuinely ambiguous — they are present). Classify the
miss together: missing-journey, missing-node, missing-oracle,
missing-contract-detail, or review-rule-gap. Then file it:
`factory escape <journey> "<finding>" --miss-type <type> [--item <id>] [--node <N>] [--evidence <path>]...`
and read back the escape id.

If the finding is a functional bug (the product misbehaves, not just
incoheres), also run the factory-bug skill on the same finding and re-file
the escape with `--item <the new bug item id>` so the two records link.

An escape stays open until it is promoted into a durable check — say so.
When the human (or a later council judgement) lands the promotion, close it:
`factory promote <esc-id> --via <jdg-NNNN|test:path|contract:path|oracle:ref|decision:ref>`.
`factory status` nags the open count until then. Never file escapes on the
factory's own behalf — this command is for what a HUMAN found.
```

- [ ] **Step 3: FULL suite green; commit**

```bash
git add commands/escape.md tests/test_plugin_structure.py
git commit -m "feat(escape): /factory:escape command — human discovery intake + promotion loop

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Docs sweep — README, getting-started, CHANGELOG 0.7.0, version bump, stage-line sweep

**Files:**
- Modify: `README.md`, `docs/getting-started.md`, `CHANGELOG.md`, `.claude-plugin/plugin.json`
- Test: none new (suite must stay green; README "Tests:" line updated to the real count)

**Interfaces:**
- Produces: user-facing docs describe the assure stage, the two human verbs, escapes, and migration.

- [ ] **Step 1: Stage-line sweep.** `grep -rn "review → verify → ship" README.md docs/getting-started.md skills/ commands/ templates/` — update every LIVE surface to `… review → verify → assure → ship → done` (do NOT touch docs/superpowers/ history or .superpowers/). Update README's mermaid pipeline (add `verify --> assure` node styled like review/verify, `assure --> ship`; class `assure` as council? No — style `assure` with the human/amber class ONLY IF gated... keep it neutral: add the node unstyled) and the "See it run" block's second `/factory:run` line to include `assure`.

- [ ] **Step 2: README content.** In "The idea in one minute" four-rules list, extend the first rule's examples with journey assurance, or add one sentence to the "Nothing advances until it passes" bullet: `— and before anything ships, a fresh-context reviewer walks the affected customer journey against the running product (screenshots, console, network — not vibes).` In "What makes it different", add one bullet:

```markdown
- **"Done" means a customer got through it.** Between verify and ship, a fresh-context journey reviewer — no memory of the implementation — walks the affected journeys against the running product and files evidence the engine validates. What it can't run parks for you; what you still find becomes an escape that stays open until it's promoted into a permanent check.
```

Update the "Tests:" line count to the current suite size (run the suite, use the real number, keep the `+`).

- [ ] **Step 3: getting-started.** In §3 (pipeline walkthrough): update the stage line and stage→skill list (factory-assure after factory-verify); add a short paragraph after the design-gate one:

```markdown
**The assurance stage.** Between verify and ship, journey-affecting items
get a fresh-context walk of the affected customer journeys against the
running product (browser journeys need a browser-automation tool — absent,
the item parks for you rather than silently passing). Failures route back
to implement; judgement calls park with a packet. Your two verbs:
`factory waive <id> --reason "..."` (override with a recorded reason) and
`factory confirm <id>` (when you've configured `"assure"` in the config
`gates` list, items pause for your confirmation after passing). Anything
you still find after shipping: `/factory:escape` files it, and it stays
open until promoted into a contract, test, oracle, or review rule.
```

- [ ] **Step 4: CHANGELOG `[0.7.0]` + plugin.json bump.** New dated entry in house style (bold feature title + dense paragraph). It MUST cover: the assure stage + journeys declaration + hardened spec-exit gates; round-scoped ship gate over schema-validated evidence; journey model (inventory/graph/contracts, split write regime); spec's three duties + bug seeding; the fresh-context journey-reviewer + Browser drive capability (park-don't-pass); waive/confirm human verbs (engine-enforced single-writer); escapes ledger + /factory:escape + promotion; tier `assure` profiles; **the migration note** — pre-existing items reaching assure undeclared park waiting-human; `factory journeys <id> none` (valid even while parked — the engine falls back to the unfiltered sequence) or `factory waive` unblocks; suite count `434 → <real count> tests` (run the suite for the number). Bump `.claude-plugin/plugin.json` version to `0.7.0`.

- [ ] **Step 5: FULL suite green; commit**

```bash
git add README.md docs/getting-started.md CHANGELOG.md .claude-plugin/plugin.json skills/ commands/ templates/
git commit -m "docs: v0.7.0 — journey assurance (README, getting-started, changelog, version bump)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(`git add skills/ commands/ templates/` only picks up stage-line sweep edits if Step 1 touched any; run `git status --short` first and stage only what you actually changed.)

---

## Plan self-review notes

- Spec coverage: confirmation flow + resume (T2 + Plan-1 engine), escapes intake + promotion (T3 + Plan-1 engine), single-writer enforcement closing the Plan-1 final-review recommendation (T1), docs incl. the corrected migration note (T4).
- Dispatch stays artifact-based — waiver.md exists precisely so step 0 never reads log.jsonl.
- The blocker-park resume path is deliberately manual (`factory advance ITEM assure` after fixing the environment) — the packet's Respond section already tells the human; no silent auto-resume of an unfixed environment.
