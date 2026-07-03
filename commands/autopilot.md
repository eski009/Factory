---
description: Run the factory autonomously until the backlog drains or the budget is spent ($ARGUMENTS = optional budget hint)
---
Invoke the factory-autopilot skill, passing $ARGUMENTS as an optional budget hint
(empty means run until the backlog drains).
Follow it exactly; it owns the preflight, the dispatch loop, gate respect, and
termination — including never answering its own human gates.
