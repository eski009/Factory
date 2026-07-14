# Personas

_Seeded by `factory-research`. Every claim is cited `(source: …)` or marked `(assumption)`; unsourced traits belong in `open-questions.md`, not here._

## Primary persona

- **Label:** **"The Overnight Operator"** — an expert solo developer /
  founder-engineer already living in Claude Code.
- **Summary:** An experienced terminal-native developer (solo or in a tiny
  startup) who already runs coding agents unattended and pays the token bill
  personally. Hires Factory to carry features from idea to shipped while they
  sleep or do other work — and to give them review they can trust on code they
  didn't watch being written (source: .factory/runs/research/synthesis.md;
  README.md "See it run").
- **Context:** Sits in the ~31% minority of developers using AI agents at all
  (source: https://survey.stackoverflow.co/2025/ai/); a Claude Code Pro/Max
  subscriber or API payer, comfortable installing plugins by hand — the
  Factory+Superpowers install path preselects exactly this person
  (source: README.md "Install"). Skews to the startup-speed end of Anthropic's
  adoption data (source: https://www.anthropic.com/research/impact-software-development).
- **Goals:** Multiply personal throughput — the Ralph-loop pattern of overnight
  autonomous runs (e.g. "6+ repositories overnight for ~$297 in API costs",
  source: https://awesomeclaude.ai/ralph-wiggum) — with structure, memory, and
  auditability a bare bash loop doesn't give (source: .factory/runs/research/round-1/product.md).
- **Jobs-to-be-done:** (1) run a feature end-to-end unattended: "add → run →
  pick a design → run → shipped" (source: README.md); (2) turn a PRD into a
  triaged backlog that drains itself (source: README.md "Three ways to start");
  (3) get trustworthy, consistent review of agent-written code
  (source: .factory/runs/research/round-1/customer.md).
- **Pains:** fixing "almost right, but not quite" AI code — the category's #1
  frustration at 45%, with 66% saying it costs them time (source:
  https://survey.stackoverflow.co/2025/ai/); AI-review noise and run-to-run
  non-determinism (source: https://news.ycombinator.com/item?id=46766961);
  token bills outrunning subscriptions (source:
  https://news.ycombinator.com/item?id=48646276); agents losing business
  intent on long tasks (source: https://news.ycombinator.com/item?id=46766961).
- **Behaviors / drivers:** arrives pre-burned by AI review tools and is
  skeptical by default — trust in AI accuracy is ~29–33% with 46% actively
  distrusting (source: https://survey.stackoverflow.co/2025/ai/). Judges a
  council by whether its output is terse, consistent, and grounded in their
  own conventions, not by the concept (source: .factory/runs/research/round-1/customer.md).
  Expertise matters: verified success runs 28–33% for intermediate/expert
  sessions vs 15% for novices (source: https://www.anthropic.com/research/claude-code-expertise).
- **Voice:** "the signal to noise ratio is poor"; "it's non deterministic, so
  you end up with half a dozen commits, with each run noting different
  issues"; "you review the proposed review... Sounds incredibly pointless"
  (source: https://news.ycombinator.com/item?id=46766961); "Most of us are in
  the $700-$1000 range, and I don't feel like I really spend that much"
  (source: https://news.ycombinator.com/item?id=48646276).
- **Not for:** novices hoping the pipeline substitutes for judgment (the
  evidence says it won't — source: https://www.anthropic.com/research/claude-code-expertise);
  enterprise platform teams, whose requirements (hard merge gates, headless
  CI, multi-repo) are explicit v1 non-goals (source:
  docs/superpowers/specs/2026-07-03-software-factory-design.md §1 Non-goals;
  https://dora.dev/ai/).
- **Confidence & assumptions:** Medium confidence — a cited hypothesis, not
  observed Factory users; no direct user interviews or telemetry exist
  (assumption: the Ralph-loop adopter profile transfers to Factory). The
  persona's cost sensitivity is well-sourced, but Factory's actual
  cost-per-item is unmeasured (see open-questions.md). Secondary personas
  (startup teams adopting as a shared line) deferred — depth `web` produces
  one primary persona; re-run at `deep` for a persona set.
