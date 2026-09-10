> Archived source: Sortly's `docs/factory/2026-09-04-harness-improvement-retrospective.md`, copied 2026-09-10. Relative evidence links belong to Sortly and are not portable within this repository. This remains proposed intake, not a universal defect list or development authorization.

# Factory harness improvement retrospective — Sortly autonomous run

Date: 2026-09-04

Status: proposed improvement intake only.

Audience: Factory harness maintainers.

Scope: approximate Sortly autonomous run from 2026-09-03 13:00 BST through 2026-09-04 08:00 BST.

Installed Factory label observed in this checkout: `0.15.0+codex.20260903120910`.

This report does not execute improvements, alter current gates, create Factory tickets, file escape events, inspect Factory source, or approve any policy change. Before turning any candidate below into Factory work, deduplicate it against the Factory repository's current backlog and implementation. The observations are from one project-specific execution and are not proof that the named capabilities are universally absent from the harness.

## Evidence boundary

The analysis was bounded to Sortly history ending at `76b9a6930d210b21acc00476d1094fad8ea860c0`.

Key references:

- [execution-status.yaml](../audits/evidence/2026-08-15-ios-shippability/execution-status.yaml)
- [0072 ship summary](../../.factory/items/0072-add-contextual-accessibility-names-to-ne/evidence/ship/20260904T020628Z/summary.md)
- [0072 lifecycle log](../../.factory/items/0072-add-contextual-accessibility-names-to-ne/log.jsonl)
- [0071/0063 atomic addendum](../audits/evidence/2026-08-15-ios-shippability/packets/0071-0063-atomic-integration/addendum.md)
- [0071 controller transport status](../../.factory/items/0071-recover-readiness-mount-and-focus-card-o/reviews/evidence/plan-author/controller-transport-status.md)
- [0071 recovered plan part 1](../../.factory/items/0071-recover-readiness-mount-and-focus-card-o/reviews/evidence/plan-author-recovery/plan-part-1.md) — local working artifact, currently untracked and not available from the pinned commit
- [0071 recovered plan part 1 provenance](../../.factory/items/0071-recover-readiness-mount-and-focus-card-o/reviews/evidence/plan-author-recovery/plan-part-1-provenance.json) — local working artifact, currently untracked and not available from the pinned commit
- [0067 shipped packet report](packets/reports/0067-reflow-the-home-dashboard-header-legibly-shipped.md)

Ground-truth command used for the first-parent window:

```sh
git log --first-parent --since='2026-09-03T12:00:00+01:00' --until='2026-09-04T08:15:00+01:00' 76b9a693 --format='%H|%cI|%s'
```

File classification used each commit's actual diff against its parent, not commit subject text.

## Verified outcomes

The run produced real value, but converted it poorly into the desired finished Home/Circles "one obvious action" experience.

First-parent history in the bounded period contains 123 commits:

- 6 commits changed iOS app or DesignSystem files.
- 117 commits changed only `docs/` or `.factory/`.
- These counts are not time accounting, productivity percentages, or proof that any specific stage consumed the whole window.

The six iOS-changing merges were:

| Merge | Local time | Product effect |
|---|---:|---|
| `6fa44142` | 2026-09-03 15:34 BST | Day 8 scroll/reachability baseline |
| `1ddfebcb` | 2026-09-03 18:01 BST | Sunday card accessibility-size containment |
| `f9cac164` | 2026-09-03 20:44 BST | Home header accessibility reflow |
| `91271d07` | 2026-09-03 21:47 BST | Day 1 Invite clearance |
| `f9eb07a0` | 2026-09-03 23:34 BST | Day 2-7 bottom action clearance |
| `cf13d3a6` | 2026-09-04 02:30 BST | Shared `NetworkErrorCard` optional contextual retry accessibility label |

The last green governance point was `f67357ab45baeb893b00531da7adf235a2ac89c2`; the source merge it preserved was `cf13d3a6bf59323a04af685381803e8a9ba6fab8`.

Final recorded green test evidence was local simulator-only:

- Sortly app: `1323/1323` passed, made of `1312` unit tests plus `11` UI tests.
- DesignSystem: `239/239` passed, made of `32` snapshots plus `207` behavior tests.
- Device: iPhone 16 simulator, iOS 26.1 only.
- Failures/skips/expected failures: zero.
- Pre-existing unowned warnings remained.

No TestFlight, App Store, physical-device, full-app beauty, or physical VoiceOver claim is supported by these receipts.

The `37` completed AUD items in `execution-status.yaml` are cumulative, not this run's throughput. Five broader Home audit closures still remain pending composition with the new readiness card.

Completed groundwork is still meaningful: the relevant specification was approved, the Statement-card design was selected, and the 0071/0063 joint-release conflict was resolved. The new Home/readiness/Root implementation and adoption of the shared contextual retry label by its consumers remain unfinished.

## Main findings

1. The harness did useful safety work, but small changes were surrounded by heavy repeated ceremony.

The 0072 lifecycle shows RED/GREEN/mutation proof, full DesignSystem, code review, flow review, Phase A candidate proof, Phase B integration proof, blind node assurance, and fresh ship full suites. Some reruns corrected invalid or incomplete evidence and should not be dismissed as redundant. The records show separate proof collection across candidate, integration, assurance, and ship phases. Whether an existing Factory reuse mechanism could already satisfy these declared gates was not established in this retrospective.

2. Dependency ownership contradictions were discovered late.

The 0071/0063 addendum records a structural conflict: 0071's production mount proof required a caller in files excluded from 0071 ownership, while 0063 owned that caller and was waiting for 0071 to ship. The corrected approach was a jointly staged, atomic integration. This was important planning progress, but the harness should detect impossible acceptance before dispatching work.

3. Evidence quality defects forced manual repair.

The execution status records a historical Sunday discovery mismatch: intended `42`, discovered `39`, later corrected. The addendum had to make the production-mount versus component-proof boundary explicit before joint closure. The harness needs stronger preflight around expected test IDs, discovered counts, route/state screenshots, and stale or wrong-screen evidence.

4. Manual receipt and handoff volume obscured the current state.

The 0071 recovered plan part is `2,891` lines and `122,115` bytes, and its body includes implementation-level code. Provenance correctly says part 1 is complete while the whole plan is incomplete: Tasks 1-4, matrices, gates, independent review, and provenance remain pending. Repository-record facts and local-working-artifact facts have separate scope; the part 1/provenance files were locally present but untracked and therefore not durable pinned-commit handoff by default.

5. Worker supervision caused a premature abort and stale ledger risk.

The original 0071 plan author was controller-aborted by `SIGTERM` to PID `30949`, exit `143`, before producing a final plan. The transport record correctly says this was not a provider failure. The harness should preserve partial progress while avoiding invented terminal success, stale active state, or repeated restart waste.

6. Ledger/accounting surfaces invite false conclusions.

The run has multiple valid inventories: Factory items, AUD aliases, packet reports, first-parent commits, and test waves. The 0067 report shows repeated candidate and integrated test evidence (`2/2` twice, `41/41` five times, final `44/44`), but artifact timestamps are not stage durations. A derived ledger should prevent summing overlapping inventories or presenting commit counts as proof of delivery speed.

Accountability is mixed. Some safety process came from the user, `AGENTS.md`, and project packet policy: independent review, useful behavior tests, build-per-merge discipline, and protected gates. The observations above should not be assigned wholesale to Factory engine code without a source audit.

## Improvement candidates

### FH-01 — dependency, ownership and capability gate

Priority: first.

Observed evidence: 0071 needed production mount proof in `SortlyApp.swift`/`RootView.swift`, but those files were excluded and owned by 0063.

Intent: fail early when an item's acceptance requires files, runtime capabilities, devices, routes, or owners outside its legal scope.

Acceptance tests:

- A 0071/0063-style impossible solo delivery fails before implementation dispatch.
- Disjoint parallel component work still passes when its acceptance is component-only.
- A declared joint staged delivery passes when both owners, shared gates, and merge sequence are explicit.

### FH-02 — risk-proportionate verification stages

Priority: second.

Observed evidence: small accessibility/layout deltas carried many full reruns, while the final Home/Root/Circles outcome remained unshipped.

Intent: preserve independent review, useful behavior tests, build-per-merge, final full-wave gates, and strict handling for auth/session/data/routing/stale-action changes, but make low-risk verification explicitly versioned and bounded.

Acceptance tests:

- A policy change requires a versioned approved amendment, not silent skipping or retry reset.
- Shared accessibility semantics are not classified as zero-risk by default.
- An approved low-risk policy executes bounded evidence once per required purpose without dropping integrated or full-wave gates.
- High-risk auth/session/routing changes still require strict fresh proof.

### FH-03 — evidence receipt reuse by identity

Priority: third.

Observed evidence: 0072 recorded separate pre-merge and shipping full-suite phases while later governance and source points had equivalent app trees. This does not prove the reruns were caused by metadata changes or were unnecessary; all explicit fresh/coupled gates remain mandatory until an approved amendment says otherwise.

Intent: reuse receipts only when source, dependencies, toolchain, config, device, fixtures, oracle, and policy identity all match.

Acceptance tests:

- Metadata-only non-product changes retain valid product evidence.
- Source, fixture, oracle, policy, device, dependency, or toolchain changes invalidate applicable proof.
- Missing, stale, or invalid proof fails closed.
- Independent reviewer identity is never reused as implementer identity.

### FH-04 — reliable evidence capture preflight

Priority: fourth.

Observed evidence: Sunday test discovery corrected from `39` to intended `42`; production proof and node proof required manual separation.

Intent: make evidence capture deterministic and adversarial before gates can pass.

Acceptance tests:

- Expected test IDs and discovered counts are checked before accepting suite receipts.
- Component-only evidence cannot satisfy a production gate; every receipt must meet its declared purpose.
- Screenshots must identify the intended route and state.
- A missing test, wrong screen, or broken action fails a gate.
- Warnings remain visible and cannot be hidden by a passing summary.

### FH-05 — compact self-contained planning artifacts

Priority: fifth.

Observed evidence: 0071 plan part 1 was huge, implementation-like, locally untracked, and incomplete despite a successful partial output.

Intent: plans should freeze contracts and execution boundaries without prescribing every line of implementation.

Acceptance tests:

- Required fields include owned files, interfaces, acceptance criteria, test commands, out-of-scope boundaries, resume cursor, artifact hash, and revision reason.
- A compact complete plan is accepted.
- Missing required fields fail.
- Contract changes require a new scoped reason, not reopening all design.
- No arbitrary hard line cap rejects an otherwise complete plan.

### FH-06 — resumable worker supervision

Priority: sixth.

Observed evidence: one plan author was killed while quiet/unfinished; recovery persisted part 1 but the whole plan remained incomplete.

Intent: supervise by heartbeat, phase, progress, and complete-part checkpoints. Preserve the run's configured stall policy: 45 minutes without meaningful progress, or three same-error self-reported retries. Silence or low CPU is not the same as absence of true progress; never terminate early only because a worker is quiet.

Acceptance tests:

- A quiet but valid worker survives.
- A fake-clock threshold test proves no termination before the configured 45-minute no-progress boundary when the same-error retry limit has not been reached.
- A true stall is bounded and reported.
- Abort evidence is preserved as external partial/aborted state, not provider failure.
- Resume does not duplicate source edits or advance a gate.
- Active and transition status are derived from events, not stale notes.

### FH-07 — one derived ledger for evidence and accounting

Priority: seventh.

Observed evidence: 123 first-parent commits, six iOS merges, 117 metadata-only commits, cumulative `37` AUD completions, and packet-level repeated test waves are all different metrics.

Intent: derive a single read-only ledger that separates AUD aliases, Factory items, stage timings, waits, test waves, reviews, admin/metadata work, and shipped flows.

Acceptance tests:

- The bounded run reports exactly six iOS-changing merges and 117 docs/Factory-only commits.
- Cumulative AUD completion counts are labelled separately from run-local throughput.
- Stage timing separates active work, waiting, test runtime, review, and admin.
- Per wave, the ledger records shipped flows, screenshot coverage, and green reference SHAs.
- It never sums overlapping inventories or treats commit counts as proof of speed.

No candidate above asserts hours saved or speedup. A future pilot should compare same-risk packets with equally strong outcomes before claiming efficiency improvement.

## Nonnegotiables to preserve

- Useful tests that prove behavior, including mutation-sensitive stale-state cases.
- Independent review for implementation and tests.
- Build-per-merge and final full-wave gates until amended by an approved policy.
- Fail-closed evidence handling.
- Explicit distinction among local simulator, hosted checks, physical device, TestFlight, and App Store release states.
- User/project-specific gates, including no production/domain writes and no unauthorized physical iPhone 17 substitution.

## Immediate recommended sequence for Sortly

1. Complete the 0071 Home/readiness plan, including Tasks 1-4, matrices, gates, and independent review.
2. Compose the 0071/0063 work through the approved joint staged plan.
3. Prove the real cold-launched Home/Root flow, not only node/component behavior.
4. Only then continue the Circles-dependent chain.

The current state does not support claiming the new Home/readiness/Root/Circles experience as shipped.
