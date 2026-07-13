# Artifact hosting

The Artifact tool hosts a self-contained HTML page as a link that opens on any device. The degraded path — writing plain HTML to a repo path and telling the user to open it locally — is always sufficient and is what `factory-design` and every other stage are written against by default, but a local `file://` page does not travel: it can't be opened from a phone, and "go open this local file" is a poor way to hand someone design options to look at.

## Design options

`factory-design` writes `items/<id>/design/options.html` as a self-contained file — the canonical artifact every downstream stage (packet, choice, resume) reads and reasons about. **Whenever design options are shown to a human in an interactive session and the Artifact tool is present, publishing that same file as an Artifact is the standard way to present them — not an optional extra.** A hosted Artifact opens from one link on phone or desktop, which is exactly what makes options reviewable wherever the human happens to be; a bare local file does not. It changes nothing about the content: the same options, the same `data-option="a"` sections, the same design-system tokens — published through a channel the human can actually open, not redesigned for it.

Surface the resulting Artifact URL where the human will look for it: it is the primary "view the options" link in the design packet and in the `waiting-human` exit reason, with the local `items/<id>/design/options.html` path named as the fallback for anyone working from the checkout. Publishing is only skipped when the tool is absent or there is no human to hand a link to (headless and scheduled runs — see below).

The repo file stays the single source of truth. If the human's pick, the packet text, or any later stage ever needs to re-derive what the options were, it reads `items/<id>/design/options.html` — never the Artifact. Treat the Artifact purely as the human-facing view; regenerating or editing it without also updating the repo file would create two disagreeing copies, which is exactly what "canonical copy stays the repo file" is there to prevent. When the options are regenerated on a rejection round, re-publish to the same Artifact (update in place, same file path — and same `url` for an Artifact first published in an earlier session) so the link the human already has keeps showing the current options.

### Publishing mechanics

The two representations differ only in their document wrapper, never in content:

- **Local `options.html` stays a complete standalone document** — its own `<!doctype html>`, `<head>` with `<meta name="viewport">`, the decision-block script, and the `<noscript>` line — because it has to render and finalize a pick from `file://` with no host around it. That is the canonical file; leave it whole.
- **The Artifact host wraps the published file in its own `<!doctype>/<head>/<body>` skeleton** (with a viewport meta and a CSS reset). So publish the options *body content* — the `<section data-option>` blocks, the decision block, and their inline `<style>`/`<script>` — without the document-level `<html>`/`<head>`/`<body>` tags. Write that body-only version to a scratch file and pass its path to the Artifact tool; do not point the tool at the canonical `options.html` (its `<head>`/`<noscript>` would be double-wrapped). Everything the human sees and clicks is identical either way.
- **Set a stable `title`, `favicon`, and one-line `description`** so the Artifact reads as one page across redeploys: title like `Design options — <id> <item title>`, a fixed favicon (e.g. `🎨`), kept the same every time this item's options are re-published. Load the `artifact-design` skill before publishing, as that tool requires.
- **Zero-network still holds:** the options page makes no external requests by construction, which is exactly what the Artifact host's strict CSP requires — inline everything, embed nothing remote.
- **Browser read-back is unaffected** (`references/browser-read.md`): the in-page "Record choice" capture reads the *local* `file://` page in the controlled browser, independent of the hosted Artifact. The Artifact is the cross-device viewing channel; the local page remains the session-live capture channel. Neither records a pick — every path still terminates in `factory choice`.

### Hosted surface is view-only for the pick

An Artifact is sandboxed and view-only: nothing in-session reads its console and no terminal runs its composed command, so the decision block's Record-choice control is genuinely inert there. Per factory-design's surface-adaptive requirement, the page branches on `window.location.protocol` and, on the hosted surface, **drops the Record-choice control** and leads with "reply with your pick and I'll record it" (the reply-in-session capture path, which the orchestrator relays to `factory choice`). The local `file://` page keeps the full clickable flow. This is one canonical page with a runtime branch — never a second authored HTML variant.

## Status dashboard

The same upgrade applies to operational status: when the Artifact tool is available, publish a small dashboard built from `factory status --json` and `factory doctor --json` — the same data a human would otherwise get by running those commands and reading terminal output, laid out as a page instead of two JSON blobs. This is a convenience view over existing, already-authoritative data; it never becomes a place new state gets written, and nothing downstream should ever read status back out of the dashboard instead of calling `factory status`/`factory doctor` directly.

## Never required

Headless and scheduled runs (see `references/scheduling.md`) have no one to hand a hosted link to and no interactive session to host one from. In those runs, and in any run where the Artifact tool is absent, skip the publish step entirely and rely on the local HTML file — the degraded path is not a fallback to apologize for, it is the contract every option-generating and status-reporting stage is built to satisfy on its own.
