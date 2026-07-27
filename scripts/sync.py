#!/usr/bin/env python3
"""Sync tauri-runtime-cef from tauri-apps/tauri feat/cef branch.

Strategy: for each file in upstream's src/, copy it to the fork UNLESS the fork
already has a version that differs from upstream. Files the fork created (not
in upstream) are always preserved. This means every fork modification — whether
a new module or a modified copy of an upstream file — survives the sync.

For Cargo.toml: resolve workspace-inherited fields and convert path deps.
"""

import os
import shutil
import sys
import tomllib
from pathlib import Path

UPSTREAM = Path(
    os.environ.get("UPSTREAM_DIR", "/tmp/upstream/crates/tauri-runtime-cef")
)
FORK_ROOT = Path(os.environ.get("FORK_ROOT", "."))
OVERLAY_CONFIG = FORK_ROOT / ".overlay.toml"


def load_config() -> dict:
    if not OVERLAY_CONFIG.exists():
        print("ERROR: .overlay.toml not found", file=sys.stderr)
        sys.exit(1)
    with open(OVERLAY_CONFIG, "rb") as f:
        return tomllib.load(f)


def files_equal(a: Path, b: Path) -> bool:
    """Compare two files by content."""
    if not a.exists() or not b.exists():
        return False
    return a.read_bytes() == b.read_bytes()


def sync_src_files(config: dict) -> tuple[int, int, int]:
    """Copy upstream src/ files, preserving any fork file that differs.

    Returns (copied, preserved, new_files) counts.
    """
    force_overwrite = set(config.get("force-overwrite", []))
    upstream_src = UPSTREAM / "src"
    fork_src = FORK_ROOT / "src"

    copied = 0
    preserved = 0

    for f in upstream_src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(upstream_src)
        dest = fork_src / rel

        rel_str = str(rel)
        if rel_str in force_overwrite:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied += 1
            continue

        if dest.exists():
            if files_equal(f, dest):
                # Identical — no action needed (already in sync)
                continue
            else:
                # Fork has a modified version — preserve it
                print(f"  PRESERVE: {rel}")
                preserved += 1
        else:
            # New file from upstream — copy it
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            copied += 1

    # Count fork-only files (exist in fork, not in upstream)
    new_files = 0
    if fork_src.exists():
        upstream_rels = set(
            str(f.relative_to(upstream_src))
            for f in upstream_src.rglob("*")
            if f.is_file()
        )
        for f in fork_src.rglob("*"):
            if f.is_file() and str(f.relative_to(fork_src)) not in upstream_rels:
                print(f"  FORK-ONLY: {f.relative_to(fork_src)}")
                new_files += 1

    return copied, preserved, new_files


def sync_cargo_toml(config: dict) -> None:
    """Resolve workspace-inherited fields and convert path deps in Cargo.toml.

    Reads upstream's Cargo.toml, resolves all .workspace = true fields to
    concrete values from .overlay.toml, converts path deps to version deps,
    and writes the result.
    """
    upstream_toml = UPSTREAM / "Cargo.toml"
    fork_toml = FORK_ROOT / "Cargo.toml"

    # Read upstream as text to preserve structure
    content = upstream_toml.read_text()

    cargo_cfg = config.get("cargo", {})
    pkg_overrides = cargo_cfg.get("package", {})
    dep_versions = cargo_cfg.get("dep-versions", {})

    # Resolve workspace-inherited package fields via string replacement
    for key, value in pkg_overrides.items():
        if isinstance(value, list):
            val_str = "[" + ", ".join(f'"{v}"' for v in value) + "]"
        else:
            val_str = f'"{value}"'
        if f"{key}.workspace = true" in content:
            content = content.replace(f"{key}.workspace = true", f"{key} = {val_str}")
        elif f"\n{key} = " not in content:
            # Field doesn't exist upstream — insert after the version line
            version_line = 'version = "0.1.0"'
            content = content.replace(
                version_line,
                version_line + "\n" + f"{key} = {val_str}",
            )

    # Convert path deps to version deps
    for dep_name, new_version in dep_versions.items():
        # Match patterns like: tauri-runtime = { version = "x", path = "../tauri-runtime" }
        # and: tauri-utils = { version = "x", path = "../tauri-utils", features = [...] }
        import re

        # Remove path = "..." from dep specs, keep version and other fields
        pattern = rf'({dep_name}\s*=\s*\{{[^}}]*?)\s*path\s*=\s*"[^"]*",?\s*'
        content = re.sub(pattern, r"\1", content)
        # Clean up any trailing commas left behind
        content = re.sub(r",\s*}", "}", content)

    # Append dev-dependencies that the fork adds but upstream doesn't have
    dev_deps = cargo_cfg.get("dev-dependencies", [])
    if dev_deps:
        content = content.rstrip()
        content += "\n\n[dev-dependencies]\n"
        for dep in dev_deps:
            name = dep["name"]
            version = dep["version"]
            extras = []
            if dep.get("default-features") is False:
                extras.append("default-features = false")
            if dep.get("features"):
                feats = ", ".join(f'"{f}"' for f in dep["features"])
                extras.append(f"features = [{feats}]")
            if extras:
                content += f'{name} = {{ version = "{version}", {" ".join(extras)} }}\n'
            else:
                content += f'{name} = "{version}"\n'

    fork_toml.write_text(content)
    print(f"  Resolved Cargo.toml")


def main():
    config = load_config()
    print("=== Syncing src/ files ===")
    copied, preserved, new_files = sync_src_files(config)
    print(
        f"  Copied {copied} from upstream, preserved {preserved} modified, {new_files} fork-only"
    )
    print("\n=== Resolving Cargo.toml ===")
    sync_cargo_toml(config)
    print("  Done")


if __name__ == "__main__":
    main()
