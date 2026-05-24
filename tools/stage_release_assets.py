#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy DB archives into a GitHub Release asset folder.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest", default="db_version.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    files = manifest.get("files") or []
    out.mkdir(parents=True, exist_ok=True)

    for entry in files:
        source = repo_root / Path(str(entry["path"]).replace("\\", "/"))
        target = out / str(entry["asset_name"])
        if not source.exists():
            raise FileNotFoundError(source)
        shutil.copy2(source, target)
        print(f"{source} -> {target}")

    print(f"Staged {len(files)} file(s) in {out}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
