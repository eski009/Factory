# Browser drive

The assure stage's driving capability: a browser-automation tool family
that can **navigate, click, type, screenshot, and read console/network**.
The probe is behavioral — match whichever family is present in the tool
list:

- Playwright MCP (`mcp__playwright__*` — e.g. browser_navigate,
  browser_click, browser_type, browser_take_screenshot,
  browser_console_messages, browser_network_requests)
- chrome-devtools MCP (`mcp__chrome-devtools__*` — navigate_page, click,
  fill, take_screenshot, list_console_messages, list_network_requests)
- Claude-in-Chrome browser tools (the `computer`/browser action family)

Any one family satisfies the capability; prefer the one already connected.
Never mix families within one journey walk.

## Evidence conventions

- Screenshots → `.factory/items/<id>/assurance/screenshots/<journey>-<node>-<n>.png`
  (or the family's native format), one per walk step that changed the screen.
- Console → append one JSON line per material message to
  `assurance/console.ndjson`: `{"journey", "node", "level", "text"}`.
- Network → append one JSON line per failure or unexpected request to
  `assurance/network.ndjson`: `{"journey", "node", "method", "url", "status"}`.
- verdicts.json evidence entries reference these files with types
  `screenshot | dom | console | network` (cli/api journeys use `transcript`).

## When the capability is absent

A browser-borne journey without a Browser drive family is a **blocker**:
record it in `assurance/blockers.md`, park the item `waiting-human`, and the
packet names the human's two honest exits — connect a browser family and
re-run the stage, or `factory waive <id> --reason "..."`. **Never a
silent pass; never "inspection passed."** Parking is not failing — the
capabilities doctrine ("never let a missing optional tool fail a stage")
survives because the stage refuses to *lie*, not because it crashes: the
degraded contract for assurance is an explicit human decision, exactly like
an unavailable stage skill in dispatch. cli/api journeys never need this
capability.
