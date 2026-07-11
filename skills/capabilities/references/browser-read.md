# Browser read-back: capturing the design pick without copy-paste

The options page's decision block finalizes the human's pick in-page: clicking "Record choice" writes `{"item", "option", "notes"}` JSON into `<output id="factory-choice" data-final="true">` and logs a matching `FACTORY_CHOICE <json>` console line. When a browser-automation tool that can read a live page's DOM or console is present in the tool list, an interactive session can capture that finalized state and run the engine command itself.

## The promise

In an interactive session where a browser-read tool is live and the human reviews the options page in that same session, they click and never copy-paste: open `items/<id>/design/options.html` in the controlled browser, let the human pick (and optionally comment), and after they click "Record choice", read the finalized `#factory-choice` element (or the `FACTORY_CHOICE` console line), parse the JSON, and run `factory choice <id> <opt> --notes "…"` on their behalf. The single-writer funnel is preserved because the *session*, not the page, invokes the engine — every capture path still terminates in `factory choice` / `design.record_choice`, the single writer of `design/choice.md`.

## Session-live only

Page state lives in a browser tab and dies with it. Nothing polls, nothing persists, nothing listens in the background. If the session ends, or the human reviews later or from another device, the answer arrives via the CLI line exactly as before — the page's composed command or the packet's verbatim `factory choice` line.

## Degradation

This capability is never required, never blocks, and never gates a stage: the zero-network `file://` page plus the composed CLI command is the contract; browser read-back is opportunistic. Explicit restatement of the zero-network rule: no server, no daemon, no loopback listener, no port bound anywhere — the page never makes a request, and adding a future listener of any kind requires a judgement amending the zero-network rule first.

## Probe

Probe by tool list, as always: any tool that can read a live page's DOM or console counts — named browser-automation tool families are illustrative examples, not requirements. A negative probe falls through silently to the "Without it" column: the human copies the composed command (or the packet's CLI line) and runs it.
