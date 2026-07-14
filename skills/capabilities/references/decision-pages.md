# Decision pages

Every human decision pause surfaces a clickable link to a visual HTML page of the options. Prefer a hosted Artifact URL when one is available because it opens on phone or desktop; otherwise use the local absolute `file://` URL. Never make a Markdown file the primary view while an HTML page exists.

`packet_html_path` names the visual packet at `docs/factory/packets/<id>.html`. The design gate's canonical HTML surface remains `.factory/items/<id>/design/options.html`; use that `options.html` ahead of other local artifacts when present.

The Markdown packet remains the durable text companion, not the preferred viewing surface. Every pause still has the HTML packet fallback even when it has no separate options artifact.
