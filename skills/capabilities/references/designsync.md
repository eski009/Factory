# DesignSync

DesignSync is the factory's name for mirroring design tokens and built UI between the repo and a linked Claude Design project, via the `mcp__claude-design__*` MCP tool family. It is only useful when that tool family and an interactive claude.ai login are available; the degraded path — repo-local `docs/factory/brain/design-system.md` tokens — is always sufficient and is what `factory-design` is written against by default. `docs/factory/brain/design-system.md` and `items/<id>/design/` stay canonical and cold-resumable; the linked project is a preferred interactive mirror, never a second source of truth.

## Tool family and probe

The concrete tool family is `mcp__claude-design__*`. The probe is presence of any tool in the family in the current session's tool list — check the list once, take the matching branch, and never retry a probe that already came back negative (per the capabilities SKILL.md). The steps below use these tools and no others:

- `mcp__claude-design__get_project` — resolve/confirm the linked project.
- `mcp__claude-design__list_files` / `mcp__claude-design__read_file` — pull the project's design tokens/system.
- `mcp__claude-design__write_files` — push convenience mirrors back to the project.
- `mcp__claude-design__render_preview` — optional convenience view of pushed files.

Conversation, sharing, and membership tools in the family are not part of this pattern.

## Linking a project

Linking is a one-time, per-repo manual step: resolve the Claude Design project id — via `mcp__claude-design__get_project` in an interactive session, or by reading it from claude.ai/design — and record it in `.factory/config.json` as `designsync_project`. That key already exists in `schemas/config.schema.json`, so this is pure reuse: no new key, no new command, and no schema diff. The config root schema is closed (`additionalProperties: false`), so any claude-design-specific key would require an engine schema change — see `docs/factory/brain/open-questions.md`, "Should skills get a config extension point?". Once set, every later session (with or without the MCP available) can see that the repo intends to use a linked design system, via `factory doctor`'s readout of that config key.

## Pull, and mirroring through the firewall

With a project linked and the MCP present in an interactive session, `factory-design` pulls the linked project's design tokens (colors, spacing, type scale) via `mcp__claude-design__list_files` / `mcp__claude-design__read_file` as the preferred source over `design-system.md` for the options it generates. Pulled tokens reach the brain **only** through the firewall:

1. Write a dated snapshot of the pulled tokens to `items/<id>/design/claude-design-pull.md` — tokens only, as sourced bullets matching design-system.md's existing shape.
2. File a bid targeting `brain/design-system.md` via the `council-judgement` skill, with that snapshot as `--evidence`. Cite pulled facts as `(source: claude-design project <id>, pulled <date>; snapshot items/<id>/design/claude-design-pull.md)` — the snapshot keeps the claim diffable and cold-verifiable in-repo even when the MCP is absent.
3. The orchestrator judges the bid; `design-system.md` changes only on an accepted judgement. The skill never edits `design-system.md` directly.

If the bid is rejected, the pulled tokens still govern this session's options; the brain stays unchanged. Either way the repo files stay canonical — the mirror bid is how headless runs inherit interactive pulls, never a bypass.

Compare the pulled token bullets against design-system.md's current recorded tokens first, and file the bid only when the snapshot differs — when the tokens are unchanged, skip the bid entirely, note "tokens unchanged — no mirror bid" in the run notes, and let the session proceed on the pulled tokens as usual. The first accepted mirror judgement replaces design-system.md's invented-neutrals fallback tokens bullet (which self-describes as replaceable) rather than accumulating beside it; later accepted mirrors update that same bullet.

## Push: convenience mirror, never a second writer

Pushed artifacts (options.html, a chosen-direction note, built output) are convenience mirrors in the linked project via `mcp__claude-design__write_files` (optionally `mcp__claude-design__render_preview`), exactly like the Artifact-tool pattern in `skills/factory-design/SKILL.md`: a convenience view, not a second source of truth. Nothing viewed, commented, or picked inside Claude Design records a decision — every design-gate decision still terminates in `factory choice` / `design.record_choice`, the sole writer of `design/choice.md`. Pushes never write `design/choice.md`, and a failed push never blocks a stage: at design time it never blocks the options exit or `factory advance ITEM plan`; at ship time it is never grounds for `ship.failed` and never delays `factory advance ITEM done`.

## Spend

Every MCP pull or push round-trip logs one spend event through the existing convention:

```
factory log ITEM spend --data '{"provenance":"proxy","stage":"<stage>","source":"<skill>","note":"claude-design <pull|push> round-trip"}'
```

Provenance is `proxy` with no `tokens` key, because main-loop MCP calls surface no harness token counts. Never estimate or invent token numbers, and never log `measured` without harness counts.

## Readout, not a gate

`factory doctor` surfaces `designsync_project` from config as a plain readout — it reports whether a project is linked, it never blocks or requires one. A repo with no linked project, or a session without the MCP available even though one is linked, simply falls through: `factory-design` reads `design-system.md` instead, exactly as it would if the MCP had never existed for this repo.

## Interactive-only

The `mcp__claude-design__*` family depends on an interactive claude.ai login, so it is never attempted in headless, scheduled, or autopilot runs (see `references/scheduling.md`) — those runs don't have a session to log in with, and pull/push semantics assume a human is available to reconcile the interaction if it comes back oddly. Autopilot and other unattended runs skip the pull/push entirely and rely on `design-system.md`, same as any session where the MCP simply isn't present. A missing tool, a missing `designsync_project` link, or a failed MCP call falls through silently to `design-system.md` — the degraded path is the tested contract, not an error state.

## Journeys

The journey model (`docs/factory/journeys/`) gets the same convenience-mirror
treatment as design tokens — repo files canonical, the linked project never a
second source of truth:

- **Visual map (push).** The pipeline surfaces that mutate the journey model —
  factory-intake at the end of seeding, factory-spec when it registers a
  journey or drafts a contract, and `/factory:escape` after a `contract:`
  promotion — regenerate `factory-journeys.html` in the linked project via
  `mcp__claude-design__write_files`: one self-contained HTML flow view built
  from `graph.json` (nodes, transitions, criticality, contract status),
  replacing the previous file. Strictly best-effort: a failed push never
  blocks the stage. A round-trip logs one proxy spend event when an item
  is in scope (factory-spec's push, or an escape carrying `--item`);
  item-less pushes — intake's seeding-end regen — skip the spend log,
  since spend events are item-scoped.
- **Greenfield frame-pull (intake only).** A greenfield repo has no routes to
  mine, but a linked design project often holds the product's screens before
  any code exists. When the tool family is present and `designsync_project`
  is set, factory-intake reads the project's frame/flow structure
  (`mcp__claude-design__list_files` + `read_file`) and emits journey-inventory
  entries (inventory.md plus matching graph.json records, same J-NNN ids)
  from screen sequences — each cited
  `(source: claude-design <project>/<file>)`, criticality tagged
  `(assumption)`, `status: inventory`, never contracts/. Frames are
  hypotheses, not evidence: the init interview's normal assumption-harvest
  puts every inferred journey in front of the human. Without the capability,
  greenfield intake is unchanged.
- **What never happens here:** no pull ever touches `contracts/` (drafts are
  the spec stage's job; approved contracts amend only through the
  council-judgement firewall), and no design artifact ever substitutes for
  the assure stage's running-product evidence.
