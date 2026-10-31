#!/usr/bin/env python3
"""Copy the latest render PNGs from build/ into tracked docs/renders/.

The render scripts write to build/ (git-ignored). This copies the finished
stills into docs/renders/ so the repo always shows the current board and case.

    python3 scripts/sync_renders.py           # copy, then commit docs/renders
    python3 scripts/sync_renders.py --check   # fail if docs/renders is behind

--check is what .githooks/pre-push runs. A missing build/ (fresh clone) is
not a failure: there is nothing newer to lose.
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCES = {
    "board": (REPO / "build" / "product-renders", "recorder-*.png"),
    "case": (REPO / "build" / "case-renders", "case-6061-*.png"),
}
DEST = REPO / "docs" / "renders"


def pairs():
    for sub, (src, pattern) in SOURCES.items():
        for png in sorted(src.glob(pattern)):
            yield png, DEST / sub / png.name


def main() -> int:
    check = "--check" in sys.argv[1:]
    stale = []
    copied = 0
    for src, dst in pairs():
        if dst.is_file() and filecmp.cmp(src, dst, shallow=False):
            continue
        if check:
            stale.append(dst.relative_to(REPO))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
        print("copied", dst.relative_to(REPO))
    if check and stale:
        print("docs/renders is behind build/. Run "
              "'python3 scripts/sync_renders.py' and commit:")
        for path in stale:
            print("  ", path)
        return 1
    if not check:
        print(f"sync_renders: {copied} updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
