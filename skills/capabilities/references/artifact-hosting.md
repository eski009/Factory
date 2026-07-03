# Artifact hosting

Only useful if you have the Artifact tool; the degraded path — writing plain HTML to a repo path and telling the user to open it locally — is always sufficient and is what `factory-design` and every other stage are written against by default.

## Design options

`factory-design` writes `items/<id>/design/options.html` as a self-contained file — the canonical artifact every downstream stage (packet, choice, resume) reads and reasons about. When the Artifact tool is available, additionally publish that same file as an artifact. This buys the human a one-click hosted view instead of a "go open this local file" instruction, and richer interaction (scrolling, resizing, whatever the artifact host provides) than a bare local file gets. It changes nothing about the content: the same options, the same `data-option="a"` sections, the same design-system tokens — published through a second channel, not redesigned for it.

The repo file stays the single source of truth. If the human's pick, the packet text, or any later stage ever needs to re-derive what the options were, it reads `items/<id>/design/options.html` — never the artifact. Treat the artifact purely as a view that happens to be convenient to open; regenerating or editing it without also updating the repo file would create two disagreeing copies, which is exactly what "canonical copy stays the repo file" is there to prevent.

## Status dashboard

The same upgrade applies to operational status: when the Artifact tool is available, publish a small dashboard built from `factory status --json` and `factory doctor --json` — the same data a human would otherwise get by running those commands and reading terminal output, laid out as a page instead of two JSON blobs. This is a convenience view over existing, already-authoritative data; it never becomes a place new state gets written, and nothing downstream should ever read status back out of the dashboard instead of calling `factory status`/`factory doctor` directly.

## Never required

Headless and scheduled runs (see `references/scheduling.md`) have no one to hand a hosted link to and no interactive session to host one from. In those runs, and in any run where the Artifact tool is absent, skip the publish step entirely and rely on the local HTML file — the degraded path is not a fallback to apologize for, it is the contract every option-generating and status-reporting stage is built to satisfy on its own.
