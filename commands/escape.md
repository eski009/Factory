---
description: File a post-assurance escape - something a human still found after the factory said done ($ARGUMENTS = the finding, in your own words)
---
Below, `factory` means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo .`.

$ARGUMENTS is the finding. Identify the journey and node from
docs/factory/journeys/graph.json and inventory.md (ask the human one
clarifying question if genuinely ambiguous — they are present). Classify the
miss together: missing-journey, missing-node, missing-oracle,
missing-contract-detail, or review-rule-gap.

For a `missing-journey` miss, first register the journey (the human is
present): add it to `docs/factory/journeys/inventory.md` + `graph.json` as an
inventory-only entry with the next free J-NNN id, then file the escape under
that id — the schema requires a real journey id.

If the finding is a functional bug (the product misbehaves, not just
incoheres), run the factory-bug skill on the same finding first to get the
new bug item id. Then file the escape once:
`factory escape <journey> "<finding>" --miss-type <type> [--item <id>] [--node <N>] [--evidence <path>]...`
(pass the new bug item id as `--item` when the finding was a functional bug)
and read back the escape id.

An escape stays open until it is promoted into a durable check — say so.
When the human (or a later council judgement) lands the promotion, close it:
`factory promote <esc-id> --via <jdg-NNNN|test:path|contract:path|oracle:ref|decision:ref>`.
`factory status` nags the open count until then. Never file escapes on the
factory's own behalf — this command is for what a HUMAN found.
