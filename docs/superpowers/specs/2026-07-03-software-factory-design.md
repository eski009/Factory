# Factory — Autonomous Software Factory: Design Spec

- **Date:** 2026-07-03
- **Owner:** Steve
- **Status:** Approved design, pre-implementation
- **Predecessor:** https://github.com/jzjq567/superpowers-council (branch `product-brain-council-mvp`)

## 1. Purpose

Factory is a GitHub project installable into any codebase that turns Claude Code into an autonomous software factory: a full **product brain** that maintains a roadmap, proposes and prioritizes features, then specs, designs, plans, implements, reviews, verifies, and ships them — with exactly one class of human gate (UI design choices) in the default configuration.

It succeeds `superpowers-council`, which built a product-memory and council-judgement layer but had no execution pipeline. Factory keeps that repo's proven ideas (bounded council protocol, code-enforced memory firewall, derived reputation, review packets) and adds the missing factory: a file-based pipeline state machine driven by skills and enforced by a deterministic script.

### Goals

1. **Autonomy:** a backlog item goes from idea to merged code without human input unless it touches UI design (or config says otherwise).
2. **Portability within Claude Code:** works on any Claude model. Fable-only features (Workflow tool, forks) are opportunistic upgrades, never requirements.
3. **Installable:** one plugin install per machine + one idempotent `init` per target repo. Never modifies product code, CLAUDE.md, or existing docs on install.
4. **Auditable and resumable:** all state is files (markdown + JSONL + JSON). Any session on any model can resume any item mid-pipeline cold. Everything is diffable and reversible.

### Non-goals (v1)

- Running on non-Claude agents (Codex, Gemini CLI, Cursor). The engine is agent-agnostic Python, so this stays *possible*, but no adapter docs or packaging ship in v1.
- Fully headless CI operation (GitHub Actions driving the loop). The dispatcher's `loop` mode plus scheduled agents cover continuous operation; CI integration is a later phase.
- Multi-repo/monorepo-aware orchestration. One target repo per `.factory/` state dir.

## 2. Shape of the deliverable

One repo, working name **Factory**, shipping two installables:

1. **A Claude Code plugin** (`.claude-plugin/plugin.json` + `marketplace.json`): skills, agents, commands, hooks. Declares **Superpowers as a dependency** — Factory invokes Superpowers skills (test-driven-development, systematic-debugging, verification-before-completion, using-git-worktrees, finishing-a-development-branch) rather than vendoring them.
2. **An installer/engine** (`scripts/factory/`, Python 3 stdlib, zero third-party deps): `factory.py init` scaffolds a target repo; the same engine enforces pipeline gates, validates ledgers, computes reputation and memory health, and renders review packets.

### Factory repo layout

```
factory/
  .claude-plugin/
    plugin.json               # name: factory; depends on superpowers
    marketplace.json
  skills/
    factory-init/             # guide init + first product-brain intake
    factory-dispatch/         # the dispatcher loop (see §4)
    factory-triage/           # council triage: should we build it, priority
    factory-spec/             # write item spec from brain + brainstorming skill
    factory-design/           # UI design options gate (see §5)
    factory-plan/             # implementation plan (wraps superpowers writing-plans)
    factory-implement/        # execute plan via subagents + TDD
    factory-review/           # council code/product review (see §6)
    factory-verify/           # wraps verification-before-completion + e2e checks
    factory-ship/             # merge per policy, update roadmap + brain
    council-bidding/          # escalation bids (ported)
    council-judgement/        # orchestrator judgement (ported)
    council-memory-health/    # ported
    council-pruning/          # ported, with real prune CLI this time
  agents/                     # subagent definitions: 6 council roles + implementer,
                              #   reviewer, spec-writer
  commands/                   # /factory:run, /factory:add, /factory:status,
                              #   /factory:init, /factory:packet
  hooks/                      # SessionStart: surface factory state + pending packets
  scripts/factory/
    factory.py                # CLI entry: init, validate, advance, status, packet
    lib/                      # engine: state machine, schema validator, ledgers,
                              #   reputation, health, prune, packets
  schemas/                    # work-item, escalation-bid, orchestrator-judgement,
                              #   reputation-event, memory-health, config
  templates/                  # target-repo scaffolding (brain surfaces, role files)
  tests/                      # engine unit tests + e2e toy-repo fixture
  docs/
```

### Target repo after `factory.py init`

```
.factory/                     # machine state (hidden)
  config.json                 # autonomy level, merge policy, gates, model prefs
  items/<id>/
    item.md                   # frontmatter: id, title, stage, priority, kind
                              #   (ui|backend|mixed), created, updated
    spec.md  plan.md
    design/                   # options.html, choice.md, tokens used
    reviews/                  # council round notes, synthesis
    log.jsonl                 # append-only action log (audit + resume)
  ledgers/
    bids.jsonl  judgements.jsonl  reputation.jsonl
  runs/                       # dispatcher run records
docs/factory/                 # human-visible product brain
  roadmap.md                  # prioritized backlog; the triage council writes here
  brain/                      # vision.md, users.md, constraints.md,
                              #   design-system.md, decisions.md, open-questions.md
  council/<role>.md           # 6 role memory files
  packets/                    # review packets awaiting or answered by the human
```

`init` is idempotent: re-running never clobbers existing files, only fills gaps. `validate` checks the whole tree against schemas.

## 3. Pipeline state machine

Each work item's `item.md` frontmatter carries its stage:

```
idea → triage → spec → design → plan → implement → review → verify → ship → done
                        (design skipped when kind != ui|mixed)
any stage may drop to: blocked | waiting-human
```

**Division of labor — the core invariant:** skills do the thinking; `factory.py advance` is the deterministic gatekeeper. `advance <item> <to-stage>` refuses any transition whose preconditions are unmet:

| Transition into | Preconditions enforced by script |
|---|---|
| spec | triage record exists with accepted priority |
| design | spec.md exists, non-empty; item kind is ui/mixed |
| plan | spec.md exists; if design stage ran, design/choice.md records a selection |
| implement | plan.md exists with at least one task |
| review | implementation branch exists; log records plan tasks completed |
| verify | review synthesis exists with zero unresolved blocking findings |
| ship | verify record shows green (tests + verification evidence logged) |
| done | merge recorded per policy |

This mirrors `is_change_authorized()` from the predecessor: guardrails as tested code, not prose. Transitions also append to `log.jsonl` (who, when, evidence pointer), giving audit and cold-resume for free.

**Item creation:** `/factory:add "title"` (or the triage council proposing items from the roadmap/brain) creates `items/<id>/item.md` at `idea`.

## 4. Dispatcher

`/factory:run [step|item|loop]`:

- **step** — advance the single highest-priority actionable item by one stage.
- **item** — run one item from its current stage to `done`, `blocked`, or `waiting-human`.
- **loop** — keep pulling the next actionable item until the backlog has none, pausing items at human gates and continuing past them with other items. Continuous operation pairs with `/loop` or a scheduled agent; because state is files, stop/resume costs nothing.

"Actionable" = not `done|blocked|waiting-human`, dependencies satisfied, highest priority per roadmap order. Items in `waiting-human` whose packet has been answered (choice recorded) become actionable again automatically.

**Execution:** each stage runs as one or more subagents (the plugin's `agents/` definitions), keeping the driving session's context small. Item implementation happens in a per-item git worktree/branch (via Superpowers using-git-worktrees).

## 5. Design gate (the one human gate)

For `ui`/`mixed` items, `factory-design`:

1. Reads design context: `docs/factory/brain/design-system.md` (repo-local tokens — always present, seeded at init) and, when an interactive session has DesignSync access, the linked claude.ai/design project as an upstream token source.
2. Generates **2–4 distinct mockup options as one self-contained HTML page** — as a hosted artifact when the Artifact tool exists, else written to `items/<id>/design/options.html` for local viewing.
3. Writes a review packet to `docs/factory/packets/<id>-design.md` (mobile-legible: screenshots/summary per option, one recommendation, a `choice:` line to fill in) and parks the item at `waiting-human`.
4. On answer (in-session reply or edited `choice:` line), records `design/choice.md` and the item resumes.

**DesignSync is additive, never load-bearing:** interactive sessions may pull tokens from and push finished components back to the user's Claude Design project; headless/scheduled runs use repo-local tokens and artifacts only. The pipeline never blocks on DesignSync auth.

Config can widen the gate set (`gates: ["design", "spec", "merge"]`) for cautious operation, or narrow it to `[]` for full auto.

## 6. Council layer

Rebuilt from superpowers-council, slimmed and wired into the pipeline.

**Six roles** (down from 11): `product`, `ui-taste`, `architecture`, `engineering-quality`, `customer`, `commercial`. Each `docs/factory/council/<role>.md` carries scope, evidence standards, escalation criteria, known blind spots, and per-topic reputation history. More roles only when real usage shows a gap.

**Two council moments per item:**

- **Triage:** should we build this, at what priority, what scope cuts. Output updates `roadmap.md` and the item's triage record. This is also where the council *proposes* new items from brain surfaces (open questions, decisions, scan findings).
- **Review:** council reviews the diff against the spec and brain before verify. Blocking findings send the item back to `implement` (max 2 round-trips, then `blocked` with a packet).

**Bounded protocol (preserved exactly from predecessor):**
1. Shared `seed-context.md` per council run.
2. Round 1: specialists dispatched independently in parallel (each sees seed + own memory only), max 3 new claims per agent.
3. Orchestrator synthesis: dedupe, group, conflict-detect, select agents for round 2.
4. Round 2 delta-only: selected agents respond to the synthesis (agree/disagree/withdraw/refine) — no restatement.
5. Hard stop: max 2 rounds; a 3rd requires a written reason. Default convergence checks.

**Memory firewall (preserved, ported from `pblib.py` with its tests):** specialists never mutate the brain. They file schema-validated **escalation bids**; the orchestrator records exactly one **judgement** (`accept/reject/defer/merge/downgrade`) per bid; only accept/merge authorize a canonical edit naming a specific surface and anchor. **Reputation** is derived from judgements per agent per topic (wolf tax: −0.05 overclaimed, −0.10 false/noisy, +0.05 accepted useful) and ranks attention, never suppresses claims. `council-memory-health` recommends pruning; `council-pruning` produces a provenance-preserving diff (invariant: kept ∪ archived == input) — implemented as a real CLI this time, not just a library function.

## 7. Merge policy & shipping

`factory-ship` acts per `config.json` `merge` setting:

- **`auto` (default):** merge when green — tests pass, council review has no unresolved blocking findings, verification evidence is logged. A shipped packet (what merged, why, evidence links) lands in `docs/factory/packets/`.
- **`queue`:** open a PR, continue with the next item; human merges async.
- **`tiered`:** auto-merge items below a configured risk tier (docs, fixes, refactors); queue features and schema/API changes.

Ship also closes the loop on the brain: outcomes append to `decisions.md`, and the roadmap entry moves to shipped.

## 8. Capability adapter (working without Fable)

One `capabilities` probe at dispatch time — skills are written against the degraded baseline and opportunistically upgrade. No forked skill variants.

| Capability | Present (Fable) | Absent (any Claude model) |
|---|---|---|
| Workflow tool | Council rounds and independent plan tasks fan out as orchestrated workflows with structured outputs | Same stages as parallel/sequential Task subagent dispatches |
| Artifacts | Design options and status dashboards as hosted artifact pages | HTML written into the repo, opened locally |
| Scheduled agents / cron | `loop` mode runs on a schedule | User starts `/factory:run loop` manually |
| DesignSync | Pull/push claude.ai/design project | Repo-local design tokens only |

The detection convention (attempt/probe and fall back) lives in one reference doc that every stage skill cites, so degradation logic stays in one place.

## 9. Error handling

- A stage failing twice moves the item to `blocked` with a packet stating what failed and what's needed; the dispatcher moves on. No unbounded retries anywhere.
- Every subagent action appends to the item's `log.jsonl`; a crashed or interrupted run resumes from files with no lost state.
- `factory.py validate` runs at dispatcher start; a corrupt state tree halts the loop with a packet rather than guessing.
- Review→implement round-trips capped at 2 (then `blocked`).
- Worktree-per-item isolation means a failed item never contaminates main or other items.

## 10. Testing

1. **Engine unit tests** (Python, stdlib unittest): every transition gate in §3 (both directions — allowed and refused), ledger append/validation, bid/judgement business rules, reputation derivation, prune provenance invariant, init idempotence. Ports and extends the predecessor's 30+ tests.
2. **End-to-end fixture:** a toy target repo in `tests/fixtures/`; the suite runs `init`, injects a scripted work item, and drives it through every stage with stubbed agent outputs, asserting state-file evolution and gate refusals.
3. **Skills:** authored and checked with the writing-skills discipline; each stage skill names its preconditions/postconditions matching §3's table.
4. **CI:** GitHub Actions running the Python suite on push (the one CI piece in v1).

## 11. Build order (phases)

1. **Engine core:** `factory.py` init/validate/advance/status + state machine + schemas + unit tests.
2. **Council port:** ledgers, bids, judgements, reputation, health, prune (+ tests) adapted from predecessor.
3. **Pipeline skills + agents + commands:** dispatcher and stage skills against the degraded baseline.
4. **Design gate:** options generation, packets, choice handling; DesignSync as optional upgrade.
5. **Capability upgrades:** Workflow fan-out, artifacts, scheduling.
6. **E2E fixture + docs + install polish** (README, marketplace packaging).

Each phase lands independently useful and tested.

## 12. Open questions (deferred, with working defaults)

- **Merge policy default** is `auto`; Steve hasn't explicitly confirmed — flag at first ship. Config knob exists either way.
- **First pilot repo** unknown ("Domino" from the predecessor spec is a candidate). Factory is product-agnostic; pilot selection happens at first install.
- **Repo/plugin final name:** working name `factory`; confirm before publishing to a marketplace.
