# Headless workers (`factory work`)

`factory work <id>` runs one headless coding-agent worker in an item's
`factory/<id>` worktree and captures a normalized `items/<id>/worker/result.json`.
It is the out-of-process executor: the worker owns its own context, and the
orchestrator only ever reads the result packet.

## Command

```
factory work <id> [--backend claude|codex|stub] [--model M]
                  [--timeout S] [--network on|off] [--worktree PATH] [--json]
```

Exit codes: `0` succeeded (result `done`, `implement.completed` logged);
`1` usage/internal; `2` precondition refusal (not at `implement`, or no
unticked plan tasks); `3` worker attempted but failed — read `result.json`'s
typed `reason`. Phase A actually emits
`crash|timeout|no_changes|red_tests|rate_limited`; `auth` and `prep_failed`
are reserved for a later phase (auth-failure classification and the
dependency-prep step are not wired up yet).

## Config (`.factory/config.json` → `workers`)

Off by default. Keys: `enabled`, `backend` (default `claude`), `max_parallel`
(default 2), `timeout_seconds`, `network` (default `off`), `prep`,
`test_command`, `models.{claude,codex}`, `codex.sandbox`, `retry`.

## Auth (environment only)

Fleet/unattended mode uses **API keys**, not subscription tokens (which race
and expire mid-run): `ANTHROPIC_API_KEY` for `claude`, `OPENAI_API_KEY` for
`codex`. `factory doctor` reports presence without printing values.

## Autonomy / network

The worker runs autonomously **inside the worktree** (Claude
`--permission-mode acceptEdits`; Codex `-a never --sandbox workspace-write`).
Network is **off** by default — install dependencies in a prep step, not in
the worker. Codex enforces its sandbox at the OS level; Claude does not
(the network-off tool allowlist is best-effort — use a container for hard
isolation). `--permission-mode` is confirmed against the installed CLI at
run time (design spec open-question 1).

## Trust

Worker output is untrusted until it clears Factory's existing review +
verify + green-tests gates. `factory work` only fills the `implement`
station; nothing about the gates changes. Set `workers.test_command` so the
implement station has a real green-check: without it, a worker's plan-tick
happens with no independent test gate at this stage, and partial or broken
work is only caught later at the review/verify gates — `verify.green`
remains authoritative.

## `stub` backend

`--backend stub` is a test-only in-process backend (writes a file, commits,
returns a canned result); it never spawns a CLI. Used by the engine tests.
