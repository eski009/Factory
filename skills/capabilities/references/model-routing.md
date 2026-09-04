# Model routing (Claude-hosted fleet)

When Factory is hosted by Codex, use `model-routing-codex.md` instead. The map
below is retained for Claude-hosted sessions and their external Codex coding
worker; it is not a Codex-native routing recommendation.

`references/model-tiering.md` defines three **abstract** tiers (cheapest / mid /
most-capable) and never names a model — that is deliberate, so the factory runs on any
model. This doc is the *fork-local* resolution: it pins those abstract tiers to the
concrete fleet this operator runs. It is advisory to the orchestrator, not read by the
engine. If you are running a different fleet, replace this file; do not edit
`model-tiering.md`.

## Lead orchestrator

For Claude-hosted Factory, use **Claude Fable 5.1** (`claude-fable-5-1`) as
the lead orchestrator for complex thinking and planning. It owns goal
decomposition, architecture and approach decisions, spec/plan/roadmap authoring,
task sequencing, delegation, and blocker diagnosis and replanning. Delegate
bounded research and execution, but keep the decisions that determine the path
to the goal on Fable 5.1.

For Fable-owned reasoning or planning stages that require a fresh context,
dispatch to Fable 5.1 with the stage's disk-only inputs; lead ownership does not
permit running it inline or passing private orchestration context. Opus can
gather evidence and review the resulting plan, but is not the default planning
author.

This is routing guidance, not a runtime model switch. Start the Claude lead
with `claude --model claude-fable-5-1`, or select it in Claude Code's `/model`
picker and verify the active model in `/status`. Do not silently substitute
another lead if Fable 5.1 is unavailable; report that and ask for a fallback.
Use the provider-specific ID when not connecting directly to Anthropic.
See the [model ID reference](https://platform.claude.com/docs/en/models/fable-5-1/overview)
and [Claude Code model selection](https://code.claude.com/docs/en/model-config).

## The fleet → tier map

| Model | Role in the factory | Abstract tier |
|---|---|---|
| **Fable 5.1** | The **lead orchestrator and planner**: complex reasoning, goal decomposition, architecture & design strategy, spec/plan/roadmap authoring, pipeline dispatch, delegation, and blocker diagnosis/replanning. | most-capable (orchestration and planning) |
| **Opus** | The **default supporting subagent**, except for Fable-led reasoning and planning. Every reviewer seat (task review, all six council seats, re-review), the whole-branch walk (pattern 4), the journey/assure walk, and adversarial audits. | most-capable (review/audit) **and** mid |
| **Codex** (external CLI) | Coding **above the trivial bar**. The implementer subagent (Opus) shells out to `codex exec … < /dev/null`; Codex is not a native Claude subagent. Trivial edits stay in-loop on Opus (see the bar below). | cheapest (coding) |
| **Sonnet** | Mechanical, non-coding execution: driving Maestro/Playwright, *running* tests, issuing commands to other apps. | cheapest (mechanical) |
| **Haiku** | Basic shell/commands and lookups. | cheapest (trivial) |

Opus deliberately spans two abstract tiers: it is both the reviewer *floor* (mid) and the
*most-capable* review/audit tier. Resolve a most-capable dispatch by role:
**Fable 5.1** for complex reasoning and planning, **Opus** for independent
review and assurance. Neither role inherits the parent's model implicitly.

## Hard rules this map must not violate

- **Evaluation judgment is never Sonnet.** Sonnet *drives* the test harness (mechanical);
  it never *judges* whether the running product satisfies a journey. That judgment — the
  `journey-reviewer` / assure walk and the factory-review whole-branch walk — is
  most-capable tier = **Opus**. Reviewing is never delegated below the mid tier
  (`model-tiering.md`), and Sonnet is below it here.
- **Reviewer ≠ implementer.** Codex writes the code, Opus reviews and assures it — a
  different model, satisfying `factory-assure/SKILL.md`'s "different model from the one
  that ran implement." If Codex is rate-limited and coding falls back to Sonnet, the Opus
  reviewer still differs — keep the assure walk on Opus regardless.
- **Set `model:` explicitly on every dispatch.** The omitted-model rule
  (`model-tiering.md`) makes an unspecified model inherit the parent — with five models
  over three tiers, that silently runs Sonnet/Haiku work at Fable/Opus (wasted budget) or a
  walk a rung too low while still reporting a pass. Never let a model choice inherit;
  choose it per task.
- **Fable 5.1 plans, Opus independently reviews.** Dispatch the whole-branch and
  journey walks to fresh Opus reviewers. Fable's planning ownership does not replace
  independent review or assurance evidence.
- **Replanning preserves gates.** Fable 5.1 chooses recovery within the current
  stage's permitted actions. It does not reset retry caps, bypass refused gates,
  answer human-only decisions, or expand the user's authority. Existing dispatcher
  stopping rules still apply; a stronger lead does not change engine policy.

## The trivial bar (Codex vs. in-loop Opus)

Coding goes to Codex **only above the trivial bar**; at or below it, the Opus implementer
edits directly rather than paying the `codex exec` round-trip. A change is trivial — keep
it on Opus — only when **all** hold: touches one file, is roughly ≤15 changed lines, and
adds no new logic, control flow, or public symbol (a rename, import, config/build tweak,
string/constant change, type-signature wiring, or a one-line patch a review already
specified verbatim). Anything else — 2+ files, a new type/component/function/endpoint or
meaningful branch, a feature/refactor/algorithm, a shared design-system primitive, or a
diff you'd want to review to trust — goes to Codex. When unsure which side of the bar a
task is on, it goes to Codex.
