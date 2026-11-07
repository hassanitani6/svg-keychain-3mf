#!/usr/bin/env python3
"""Check a proposed fix before you review it. Runs nothing from the issue; only pytest.

    git worktree add ../before main
    git worktree add ../after fix-branch
    python tools/triage/verify_fix.py --before ../before --after ../after \
        --test tests/test_engine.py::test_new_regression

Passes only if the new test FAILS on the old code, PASSES on the fixed code, and the
whole suite passes on the fixed code. Anything else prints why and exits non-zero.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def pytest(cwd: Path, *args: str, timeout: int) -> tuple[int, str]:
    # Each tree must import its own code, not whatever copy is installed in the environment.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(p) for p in (cwd / "src", cwd) if p.exists()),
           "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
                           cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout} s"
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def verify(before: Path, after: Path, test: str, timeout: int = 900) -> list[str]:
    problems = []
    test_file = test.split("::")[0]
    if not (after / test_file).is_file():
        return [f"{test} does not exist in the fixed checkout"]
    with tempfile.TemporaryDirectory() as tmp:
        # Run the NEW test against a copy of the OLD code, so "fails before" is a real check.
        old = Path(tmp) / "before"
        shutil.copytree(before, old, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".triage"))
        (old / test_file).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(after / test_file, old / test_file)
        code, out = pytest(old, test, timeout=timeout)
    if code == 0:
        problems.append("the regression test already passes on the old code, so it does not reproduce the bug")
    elif code != 1:
        problems.append(f"could not run the test on the old code (pytest exit {code}):\n{out}")
    code, out = pytest(after, test, timeout=timeout)
    if code != 0:
        problems.append(f"the regression test fails on the fixed code:\n{out}")
    code, out = pytest(after, timeout=timeout)
    if code != 0:
        problems.append(f"the full test suite fails on the fixed code:\n{out}")
    return problems


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    p.add_argument("--test", required=True, help="pytest node id, e.g. tests/test_x.py::test_y")
    p.add_argument("--timeout", type=int, default=900)
    a = p.parse_args(argv)
    problems = verify(a.before.resolve(), a.after.resolve(), a.test, a.timeout)
    if problems:
        print("NOT VERIFIED — do not merge:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1
    print("verified: test fails before, passes after, full suite passes after")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
