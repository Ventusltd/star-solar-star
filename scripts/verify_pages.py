#!/usr/bin/env python3
"""Request a Pages build and prove its committed publication is served byte-for-byte."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from urllib.parse import quote


def api(endpoint: str, method: str = "GET") -> dict:
    return json.loads(subprocess.check_output(
        ["gh", "api", "--method", method, endpoint], text=True))


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def committed_payloads(commit: str, paths: list[str]) -> dict[str, bytes]:
    return {path: git("show", f"{commit}:{path}") for path in paths}


def verify_build(build: dict, published: str, expected: dict[str, bytes]) -> bool:
    if build["status"] != "built":
        return False
    built_commit = build["commit"]
    if subprocess.run(["git", "merge-base", "--is-ancestor", published, built_commit],
                      capture_output=True).returncode:
        return False
    # A descendant may change unrelated files, but must retain every payload.
    return committed_payloads(built_commit, list(expected)) == expected


def verify_served(base_url: str, expected: dict[str, bytes], commit: str) -> dict:
    hashes = {}
    for path, contents in expected.items():
        url = base_url.rstrip("/") + "/" + quote(path, safe="/")
        request = urllib.request.Request(url + "?commit=" + commit,
                                         headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=30) as response:
            served = response.read()
        if served != contents:
            raise ValueError(f"served bytes do not match {commit}:{path}")
        hashes[path] = {"url": url, "bytes": len(contents),
                        "sha256": hashlib.sha256(served).hexdigest()}
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=720)
    args = parser.parse_args()
    publication = json.loads(args.publication.read_text(encoding="utf-8"))
    repo = os.environ["GITHUB_REPOSITORY"]
    endpoint = f"repos/{repo}/pages"
    site = api(endpoint)
    if site["source"] != {"branch": "main", "path": "/"} or site["build_type"] != "legacy":
        raise RuntimeError("expected existing legacy Pages source main /")
    expected = committed_payloads(publication["published_commit"], publication["paths"])
    result = {**publication, "pass": False, "pages_request": None}
    try:
        previous_url = api(endpoint + "/builds/latest")["url"]
        requested = api(endpoint + "/builds", "POST")
        result["pages_request"] = requested
        # The API normally returns /latest. Resolve it to a new numeric build
        # before following it; a previous unrelated success is insufficient.
        build_url = requested["url"]
        deadline = time.monotonic() + args.timeout
        last_error = "Pages build pending"
        while time.monotonic() < deadline:
            build = api(build_url)
            if build_url.endswith("/latest"):
                if build["url"] == previous_url:
                    time.sleep(15)
                    continue
                build_url = build["url"]
            result["pages_build"] = {key: build.get(key) for key in
                                     ("url", "commit", "status", "created_at", "updated_at", "error")}
            if build["status"] == "errored":
                raise RuntimeError(f"Pages build failed: {build.get('error')}")
            if build["status"] == "built":
                git("fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
                if not verify_build(build, publication["published_commit"], expected):
                    raise RuntimeError("Pages built commit does not retain the publication")
                try:
                    result["served"] = verify_served(site["html_url"], expected,
                                                     publication["published_commit"])
                    result["pass"] = True
                    break
                except (OSError, ValueError) as error:
                    last_error = str(error)
            time.sleep(15)
        if not result["pass"]:
            raise TimeoutError(last_error)
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        result["verified_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    main()
