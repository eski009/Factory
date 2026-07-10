---
description: Research the product, market, and user and seed a cited persona - $ARGUMENTS = [<prd-path>] [<design-path>] [--depth inputs-only|web|deep] [--focus-group|--no-focus-group]
---
Parse $ARGUMENTS into an optional PRD path, an optional design-file path, an
optional --depth override, and an optional --focus-group or --no-focus-group
flag. Invoke the factory-research skill with them. Follow it exactly; it owns
depth handling, the council research mode, the opt-in focus-group step
(--focus-group forces it at any depth, --no-focus-group suppresses it at
deep), seeding docs/factory/brain/personas.md and market.md, and stating the
hard gate.
