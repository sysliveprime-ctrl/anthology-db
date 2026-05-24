#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy DB archives into a flat GitHub Release asset folder.")
    parser.add_argument("--db-root", required=True, help="Path to the game db folder.")
    parser.add_argument("--manifest", default="db_version.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    db_root = Path(args.db_root).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    files = manifest.get("files") or []
    out.mkdir(parents=True, exist_ok=True)

    for entry in files:
        rel = Path(str(entry["path"]).replace("\\", "/"))
        if len(rel.parts) < 3 or rel.parts[0].lower() != "db":
            raise ValueError(f"invalid DB manifest path: {entry['path']}")
        source = db_root / Path(*rel.parts[1:])
        asset_name = entry.get("asset_name") or rel.name
        target = out / asset_name
        if not source.exists():
            raise FileNotFoundError(source)
        shutil.copy2(source, target)
        print(f"{source} -> {target}")

    print(f"Staged {len(files)} file(s) in {out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
