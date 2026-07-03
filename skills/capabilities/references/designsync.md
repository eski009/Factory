# DesignSync

Only useful if DesignSync and an interactive claude.ai login are available; the degraded path — repo-local `docs/factory/brain/design-system.md` tokens — is always sufficient and is what `factory-design` is written against by default.

## Linking a project

When DesignSync is available and the session is logged in to claude.ai, link the repo to a design-system project by recording its project id in `.factory/config.json` as `designsync_project`. This is a one-time, per-repo setup step — once set, every later session (with or without DesignSync itself available) can see that the repo intends to use a linked design system, via `factory doctor`'s readout of that config key.

## What it upgrades

With a project linked and DesignSync available in the current session, `factory-design` prefers pulling that project's tokens over reading `design-system.md` — the linked project becomes the preferred source of colors, spacing, and type scale for the options it generates, ahead of the repo-local fallback. The relationship can run the other direction too: components built out in an item can be pushed back to the linked project, keeping the claude.ai/design source and the repo's built output in sync rather than letting them drift apart silently.

## Readout, not a gate

`factory doctor` surfaces `designsync_project` from config as a plain readout — it reports whether a project is linked, it never blocks or requires one. A repo with no linked project, or a session without DesignSync available even though one is linked, simply falls through: `factory-design` reads `design-system.md` instead, exactly as it would if DesignSync had never existed for this repo.

## Interactive-only

DesignSync depends on an interactive claude.ai login, so it is never attempted in headless or scheduled runs (see `references/scheduling.md`) — those runs don't have a session to log in with, and pull/push semantics assume a human is available to reconcile the interaction if it comes back oddly. Autopilot and other unattended runs skip the pull/push entirely and rely on `design-system.md`, same as any session where DesignSync simply isn't present.
