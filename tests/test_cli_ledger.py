import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scripts.factory import factory
from scripts.factory.lib import initrepo, items, logs


class LedgerCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Factory Tests")
        self.git("config", "user.email", "factory@example.test")
        self.base = self.commit(
            "README.md", "base\n", "2026-01-01T10:00:00+00:00")
        self.head = self.commit(
            "docs/end.md", "end\n", "2026-01-01T14:00:00+00:00")
        initrepo.init(self.repo)
        self.item = "0001-example"
        items.save_item(self.repo, {
            "id": self.item,
            "title": "Example",
            "stage": "done",
            "kind": "backend",
            "created": "2026-01-01T09:00:00Z",
            "updated": "2026-01-01T12:00:00Z",
        }, "# Example\n")
        self.log_at("2026-01-01T09:00:00Z", "item.created")
        self.log_at(
            "2026-01-01T12:00:00Z", "stage.advance",
            {"from": "idea", "to": "done"})

        evidence = self.repo / "evidence/wave.txt"
        evidence.parent.mkdir()
        evidence.write_bytes(b"captured state")
        digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
        self.log_at("2026-01-01T13:00:00Z", "test.wave", {
            "wave_id": "wave-integrated",
            "purpose": "integrated",
            "stage": "verify",
            "command": ["python3", "-m", "unittest"],
            "started_at": "2026-01-01T12:30:00Z",
            "finished_at": "2026-01-01T13:00:00Z",
            "result": "passed",
            "tests": {"passed": 7, "failed": 0, "skipped": 1},
            "tested_sha": self.head,
            "green_sha": self.head,
            "shipping_ref": self.head,
            "flows": ["J-001:S1"],
            "shipped_flows": ["J-001:S1"],
            "screenshots": [{
                "path": "evidence/wave.txt",
                "sha256": digest,
                "flow": "J-001:S1",
                "state": "complete",
            }],
        })
        self.log_at("2026-01-01T12:00:00Z", "activity.span", {
            "span_id": "review-1",
            "category": "review",
            "started_at": "2026-01-01T11:00:00Z",
            "finished_at": "2026-01-01T12:00:00Z",
            "source": "independent-review",
        })
        (self.repo / ".factory/ledger-aliases.json").write_text(
            json.dumps({"AUD-7": {"item": self.item}}), encoding="utf-8")

    def tearDown(self):
        os.environ.pop("FACTORY_NOW", None)
        self.tmp.cleanup()

    def git(self, *args, env=None):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            ["git", "-C", str(self.repo), *args], check=True, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=merged).stdout.strip()

    def commit(self, rel, content, stamp):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.git("add", "--", rel)
        self.git("commit", "-q", "-m", f"change {rel}", env={
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
        })
        return self.git("rev-parse", "HEAD")

    def log_at(self, stamp, event, data=None):
        os.environ["FACTORY_NOW"] = stamp
        logs.append_event(self.repo, self.item, event, data)

    def invoke(self, *argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = factory.main(["--repo", str(self.repo), *argv])
        return code, stdout.getvalue(), stderr.getvalue()

    def files(self):
        return {
            path.relative_to(self.repo).as_posix(): path.read_bytes()
            for path in self.repo.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(self.repo).parts
        }

    def test_json_is_stable_separate_and_read_only(self):
        before = self.files()
        args = (
            "ledger", "--base", self.base, "--head", self.head,
            "--product-path", "apps/ios", "--json")
        first = self.invoke(*args)
        second = self.invoke(*args)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0)
        self.assertEqual(first[2], "")
        report = json.loads(first[1])
        self.assertEqual(set(report), {
            "run", "commits", "factory_items", "aliases", "timing",
            "waves", "warnings", "limits",
        })
        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(child) for child in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(child) for child in value))
            return set()
        self.assertTrue(
            {"total_work", "throughput", "velocity"}.isdisjoint(keys(report)))
        self.assertEqual(
            report["factory_items"]["completions"]["value"]["items"],
            [self.item])
        self.assertEqual(
            report["waves"]["value"]["rows"][0]["delivery_status"],
            "delivery-bound")
        self.assertEqual(before, self.files())

    def test_text_has_one_provenance_tag_per_line_and_all_sections(self):
        code, output, error = self.invoke(
            "ledger", "--base", self.base, "--head", self.head,
            "--product-path", "apps/ios")
        self.assertEqual((code, error), (0, ""))
        allowed = ("[measured]", "[proxy]", "[unmeasured]",
                   "[inventory]", "[warning]")
        for line in output.splitlines():
            self.assertEqual(sum(line.startswith(tag) for tag in allowed), 1,
                             line)
        for expected in (
                "[inventory] run:",
                "product-changing merges: count=0 shas=none",
                "admin-only commits: count=1",
                "Factory items current cumulative: count=1",
                "Factory item completions observed in run: count=1",
                "external aliases cumulative non-additive: count=1",
                "status=UNAVAILABLE",
                "[proxy] stage interval:",
                "[measured] activity span:",
                "[unmeasured] activity category test: UNMEASURED",
                "[unmeasured] activity category admin: UNMEASURED",
                "[measured] test wave:",
                "purpose=integrated result=passed",
                "tests=passed:7,failed:0,skipped:1",
                "delivery=delivery-bound",
                "shipped_flows=J-001:S1",
                "screenshots=1",
                "[warning] limit: commit counts are inventory",
        ):
            self.assertIn(expected, output)

    def test_text_escapes_multiline_fields_and_lists_every_completion_event(self):
        self.log_at(
            "2026-01-01T13:30:00Z", "stage.advance",
            {"from": "done", "to": "done"})
        self.log_at("2026-01-01T13:40:00Z", "activity.span", {
            "span_id": "admin-1",
            "category": "admin",
            "started_at": "2026-01-01T13:10:00Z",
            "finished_at": "2026-01-01T13:20:00Z",
            "source": "operator\n[measured] forged=1",
        })
        code, output, error = self.invoke(
            "ledger", "--base", self.base, "--head", self.head,
            "--product-path", "apps/ios")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(output.count("Factory completion event:"), 2)
        self.assertIn(r"source=operator\n[measured] forged=1", output)
        self.assertNotIn("\n[measured] forged=1", output)
        allowed = ("[measured]", "[proxy]", "[unmeasured]",
                   "[inventory]", "[warning]")
        for line in output.splitlines():
            self.assertEqual(sum(line.startswith(tag) for tag in allowed), 1,
                             line)

    def test_text_escapes_invalid_item_metadata_that_reader_surfaces(self):
        forged = "\u2028[measured] forged=1"
        meta, body = items.load_item(self.repo, self.item)
        meta["stage"] = "done" + forged
        items.save_item(self.repo, meta, body)
        unsafe_id = "0002-unsafe" + forged
        items.save_item(self.repo, {
            "id": unsafe_id,
            "title": "Unsafe",
            "stage": "done",
            "kind": "backend",
            "created": "2026-01-01T09:00:00Z",
            "updated": "2026-01-01T12:00:00Z",
        }, "")
        code, output, error = self.invoke(
            "ledger", "--base", self.base, "--head", self.head)
        self.assertEqual((code, error), (0, ""))
        self.assertIn(r"done\u2028[measured] forged=1=1", output)
        self.assertIn(r"0002-unsafe\u2028[measured] forged=1", output)
        self.assertNotIn("\u2028", output)
        self.assertFalse(any(line.startswith("[measured] forged=1")
                             for line in output.splitlines()))

    def test_refusals_are_stable(self):
        code, output, error = self.invoke(
            "ledger", "--base", "not-a-ref", "--head", self.head)
        self.assertEqual((code, output), (2, ""))
        self.assertTrue(error.startswith("refused: "))

        code, output, error = self.invoke(
            "ledger", "--base", self.base, "--head", self.head,
            "--product-path", "../outside")
        self.assertEqual((code, output), (2, ""))
        self.assertEqual(error, "refused: invalid product path: '../outside'\n")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = factory.main(["--repo", str(self.repo), "ledger"])
        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("the following arguments are required: --base, --head",
                      stderr.getvalue())

    def test_ledger_does_not_change_cost_output(self):
        before = self.invoke("cost", self.item)
        ledger_result = self.invoke(
            "ledger", "--base", self.base, "--head", self.head,
            "--product-path", "apps/ios")
        after = self.invoke("cost", self.item)
        self.assertEqual(ledger_result[0], 0)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
