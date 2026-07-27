#!/usr/bin/env python3
"""Sync tauri-runtime-cef from tauri-apps/tauri feat/cef branch.

Strategy: copy ALL upstream files (accepting upstream changes), but preserve
files that exist ONLY in the fork (config.rs, policy.rs, streaming.rs, compat.rs).
Modified files (permission.rs, request_handler.rs, etc.) get upstream's version
so the PR shows what changed — the user re-applies the fork's patches manually.
"""

import os
import shutil
import sys
from pathlib import Path

UPSTREAM = Path(
    os.environ.get("UPSTREAM_DIR", "/tmp/upstream/crates/tauri-runtime-cef")
)
FORK_ROOT = Path(os.environ.get("FORK_ROOT", "."))

# Files that exist only in the fork (not in upstream). These are always preserved.
FORK_ONLY_FILES = {
    "src/config.rs",
    "src/policy.rs",
    "src/streaming.rs",
    "src/compat.rs",
}


def main():
    upstream = UPSTREAM
    fork = FORK_ROOT

    copied = 0
    preserved = 0

    # Copy all upstream files, preserving fork-only files
    for f in upstream.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(upstream))

        if rel in FORK_ONLY_FILES:
            print(f"  PRESERVE (fork-only): {rel}")
            preserved += 1
            continue

        dest = fork / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        copied += 1

    # Verify fork-only files still exist
    for rel in FORK_ONLY_FILES:
        if not (fork / rel).exists():
            print(f"  WARNING: fork-only file missing: {rel}")

    print(f"  Copied {copied} from upstream, preserved {preserved} fork-only files")
    print("  Modified files now have upstream's version — re-apply patches in the PR.")


if __name__ == "__main__":
    main()
