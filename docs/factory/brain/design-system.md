# Design System

<!-- Design tokens, component conventions, and visual language.
     Tokens here are the headless fallback when DesignSync is unavailable. -->

- Factory has no GUI of its own — its user-facing surfaces are slash commands,
  CLI output, and markdown documents (review packets, the roadmap, the brain)
  (source: commands/; docs/factory/; README.md "Under the hood").
- Documented document conventions: review packets are markdown files under
  `docs/factory/packets/` presenting 2–4 design options for a human choice;
  the README explains flows with mermaid diagrams (source: README.md;
  docs/factory/packets/).
- No visual tokens, theme files, or component library exist in this repo
  (source: repo inventory — no CSS/theme/token files present). Visual language
  for mockups Factory generates in target repos is governed per-target, not
  here; see open-questions.md for what remains undefined.
- Headless fallback tokens for factory-generated pages (first used by 0003's
  options page; replace with deliberate tokens when a human supplies them):
  system font stack; light `#fafaf8`/ink `#1a1a1a` and dark `#161614`/ink
  `#ececе8` via `prefers-color-scheme`; single accent `#2f5d3a` (dark:
  `#7dab88`); hairline borders `#e2e0da`/`#33332e`; 10px radii; monospace for
  commands (source: .factory/items/0003-interactive-decision-pages-clickable-cho/design/options.html;
  authorized: judgement on bid-0015).
- Packet house style for human-facing artifacts: one recommendation with one
  sentence of reasoning, evidence bullets with hard caps, and exactly one
  copy-pasteable next action. The design-gate packet
  (skills/factory-design/SKILL.md) exemplifies it; the generic packet
  renderer does not yet (scripts/factory/lib/packet.py:21-22 renders
  artifact-existence booleans). New human-facing artifacts must follow it
  (source: .factory/items/0001-focus-group-research-structured-intervie/reviews/round-1/ui-taste.md;
  authorized: judgement on bid-0003).

- **Missing-field refusals name the field with a single-token metavar**, never
  by respelling the whole value grammar: `no '- answer: <option>' line`, not
  `no '- answer: <continue|narrow|defer>' line` — the enum already repeats in
  the shared retry clause, so respelling it renders the same 24 characters
  twice on one line. House pattern: `no '- redesigns: N' line`,
  `no '- rework-edges: N' line`. Note the field name alone (`no '- answer:'
  line`) is *not* the fix: a literal paste of `- answer:` fails the value
  regex and re-fires the same arm with a byte-identical message, an unbreaking
  loop (source: .factory/items/0015-…/reviews/round-3/; authorized: judgement
  on bid-0127).
