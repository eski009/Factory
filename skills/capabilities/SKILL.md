---
name: capabilities
description: Use when a factory skill needs to fan out work, render design options, or schedule runs - defines probe-and-upgrade for optional tools
---

Factory skills are written against a degraded baseline that works on any Claude model, then upgrade opportunistically when a tool happens to be available. This skill is the one place that degradation logic lives; every stage skill cites it instead of re-deriving it.

| Capability | Probe | With it | Without it |
|---|---|---|---|
| Workflow tool | tool present in tool list | Fan out council rounds and independent plan tasks via Workflow | Parallel Task subagent dispatches in one message |
| Artifact tool | tool present in tool list | Host the options page as an artifact | Write HTML to `items/<id>/design/options.html` and tell the user to open it |
| DesignSync | tool present in tool list | Pull/push claude.ai/design tokens | Use `docs/factory/brain/design-system.md` tokens |
| Scheduled agents | tool present in tool list | `loop` mode runs on a schedule | User runs `/factory:run loop` manually |

Probe by attempting nothing: check the tool list. Never let a missing optional tool fail a stage — the degraded path is the contract, upgrades are opportunistic.

Apply this row by row: check the tool list once per capability you need, take the matching branch, and move on. Don't ask the user whether a tool is available, don't retry a probe that already came back negative, and don't block a stage on an absent capability — fall through to the "Without it" column and keep going.
