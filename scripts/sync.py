#!/usr/bin/env python3
"""Sync tauri-runtime-cef from tauri-apps/tauri feat/cef branch.

Strategy: for each file in upstream's src/, copy it to the fork UNLESS the fork
already has a version that differs from upstream. Files the fork created (not
in upstream) are always preserved. This means every fork modification — whether
a new module or a modified copy of an upstream file — survives the sync.

Cargo.toml is also preserved if the fork's version differs from upstream —
the user manually resolves workspace fields and version bumps when merging.
"""

import os
import shutil
import sys
from pathlib import Path

UPSTREAM = Path(
    os.environ.get("UPSTREAM_DIR", "/tmp/upstream/crates/tauri-runtime-cef")
)
FORK_ROOT = Path(os.environ.get("FORK_ROOT", "."))


def files_equal(a: Path, b: Path) -> bool:
    """Compare two files by content."""
    if not a.exists() or not b.exists():
        return False
    return a.read_bytes() == b.read_bytes()


def sync_files() -> tuple[int, int, int]:
    """Copy upstream files, preserving any fork file that differs.

    Returns (copied, preserved, new_files) counts.
    """
    upstream_root = UPSTREAM
    fork_root = FORK_ROOT

    copied = 0
    preserved = 0

    for f in upstream_root.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(upstream_root)
        dest = fork_root / rel

        if dest.exists():
            if files_equal(f, dest):
                continue
            else:
                print(f"  PRESERVE: {rel}")
                preserved += 1
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied += 1

    # Count fork-only files
    new_files = 0
    upstream_rels = set(
        str(f.relative_to(upstream_root))
        for f in upstream_root.rglob("*")
        if f.is_file()
    )
    for f in fork_root.rglob("*"):
        if f.is_file() and str(f.relative_to(fork_root)) not in upstream_rels:
            # Skip non-source files
            if not any(f.name.endswith(ext) for ext in [".rs", ".toml"]):
                continue
            if f.name.startswith("."):
                continue
            print(f"  FORK-ONLY: {f.relative_to(fork_root)}")
            new_files += 1

    return copied, preserved, new_files


def main():
    print("=== Syncing files ===")
    copied, preserved, new_files = sync_files()
    print(
        f"  Copied {copied} from upstream, preserved {preserved} modified, {new_files} fork-only"
    )
    print("  Done — Cargo.toml preserved if modified, user resolves manually")


if __name__ == "__main__":
    main()
