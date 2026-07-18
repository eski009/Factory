---
name: factory-design
description: Use when a factory item is at stage design - generates 2-4 UI mockup options, parks the item for the human's pick
context: fork
---

Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`. Item paths like `items/<id>/...` live under `.factory/` — the full path is `.factory/items/<id>/...`.

This skill runs in a forked context (`context: fork`): nothing from the invoking session is visible here. The item id arrives as the skill argument; everything else is read from disk — `factory status --json`, `.factory/items/<id>/...`, and the brain surfaces this skill names below. Your final message is the report the dispatcher acts on: state the outcome (the stage advanced to, or the failure/pause reason, verbatim where a gate refused), name the key artifact paths written, and keep it to a few lines — never paste file contents into it.

For publishing the options page as a hosted artifact, see the capabilities skill's `references/artifact-hosting.md`.

## Contract

- **Entry stage:** `design` (only reachable for `kind: ui` or `kind: mixed` — `backend` items skip this stage entirely).
- **Entry check (a three-way branch on `items/<id>/design/choice.md`):**
  1. **Absent or empty** → proceed with normal option generation below.
  2. **Non-empty with `- option:` a–d** — the human has already chosen: skip option generation, run `factory advance ITEM plan`, delete `docs/factory/packets/<id>-design.md` if present, and exit.
  3. **Non-empty with `- option: none`** — the human rejected every direction; run the rejection round:
     - Count prior rejection rounds: N = the number of existing `items/<id>/design/feedback/round-*.md` files.
     - **Consume the answer:** move the full content of `choice.md` to `items/<id>/design/feedback/round-<N+1>.md`, then delete `design/choice.md`. The audit trail stays intact — the `design.choice` event (`{"option": "none"}`) is already in the item log and the commentary is preserved in the feedback file. With `choice.md` gone, the engine's plan gate mechanically refuses any advance to plan and dispatch's resume check goes quiet.
     - **If N+1 ≤ 2:** regenerate the options via the normal generation below, with every `items/<id>/design/feedback/round-*.md` file as required input — each new option must visibly respond to the commentary, and the regenerated design packet states, per option, what changed in answer to it. Then exit as normal: advance to `waiting-human` with a reason citing regeneration round N+1, and write packets.
     - **If N+1 > 2 (the cap: 2 regeneration rounds):** do not regenerate. Run `factory advance ITEM waiting-human --reason "two design regeneration rounds rejected; a human-authored steer is needed: see docs/factory/packets/<id>-design.md"`, and write a packet asking the human to either pick from the latest `options.html`, amend `spec.md`'s UI acceptance criteria, or supply an explicit direction in `--notes` with a pick.
- **Artifacts produced:** `items/<id>/design/options.html`, packet `docs/factory/packets/<id>-design.md`.
- **Exit:** `factory advance ITEM waiting-human --reason "pick a design option: see docs/factory/packets/<id>-design.md"`, then `factory packet ITEM`.

This skill never writes `design/choice.md`. The pick itself is recorded later, by the human in-session or by an orchestrator relaying their pick, via `factory choice ITEM OPTION [--notes TEXT]` — this skill's job ends at handing the human a packet to answer. Precisely: it never *authors a pick* into `choice.md`. Archiving a consumed `none` answer into `design/feedback/` — a move-and-delete performed only after the engine has already durably logged the `design.choice` event — is the one file operation this skill performs on `choice.md`, and it never creates or edits `choice.md` content.

## Design context

Read, in this order:

1. `docs/factory/brain/design-system.md` — always present, the headless fallback. This is the tokens surface every option must respect.
2. `items/<id>/spec.md`'s `## Acceptance criteria` — the UI surface the options must actually render.
3. If DesignSync is available (per the `capabilities` skill — probe: any `mcp__claude-design__*` tool present in the tool list, interactive sessions only) and `.factory/config.json` sets `designsync_project`, pull the linked Claude Design project's tokens via `mcp__claude-design__list_files` / `mcp__claude-design__read_file` as the preferred source over step 1. Write a dated snapshot of the pulled tokens to `items/<id>/design/claude-design-pull.md`, then mirror toward the brain the same way the thin-design-system bid below works: file a bid targeting `brain/design-system.md` via the `council-judgement` skill with that snapshot as `--evidence` — this skill never edits `design-system.md` directly; the brain changes only on an accepted judgement (mechanics: the capabilities skill's `references/designsync.md`). File that bid only when the snapshot differs from design-system.md's current tokens (see the reference). Log one spend event for the pull round-trip: `factory log ITEM spend --data '{"provenance":"proxy","stage":"design","source":"factory-design","note":"claude-design pull round-trip"}'` — provenance `proxy` with no `tokens` key, never estimated. A missing tool, a missing `designsync_project`, or a failed MCP call falls through silently to step 1 — never block or fail when it's absent; the design-system.md fallback is the contract, DesignSync is opportunistic.

If design-system.md is thin or placeholder (no real tokens, just scaffolding), don't stall on it: use restrained neutral defaults for the options, and file a bid targeting `brain/design-system.md` via the `council-judgement` skill so the gap becomes durable instead of getting silently re-decided by the next design item.

## The options page

Write one self-contained HTML file to `items/<id>/design/options.html`:

- Zero external requests — no CDN fonts, scripts, or images; no network calls of any kind.
- 2-4 options, each a labeled `<section data-option="a">` (etc.) headed "Option A — <direction name>", "Option B — <direction name>", and so on.
- Options must be **genuinely distinct directions** — differences in layout, structure, or interaction model — not palette or font swaps of the same underlying design. For example: single-column form vs. wizard flow vs. dashboard panel = three directions; the same layout in two palettes = one direction. If you can't name what structurally differs between two options, they're one option.
- Each option renders the item's actual UI surface from `spec.md` — real content and controls for this item, not lorem-ipsum or generic placeholder abstractions — and serves the primary persona in `docs/factory/brain/personas.md` (their goals and context, not a generic user).
- Respect the design-system tokens read above (colors, spacing, type scale).
- If the design system defines both light and dark treatments, render both for each option; if it only defines one, one is enough.

### The decision block (binding template requirements — chosen direction: inline per-option controls, item 0003)

Every options page also carries an interactive decision block, in the inline-per-option-controls pattern the human picked for item 0003. Each requirement below is binding, not a suggestion:

- **Recommendation first:** render this skill's single recommendation, with its one sentence of reasoning, visibly before the first pick button in the DOM.
- **Reversibility note:** render text stating the pick can be changed any time before the item resumes — re-run `factory choice` with a different option (behaviorally true: `record_choice` overwrites).
- **1:1 pick buttons, inline:** one pick button directly beneath each rendered option — `<button data-pick="a">` under `<section data-option="a">`, and so on — plus exactly one "None of these" block carrying `<button data-pick="none">`. No more, no fewer.
- **Commentary boxes, inline:** one `<textarea data-comment-for="a" maxlength="500">` (etc.) directly beneath each option's pick button, and one `<textarea data-comment-for="none" maxlength="500">` asking what's missing in the none-of-these block. Commentary is always optional — a bare pick submits with no `--notes`.
- **Notes convention (the page's script implements it):** one segment per commented option — `[a] <text>`, `[b] <text>`, … `[none] <text>` — in option order, only for non-empty comments, joined into a single line with ` | `. The script strips newlines and `|` from input, so the composed command survives phones and terminals and the segments stay greppable in `choice.md`.
- **Sticky command bar:** a bar fixed to the bottom of the viewport holding (a) a visible readonly command element containing the exact composed `factory choice <id> <opt> --notes '[x] …'` line, live-updated on every pick click and every commentary keystroke, with single quotes shell-escaped (`'` → `'\''`); clicking it selects the full text; (b) a Copy button that uses `navigator.clipboard` where available and falls back to selecting the text — no network either way; (c) the Record-choice control. The composed command is the page's one copy-pasteable next action.
- **Record-choice finalization (for browser read-back — see the capabilities skill's `references/browser-read.md`):** clicking "Record choice" (a) writes the final state as JSON — `{"item": "<id>", "option": "<opt>", "notes": "<composed notes>"}` — into `<output id="factory-choice" data-final="true">` in the DOM, and (b) emits `console.log("FACTORY_CHOICE " + <that JSON>)`. This is display/capture only — the page never writes files and never makes a request.
- **Surface-adaptive affordances (Option A, item 0012 — one canonical file, runtime branch):** the page branches on `window.location.protocol` at load; author ONE `options.html`, never two HTML variants. On the local `file:` surface, render the full block above — the sticky command bar with the composed command, Copy, and the Record-choice control — unchanged. On a hosted surface (an Artifact opened over `http`/`https`, where no in-session browser reads the page and no terminal is present), the Record-choice control is **not rendered** — it is the one affordance that is genuinely inert there — and instead a mode banner leads with "reply with your pick and I'll record it" (the ratified reply-in-session capture path), each option carries a copyable "reply: pick `<opt>`" chip that composes any per-option commentary the reviewer typed into the reply's notes segment (the same `[opt] text` convention as the composed command, so a phone pick never silently drops the note), and the composed `factory choice` command folds into a demoted "for terminal use" disclosure rather than being removed. Every other element — the options, per-option commentary, `<meta viewport>`, and the `<noscript>` line — renders identically on both surfaces. The `file:` surface keeps `<output id="factory-choice">`, the `FACTORY_CHOICE` console line, and the `<noscript>` fallback fully intact, so browser read-back (`references/browser-read.md`, which reads only the local `file://` DOM/console) is unaffected. A `window.location.protocol` read is not a network request; zero-network holds on both surfaces. Worked reference illustrating the branch: `.factory/items/0012-adapt-the-design-options-decision-block-/design/options.html`.
- **Degradation:** with JavaScript disabled, all options still render and a `<noscript>` line carries the verbatim CLI instruction. Include `<meta name="viewport" content="width=device-width, initial-scale=1">` so the page is usable from a phone. The page works from `file://` by construction: zero external requests, zero network calls, no server, no daemon, no local listener of any kind.

When the Artifact tool is present (per the `capabilities` skill), publishing the same file as an Artifact is the standard way to show these options to the human — do it, don't treat it as optional. A hosted Artifact opens from one link on phone or desktop, so the human can review the options wherever they are instead of being told to open a local file. Carry the resulting Artifact URL into the packet and the exit reason (below) as the primary "view the options" link. The local `items/<id>/design/options.html` file stays canonical either way — the Artifact is the human-facing view, not a second source of truth. On a regeneration round, re-publish to the same Artifact so the human's existing link shows the current options. Publishing is skipped only when the tool is absent or the run is headless/scheduled (no human to hand a link to) — then the local file and its CLI instruction are the whole contract.

Likewise, when DesignSync is available (per the `capabilities` skill) and `designsync_project` is set, additionally push `options.html` to the linked Claude Design project via `mcp__claude-design__write_files` (optionally `mcp__claude-design__render_preview`) as the same kind of convenience view. Annotate each pushed option with the journey nodes its screens serve, read from the item's `impact.json` (e.g. "J-004/N3 — invitation accepted"); the chosen-direction note carries the same node mapping. Best-effort: a failed push never blocks the Exit sequence below. The local file stays canonical here too, and nothing viewed, commented, or picked inside Claude Design records a decision — the pick still terminates in `factory choice`. Log one spend event for the push round-trip: `factory log ITEM spend --data '{"provenance":"proxy","stage":"design","source":"factory-design","note":"claude-design push round-trip"}'`.

## The design packet

Write `docs/factory/packets/<id>-design.md` directly — this is a bespoke packet, not the generic one `factory packet` writes, so author it by hand rather than calling that command here. Include:

- Where to view the options, as the first line: the Artifact URL when one was published this session (the link that opens on phone or desktop), with the local `items/<id>/design/options.html` path named as the fallback for anyone in the checkout. When no Artifact was published (tool absent or headless), give the local path only.
- One paragraph per option: the direction it takes, and its trade-offs.
- This skill's single recommendation, with one sentence of reasoning.
- How to answer: `factory choice <id> <option> [--notes "..."]` from any session in this repo, or reply in-session.
- One line documenting the notes convention: commentary rides in `--notes` as `[opt] text | …` segments, in option order.
- A line stating that "None of these" sends the item back to design regeneration with the commentary as input — it never advances the item toward plan.
- On a regeneration round: per option, what changed in answer to the round-N commentary.
- A note that the pick can be changed any time before the item resumes — just re-run `choice` with a different option.
- When a Claude Design pull happened this session: one disclosure line naming the token source (the linked project), the snapshot path, and the mirror bid status — including explicitly when the bid was rejected (e.g. "options were rendered from claude-design tokens the orchestrator declined to mirror").

## Exit

1. `factory advance ITEM waiting-human --reason "pick a design option: see docs/factory/packets/<id>-design.md"` — when an Artifact was published this session, append its URL to the reason (e.g. `... — view: <artifact-url>`) so the hosted link travels with the item's status, not only inside the packet.
2. `factory packet ITEM` — the generic status packet, written in addition to the bespoke design packet above.

## Resume

When the human runs `factory choice`, the dispatcher's step-0 resume check (in `factory-dispatch`) notices `design/choice.md` is present and non-empty on the next `/factory:run`, and unpauses the item back to `design` — regardless of which option it records. On the next dispatch iteration, this skill re-invokes at `design` stage. The entry check (above) routes on the recorded option: a pick (a–d) skips option generation, runs `factory advance ITEM plan`, and exits — the human's pick is now acted upon; `- option: none` runs the rejection round instead (archive to `design/feedback/`, then regenerate or escalate). This is the two-hop path: pause→resume unpause to design→entry check routes on the recorded option.

On that entry-check resume, when DesignSync is available (per the `capabilities` skill) and `designsync_project` is set, optionally push a short chosen-direction note (the picked option and any notes read from `design/choice.md`) to the linked Claude Design project via `mcp__claude-design__write_files` before advancing. Best-effort: a failed push never blocks `factory advance ITEM plan`, and the push never writes `design/choice.md` — it mirrors the recorded pick, it doesn't record one. Log one spend event for the push round-trip (same `"provenance":"proxy"` form as above). Headless resumes skip it entirely.

With a recorded pick, you MAY refresh the touched nodes' "what the customer expects" text in any affected still-draft contract, citing the chosen option — never an approved contract (those amend only through the council-judgement firewall), and never blocking the advance to plan.
