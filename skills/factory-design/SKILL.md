---
name: factory-design
description: Use when a factory item is at stage design - generates 2-4 UI mockup options, parks the item for the human's pick
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths below (`items/<id>/...`) are shorthand for `.factory/items/<id>/...`.

## Contract

- **Entry stage:** `design` (only reachable for `kind: ui` or `kind: mixed` — `backend` items skip this stage entirely).
- **Entry check:** If `items/<id>/design/choice.md` exists and is non-empty, the human has already chosen — skip option generation, run `factory advance ITEM plan`, delete `docs/factory/packets/<id>-design.md` if present, and exit. Only proceed with normal generation if `choice.md` is absent or empty.
- **Artifacts produced:** `items/<id>/design/options.html`, packet `docs/factory/packets/<id>-design.md`.
- **Exit:** `factory advance ITEM waiting-human --reason "pick a design option: see docs/factory/packets/<id>-design.md"`, then `factory packet ITEM`.

This skill never writes `design/choice.md`. The pick itself is recorded later, by the human in-session or by an orchestrator relaying their pick, via `factory choice ITEM OPTION [--notes TEXT]` — this skill's job ends at handing the human a packet to answer.

## Design context

Read, in this order:

1. `docs/factory/brain/design-system.md` — always present, the headless fallback. This is the tokens surface every option must respect.
2. `items/<id>/spec.md`'s `## Acceptance criteria` — the UI surface the options must actually render.
3. If DesignSync is available (per the `capabilities` skill, interactive sessions only), pull the linked claude.ai/design project's tokens as the preferred source over step 1 — never block or fail when it's absent; the design-system.md fallback is the contract, DesignSync is opportunistic.

If design-system.md is thin or placeholder (no real tokens, just scaffolding), don't stall on it: use restrained neutral defaults for the options, and file a bid targeting `brain/design-system.md` via the `council-judgement` skill so the gap becomes durable instead of getting silently re-decided by the next design item.

## The options page

Write one self-contained HTML file to `items/<id>/design/options.html`:

- Zero external requests — no CDN fonts, scripts, or images; no network calls of any kind.
- 2-4 options, each a labeled `<section data-option="a">` (etc.) headed "Option A — <direction name>", "Option B — <direction name>", and so on.
- Options must be **genuinely distinct directions** — differences in layout, structure, or interaction model — not palette or font swaps of the same underlying design. For example: single-column form vs. wizard flow vs. dashboard panel = three directions; the same layout in two palettes = one direction. If you can't name what structurally differs between two options, they're one option.
- Each option renders the item's actual UI surface from `spec.md` — real content and controls for this item, not lorem-ipsum or generic placeholder abstractions.
- Respect the design-system tokens read above (colors, spacing, type scale).
- If the design system defines both light and dark treatments, render both for each option; if it only defines one, one is enough.

When the Artifact tool is present (per the `capabilities` skill), additionally publish the same file as an artifact for one-click viewing. The local `items/<id>/design/options.html` file stays canonical either way — the artifact is a convenience view, not a second source of truth.

## The design packet

Write `docs/factory/packets/<id>-design.md` directly — this is a bespoke packet, not the generic one `factory packet` writes, so author it by hand rather than calling that command here. Include:

- One paragraph per option: the direction it takes, and its trade-offs.
- This skill's single recommendation, with one sentence of reasoning.
- How to answer: `factory choice <id> <option> [--notes "..."]` from any session in this repo, or reply in-session.
- A note that the pick can be changed any time before the item resumes — just re-run `choice` with a different option.

## Exit

1. `factory advance ITEM waiting-human --reason "pick a design option: see docs/factory/packets/<id>-design.md"`
2. `factory packet ITEM` — the generic status packet, written in addition to the bespoke design packet above.

## Resume

When the human runs `factory choice`, the dispatcher's step-0 resume check (in `factory-dispatch`) notices `design/choice.md` is present and non-empty on the next `/factory:run`, and unpauses the item back to `design`. On the next dispatch iteration, this skill re-invokes at `design` stage. The entry check (above) detects the recorded choice in `design/choice.md`, skips option generation, runs `factory advance ITEM plan`, and exits — the human's pick is now acted upon. This is the two-hop path: pause→resume unpause to design→entry check advances to plan.
