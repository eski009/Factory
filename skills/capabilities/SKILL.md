---
name: capabilities
description: Use when a factory skill needs to fan out work, render design options, or schedule runs - defines probe-and-upgrade for optional tools
---

Factory skills are written against a degraded baseline that works on any Claude model, then upgrade opportunistically when a tool happens to be available. This skill is the one place that degradation logic lives; every stage skill cites it instead of re-deriving it.

| Capability | Probe | With it | Without it |
|---|---|---|---|
| Workflow tool | tool present in tool list | Fan out council rounds and independent plan tasks via Workflow → see references/workflow-fanout.md | Parallel Task subagent dispatches in one message |
| Artifact tool | tool present in tool list | Host the options page as an artifact → see references/artifact-hosting.md | Write HTML to `items/<id>/design/options.html` and tell the user to open it |
| DesignSync | any `mcp__claude-design__*` tool present in tool list, or the built-in `DesignSync` tool | Pull/push the linked Claude Design project → see references/designsync.md | Use `docs/factory/brain/design-system.md` tokens |
| Scheduled agents | tool present in tool list | `loop` mode runs on a schedule → see references/scheduling.md | User runs `/factory:run loop` manually |
| Browser read-back | a browser-automation tool that can read page DOM/console is present in the tool list | Open the options page in the controlled browser; after the human clicks "Record choice", read the finalized `#factory-choice` state (or the `FACTORY_CHOICE` console line) and run `factory choice <id> <opt> --notes "…"` on their behalf → see references/browser-read.md | Human copies the page's composed `factory choice` command (or the packet's verbatim CLI line) and runs it |
| Browser drive | a browser-automation tool family that can navigate, click, type, screenshot, and read console/network is present (Playwright MCP, chrome-devtools MCP, Claude-in-Chrome) | factory-assure's journey-reviewer drives browser-borne journeys and captures screenshot/console/network evidence → see references/browser-drive.md | Browser-borne journeys are a blocker: the item parks waiting-human with a packet naming `factory waive` — never a silent pass; cli/api journeys proceed unaffected |
| Headless worker | `workers.enabled` true in `.factory/config.json` and the configured backend CLI (`claude`/`codex`) resolvable on `PATH` with its key env var set (or, for codex, `workers.codex.auth: "chatgpt"` plus a fresh `codex` login — `factory doctor` reports both) | Dispatch an item's implementation out-of-process via `factory work <id>`; with several independent items at `implement`, run the bounded parallel pool (the `factory-workers` skill) → see references/headless-workers.md | Today's in-process `superpowers:subagent-driven-development` path, unchanged |

Probe by attempting nothing: check the tool list. Never let a missing optional tool fail a stage — the degraded path is the contract, upgrades are opportunistic. In a forked or subagent context, optional MCP tools may be deferred rather than listed — attempt to load them via ToolSearch before concluding absence; a tool that cannot be loaded is absent, take the degraded path.

**Process patterns** (not capability-gated — these apply regardless of which tools or model are available): see references/orchestration-patterns.md for the seven patterns that make this factory's outcomes reproducible on any orchestrating model, and references/model-tiering.md for which model tier each kind of task needs.

Apply this row by row: check the tool list once per capability you need, take the matching branch, and move on. Don't ask the user whether a tool is available, don't retry a probe that already came back negative, and don't block a stage on an absent capability — fall through to the "Without it" column and keep going.
