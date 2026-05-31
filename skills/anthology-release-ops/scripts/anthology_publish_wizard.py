#!/usr/bin/env python3
"""Small interactive publisher for Anthology DB and MO2 updates."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


WORKGIT_DIR = Path(r"E:\dev\Anthology-Work-Git")
HELPER = WORKGIT_DIR / "skills" / "anthology-release-ops" / "scripts" / "anthology_release_ops.py"
MODPACK_DIR = Path(r"D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods")
DB_SOURCE_DIRS = {
    "configs": Path(r"D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs"),
    "mods": Path(r"D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods"),
}

DB_REPO_URL = "https://github.com/sysliveprime-ctrl/anthology-db.git"
DB_MANIFEST_API = "https://api.github.com/repos/sysliveprime-ctrl/anthology-db/contents/db_version.json?ref=main"
MO2_MANIFEST_API = "https://api.github.com/repos/sysliveprime-ctrl/anthology-mo2-modpack/contents/version.json?ref=main"


class PublishError(RuntimeError):
    pass


def run(args: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    print("+", " ".join(args))
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout.rstrip())
        raise PublishError(f"Command failed with exit code {result.returncode}: {' '.join(args)}")
    return result.stdout if capture else ""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def next_version(current: str) -> str:
    today = time.strftime("%Y.%m.%d")
    parts = current.split(".")
    if len(parts) == 4 and ".".join(parts[:3]) == today:
        return f"{today}.{int(parts[3]) + 1}"
    return f"{today}.1"


def prompt(default: str, text: str) -> str:
    value = input(f"{text} [{default}]: ").strip()
    return value or default


def prompt_yes(text: str, yes: bool) -> bool:
    if yes:
        return True
    value = input(f"{text} [y/N]: ").strip().lower()
    return value in {"y", "yes", "д", "да"}


def github_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "AnthologyPublishWizard"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def github_manifest(url: str) -> dict:
    data = github_json(url)
    raw = base64.b64decode("".join(data["content"].split()))
    return json.loads(raw.decode("utf-8-sig"))


def git_status(root: Path) -> str:
    return run(["git", "status", "--short", "--branch"], cwd=root, capture=True).rstrip()


def git_short_status(root: Path) -> str:
    return run(["git", "status", "--short"], cwd=root, capture=True).strip()


def git_user_config(source_root: Path) -> tuple[str, str]:
    name = run(["git", "config", "user.name"], cwd=source_root, capture=True).strip()
    email = run(["git", "config", "user.email"], cwd=source_root, capture=True).strip()
    return name or "sysliveprime-ctrl", email or "sysliveprime-ctrl@users.noreply.github.com"


def db_asset_name(rel_path: str) -> str:
    return rel_path.replace("/", "_").replace("[", "").replace("]", "").replace(" ", "_")


def live_db_files() -> dict[str, dict]:
    files: dict[str, dict] = {}
    for folder, base in DB_SOURCE_DIRS.items():
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = (Path("db") / folder / path.relative_to(base)).as_posix()
            files[rel] = {
                "path": rel,
                "asset_name": db_asset_name(rel),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    return files


def summarize_db_changes(manifest_path: Path) -> dict[str, list[str]]:
    current = {entry["path"]: entry for entry in read_json(manifest_path).get("files", [])}
    live = live_db_files()
    added = sorted(set(live) - set(current))
    removed = sorted(set(current) - set(live))
    changed = sorted(
        path
        for path in set(live) & set(current)
        if live[path]["size"] != current[path].get("size") or live[path]["sha256"] != current[path].get("sha256")
    )
    return {"added": added, "changed": changed, "removed": removed}


def print_change_summary(title: str, changes: dict[str, list[str]]) -> None:
    print(f"\n{title}")
    for key in ("added", "changed", "removed"):
        items = changes[key]
        print(f"  {key}: {len(items)}")
        for item in items[:12]:
            print(f"    - {item}")
        if len(items) > 12:
            print(f"    ... and {len(items) - 12} more")


def summarize_mo2_changes() -> None:
    print("\nMO2 Git status")
    print(git_status(MODPACK_DIR))
    current = read_json(MODPACK_DIR / "version.json").get("version", "")
    bump = run(
        ["git", "log", "--grep", f"Bump modpack to {current}", "--format=%H", "-1"],
        cwd=MODPACK_DIR,
        capture=True,
    ).strip()
    if bump:
        commits = run(["git", "log", "--oneline", f"{bump}..HEAD"], cwd=MODPACK_DIR, capture=True).strip()
        print(f"\nMO2 commits after version {current}:")
        print(commits or "  none")
    else:
        print(f"\nCould not find previous bump commit for MO2 version {current}.")


def clean_temp_clone() -> Path:
    root = Path(tempfile.gettempdir()) / "anthology-db-release"
    if root.exists():
        shutil.rmtree(root)
    run(["git", "clone", DB_REPO_URL, str(root)])
    name, email = git_user_config(WORKGIT_DIR)
    run(["git", "config", "user.name", name], cwd=root)
    run(["git", "config", "user.email", email], cwd=root)
    return root


def publish_db(version: str, notes: str, yes: bool, dry_run: bool) -> None:
    changes = summarize_db_changes(WORKGIT_DIR / "db_version.json")
    print_change_summary("DB live files vs current manifest", changes)
    if not any(changes.values()):
        print("DB manifest already matches live files.")
        if not prompt_yes("Still bump DB version and upload assets?", yes):
            return
    if not prompt_yes(f"Publish DB {version}?", yes):
        return

    root = clean_temp_clone()
    args = [
        sys.executable,
        str(HELPER),
        "workgit",
        "--path",
        str(root),
        "--version",
        version,
        "--notes",
        notes,
    ]
    if dry_run:
        args.append("--dry-run")
    run(args)
    if not dry_run:
        run(["git", "pull", "--ff-only", "origin", "main"], cwd=WORKGIT_DIR)
        manifest = github_manifest(DB_MANIFEST_API)
        print(f"Verified DB API version: {manifest.get('version')} ({len(manifest.get('files', []))} files)")


def publish_mo2(version: str, notes: str, yes: bool, dry_run: bool) -> None:
    run(["git", "fetch", "origin", "main", "--prune"], cwd=MODPACK_DIR)
    summarize_mo2_changes()
    if not git_short_status(MODPACK_DIR):
        print("\nMO2 working tree is clean. This will still bump version.json so players redownload current main.zip.")
    if not prompt_yes(f"Publish MO2 {version}?", yes):
        return

    args = [sys.executable, str(HELPER), "modpack", "--version", version, "--notes", notes]
    if dry_run:
        args.append("--dry-run")
    run(args, cwd=WORKGIT_DIR)
    if not dry_run:
        manifest = github_manifest(MO2_MANIFEST_API)
        print(f"Verified MO2 API version: {manifest.get('version')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Anthology DB/MO2 publisher.")
    parser.add_argument("--target", choices=["db", "mo2", "all"], help="What to publish.")
    parser.add_argument("--version", help="Use the same version for selected targets.")
    parser.add_argument("--db-version", help="DB version override.")
    parser.add_argument("--mo2-version", help="MO2 version override.")
    parser.add_argument("--notes", help="Use the same notes for selected targets.")
    parser.add_argument("--db-notes", help="DB notes override.")
    parser.add_argument("--mo2-notes", help="MO2 notes override.")
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    parser.add_argument("--dry-run", action="store_true", help="Run checks and local writes, but skip push/upload in helper.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.target or prompt("all", "Что обновилось? db / mo2 / all").lower()
    if target not in {"db", "mo2", "all"}:
        raise PublishError("Target must be db, mo2, or all.")

    db_current = read_json(WORKGIT_DIR / "db_version.json").get("version", "0.0.0.0")
    mo2_current = read_json(MODPACK_DIR / "version.json").get("version", "0.0.0.0")

    if target in {"db", "all"}:
        default = args.version or args.db_version or next_version(db_current)
        db_version = args.db_version or args.version or prompt(default, "DB version")
        db_notes = args.db_notes or args.notes or prompt("Обновление DB Anthology.", "DB notes")
        publish_db(db_version, db_notes, args.yes, args.dry_run)

    if target in {"mo2", "all"}:
        default = args.version or args.mo2_version or next_version(mo2_current)
        mo2_version = args.mo2_version or args.version or prompt(default, "MO2 version")
        mo2_notes = args.mo2_notes or args.notes or prompt("Обновление MO2 модпака.", "MO2 notes")
        publish_mo2(mo2_version, mo2_notes, args.yes, args.dry_run)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
