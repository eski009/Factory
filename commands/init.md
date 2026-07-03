---
description: Initialize this repo as a Factory target (scaffolds .factory/ and docs/factory/)
---
Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . init --product "$ARGUMENTS"` when arguments are given, otherwise drop `--product "$ARGUMENTS"`; then `... validate`.
Show the created paths. Then invoke the factory-intake skill to seed
docs/factory/brain/ from real sources ($ARGUMENTS names the product if given).
If the brain templates are still placeholders, tell the user triage will treat
empty surfaces as open questions.
