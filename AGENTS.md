# Repository Working Instructions

This repository contains the Factory product source, but it is not a Factory
pipeline target. Work on it directly.

## Workflow

- Do not invoke Factory commands, Factory skills, dispatch, autopilot, review
  gates, or other harness workflows for work in this repository.
- Do not create or restore a repository-root `.factory/` runtime directory.
  Tests may use isolated temporary fixtures where required.
- Work through the backlog as ordinary engineering work: inspect, implement,
  test, commit, and report evidence.
- Do not require a separate `PLAN.md` or stage transition unless the user asks
  for one.

## Models and delegation

- Use Astra at medium reasoning as the primary orchestrator.
- When code-execution delegation is explicitly requested and available, use
  GPT-5.6 Sol at xhigh reasoning.
- Preserve existing worktrees and unrelated dirty changes.

## Review and completion

- There is no fixed-count review loop and no three-review cap in this
  repository.
- Do not rerun reviews merely to obtain approval. Address concrete findings
  directly and use focused tests plus engineering evidence to decide whether
  the work is complete.
- Request an independent review only when the user asks for one or the risk of
  the change materially warrants it.

These instructions govern how the repository is developed. They do not prevent
editing or testing the Factory product, its CLI, hooks, skills, or packaging.
