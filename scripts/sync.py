#!/usr/bin/env python3
"""Sync tauri-runtime-cef from tauri-apps/tauri feat/cef branch.

Copies ALL upstream files. Only preserves fork-only examples.
The PR diff shows every upstream change including overlay modules.
User re-applies fork patches on top manually.
"""

import os
import shutil
from pathlib import Path

UPSTREAM = Path(os.environ.get("UPSTREAM_DIR", "/tmp/upstream/crates/tauri-runtime-cef"))
FORK_ROOT = Path(os.environ.get("FORK_ROOT", "."))

FORK_ONLY_PRESERVE = {
    "examples/stream_probe.rs",
    "examples/sw_probe.rs",
}


def main():
    upstream = UPSTREAM
    fork = FORK_ROOT

    saved = {}
    for rel in FORK_ONLY_PRESERVE:
        p = fork / rel
        if p.exists():
            saved[rel] = p.read_bytes()

    copied = 0
    for f in upstream.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(upstream))
        dest = fork / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        copied += 1

    for rel, data in saved.items():
        p = fork / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    print(f"Copied {copied} from upstream, preserved {len(saved)} fork-only examples")


if __name__ == "__main__":
    main()
