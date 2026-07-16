---
description: File a post-assurance escape - something a human still found after the factory said done ($ARGUMENTS = the finding, in your own words)
---
Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

$ARGUMENTS is the finding. Identify the journey and node from
docs/factory/journeys/graph.json and inventory.md (ask the human one
clarifying question if genuinely ambiguous — they are present). Classify the
miss together: missing-journey, missing-node, missing-oracle,
missing-contract-detail, or review-rule-gap. Then file it:
`factory escape <journey> "<finding>" --miss-type <type> [--item <id>] [--node <N>] [--evidence <path>]...`
and read back the escape id.

If the finding is a functional bug (the product misbehaves, not just
incoheres), also run the factory-bug skill on the same finding and re-file
the escape with `--item <the new bug item id>` so the two records link.

An escape stays open until it is promoted into a durable check — say so.
When the human (or a later council judgement) lands the promotion, close it:
`factory promote <esc-id> --via <jdg-NNNN|test:path|contract:path|oracle:ref|decision:ref>`.
`factory status` nags the open count until then. Never file escapes on the
factory's own behalf — this command is for what a HUMAN found.
