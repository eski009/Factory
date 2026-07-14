# Users

<!-- Who uses this product, their needs and workflows, what they're trying
     to accomplish. Every claim should cite a source: (source: <path-or-url>) -->

- The user is a developer working inside Claude Code who wants a feature idea
  carried to merged, tested code with minimal intervention — the README's
  whole loop is "add → run → pick a design → run → shipped"
  (source: README.md "See it run").
- Three documented entry workflows: a single idea (`/factory:add` then
  `/factory:run`), a whole PRD (`/factory:roadmap prd.md` → triaged,
  prioritized backlog), and an existing codebase (`/factory:init` mines
  routes, tests, conventions, git history before touching anything)
  (source: README.md "Three ways to start").
- The user-facing surface is nine slash commands — `/factory:init`, `add`,
  `bug`, `run`, `status`, `packet`, `autopilot`, `roadmap`, `research` — plus
  the `factory` CLI for direct engine calls like `factory choice <item> <a-d>`
  (source: commands/; README.md; authorized: judgement on bid-0049).
- The one interaction the product deliberately asks of the human is picking a
  design direction from 2–4 rendered mockup options in a review packet;
  backend-only items skip this (source: README.md "How it works").
- Users are expected to review what lands: the SessionStart hook surfaces
  factory state and packets awaiting human review at the start of each
  session (source: hooks/session-start.sh; hooks/hooks.json).
- Users must also install the Superpowers plugin — Factory delegates execution
  discipline (TDD, debugging, verification) to it rather than vendoring that
  logic (source: README.md "Install"; docs/getting-started.md §1).
