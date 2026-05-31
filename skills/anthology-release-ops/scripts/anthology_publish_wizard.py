#!/usr/bin/env python3
"""Small interactive publisher for Anthology DB and MO2 updates."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


WORKGIT_DIR = Path(r"E:\dev\Anthology-Work-Git")
HELPER = WORKGIT_DIR / "skills" / "anthology-release-ops" / "scripts" / "anthology_release_ops.py"
MODPACK_DIR = Path(r"D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods")
ENGINE_DIR = Path(r"E:\dev\xray-monolith")
ENGINE_BRANCH = "anthology-2026.5.8-mt-nanfix"
ENGINE_REPO = "sysliveprime-ctrl/xray-monolith"
ENGINE_BUILD_SCRIPT = Path(r"E:\dev\anomaly-codex-main\tools\build_anthology_engine.ps1")
LIVE_GAME_DIR = Path(r"D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1")
LIVE_BIN_DIR = LIVE_GAME_DIR / "bin"
LIVE_ENGINE_DB = LIVE_GAME_DIR / "db" / "mods" / "00_modded_exes_gamedata.db0"
DB_SOURCE_DIRS = {
    "configs": Path(r"D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs"),
    "mods": Path(r"D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods"),
}

DB_REPO_URL = "https://github.com/sysliveprime-ctrl/anthology-db.git"
DB_MANIFEST_API = "https://api.github.com/repos/sysliveprime-ctrl/anthology-db/contents/db_version.json?ref=main"
MO2_MANIFEST_API = "https://api.github.com/repos/sysliveprime-ctrl/anthology-mo2-modpack/contents/version.json?ref=main"
ENGINE_MANIFEST_API = (
    "https://api.github.com/repos/sysliveprime-ctrl/xray-monolith/contents/"
    "engine_version.json?ref=anthology-2026.5.8-mt-nanfix"
)

CSI = "\033["
RESET = f"{CSI}0m"
BOLD = f"{CSI}1m"
DIM = f"{CSI}2m"
CYAN = f"{CSI}36m"
GREEN = f"{CSI}32m"
YELLOW = f"{CSI}33m"
RED = f"{CSI}31m"
MAGENTA = f"{CSI}35m"


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
    value = input(f"{CYAN}{text}{RESET} [{default}]: ").strip()
    return value or default


def prompt_yes(text: str, yes: bool) -> bool:
    if yes:
        return True
    value = input(f"{YELLOW}{text}{RESET} [y/N]: ").strip().lower()
    if value in {"д", "да"}:
        return True
    return value in {"y", "yes", "д", "да"}


def clear_screen() -> None:
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def line(char: str = "=", width: int = 72) -> str:
    return char * width


def banner() -> None:
    clear_screen()
    print(f"{MAGENTA}{line('=')}{RESET}")
    print(f"{BOLD}{CYAN}  ANTHOLOGY RELEASE CONTROL{RESET}")
    print(f"{DIM}  DB assets, MO2 modpack, manifests, GitHub releases{RESET}")
    print(f"{MAGENTA}{line('=')}{RESET}\n")


def card_row(label: str, value: str, color: str = RESET) -> None:
    print(f"  {DIM}{label:<16}{RESET} {color}{value}{RESET}")


def current_versions() -> tuple[str, str, str]:
    db_current = read_json(WORKGIT_DIR / "db_version.json").get("version", "0.0.0.0")
    mo2_current = read_json(MODPACK_DIR / "version.json").get("version", "0.0.0.0")
    engine_current = read_json(ENGINE_DIR / "engine_version.json").get("version", "0.0.0.0")
    return db_current, mo2_current, engine_current


def print_dashboard(db_current: str, mo2_current: str, engine_current: str) -> None:
    print(f"{BOLD}Current state{RESET}")
    card_row("DB local", db_current, GREEN)
    card_row("MO2 local", mo2_current, GREEN)
    card_row("MT engine", engine_current, GREEN)
    print()
    print(f"{BOLD}What changed?{RESET}")
    print(f"  {CYAN}1{RESET}. DB only      {DIM}db/configs + db/mods release assets{RESET}")
    print(f"  {CYAN}2{RESET}. MO2 only     {DIM}MO2 main.zip + version.json{RESET}")
    print(f"  {CYAN}3{RESET}. MT engine    {DIM}build/deploy, package ZIP, upload release{RESET}")
    print(f"  {CYAN}4{RESET}. DB + MO2     {DIM}publish both content channels{RESET}")
    print(f"  {CYAN}5{RESET}. All          {DIM}DB + MO2 + MT engine{RESET}")
    print(f"  {CYAN}6{RESET}. Dry run      {DIM}preview checks without push/upload{RESET}")
    print(f"  {CYAN}7{RESET}. Exit\n")


def choose_target() -> tuple[str, bool]:
    while True:
        choice = input(f"{BOLD}Select action{RESET} [3]: ").strip().lower() or "3"
        mapping = {
            "1": ("db", False),
            "db": ("db", False),
            "2": ("mo2", False),
            "mo2": ("mo2", False),
            "3": ("engine", False),
            "engine": ("engine", False),
            "mt": ("engine", False),
            "движок": ("engine", False),
            "4": ("content", False),
            "content": ("content", False),
            "5": ("all", False),
            "all": ("all", False),
            "6": ("all", True),
            "dry": ("all", True),
            "dry-run": ("all", True),
            "7": ("exit", False),
            "exit": ("exit", False),
            "q": ("exit", False),
        }
        if choice in mapping:
            return mapping[choice]
        print(f"{RED}Unknown option. Use 1, 2, 3, 4, 5, 6, or 7.{RESET}")


def print_release_plan(
    target: str,
    dry_run: bool,
    db_version: str | None,
    mo2_version: str | None,
    engine_version: str | None,
) -> None:
    print()
    print(f"{BOLD}Release plan{RESET}")
    card_row("target", target.upper(), CYAN)
    card_row("mode", "DRY RUN" if dry_run else "PUBLISH", YELLOW if dry_run else GREEN)
    if db_version:
        card_row("DB version", db_version, GREEN)
    if mo2_version:
        card_row("MO2 version", mo2_version, GREEN)
    if engine_version:
        card_row("MT version", engine_version, GREEN)
    print()


def github_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "AnthologyPublishWizard"})
    with urlopen(req, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def github_manifest(url: str) -> dict:
    data = github_json(url)
    raw = base64.b64decode("".join(data["content"].split()))
    return json.loads(raw.decode("utf-8-sig"))


def github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    result = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        for line_text in result.stdout.splitlines():
            if line_text.startswith("password="):
                return line_text.split("=", 1)[1]
    raise PublishError("No GitHub token found in env or git credential manager.")


def gh_request(method: str, url: str, token: str, data: bytes | None = None, content_type: str = "application/json") -> dict | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AnthologyPublishWizard",
    }
    if data is not None:
        headers["Content-Type"] = content_type
    req = Request(url, method=method, headers=headers, data=data)
    try:
        with urlopen(req, timeout=300) as response:
            raw = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise PublishError(f"GitHub API failed {method} {url}: HTTP {exc.code} {body}") from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def release_by_tag(repo: str, tag: str, token: str) -> dict | None:
    try:
        return gh_request("GET", f"https://api.github.com/repos/{repo}/releases/tags/{quote(tag)}", token)
    except PublishError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def create_release(repo: str, tag: str, token: str, notes: str) -> dict:
    payload = json.dumps({"tag_name": tag, "name": tag, "body": notes, "draft": False, "prerelease": False}).encode("utf-8")
    release = gh_request("POST", f"https://api.github.com/repos/{repo}/releases", token, payload)
    if not release:
        raise PublishError(f"Failed to create release {repo}@{tag}")
    return release


def upload_asset(release: dict, asset_path: Path, asset_name: str, token: str) -> dict:
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            gh_request("DELETE", asset["url"], token)
            break
    upload_base = release["upload_url"].split("{", 1)[0]
    data = asset_path.read_bytes()
    asset = gh_request(
        "POST",
        f"{upload_base}?name={quote(asset_name)}",
        token,
        data=data,
        content_type="application/octet-stream",
    )
    if not asset:
        raise PublishError(f"Failed to upload asset {asset_name}")
    return asset


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


def engine_asset_name(version: str) -> str:
    return f"STALKER-Anomaly-modded-exes-MT-TEST_{version}.zip"


def engine_zip_path(version: str) -> Path:
    return Path(tempfile.gettempdir()) / engine_asset_name(version)


def package_engine_zip(version: str) -> Path:
    if not LIVE_BIN_DIR.exists():
        raise PublishError(f"Live bin folder not found: {LIVE_BIN_DIR}")
    if not LIVE_ENGINE_DB.exists():
        raise PublishError(f"Live engine DB not found: {LIVE_ENGINE_DB}")

    zip_path = engine_zip_path(version)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(LIVE_BIN_DIR.rglob("*")):
            if path.is_file():
                archive.write(path, (Path("bin") / path.relative_to(LIVE_BIN_DIR)).as_posix())
        archive.write(LIVE_ENGINE_DB, (Path("db") / "mods" / LIVE_ENGINE_DB.name).as_posix())
    return zip_path


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publish_engine(version: str, notes: str, yes: bool, dry_run: bool, skip_build: bool) -> None:
    run(["git", "fetch", "origin", ENGINE_BRANCH, "--prune"], cwd=ENGINE_DIR)
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ENGINE_DIR, capture=True).strip()
    if branch != ENGINE_BRANCH:
        raise PublishError(f"Engine repo must be on {ENGINE_BRANCH}, current branch is {branch}.")

    print("\nMT Engine Git status")
    print(git_status(ENGINE_DIR))
    if not skip_build:
        if not prompt_yes("Build/deploy MT engine before packaging?", yes):
            raise PublishError("Engine build/deploy canceled.")
        run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ENGINE_BUILD_SCRIPT), "-Deploy"])
    else:
        print("Skip engine build/deploy.")

    zip_path = package_engine_zip(version)
    zip_sha = sha256_file(zip_path)
    print(f"\nEngine ZIP: {zip_path}")
    print(f"  size: {zip_path.stat().st_size}")
    print(f"  sha256: {zip_sha}")
    if dry_run:
        print("DRY RUN: skip engine manifest write, commit, push, and upload.")
        return

    asset_name = engine_asset_name(version)
    manifest_path = ENGINE_DIR / "engine_version.json"
    data = read_json(manifest_path)
    data["version"] = version
    data["mode"] = data.get("mode") or "mt"
    data["label"] = data.get("label") or "MT TEST"
    data["url"] = f"https://github.com/{ENGINE_REPO}/releases/download/{version}/{asset_name}"
    data["notes"] = notes
    write_json(manifest_path, data)

    if not prompt_yes(f"Publish MT engine {version}?", yes):
        return
    run(["git", "add", "-A"], cwd=ENGINE_DIR)
    if git_short_status(ENGINE_DIR):
        run(["git", "commit", "-m", f"Bump MT engine to {version}"], cwd=ENGINE_DIR)
    else:
        print("No engine git changes to commit.")
    run(["git", "push", "origin", ENGINE_BRANCH], cwd=ENGINE_DIR)

    token = github_token()
    release = release_by_tag(ENGINE_REPO, version, token) or create_release(ENGINE_REPO, version, token, notes)
    asset = upload_asset(release, zip_path, asset_name, token)
    manifest = github_manifest(ENGINE_MANIFEST_API)
    print(f"Verified MT engine API version: {manifest.get('version')}")
    print(f"Uploaded asset: {asset.get('name')} ({asset.get('size')} bytes)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Anthology DB/MO2 publisher.")
    parser.add_argument("--target", choices=["db", "mo2", "engine", "content", "all"], help="What to publish.")
    parser.add_argument("--version", help="Use the same version for selected targets.")
    parser.add_argument("--db-version", help="DB version override.")
    parser.add_argument("--mo2-version", help="MO2 version override.")
    parser.add_argument("--engine-version", help="MT engine version override.")
    parser.add_argument("--notes", help="Use the same notes for selected targets.")
    parser.add_argument("--db-notes", help="DB notes override.")
    parser.add_argument("--mo2-notes", help="MO2 notes override.")
    parser.add_argument("--engine-notes", help="MT engine notes override.")
    parser.add_argument("--skip-engine-build", action="store_true", help="Package currently deployed live bin without rebuilding engine.")
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    parser.add_argument("--dry-run", action="store_true", help="Run checks and local writes, but skip push/upload in helper.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_current, mo2_current, engine_current = current_versions()
    dry_run = args.dry_run

    if args.target:
        target = args.target
    else:
        banner()
        print_dashboard(db_current, mo2_current, engine_current)
        target, menu_dry_run = choose_target()
        dry_run = dry_run or menu_dry_run
        if target == "exit":
            print("Canceled.")
            return 0

    if target not in {"db", "mo2", "engine", "content", "all"}:
        raise PublishError("Target must be db, mo2, engine, content, or all.")

    db_version = None
    mo2_version = None
    engine_version = None
    db_notes = None
    mo2_notes = None
    engine_notes = None

    if target in {"db", "content", "all"}:
        default = args.version or args.db_version or next_version(db_current)
        db_version = args.db_version or args.version or prompt(default, "DB version")
        db_notes = args.db_notes or args.notes or prompt("Обновление DB Anthology.", "DB notes")

    if target in {"mo2", "content", "all"}:
        default = args.version or args.mo2_version or next_version(mo2_current)
        mo2_version = args.mo2_version or args.version or prompt(default, "MO2 version")
        mo2_notes = args.mo2_notes or args.notes or prompt("Обновление MO2 модпака.", "MO2 notes")

    if target in {"engine", "all"}:
        default = args.version or args.engine_version or next_version(engine_current)
        engine_version = args.engine_version or args.version or prompt(default, "MT engine version")
        engine_notes = args.engine_notes or args.notes or prompt("MT engine update.", "MT engine notes")

    print_release_plan(target, dry_run, db_version, mo2_version, engine_version)
    if not prompt_yes("Start this release?", args.yes):
        print("Canceled.")
        return 0

    if target in {"db", "content", "all"} and db_version and db_notes is not None:
        publish_db(db_version, db_notes, args.yes, dry_run)

    if target in {"mo2", "content", "all"} and mo2_version and mo2_notes is not None:
        publish_mo2(mo2_version, mo2_notes, args.yes, dry_run)

    if target in {"engine", "all"} and engine_version and engine_notes is not None:
        publish_engine(engine_version, engine_notes, args.yes, dry_run, args.skip_engine_build)

    print(f"\n{GREEN}Done.{RESET}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
