"""Exercise production publication against a real temporary Git remote."""
import contextlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import issue_to_star
import publish_main
import verify_pages


@contextlib.contextmanager
def at(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], stderr=subprocess.DEVNULL).decode().strip()


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        self.repo = root / "worker"
        self.other = root / "other"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(self.remote)],
                       check=True, capture_output=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.repo)], check=True, capture_output=True)
        git(self.repo, "config", "user.name", "Publication test")
        git(self.repo, "config", "user.email", "publication@example.invalid")
        (self.repo / "initial.txt").write_bytes(b"initial\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "initial")
        git(self.repo, "push", "origin", "main")
        subprocess.run(["git", "clone", str(self.remote), str(self.other)], check=True, capture_output=True)
        git(self.other, "config", "user.name", "Other publisher")
        git(self.other, "config", "user.email", "other@example.invalid")

    def write_other(self, path, content):
        target = self.other / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        git(self.other, "add", path)
        git(self.other, "commit", "-m", "concurrent change")
        git(self.other, "push", "origin", "main")

    def test_concurrent_push_rebuilds_against_fresh_main(self):
        bases = []
        def regenerate():
            bases.append(git(self.repo, "rev-parse", "HEAD"))
            Path("data.json").write_text('{"valid":true}\n')
            if len(bases) == 1:
                self.write_other("unrelated.txt", "preserve this\n")
            return ["data.json"]
        with at(self.repo):
            result = publish_main.publish(regenerate, "publish data")
        self.assertEqual(result["attempts"], 2)
        self.assertNotEqual(bases[0], bases[1])
        self.assertEqual(git(self.remote, "show", "main:unrelated.txt"), "preserve this")
        self.assertEqual(result["published_commit"], git(self.remote, "rev-parse", "main"))

    def test_identical_immutable_record_is_idempotent(self):
        record = {"id": "example", "value": 1}
        def regenerate():
            return [issue_to_star.publish(record, Path("stars")).as_posix()]
        with at(self.repo):
            first = publish_main.publish(regenerate, "publish")
            second = publish_main.publish(regenerate, "publish")
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["published_commit"], second["published_commit"])

    def test_concurrent_immutable_id_collision_rejected(self):
        calls = []
        def regenerate():
            path = issue_to_star.publish({"id": "example", "value": 1}, Path("stars"))
            calls.append(True)
            self.write_other("stars/example.star.json", '{"id":"example","value":2}\n')
            return [path.as_posix()]
        with at(self.repo), self.assertRaises(FileExistsError):
            publish_main.publish(regenerate, "publish")
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(git(self.remote, "show", "main:stars/example.star.json"))["value"], 2)

    def test_dirty_tracked_checkout_rejected(self):
        (self.repo / "initial.txt").write_text("user change\n")
        with at(self.repo), self.assertRaisesRegex(RuntimeError, "clean disposable"):
            publish_main.publish(lambda: ["initial.txt"], "publish")

    def test_push_failures_are_bounded(self):
        original = publish_main.run
        attempts = []
        def run(*args, **kwargs):
            if args[:2] == ("git", "push"):
                attempts.append(True)
                return subprocess.CompletedProcess(args, 1, "", "remote unavailable")
            return original(*args, **kwargs)
        def regenerate():
            Path("data.json").write_text("{}\n")
            return ["data.json"]
        with at(self.repo), patch.object(publish_main, "run", run), self.assertRaisesRegex(RuntimeError, "bounded retries"):
            publish_main.publish(regenerate, "publish")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(git(self.remote, "rev-list", "--count", "main"), "1")

    def test_pages_requires_built_descendant_with_same_bytes(self):
        published = git(self.repo, "rev-parse", "HEAD")
        self.write_other("other.txt", "unrelated")
        with at(self.repo):
            git(self.repo, "fetch", "origin")
            descendant = git(self.repo, "rev-parse", "origin/main")
            expected = verify_pages.committed_payloads(published, ["initial.txt"])
            self.assertTrue(verify_pages.verify_build({"commit": descendant, "status": "built"}, published, expected))
            self.assertFalse(verify_pages.verify_build({"commit": descendant, "status": "building"}, published, expected))
            self.write_other("initial.txt", "changed")
            git(self.repo, "fetch", "origin")
            self.assertFalse(verify_pages.verify_build({"commit": git(self.repo, "rev-parse", "origin/main"),
                                                       "status": "built"}, published, expected))

    def test_served_bytes_must_match(self):
        handler = partial(SimpleHTTPRequestHandler, directory=str(self.repo))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}/"
            result = verify_pages.verify_served(base, {"initial.txt": b"initial\n"}, "abc")
            self.assertEqual(result["initial.txt"]["bytes"], 8)
            with self.assertRaisesRegex(ValueError, "served bytes"):
                verify_pages.verify_served(base, {"initial.txt": b"wrong"}, "abc")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_pages_resolves_new_build_and_writes_success_proof(self):
        self.pages_orchestration("built")

    def test_pages_error_writes_failed_proof_and_raises(self):
        self.pages_orchestration("errored")

    def pages_orchestration(self, status):
        publication = Path(self.temp.name) / "publication.json"
        proof = Path(self.temp.name) / "proof.json"
        published = git(self.repo, "rev-parse", "HEAD")
        publication.write_text(json.dumps({"published_commit": published, "paths": ["initial.txt"]}))
        old = {"url": "builds/1", "status": "built", "commit": published}
        build = {"url": "builds/2", "status": status, "commit": published}
        responses = [
            {"source": {"branch": "main", "path": "/"}, "build_type": "legacy", "html_url": "https://example.invalid"},
            old, {"url": "builds/latest", "status": "queued"}, old, build,
        ]
        with at(self.repo), patch.dict(os.environ, {"GITHUB_REPOSITORY": "example/repo"}), \
             patch.object(sys, "argv", ["verify_pages", "--publication", str(publication), "--result", str(proof)]), \
             patch.object(verify_pages, "api", side_effect=responses) as mocked_api, \
             patch.object(verify_pages.time, "sleep"), \
             patch.object(verify_pages, "verify_served", return_value={"initial.txt": {"sha256": "test"}}):
            if status == "errored":
                with self.assertRaisesRegex(RuntimeError, "Pages build failed"):
                    verify_pages.main()
            else:
                verify_pages.main()
        result = json.loads(proof.read_text())
        self.assertEqual(result["pass"], status == "built")
        self.assertEqual(result["pages_build"]["url"], "builds/2")
        self.assertEqual(mocked_api.call_args_list[2].args, ("repos/example/repo/pages/builds", "POST"))


if __name__ == "__main__":
    unittest.main()
