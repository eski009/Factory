# Vision

<!-- What this product is, who it serves, what winning looks like.
     Every claim should cite a source: (source: <path-or-url>) -->

- Factory is a Claude Code plugin that turns a feature idea (or a whole PRD,
  or an existing codebase) into merged, tested code via an assembly line of
  AI specialists: triage → spec → design → plan → implement → review →
  verify → ship (source: README.md).
- The goal is autonomy with exactly one built-in class of human gate: choosing
  a UI design direction. Everything else runs on its own, and the gate set is
  configurable (source: README.md; docs/superpowers/specs/2026-07-03-software-factory-design.md §1 Goals).
- A council of six specialist seats (product, architecture, engineering
  quality, UI taste, customer, commercial) reviews work at triage and code
  review, files evidence-backed opinions, and — through an orchestrator-judged
  firewall — accrues durable memory of the target product's conventions, so
  reviews sharpen over time ("It learns your taste") (source: README.md; agents/).
- Winning looks like: portable across all Claude models (faster-model features
  are bonuses, never requirements), installable into any codebase with one
  plugin install plus one idempotent `init`, and fully auditable/resumable
  because all state is files — markdown, JSON, JSONL
  (source: docs/superpowers/specs/2026-07-03-software-factory-design.md §1 Goals).
- Factory succeeds the `superpowers-council` project, keeping its proven ideas
  (bounded council protocol, code-enforced memory firewall, derived
  reputation, review packets) and adding the missing execution pipeline
  (source: docs/superpowers/specs/2026-07-03-software-factory-design.md §1).
- Explicit v1 non-goals: running on non-Claude agents (Codex, Gemini CLI,
  Cursor), fully headless CI operation, and multi-repo/monorepo orchestration
  (source: docs/superpowers/specs/2026-07-03-software-factory-design.md §1 Non-goals).
