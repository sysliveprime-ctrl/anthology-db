#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ALLOWED_DIRS = {"configs", "mods"}


def is_db_archive(path: Path) -> bool:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"db", "xdb"}:
        return True
    if suffix.startswith("db") and suffix[2:].isdigit():
        return True
    if suffix.startswith("xdb") and suffix[3:].isdigit():
        return True
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def asset_name(rel_path: str) -> str:
    return rel_path.replace("/", "__").replace("\\", "__")


def build_manifest(db_root: Path, version: str, base_url: str) -> dict:
    files = []
    for part in sorted(ALLOWED_DIRS):
        root = db_root / part
        if not root.exists():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
            if not path.is_file() or not is_db_archive(path):
                continue
            rel = "db/" + path.relative_to(db_root).as_posix()
            stat = path.stat()
            files.append(
                {
                    "path": rel,
                    "asset_name": asset_name(rel),
                    "size": stat.st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {
        "version": version,
        "mode": "mirror",
        "base_url": base_url.rstrip("/") + "/",
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Anthology DB launcher update manifest.")
    parser.add_argument("--db-root", required=True, help="Path to the game db folder.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", default="db_version.json")
    args = parser.parse_args()

    db_root = Path(args.db_root).expanduser().resolve()
    if not db_root.exists():
        raise FileNotFoundError(db_root)
    manifest = build_manifest(db_root, args.version, args.base_url)
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} with {len(manifest['files'])} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
