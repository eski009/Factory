"""AC1 - default-path invariance (item 0013).

Golden bytes for the default path (no `assure.attribution` key, no
attribution fields anywhere) captured from the pre-change engine and
committed under tests/fixtures/default_path/. Every later change to the
ship gate, the packet renderers or `status --json` must leave these bytes
untouched.

Temp-dir paths differ per run, so the ONLY normalisation applied before
comparison is replacing the repo root (and its file:// URI form) with the
literals <REPO> / <REPOURI>. Everything else is compared byte-for-byte.

Regenerate ONLY with:

    python3 -m tests.test_default_path_invariance --regenerate

and only when a change to the default path is deliberate and reviewed --
inspect `git diff tests/fixtures/default_path/` before committing.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import initrepo, items, logs, machine, packet, paths

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "default_path"
ITEM = "0001-thing"
FROZEN_NOW = "2026-07-03T12:00:00Z"


def build(repo, verdict="pass", marker=False):
    """A deterministic default-path fixture: a backend item parked at
    assure whose single scenario carries `verdict`, with no attribution
    anywhere and the stock config. No git: the default path never reaches
    a merge-base lookup."""
    initrepo.init(repo, product="demo")
    meta = {"id": ITEM, "title": "Thing", "stage": "assure", "kind": "backend",
            "tier": "feature", "journeys": "J-001", "priority": 1,
            "created": "2026-07-03T10:00:00Z",
            "updated": "2026-07-03T10:00:00Z"}
    items.save_item(repo, meta, "# Thing\n")
    item_dir = paths.item_dir(repo, ITEM)
    (item_dir / "spec.md").write_text("spec\n", encoding="utf-8")
    shots = item_dir / "assurance" / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "s1.txt").write_text("evidence\n", encoding="utf-8")
    verdicts = {"item": ITEM, "journeys": [{
        "id": "J-001", "surface": "cli",
        "scenarios": [{
            "id": "S1", "verdict": verdict, "expected": "e", "actual": "a",
            "evidence": [{"type": "transcript",
                          "path": "assurance/screenshots/s1.txt"}]}]}]}
    (item_dir / "assurance" / "verdicts.json").write_text(
        json.dumps(verdicts, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    if marker:
        logs.append_event(repo, ITEM, "stage.advance",
                          {"from": "plan", "to": "implement"})
    for event in ("implement.completed", "verify.green", "assure.passed"):
        logs.append_event(repo, ITEM, event)


def normalise(text, repo):
    repo = Path(repo)
    for value in sorted({repo.resolve().as_uri(), repo.as_uri()},
                        key=len, reverse=True):
        text = text.replace(value, "<REPOURI>")
    for value in sorted({str(repo.resolve()), str(repo)},
                        key=len, reverse=True):
        text = text.replace(value, "<REPO>")
    return text


def _gate_outcome(repo):
    try:
        machine.advance(repo, ITEM, "ship")
    except machine.GateError as exc:
        return f"refused: {exc}\n"
    return "advanced: ship\n"


def capture():
    """Every default-path surface AC1 pins, as normalised text."""
    out = {}
    for name, verdict in (("gate-pass.txt", "pass"), ("gate-fail.txt", "fail")):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            # Item 0025: the round-scoped gates key on the engine-written
            # entry-into-implement marker, so the gate captures seed it —
            # a first-round event then postdates the item's only entry
            # into implement and the golden bytes are unchanged. The
            # packet/status capture below stays marker=False: rendering
            # evaluates no gate, and its "Recent events" last-5 window
            # would otherwise show the extra line and change golden bytes.
            build(repo, verdict, marker=True)
            out[name] = normalise(_gate_outcome(repo), repo)
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        build(repo, "pass")
        out["packet.md"] = normalise(packet.render_packet(repo, ITEM), repo)
        out["packet.html"] = normalise(
            packet.render_packet_html(repo, ITEM), repo)
        buf = io.StringIO()
        with redirect_stdout(buf):
            factory.main(["--repo", str(repo), "status", "--json"])
        out["status.json"] = normalise(buf.getvalue(), repo)
    return out


class TestDefaultPathInvariance(unittest.TestCase):
    def setUp(self):
        os.environ["FACTORY_NOW"] = FROZEN_NOW

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)

    def test_default_path_bytes_unchanged(self):
        for name, text in sorted(capture().items()):
            golden = FIXTURES / name
            self.assertTrue(golden.exists(), f"missing golden: {name}")
            self.assertEqual(
                golden.read_text(encoding="utf-8"), text,
                f"default-path output changed: {name} "
                "(regenerate only for a deliberate, reviewed change)")


def _regenerate():
    os.environ["FACTORY_NOW"] = FROZEN_NOW
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(capture().items()):
        (FIXTURES / name).write_text(text, encoding="utf-8")
        print(f"wrote {FIXTURES / name}")


if __name__ == "__main__":
    if "--regenerate" in sys.argv:
        _regenerate()
    else:
        unittest.main()
