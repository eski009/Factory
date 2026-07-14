# Market

_Seeded by `factory-research`. Every claim is cited `(source: …)` or marked `(assumption)`; unsourced findings belong in `open-questions.md`._

- **Category:** agentic coding orchestrators — specifically the **free
  workflow/methodology layer atop Claude Code**, not the metered cloud-agent
  tier. Nearest neighbors share Factory's distribution surface (the Claude
  Code plugin marketplace): Superpowers (free/MIT, source:
  https://claude.com/plugins/superpowers) and the Ralph Wiggum PRD-loop plugin
  (now official Anthropic, source:
  https://github.com/anthropics/claude-code/blob/main/plugins/ralph-wiggum/README.md)
  (source: .factory/runs/research/round-1/commercial.md).
- **Competitors:** ~8 in the researched set. Adjacent metered cloud agents:
  Devin — $20/mo + $2.25/ACU (source: https://devin.ai/pricing/); GitHub
  Copilot coding agent — issue→PR inside Actions, human-merge-gated (source:
  https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-cloud-agent);
  Cursor background agents — up to 8 parallel in isolated worktrees (source:
  https://cursor.com/changelog/0-50); OpenHands — open-source, model-agnostic,
  at-cost LLM passthrough (source: https://www.openhands.dev/). Same-layer:
  aider — git-native OSS pair programmer (source: https://aider.chat/),
  Superpowers, Ralph loops, and build-your-own via CrewAI/LangGraph (source:
  .factory/runs/research/evidence-pack.md §2).
- **Table-stakes / conventions:** repo context ingestion; PR-based delivery on
  isolated branches/worktrees; hard human review gates (Copilot agents cannot
  self-approve; CI waits for a human click — source:
  https://docs.github.com/en/copilot/concepts/agents/cloud-agent/risks-and-mitigations);
  agent-run tests before PR; cost metering/controls (Devin ACUs, Copilot
  premium requests, Cursor credits); sandboxing/least-privilege after
  cross-vendor prompt-injection demos (source:
  .factory/runs/research/evidence-pack.md §3;
  https://www.securityweek.com/claude-code-gemini-cli-github-copilot-agents-vulnerable-to-prompt-injection-via-comments/).
- **Gaps & differentiation:** no researched competitor combines a full
  idea→ship pipeline with a persistent, evidence-firewalled taste-memory
  council and per-seat reputation (source: README.md "It learns your taste";
  .factory/runs/research/evidence-pack.md §2). That mechanism targets the
  category's loudest pains: review noise, non-determinism, "almost right"
  slop, business-blindness (source: https://news.ycombinator.com/item?id=46766961;
  https://survey.stackoverflow.co/2025/ai/). Deterministic gates are parity,
  not a wedge — everyone gates on tests (source:
  .factory/runs/research/round-1/product.md). A structured design-direction
  gate appears in no researched competitor (source:
  .factory/runs/research/round-1/ui-taste.md). Known gaps vs conventions: no
  cost/effort visibility (three seats independently; see open-questions.md)
  and a generic review packet that shows artifact-existence booleans rather
  than decision substance (source: scripts/factory/lib/packet.py;
  .factory/runs/research/round-1/ui-taste.md).
- **Positioning notes:** hypothesis — **"the quality/taste layer for
  autonomous Claude Code runs"**: aimed at expert solo builders who already
  run agents overnight and personally pay the token bill; differentiated on
  predictable, taste-consistent output, not speed (source:
  .factory/runs/research/round-1/commercial.md). Commercial path is
  distribution (marketplace presence), not pricing — the sub-segment's price
  to users is $0 + their own tokens (source:
  .factory/runs/research/round-1/commercial.md). Threat: Anthropic absorbing
  loop techniques first-party (Ralph is already an official plugin), which
  compresses the window for third-party pipelines (source:
  https://github.com/anthropics/claude-code/blob/main/plugins/ralph-wiggum/README.md).
  Bug-domain corollary: a bug-fix loop (issue→PR) is copyable adjacent-tier
  table stakes — it is Copilot coding agent's canonical use case — so
  Factory's defensible wedge in the bug domain is the evidence-gated
  discipline itself (recorded repro before fix, engine-enforced at the plan
  gate; repro re-run + regression test as verify criteria enforced by the
  verify stage's Iron Law); scope and market bug features as verification
  discipline, not pipeline shape
  (source: .factory/items/0010-factory-bug-command-understand-replicate/reviews/round-1/commercial.md;
  .factory/runs/research/evidence-pack.md §2; authorized: judgement on bid-0039).
- **Assumptions:** the six-seat council's token-cost multiplier is inferred
  from the architecture, not measured (assumption — mirrored in
  open-questions.md); the Ralph-loop adopter profile transferring to Factory
  is a hypothesis (assumption); Devin ARR trajectory and Cursor surcharge
  figures come from secondary sources (source:
  .factory/runs/research/evidence-pack.md §2, marked "secondary").
