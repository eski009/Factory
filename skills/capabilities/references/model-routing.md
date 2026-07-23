# Model routing (concrete fleet)

`references/model-tiering.md` defines three **abstract** tiers (cheapest / mid /
most-capable) and never names a model — that is deliberate, so the factory runs on any
model. This doc is the *fork-local* resolution: it pins those abstract tiers to the
concrete fleet this operator runs. It is advisory to the orchestrator, not read by the
engine. If you are running a different fleet, replace this file; do not edit
`model-tiering.md`.

## The fleet → tier map

| Model | Role in the factory | Abstract tier |
|---|---|---|
| **Fable** | Top-level orchestration only: pipeline dispatch, running stage skills, deciding what to fan out. Sits *above* the tier table and delegates everything. | (orchestrator) |
| **Opus** | The **default subagent**. Every reviewer seat (task review, all six council seats, re-review), the whole-branch walk (pattern 4), the journey/assure walk, architecture & design-gate decisions, adversarial audits, and spec/plan/roadmap authoring. | most-capable **and** mid |
| **Codex** (external CLI) | Coding **above the trivial bar**. The implementer subagent (Opus) shells out to `codex exec … < /dev/null`; Codex is not a native Claude subagent. Trivial edits stay in-loop on Opus (see the bar below). | cheapest (coding) |
| **Sonnet** | Mechanical, non-coding execution: driving Maestro/Playwright, *running* tests, issuing commands to other apps. | cheapest (mechanical) |
| **Haiku** | Basic shell/commands and lookups. | cheapest (trivial) |

Opus deliberately spans two abstract tiers: it is both the reviewer *floor* (mid) and the
*most-capable* dispatchable tier. Fable is reserved for orchestration and is not normally
dispatched into a job — when the table calls for the most-capable tier on a subagent, that
is **Opus**.

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
- **Fable orchestrates, Opus walks.** Fable is most-capable, so it *may* walk inline — but
  since it only orchestrates, it dispatches the walk to an Opus subagent. That is compliant
  precisely because Opus is the most-capable dispatchable tier here, not a downgrade.

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
