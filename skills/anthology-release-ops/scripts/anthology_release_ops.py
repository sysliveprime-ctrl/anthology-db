#!/usr/bin/env python3
"""Release helper for Anthology launcher, MO2 modpack, and Work Git mirror."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


WORKGIT_DIR = Path(r"E:\dev\Anthology-Work-Git")
LAUNCHER_DIR = WORKGIT_DIR / "projects" / "AnthologyLauncher"
MODPACK_DIR = Path(r"D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods")
SOURCE_DIR = Path(r"E:\dev\anomaly-codex-main\ai_workspace\Source_Anthology")
DB_DIR = WORKGIT_DIR
DB_SOURCE_DIRS = {
    "configs": Path(r"D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\configs"),
    "mods": Path(r"D:\Games\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1\db\mods"),
}

LAUNCHER_REPO = "sysliveprime-ctrl/AnthologyLauncher"
DB_REPO = "sysliveprime-ctrl/anthology-db"
SOURCE_REPO = "sysliveprime-ctrl/anthology-source"
LAUNCHER_ASSET = "AnomalyLauncher.exe"


class ReleaseError(RuntimeError):
    pass


def run(args: list[str | Path], cwd: Path | None = None, capture: bool = False) -> str:
    print("+", " ".join(str(arg) for arg in args))
    result = subprocess.run(
        [str(arg) for arg in args],
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if result.returncode != 0:
        if capture and result.stdout:
            print(result.stdout.rstrip())
        raise ReleaseError(f"Command failed with exit code {result.returncode}: {' '.join(str(a) for a in args)}")
    return result.stdout if capture else ""


def status(root: Path) -> str:
    return run(["git", "status", "--short", "--branch"], cwd=root, capture=True).rstrip()


def short_status(root: Path) -> str:
    return run(["git", "status", "--short"], cwd=root, capture=True).strip()


def commit_push(root: Path, message: str, dry_run: bool) -> str:
    print(status(root))
    if dry_run:
        print("DRY RUN: skip git add/commit/push")
        return run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture=True).strip()

    run(["git", "add", "-A"], cwd=root)
    if short_status(root):
        run(["git", "commit", "-m", message], cwd=root)
    else:
        print("No git changes to commit.")
    run(["git", "push", "origin", "main"], cwd=root)
    return run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture=True).strip()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_version() -> str:
    return time.strftime("%Y.%m.%d.1")


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
        for line in result.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1]
    raise ReleaseError("No GitHub token found in env or git credential manager.")


def gh_request(method: str, url: str, token: str, data: bytes | None = None, content_type: str = "application/json") -> dict | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "AnthologyReleaseOps",
    }
    if data is not None:
        headers["Content-Type"] = content_type
    req = Request(url, method=method, headers=headers, data=data)
    try:
        with urlopen(req, timeout=180) as response:
            raw = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ReleaseError(f"GitHub API failed {method} {url}: HTTP {exc.code} {body}") from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def latest_release(repo: str, token: str) -> dict:
    release = gh_request("GET", f"https://api.github.com/repos/{repo}/releases/latest", token)
    if not release:
        raise ReleaseError(f"No latest release found for {repo}")
    return release


def release_by_tag(repo: str, tag: str, token: str) -> dict | None:
    try:
        return gh_request("GET", f"https://api.github.com/repos/{repo}/releases/tags/{quote(tag)}", token)
    except ReleaseError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def create_release(repo: str, tag: str, token: str, notes: str) -> dict:
    payload = json.dumps(
        {"tag_name": tag, "name": tag, "body": notes, "draft": False, "prerelease": False}
    ).encode("utf-8")
    release = gh_request("POST", f"https://api.github.com/repos/{repo}/releases", token, payload)
    if not release:
        raise ReleaseError(f"Failed to create release {repo}@{tag}")
    return release


def upload_asset(release: dict, asset_path: Path, asset_name: str, token: str, replace: bool = True) -> dict:
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            if not replace:
                raise ReleaseError(f"Asset already exists: {asset_name}")
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
        raise ReleaseError(f"Failed to upload asset {asset_name}")
    return asset


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_launcher_version(root: Path, version: str, notes: str) -> None:
    script = root / "anthology_launcher.py"
    meta = root / "launcher_version.json"

    text = script.read_text(encoding="utf-8")
    new_text, count = re.subn(r'LAUNCHER_VERSION = "[^"]+"', f'LAUNCHER_VERSION = "{version}"', text, count=1)
    if count != 1:
        raise ReleaseError("Could not find LAUNCHER_VERSION in anthology_launcher.py")
    script.write_text(new_text, encoding="utf-8")

    data = read_json(meta)
    data["version"] = version
    data["notes"] = notes
    data.setdefault("exe_url", f"https://github.com/{LAUNCHER_REPO}/releases/latest/download/{LAUNCHER_ASSET}")
    write_json(meta, data)


def command_launcher(args: argparse.Namespace) -> None:
    root = Path(args.path or LAUNCHER_DIR)
    version = args.version or default_version()
    notes = args.notes or "Launcher update."
    update_launcher_version(root, version, notes)

    run(["py", "-3", "-m", "py_compile", root / "anthology_launcher.py"], cwd=root)
    if not args.skip_build:
        run(["py", "-3", "-m", "PyInstaller", "--noconfirm", "AnthologyLauncherModern.spec"], cwd=root)

    exe = root / "dist" / LAUNCHER_ASSET
    if not args.skip_build and not exe.exists():
        raise ReleaseError(f"Built exe not found: {exe}")

    commit = commit_push(root, args.message or f"Bump launcher to {version}", args.dry_run)

    asset_size = None
    asset_url = None
    if args.skip_upload or args.dry_run:
        print("Skip GitHub launcher asset upload.")
    else:
        token = github_token()
        release = latest_release(LAUNCHER_REPO, token)
        asset = upload_asset(release, exe, LAUNCHER_ASSET, token)
        asset_size = asset.get("size")
        asset_url = asset.get("browser_download_url")

    print(json.dumps(
        {"type": "launcher", "version": version, "commit": commit, "asset_size": asset_size, "asset_url": asset_url},
        ensure_ascii=False,
        indent=2,
    ))


def command_modpack(args: argparse.Namespace) -> None:
    root = Path(args.path or MODPACK_DIR)
    version = args.version or default_version()
    notes = args.notes or "Modpack update."
    meta = root / "version.json"

    data = read_json(meta)
    data["version"] = version
    data["notes"] = notes
    data.setdefault("zip_url", "https://github.com/sysliveprime-ctrl/anthology-mo2-modpack/archive/refs/heads/main.zip")
    write_json(meta, data)

    commit = commit_push(root, args.message or f"Bump modpack to {version}", args.dry_run)
    print(json.dumps({"type": "modpack", "version": version, "commit": commit}, ensure_ascii=False, indent=2))


def command_source(args: argparse.Namespace) -> None:
    root = Path(args.path or SOURCE_DIR)
    version = args.version or default_version()
    notes = args.notes or "Anthology source update."
    message = args.message or f"Update Anthology source {version}: {notes}"

    commit = commit_push(root, message, args.dry_run)
    print(json.dumps({"type": "source", "version": version, "commit": commit, "repo": SOURCE_REPO}, ensure_ascii=False, indent=2))


def db_asset_paths() -> list[tuple[Path, str]]:
    paths: list[tuple[Path, str]] = []
    for folder, base in DB_SOURCE_DIRS.items():
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                rel = Path("db") / folder / path.relative_to(base)
                paths.append((path, rel.as_posix()))
    return sorted(paths, key=lambda item: item[1].casefold())


def db_asset_name(rel_path: str) -> str:
    name = rel_path.replace("/", "_").replace("[", "").replace("]", "")
    name = re.sub(r"\s+", "_", name)
    return name


def command_db(args: argparse.Namespace) -> None:
    root = Path(args.path or DB_DIR)
    version = args.version or default_version()
    notes = args.notes or "Anthology Work Git update."
    meta = root / "db_version.json"

    files = []
    asset_sources: dict[str, Path] = {}
    for path, rel in db_asset_paths():
        asset_sources[rel] = path
        files.append(
            {
                "path": rel,
                "asset_name": db_asset_name(rel),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    data = read_json(meta)
    data["version"] = version
    data["mode"] = "mirror"
    data["base_url"] = f"https://github.com/{DB_REPO}/releases/download/{version}/"
    data["notes"] = notes
    data["files"] = files
    write_json(meta, data)

    commit = commit_push(root, args.message or f"Bump Anthology Work Git to {version}", args.dry_run)

    uploaded = []
    if args.manifest_only or args.dry_run:
        print("Skip Anthology Work Git asset upload.")
    else:
        token = github_token()
        release = release_by_tag(DB_REPO, version, token) or create_release(DB_REPO, version, token, notes)
        for entry in files:
            asset = upload_asset(release, asset_sources[entry["path"]], entry["asset_name"], token)
            uploaded.append({"name": asset.get("name"), "size": asset.get("size")})

    print(json.dumps(
        {"type": "workgit", "version": version, "commit": commit, "assets": uploaded, "file_count": len(files)},
        ensure_ascii=False,
        indent=2,
    ))


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", help="Release version, e.g. 2026.05.25.7")
    parser.add_argument("--notes", help="Release notes stored in the version manifest")
    parser.add_argument("--message", help="Git commit message")
    parser.add_argument("--path", help="Override project/repo path")
    parser.add_argument("--dry-run", action="store_true", help="Write local files and run checks, but skip commit/push/upload")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Anthology release operations")
    sub = parser.add_subparsers(dest="command", required=True)

    launcher = sub.add_parser("launcher", help="Publish launcher update")
    add_common(launcher)
    launcher.add_argument("--skip-build", action="store_true", help="Do not run PyInstaller")
    launcher.add_argument("--skip-upload", action="store_true", help="Do not replace latest GitHub release exe")
    launcher.set_defaults(func=command_launcher)

    modpack = sub.add_parser("modpack", help="Publish MO2 modpack update")
    add_common(modpack)
    modpack.set_defaults(func=command_modpack)

    source = sub.add_parser("source", help="Commit and push Anthology source update")
    add_common(source)
    source.set_defaults(func=command_source)

    workgit = sub.add_parser("workgit", help="Publish Anthology Work Git mirror update")
    add_common(workgit)
    workgit.add_argument("--manifest-only", action="store_true", help="Update db_version.json without uploading release assets")
    workgit.set_defaults(func=command_db)

    db = sub.add_parser("db", help="Alias for workgit")
    add_common(db)
    db.add_argument("--manifest-only", action="store_true", help="Update db_version.json without uploading release assets")
    db.set_defaults(func=command_db)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
