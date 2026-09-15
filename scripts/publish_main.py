#!/usr/bin/env python3
"""Publish regenerated, validated outputs with bounded non-fast-forward recovery.

Run only in a disposable Actions checkout: each attempt resets tracked files to
fresh origin/main. A retry regenerates against the new tree, including immutable
Star ID checks; it never force-pushes or rebases generated records blindly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

SUN_PATHS = [f"sun/{name}.json" for name in
             ("today", "history", "uk-solar", "voices", "press", "provenance")]


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def publish(regenerate, message: str, attempts: int = 3) -> dict:
    if run("git", "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise RuntimeError("publication requires a clean disposable checkout")
    for attempt in range(1, attempts + 1):
        run("git", "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main")
        run("git", "reset", "--hard", "origin/main")
        paths = regenerate()
        if not paths:
            raise RuntimeError("publication has no validated paths")
        run("git", "add", "--", *paths)
        changed = run("git", "diff", "--cached", "--quiet", check=False)
        if changed.returncode not in (0, 1):
            raise RuntimeError("cannot inspect staged publication")
        if changed.returncode:
            run("git", "commit", "-m", message)
            pushed = run("git", "push", "origin", "HEAD:refs/heads/main", check=False)
            if pushed.returncode:
                print(f"Push attempt {attempt}/{attempts} failed; refreshing and revalidating", file=sys.stderr)
                if attempt == attempts:
                    raise RuntimeError("publication push failed after bounded retries")
                continue
        return {"published_commit": run("git", "rev-parse", "HEAD").stdout.strip(),
                "paths": paths, "changed": bool(changed.returncode), "attempts": attempt}
    raise RuntimeError("publication did not complete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("sun", "star"))
    parser.add_argument("--as-of")
    parser.add_argument("--globalgrid-root")
    parser.add_argument("--globalgrid-commit")
    parser.add_argument("--body-file")
    parser.add_argument("--issue-number", type=int)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("CLI publication is restricted to disposable Actions checkouts")
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    def regenerate() -> list[str]:
        # Subprocesses reload production code after each fresh-main reset.
        if args.kind == "sun":
            if not all((args.as_of, args.globalgrid_root, args.globalgrid_commit)):
                parser.error("sun requires date and pinned source checkout")
            result = run(sys.executable, "scripts/build_sun.py", "--as-of", args.as_of,
                         "--globalgrid-root", args.globalgrid_root,
                         "--globalgrid-commit", args.globalgrid_commit, "--output", "sun")
            print(result.stdout)
            print(run(sys.executable, "scripts/validate_sun.py", "sun").stdout)
            return SUN_PATHS
        if not args.body_file or not args.issue_number:
            parser.error("star requires proposal body and issue number")
        path = run(sys.executable, "scripts/issue_to_star.py", "--body-file",
                   args.body_file, "--output-dir", "stars").stdout.strip()
        print(run(sys.executable, "scripts/star_contract.py", path).stdout)
        return [path]

    message = (f"data: update Sun Star {args.as_of}" if args.kind == "sun" else
               f"data: publish approved Star proposal #{args.issue_number}")
    result = publish(regenerate, message)
    args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
