# Fixture — ParkSnap p1 non-convergence run, 2026-08-02

**This is a reconstruction, not the original log.** The original
`log.jsonl` lives in the ParkSnap repo and is deliberately not copied
here: multi-repo is an explicit v1 non-goal
(`docs/superpowers/specs/…` / `brain/vision.md:27-29`).

`log.jsonl` reconstructs the stage-transition sequence quoted verbatim at
`docs/factory/field-reports/2026-08-02-parksnap-p1-nonconvergence.md:18-21`:

```
idea→triage→spec→plan→implement→review→implement→review→verify→waiting-human→
verify→assure→implement→review→implement→review→verify→assure→waiting-human→
assure→implement
```

21 states, therefore 20 `stage.advance` events. Timestamps are synthetic
and evenly spaced (18 minutes apart, spanning the reported ~6 hours of
wall clock); only the ordering and the from/to pairs are load-bearing.
Token counts and spend events are **not** reconstructed — the point of
the fixture is that the rework figure survives their absence.

Backward edges into `implement` (the rework substrate), in order:

| advance # | edge | rework edge # | implement round entered |
|---|---|---|---|
| 6 | `review → implement` | 1 | 2nd |
| 12 | `assure → implement` | 2 | **3rd — the breaker fires here** |
| 14 | `review → implement` | 3 | 4th |
| 20 | `assure → implement` | 4 | 5th |
