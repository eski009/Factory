# Roadmap — consolidated 2026-09-10

This is the delivery record for the Factory product, not an instruction to run
Factory against this repository. Develop directly under [AGENTS.md](../../AGENTS.md).

The accepted implementation branches have been integrated and completed.
There are no implementation tasks in progress in this delivery batch.
Rejected mechanisms, superseded branches, and unstarted proposals have explicit
dispositions below. **Deferred does not mean implemented**: those proposals
require a new scope decision before further engineering.

See [consolidation evidence](2026-09-10-consolidation.md) and the
[previous roadmap](archive/2026-09-10/roadmap-before-consolidation.md).
Historical packets and draft plans are [archived](archive/2026-09-10/README.md);
they are not active human gates.

## Delivered and resolved

| Item | Outcome | Evidence / boundary |
|---|---|---|
| 0001 | Done — stakeholder focus-group research | Historical shipped report |
| 0002 | Done — optional design mirror | Repository files remain canonical |
| 0003 | Done — interactive design decisions | Decision pages and listener |
| 0004 | Done — per-item cost reporting | Measured evidence remains separate from proxies |
| 0007 | Done — tolerant log reading | Corrupt-line handling remains covered |
| 0008 | Done — mirror and provenance refinements | Historical shipped report |
| 0009 | Done — corruption-tolerant inspection | Config/item validation and status tests |
| 0010 | Done — reproduced-bug intake | Bug evidence is separate from materiality tier |
| 0012 | Done — surface-adaptive design choices | Historical shipped report |
| 0013 | Done — regression-scoped assurance | Existing failures do not become item regressions |
| 0014 | Done — opt-in plan convergence judgement | Integrated at 739b115; current-round judgement and safe plan exit |
| 0015 | Done — redesign loop | Existing rejection mechanism reused by 0014 |
| 0016 | Done — authoritative rework circuit breaker | No wall-clock or inferred-token threshold added |
| 0019 | Resolved through 0020 | Shared-checkout commit/index/evidence boundary |
| 0020 | Done — implementation checkout ownership | Main includes direct-engineering exclusion and regression tests |
| 0021 | Done — disk-first lost-reply recovery | daa93b4; current-attempt evidence, writer-state checks, single continuation |
| 0025 | Done — round-scoped rework evidence | Historical reports plus transactional follow-up tests |
| 0026 | Closed as split/superseded | Bug routing and roadmap visibility carried forward; shorter bug assurance is 0033. The deliberately parked depth recorder was not merged: tier-derived review depth no longer describes 0034's adaptive selection |
| 0027 | Done — reason-owned decision response | Packet response follows the actual pause reason |
| 0028 | Resolved through packet fixes | None-repr fix in 0027; both rework-number forms covered by test_rework_figure_pattern_matches_both_surface_forms |
| 0029 | Done — leaf/fork spend accounting | b51ca1e; only measured leaves total, legacy/unclassified coverage stays explicit |
| 0030 | Done — frozen timing replay and report | ecca6ed; n=13/n=16 fixture, exhaustive CAP sweep, corruption checks; no production threshold |
| 0031 | Done — state-derived continue destination | Historical shipped report; broader packet polish remains deferred |
| 0033 | Done — shorter confirmed-bug route | Immutable intake assurance declaration; fresh verification still required |
| 0034 | Done — adaptive independent review | 48caf76; finalized escalation/adjudication binding, digest-bound degraded execution records, stale optional round handling, rework-head preservation |
| 0036 | Done — acceptance feasibility and resumable execution | Plan structure, ownership, bounded task scope, atomic rework and recovery tests |
| 0038 | Done — proxy-only spend visibility | Per-stage proxy event counts render explicitly; token coverage remains partial |
| FH-01 / bounded FH-05 | Done through 0036 | No claim of runtime evidence preflight or global supervisor |
| FH-07 | Done — read-only derived ledger | 2e0d721; CLI, Git inventory, explicit timing provenance, test waves and evidence references |
| Supporting work | Done — transactional handoffs and worker attempt capture | Shared secure I/O and durable control substrate, already integrated on main |
| Host portability | Done — native Codex packaging and host adapters | Unreleased product changes; no marketplace release implied |

## Closed mechanisms

| Item | Disposition |
|---|---|
| 0011 | Duplicate of delivered 0010 |
| 0017 | Rejected standalone scope-narrowing mechanism; 0013 addressed the observed trigger |
| 0018 | Rejected wall-clock runaway threshold. 0030 demonstrates cadence-sensitive arithmetic, not calibrated runaway detection |

## Deferred proposals — outside this completed delivery batch

These are preserved ideas, not hidden implementation branches or claims of
completion. Reopen only with a bounded requirement and evidence of need.

| Item | Remaining proposal | Decision needed to reopen |
|---|---|---|
| 0005 | Generalize interactive choices beyond design | Select one additional decision journey and acceptance criteria |
| 0006 | Optional external design-polish integration | Identify an available provider/skill and concrete user need |
| 0022 | Portable export/import of Factory runtime state | Define the product's sharing, privacy and recovery contract; this repository now versions its delivery record but has no runtime export feature |
| 0023 | Packet/readout layout polish | Select terminal/browser surfaces and rendered acceptance criteria |
| 0024 | Assurance readout periphery | Define owner-priority response, known-failure ordering and JSON contract |
| 0032 / FH-06 | Pool-exhaustion/no-synthesis supervision | Select supported host and containment adapter; archived draft introduces a new supervisor beyond 0021's lost-reply recovery |
| 0035 | Broad autonomous blocker recovery | Define allowed recovery actions and authority boundaries |
| 0037 | Spend emission denominator and enforcement | Define an engine-observable denominator; 0029 does not claim complete coverage |
| FH-02 | Risk-proportionate verification policy | Define a versioned policy beyond delivered 0033 and 0034 without silently dropping integrated proof |
| FH-03 | Reuse evidence across attempts | Requires a trustworthy capture identity and invalidation policy first |
| FH-04 | Evidence-capture preflight | Archived implementation proposal; capability/host contract remains a separate feature |

## Next product decision

The highest-value future investment is a bounded 0032/FH-06 host supervisor:
pool exhaustion and missing synthesis are distinct from the lost-reply case
0021 now handles. Choose its host/containment scope before starting it.
Evidence preflight (FH-04) should precede cross-attempt reuse (FH-03).

No retired packet, old review-count stop, or archived draft starts work
automatically. The product's gates remain available for other repositories;
this source repository is not self-hosted through them.
