---
name: factory-plan
description: Use when a factory item is at stage plan - produces the TDD implementation plan the implement stage executes
---

First read the capabilities skill's `references/host-adapter.md` and resolve the plugin root for this host. Below, `factory` means `python3 "${FACTORY_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

Run this skill in a fresh context using the capabilities skill's `references/host-adapter.md`; nothing from the invoking session may be treated as input. The item id arrives as the skill argument; everything else is read from disk — `factory status --json`, `.factory/items/<id>/...`, and the brain surfaces this skill names below. Your final message is the report the dispatcher acts on: state the outcome (the stage advanced to, or the failure/pause reason, verbatim where a gate refused), name the key artifact paths written, and keep it to a few lines — never paste file contents into it.

## Contract

- **Entry stage:** `plan`. The gate into `plan` already required `spec.md` non-empty, and (for `ui`/`mixed` items) `design/choice.md` — both are readable inputs here.
- **Artifacts produced:** `items/<id>/plan.md`; when the `feasibility` gate is enabled, also `items/<id>/acceptance.json`; when approach convergence is enabled, also the engine-owned judgement record and, on rejection, a cited entry in `items/<id>/approaches/forbidden.md`.
- **Exit:** feasibility must pass first when enabled, then the Approach convergence protocol selects `factory advance ITEM implement` or the shared rejection edge to `spec`. The implementation gate requires at least one `- [ ]` checkbox in either mode.

## REQUIRED SUB-SKILL: superpowers:writing-plans

Use `superpowers:writing-plans` to build the plan. Read `items/<id>/spec.md` (and `items/<id>/design/choice.md` for `ui`/`mixed` items) as the spec input it expects, then follow its file structure, task right-sizing, and no-placeholders discipline in full. Adapt it to this factory as follows:

- **Location:** save the plan to `items/<id>/plan.md` — not the skill's default `docs/superpowers/plans/` path.
- **Checkbox tasks:** every task step uses `- [ ]` markdown checkbox syntax, exactly as writing-plans already specifies. This isn't optional dressing here — the `implement` gate mechanically greps `plan.md` for `- [ ]` and refuses to advance without one.
- **Test commands:** every task must name the exact files it touches, the exact tests it adds or runs, and the exact test command to run them (e.g. `python3 -m unittest tests.test_foo -v`) — no "run the tests" without the command.
- **Acceptance-criteria references:** every task cites which numbered item in the spec's `## Acceptance criteria` it satisfies, so a reviewer can trace task back to requirement without re-reading the whole spec.
- **One-subagent-sized tasks:** size each task so a single subagent dispatch can complete it standalone (the writing-plans skill's "Task Right-Sizing" section) — this factory always executes plans one task per subagent, never inline batches.
- **Disabled-mode complete code:** when `feasibility` is absent, retain the existing rule: every task carries the exact code, tests, commands, and expected output it needs, so implementation is transcription rather than invention. A task that says "add appropriate handling for X" is not complete.
- **Enabled contract-first branch:** when `feasibility` is present, read the capabilities skill's `references/plan-feasibility.md`. Freeze interfaces, decisions, task boundaries, exact commands, acceptance links, ownership, providers, and integrated gates in a compact plan plus closed sidecar. Do not prescribe every implementation line or add generated code merely to make the plan longer. There is no subjective compactness score or length cap.
- Skip writing-plans' "Execution Handoff" section — this factory has one execution path (the `implement` stage skill), not a choice between subagent-driven and inline execution.
- **Plan header "For agentic workers" line:** replace the REQUIRED SUB-SKILL boilerplate with `> **For agentic workers:** Executed by the factory-implement skill — one fresh subagent per task. Steps use checkbox (- [ ]) syntax for tracking.`

## Approach convergence

After finishing and self-reviewing the plan, run `factory approach-context ITEM --json`. Copy the exact engine-derived `item`, `planning_round`, `plan_sha256`, `tier`, `escalation_bound` (0 or 1), and `record` path. Do not invent a round, recompute a policy budget, or reuse a judgement for other plan bytes. Create a unique `planner_invocation` for this screen and retain it when resuming the same round/hash.

If the returned `enabled` is false, do not screen, read, consult, or collect convergence evidence; write no judgement record and invoke no reviewer. Use the ordinary `factory advance ITEM implement` flow. Unsolicited reviewer output has no authority while the gate is disabled.

If enabled, read the entire `skills/factory-plan/references/approach-convergence-corpus.json` under the resolved plugin root. Semantically compare the exact current plan against its positive and near-neighbour cases. Emit only the named signal ids supported by this plan: `natural-language-rule-tail`, `input-variety-task-growth`, and `unconstrained-output-postprocess`. Each signal is an object with `id` and a non-empty `evidence` list of bounded, non-empty plan citations: repository-relative `path` to `.factory/items/<id>/plan.md`, and 1-based inclusive `start_line` and `end_line`. Use unique signal ids; never infer a signal by regexing plan prose. The planner owns the semantic screen and its residual risk; the engine validates the envelope, identity, citations, attempt bounds, and routing coherence, not the semantic truth of the screen.

Build the version-1 record defined by `schemas/approach-judgement.schema.json`: `version: 1`, the copied item/round/hash/tier/bound fields, `configuration: {"enabled": true}`, `planner_invocation`, `signals`, `attempts`, `final_verdict`, `disposition`, and `escalation_count`. Submit the complete JSON with `factory approach-judgement ITEM --data '<JSON>'`; the engine writes the context's `record` path. Do not write the authoritative record directly or substitute a generic log event for this command.

For zero signals, use `signals: []`, `attempts: []`, `final_verdict: "not-triggered"`, `disposition: "advance"`, and `escalation_count: 0`, preserving the engine-derived `escalation_bound`. Record that judgement, then run `factory advance ITEM implement`. There is no reviewer for this path.

For one or more signals, invoke one fresh independent reviewer through the host adapter with only the item id and these disk paths: the current `plan.md`, `spec.md`, the corpus, and the saved JSON returned by `approach-context`. Pass no invoking-session history or planner persuasion. The reviewer reads the evidence from disk and judges only whether the selected approach can converge to a bounded completion. Do not invoke any council skill. Record attempt 1 with `attempt: 1`, a unique reviewer invocation in `invocation` different from `planner_invocation`, `timestamp`, `verdict` (`pass`, `reject`, or `uncertain`), boolean `evidence_conflict`, and non-empty cited `findings`. Every finding contains `claim`, repository-relative `path`, and bounded, non-empty `start_line`/`end_line` citations. Preserve the returned attempt as evidence; do not rewrite it to reach a preferred outcome.

Resolve attempt 1 with `escalation_count: 0`: an unconflicted `pass` yields `final_verdict: "pass"` and `disposition: "advance"`; an unconflicted `reject` yields `final_verdict: "reject"` and `disposition: "approach.rejected"`. An `uncertain` verdict or any evidence conflict yields `final_verdict: "uncertain"` and `disposition: "escalate"` only when the engine bound is 1; with bound 0 it yields `disposition: "approach.rejected"`. Record the judgement before acting on its disposition.

For an `escalate` disposition, invoke at most one additional fresh reviewer using the same disk-only input contract and the recorded evidence path. Its invocation must differ from both the planner and the first reviewer. Preserve the first attempt bytes, append attempt 2, and set `escalation_count: 1`; keep the same planner invocation, signals, round, hash, and engine bound. Only an unconflicted second `pass` advances. A second unconflicted `reject` records `final_verdict: "reject"`; uncertainty or conflict records `final_verdict: "uncertain"`; both yield `disposition: "approach.rejected"`. Submit the extended record through `factory approach-judgement`. There is no third attempt, human escalation, or blocked disposition in this protocol.

For a recorded `advance` disposition, run `factory advance ITEM implement`. For `approach.rejected`, first append to `items/<id>/approaches/forbidden.md`: `## <attempt timestamp> - rejected at plan`, then a paragraph naming the rejected strategy and citing the judgement record plus every decisive `path:start-end`. Preserve previous entries. Then use the shared redesign edge: `factory advance ITEM spec --reason "approach.rejected: <one line>"`. Do not create a second rejection counter, answer, cap, packet, or routing mechanism.

Interrupted review or missing evidence leaves the item at `plan`; report the missing evidence and do not fabricate a verdict or advance without a complete authoritative judgement. Rerun `factory approach-context ITEM --json` when resuming. The same round/hash resumes its existing record and planner invocation; a changed round or plan hash creates a new engine-derived record path and requires a fresh screen, leaving old records untouched. Report any gate refusal verbatim and resolve its stated cause before retrying; never guess a record mutation around the gate.

## Steps

1. Read `items/<id>/spec.md` and, for `ui`/`mixed` items, `items/<id>/design/choice.md`.
2. Follow `superpowers:writing-plans` with the adaptations above to produce `items/<id>/plan.md`. If feasibility is enabled, use its contract-first branch and produce the exact closed `items/<id>/acceptance.json` described by `references/plan-feasibility.md` and `schemas/acceptance-plan.schema.json`.
3. Self-review the plan against the spec's acceptance criteria (writing-plans' own self-review step): every criterion should trace to at least one task; every task should cite the criteria it covers.
4. Confirm `plan.md` contains at least one `- [ ]` line. When feasibility is enabled, run `factory plan-check ITEM --json`; fix only reported declaration defects and require `status: pass` before continuing.
5. Execute Approach convergence above against the finished, feasibility-valid plan. Its recorded disposition selects `implement` or `spec`; disabled mode uses the ordinary advance.

## Exit

Use the exit selected by Approach convergence: `factory advance ITEM implement`, or append the cited forbidden entry and run `factory advance ITEM spec --reason "approach.rejected: <one line>"`. If `plan-check` or advance refuses, report the refusal verbatim, resolve the stated cause, and rerun the context before retrying. An interrupted or incomplete review remains at `plan`.

Report the resulting stage (`implement` or `spec`) and the key plan, acceptance, judgement, or forbidden paths written. Never weaken a declaration or re-attempt with a guessed record mutation.
