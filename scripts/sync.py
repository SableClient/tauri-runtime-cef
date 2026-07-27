#!/usr/bin/env python3
"""Sync tauri-runtime-cef from tauri-apps/tauri feat/cef branch.

Copies upstream files, preserves local overlay modules, resolves
workspace-inherited Cargo.toml fields, and converts path deps to version deps.
"""

import os
import shutil
import sys
import tomllib
from pathlib import Path

try:
    import tomli_w
except ImportError:
    tomli_w = None  # only needed for writing TOML; we use plain string manipulation

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


def sync_src_files(config: dict) -> list[str]:
    """Copy upstream src/ files, skipping overlay modules."""
    overlay_files = set()
    for path in config.get("overlay", []):
        # Normalize to relative-from-src form
        rel = path.replace("src/", "", 1) if path.startswith("src/") else path
        overlay_files.add(rel)

    copied = []
    upstream_src = UPSTREAM / "src"
    fork_src = FORK_ROOT / "src"

    for f in upstream_src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(upstream_src)
        if str(rel) in overlay_files:
            print(f"  PRESERVE: {rel}")
            continue
        dest = fork_src / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        copied.append(str(rel))

    return copied


def sync_cargo_toml(config: dict) -> None:
    """Resolve workspace-inherited fields and convert path deps."""
    upstream_toml = UPSTREAM / "Cargo.toml"
    fork_toml = FORK_ROOT / "Cargo.toml"

    with open(upstream_toml, "rb") as f:
        upstream = tomllib.load(f)

    cargo_cfg = config.get("cargo", {})
    pkg_overrides = cargo_cfg.get("package", {})
    dep_versions = cargo_cfg.get("dep-versions", {})

    # Resolve workspace-inherited package fields
    pkg = upstream.get("package", {})
    for key, value in pkg_overrides.items():
        pkg[key] = value

    # Remove any remaining .workspace = true references (shouldn't happen after above)
    # by checking all package fields

    # Convert path deps to version deps
    deps = upstream.get("dependencies", {})
    for dep_name, dep_spec in list(deps.items()):
        if isinstance(dep_spec, dict) and "path" in dep_spec:
            new_version = dep_versions.get(dep_name)
            if new_version:
                # Preserve features and other fields, drop path
                new_spec = {k: v for k, v in dep_spec.items() if k != "path"}
                new_spec["version"] = new_version
                deps[dep_name] = new_spec
                print(f"  DEP: {dep_name} path -> version={new_version}")

    # Target-specific deps too
    for target_key, target_deps in upstream.get("target", {}).items():
        if not isinstance(target_deps, dict):
            continue
        for dep_name, dep_spec in list(target_deps.items()):
            if dep_name == "dependencies" and isinstance(dep_spec, dict):
                for dn, ds in list(dep_spec.items()):
                    if isinstance(ds, dict) and "path" in ds:
                        nv = dep_versions.get(dn)
                        if nv:
                            ns = {k: v for k, v in ds.items() if k != "path"}
                            ns["version"] = nv
                            dep_spec[dn] = ns

    # Write the resolved Cargo.toml
    # Use a simple manual serializer since we want to preserve order and formatting
    write_cargo_toml(fork_toml, upstream)


def write_cargo_toml(path: Path, data: dict) -> None:
    """Write Cargo.toml preserving key order, without external deps."""
    lines = []

    def serialize_value(v, indent=""):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            return f'"{v}"'
        if isinstance(v, list):
            if not v:
                return "[]"
            if len(v) == 1:
                return f'["{v[0]}"]' if isinstance(v[0], str) else f"[{v[0]}]"
            inner = ", ".join(
                f'"{item}"' if isinstance(item, str) else str(item) for item in v
            )
            return f"[{inner}]"
        return str(v)

    def serialize_table(table: dict, prefix=""):
        for key, value in table.items():
            if isinstance(value, dict):
                # Check if it's a simple inline table (deps with version/features)
                if all(
                    k != "dependencies" and k != "target" and not isinstance(v, dict)
                    for k, v in value.items()
                ):
                    # Inline table
                    inner = ", ".join(
                        f"{k} = {serialize_value(v)}" for k, v in value.items()
                    )
                    lines.append(f"{prefix}{key} = {{ {inner} }}")
                else:
                    lines.append(f"{prefix}[{key}]")
                    for k, v in value.items():
                        if isinstance(v, dict) and not all(
                            not isinstance(x, dict) for x in v.values()
                        ):
                            lines.append(f"{prefix}[{key}.{k}]")
                            for k2, v2 in v.items():
                                lines.append(f"{prefix}{k2} = {serialize_value(v2)}")
                        elif isinstance(v, dict):
                            inner = ", ".join(
                                f"{k2} = {serialize_value(v2)}" for k2, v2 in v.items()
                            )
                            lines.append(f"{prefix}{k} = {{ {inner} }}")
                        else:
                            lines.append(f"{prefix}{k} = {serialize_value(v)}")
                    lines.append("")
            else:
                lines.append(f"{prefix}{key} = {serialize_value(value)}")

    # [package]
    pkg = data.get("package", {})
    lines.append("[package]")
    for k, v in pkg.items():
        if isinstance(v, list):
            lines.append(f"{k} = {serialize_value(v)}")
        else:
            lines.append(f"{k} = {serialize_value(v)}")
    lines.append("")

    # [dependencies]
    deps = data.get("dependencies", {})
    if deps:
        lines.append("[dependencies]")
        for k, v in deps.items():
            if isinstance(v, dict):
                inner = ", ".join(
                    f"{dk} = {serialize_value(dv)}" for dk, dv in v.items()
                )
                lines.append(f"{k} = {{ {inner} }}")
            else:
                lines.append(f"{k} = {serialize_value(v)}")
        lines.append("")

    # [dev-dependencies]
    devdeps = data.get("dev-dependencies", {})
    if devdeps:
        lines.append("[dev-dependencies]")
        for k, v in devdeps.items():
            if isinstance(v, dict):
                inner = ", ".join(
                    f"{dk} = {serialize_value(dv)}" for dk, dv in v.items()
                )
                lines.append(f"{k} = {{ {inner} }}")
            else:
                lines.append(f"{k} = {serialize_value(v)}")
        lines.append("")

    # [target.*] sections
    for target_key, target_data in data.get("target", {}).items():
        if not isinstance(target_data, dict):
            continue
        for section, section_data in target_data.items():
            if not isinstance(section_data, dict):
                continue
            lines.append(f"[target.'{target_key}'.{section}]")
            for k, v in section_data.items():
                if isinstance(v, dict):
                    inner = ", ".join(
                        f"{dk} = {serialize_value(dv)}" for dk, dv in v.items()
                    )
                    lines.append(f"{k} = {{ {inner} }}")
                else:
                    lines.append(f"{k} = {serialize_value(v)}")
            lines.append("")

    # [features]
    features = data.get("features", {})
    if features:
        lines.append("[features]")
        for k, v in features.items():
            lines.append(f"{k} = {serialize_value(v)}")
        lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    config = load_config()
    print("=== Syncing src/ files ===")
    copied = sync_src_files(config)
    print(f"  Copied {len(copied)} files from upstream")
    print("\n=== Resolving Cargo.toml ===")
    sync_cargo_toml(config)
    print("  Done")


if __name__ == "__main__":
    main()
