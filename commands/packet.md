---
description: Render the review packet for a work item ($ARGUMENTS = item id)
---
Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py" --repo . packet $ARGUMENTS`,
read the file it prints, and relay its contents to the user with a one-line
recommendation of what to decide.
