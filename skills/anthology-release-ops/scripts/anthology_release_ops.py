#!/usr/bin/env python3
"""Release helper for Anthology launcher, MO2 modpack, and Work Git mirror."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


def configured_path(env_name: str, default: str | Path) -> Path:
    return Path(os.environ.get(env_name, str(default)))


WORKGIT_DIR = configured_path("ANTHOLOGY_WORKGIT_DIR", r"F:\Editor_Stalker\Anthology-Work-Git")
LAUNCHER_DIR = configured_path("ANTHOLOGY_LAUNCHER_DIR", WORKGIT_DIR / "projects" / "AnthologyLauncher")
MODPACK_DIR = configured_path("ANTHOLOGY_MODPACK_DIR", r"D:\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods")
SOURCE_DIR = configured_path("ANTHOLOGY_SOURCE_DIR", WORKGIT_DIR / "projects" / "anthology-source")
LIVE_GAME_DIR = configured_path("ANTHOLOGY_LIVE_GAME_DIR", r"D:\ANTHOLOGY\Anomaly-1.5.3-Anthology 2.1")
DB_DIR = WORKGIT_DIR
UPDATE_RULES_FILE = LAUNCHER_DIR / "assets" / "update_rules.json"


def read_update_rules() -> dict:
    if not UPDATE_RULES_FILE.exists():
        return {}
    return json.loads(UPDATE_RULES_FILE.read_text(encoding="utf-8-sig"))


UPDATE_RULES = read_update_rules()
DB_RULES = UPDATE_RULES.get("db", {})
MO2_RULES = UPDATE_RULES.get("mo2", {})
DB_SOURCE_DIRS = {
    "configs": LIVE_GAME_DIR / "db" / "configs",
    "mods": LIVE_GAME_DIR / "db" / "mods",
}
DB_SOURCE_DIRS.update({key: Path(value) for key, value in DB_RULES.get("source_dirs", {}).items()})
DB_SOURCE_FILES = {
    "db/shaders_anthology.xdb0": LIVE_GAME_DIR / "db" / "shaders_anthology.xdb0",
    "db/textures/textures_trees.xdb0": LIVE_GAME_DIR / "db" / "textures" / "textures_trees.xdb0",
    "db/textures/textures_trees.xdb1": LIVE_GAME_DIR / "db" / "textures" / "textures_trees.xdb1",
    "db/textures/textures_trees.xdb3": LIVE_GAME_DIR / "db" / "textures" / "textures_trees.xdb3",
}
DB_SOURCE_FILES.update({key: Path(value) for key, value in DB_RULES.get("source_files", {}).items()})
DB_EXCLUDED_REL_PATHS = {
    "db/mods/00_modded_exes_gamedata.db0",
}
DB_EXCLUDED_REL_PATHS.update(path.casefold() for path in DB_RULES.get("excluded_rel_paths", []))
DB_REMOVED_REL_PATHS = {
    str(path).replace("\\", "/").casefold()
    for path in DB_RULES.get("removed_files", [])
}

LAUNCHER_REPO = "sysliveprime-ctrl/AnthologyLauncher"
MODPACK_REPO = "sysliveprime-ctrl/anthology-mo2-modpack"
DB_REPO = "sysliveprime-ctrl/anthology-db"
SOURCE_REPO = "sysliveprime-ctrl/anthology-source"
LAUNCHER_ASSET = "AnomalyLauncher.exe"
MODPACK_ALLOWED_PARTS = set(MO2_RULES.get("allowed_parts", ["configs", "scripts", "textures"]))
MODPACK_MANAGED_STANDARD_FOLDER_NAMES = set(MO2_RULES.get("managed_standard_folders", []))
MODPACK_MANAGED_FULL_FOLDER_NAMES = set(MO2_RULES.get("managed_full_folders", [
    "[WPN][100][SPL][R.A.K. Weapon Pack Adaptation Global Simple Patch]",
]))
MODPACK_MANAGED_STANDARD_FOLDERS = {name.casefold() for name in MODPACK_MANAGED_STANDARD_FOLDER_NAMES}
MODPACK_MANAGED_FULL_FOLDERS = {name.casefold() for name in MODPACK_MANAGED_FULL_FOLDER_NAMES}
MODPACK_MANAGED_FOLDERS = MODPACK_MANAGED_STANDARD_FOLDERS | MODPACK_MANAGED_FULL_FOLDERS
MODPACK_PRESERVE_MARKERS = (
    "r.a.k weapon pack adaptation",
)
MODPACK_REMOVED_EXCLUDE_MARKERS = (
    "anthology_release_",
    ".codex_backup_",
)


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


def commit_push_paths(root: Path, paths: list[Path], message: str, dry_run: bool) -> str:
    print(status(root))
    if dry_run:
        print("DRY RUN: skip git add/commit/push")
        return run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture=True).strip()

    run(["git", "add", "--", *[path.relative_to(root) if path.is_absolute() else path for path in paths]], cwd=root)
    if short_status(root):
        staged = run(["git", "diff", "--cached", "--name-only"], cwd=root, capture=True).strip()
        if staged:
            run(["git", "commit", "-m", message], cwd=root)
        else:
            print("No staged git changes to commit.")
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
    if shutil.which("gh"):
        repo = str(release.get("url", "")).split("/repos/", 1)[-1].split("/releases/", 1)[0]
        tag = str(release.get("tag_name", "")).strip()
        if repo and tag:
            temp_dir = Path(tempfile.gettempdir()) / "anthology-release-assets"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_asset = temp_dir / asset_name
            if asset_path.resolve() != temp_asset.resolve():
                shutil.copy2(asset_path, temp_asset)
            args = ["gh", "release", "upload", tag, str(temp_asset), "--repo", repo]
            if replace:
                args.append("--clobber")
            run(args)
            refreshed = release_by_tag(repo, tag, token)
            if refreshed:
                for asset in refreshed.get("assets", []):
                    if asset.get("name") == asset_name:
                        return asset
            raise ReleaseError(f"Asset was uploaded but not found in release: {asset_name}")

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
    data["exe_url"] = f"https://github.com/{LAUNCHER_REPO}/releases/latest/download/{LAUNCHER_ASSET}?v={version}"
    write_json(meta, data)


def py_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def launcher_news_pattern(lang: str) -> re.Pattern[str]:
    return re.compile(
        rf'(?ms)(?P<prefix>    "{re.escape(lang)}": \{{.*?)(?P<entries>(?:        "news_\d+": "(?:\\.|[^"\\])*",\n        "news_\d+_body": "(?:\\.|[^"\\])*",\n)+)'
    )


def parse_launcher_news_entries(block: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r'        "news_(\d+)": "((?:\\.|[^"\\])*)",\n'
        r'        "news_\1_body": "((?:\\.|[^"\\])*)",\n'
    )
    entries = []
    for match in pattern.finditer(block):
        title = json.loads(f'"{match.group(2)}"')
        body = json.loads(f'"{match.group(3)}"')
        entries.append((title, body))
    return entries


def render_launcher_news_entries(entries: list[tuple[str, str]]) -> str:
    lines = []
    for index, (title, body) in enumerate(entries, start=1):
        lines.append(f'        "news_{index}": {py_string(title)},')
        lines.append(f'        "news_{index}_body": {py_string(body)},')
    return "\n".join(lines) + "\n"


def update_launcher_news(
    root: Path,
    ru_title: str,
    ru_body: str,
    en_title: str | None = None,
    en_body: str | None = None,
    max_items: int = 7,
) -> None:
    script = root / "anthology_launcher.py"
    text = script.read_text(encoding="utf-8")
    replacements = {
        "ru": (ru_title, ru_body),
        "en": (en_title or ru_title, en_body or ru_body),
    }

    for lang, new_entry in replacements.items():
        pattern = launcher_news_pattern(lang)
        match = pattern.search(text)
        if not match:
            raise ReleaseError(f"Could not find launcher news block for {lang}.")
        entries = [new_entry] + parse_launcher_news_entries(match.group("entries"))
        entries = entries[:max_items]
        text = text[:match.start("entries")] + render_launcher_news_entries(entries) + text[match.end("entries"):]

    script.write_text(text, encoding="utf-8")


def launcher_news_entries(root: Path, lang: str = "ru") -> list[tuple[str, str]]:
    script = root / "anthology_launcher.py"
    text = script.read_text(encoding="utf-8")
    pattern = launcher_news_pattern(lang)
    match = pattern.search(text)
    if not match:
        raise ReleaseError(f"Could not find launcher news block for {lang}.")
    return parse_launcher_news_entries(match.group("entries"))


def edit_launcher_news(
    root: Path,
    index: int,
    ru_title: str,
    ru_body: str,
    en_title: str | None = None,
    en_body: str | None = None,
) -> None:
    script = root / "anthology_launcher.py"
    text = script.read_text(encoding="utf-8")
    replacements = {
        "ru": (ru_title, ru_body),
        "en": (en_title or ru_title, en_body or ru_body),
    }
    for lang, entry in replacements.items():
        pattern = launcher_news_pattern(lang)
        match = pattern.search(text)
        if not match:
            raise ReleaseError(f"Could not find launcher news block for {lang}.")
        entries = parse_launcher_news_entries(match.group("entries"))
        if index < 1 or index > len(entries):
            raise ReleaseError(f"News index {index} is out of range for {lang}; found {len(entries)} items.")
        entries[index - 1] = entry
        text = text[:match.start("entries")] + render_launcher_news_entries(entries) + text[match.end("entries"):]
    script.write_text(text, encoding="utf-8")


def delete_launcher_news(root: Path, index: int) -> None:
    script = root / "anthology_launcher.py"
    text = script.read_text(encoding="utf-8")
    for lang in ("ru", "en"):
        pattern = launcher_news_pattern(lang)
        match = pattern.search(text)
        if not match:
            raise ReleaseError(f"Could not find launcher news block for {lang}.")
        entries = parse_launcher_news_entries(match.group("entries"))
        if index < 1 or index > len(entries):
            raise ReleaseError(f"News index {index} is out of range for {lang}; found {len(entries)} items.")
        del entries[index - 1]
        text = text[:match.start("entries")] + render_launcher_news_entries(entries) + text[match.end("entries"):]
    script.write_text(text, encoding="utf-8")


def replace_launcher_news(root: Path, ru_entries: list[tuple[str, str]], en_entries: list[tuple[str, str]]) -> None:
    if not ru_entries:
        raise ReleaseError("At least one launcher news item is required.")
    if len(ru_entries) != len(en_entries):
        raise ReleaseError(f"RU/EN news count mismatch: {len(ru_entries)} != {len(en_entries)}.")

    script = root / "anthology_launcher.py"
    text = script.read_text(encoding="utf-8")
    replacements = {"ru": ru_entries, "en": en_entries}
    for lang, entries in replacements.items():
        pattern = launcher_news_pattern(lang)
        match = pattern.search(text)
        if not match:
            raise ReleaseError(f"Could not find launcher news block for {lang}.")
        text = text[:match.start("entries")] + render_launcher_news_entries(entries) + text[match.end("entries"):]
    script.write_text(text, encoding="utf-8")


def is_modpack_update_path(path: str) -> bool:
    candidate = Path(path.replace("\\", "/"))
    if candidate.is_absolute():
        return False
    parts = candidate.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        return False
    if parts[0].casefold() in MODPACK_MANAGED_FULL_FOLDERS:
        return True
    lowered = [part.lower() for part in parts]
    if "gamedata" not in lowered:
        return False
    index = lowered.index("gamedata")
    return index + 1 < len(parts) and lowered[index + 1] in MODPACK_ALLOWED_PARTS


def should_preserve_modpack_path(path: str) -> bool:
    parts = Path(path.replace("\\", "/")).parts
    if parts and parts[0].casefold() in MODPACK_MANAGED_FOLDERS:
        return False
    normalized = Path(path.replace("\\", "/")).as_posix().casefold()
    return any(marker in normalized for marker in MODPACK_PRESERVE_MARKERS)


def should_exclude_removed_modpack_path(path: str) -> bool:
    normalized = Path(path.replace("\\", "/")).as_posix().casefold()
    return any(marker in normalized for marker in MODPACK_REMOVED_EXCLUDE_MARKERS)


def deleted_modpack_files(root: Path) -> list[str]:
    deleted = set()
    pathspecs = [f":(glob)**/gamedata/{part}/**" for part in sorted(MODPACK_ALLOWED_PARTS)]
    pathspecs.extend(f":(literal){folder}" for folder in sorted(MODPACK_MANAGED_FULL_FOLDER_NAMES))
    pathspecs.extend(f":(literal){folder}/gamedata/{part}" for folder in sorted(MODPACK_MANAGED_STANDARD_FOLDER_NAMES) for part in sorted(MODPACK_ALLOWED_PARTS))
    output = run(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "log",
            "--diff-filter=D",
            "--name-only",
            "--pretty=format:",
            "--",
            *pathspecs,
        ],
        cwd=root,
        capture=True,
    )
    for line in output.splitlines():
        rel = line.strip().replace("\\", "/")
        if (
            not rel
            or not is_modpack_update_path(rel)
            or should_preserve_modpack_path(rel)
            or should_exclude_removed_modpack_path(rel)
        ):
            continue
        if not (root / rel).exists():
            deleted.add(Path(rel).as_posix())

    status_output = run(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "status",
            "-z",
            "--short",
            "--",
            *pathspecs,
        ],
        cwd=root,
        capture=True,
    )
    for entry in status_output.split("\0"):
        if not entry:
            continue
        if not entry.startswith(" D ") and not entry.startswith("D  "):
            continue
        rel = entry[3:].strip().replace("\\", "/")
        if (
            rel
            and is_modpack_update_path(rel)
            and not should_preserve_modpack_path(rel)
            and not should_exclude_removed_modpack_path(rel)
        ):
            deleted.add(Path(rel).as_posix())

    return sorted(deleted, key=str.casefold)


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


def command_launcher_news(args: argparse.Namespace) -> None:
    root = Path(args.path or LAUNCHER_DIR)
    version = args.version or default_version()
    title = (args.news_title or "").strip()
    body = (args.news_body or "").strip()
    if not title or not body:
        raise ReleaseError("launcher-news requires --news-title and --news-body.")

    update_launcher_news(
        root,
        title,
        body,
        en_title=(args.news_title_en or "").strip() or None,
        en_body=(args.news_body_en or "").strip() or None,
        max_items=args.max_news,
    )
    args.notes = args.notes or f"Launcher news: {title}"
    command_launcher(args)


def command_launcher_news_list(args: argparse.Namespace) -> None:
    root = Path(args.path or LAUNCHER_DIR)
    lang = args.lang or "ru"
    entries = launcher_news_entries(root, lang)
    print(json.dumps(
        {
            "type": "launcher-news-list",
            "lang": lang,
            "count": len(entries),
            "news": [
                {"index": index, "title": title, "body": body}
                for index, (title, body) in enumerate(entries, start=1)
            ],
        },
        ensure_ascii=False,
        indent=2,
    ))


def command_launcher_news_edit(args: argparse.Namespace) -> None:
    root = Path(args.path or LAUNCHER_DIR)
    title = (args.news_title or "").strip()
    body = (args.news_body or "").strip()
    if not title or not body:
        raise ReleaseError("launcher-news-edit requires --news-title and --news-body.")
    edit_launcher_news(
        root,
        args.index,
        title,
        body,
        en_title=(args.news_title_en or "").strip() or None,
        en_body=(args.news_body_en or "").strip() or None,
    )
    args.notes = args.notes or f"Edit launcher news #{args.index}: {title}"
    command_launcher(args)


def command_launcher_news_delete(args: argparse.Namespace) -> None:
    root = Path(args.path or LAUNCHER_DIR)
    delete_launcher_news(root, args.index)
    args.notes = args.notes or f"Delete launcher news #{args.index}"
    command_launcher(args)


def command_launcher_news_apply(args: argparse.Namespace) -> None:
    root = Path(args.path or LAUNCHER_DIR)
    if args.news_json:
        payload = json.loads(args.news_json)
    elif args.news_file:
        payload = json.loads(Path(args.news_file).read_text(encoding="utf-8-sig"))
    else:
        raise ReleaseError("launcher-news-apply requires --news-json or --news-file.")

    items = payload.get("news") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ReleaseError("launcher-news-apply payload must contain a news list.")

    ru_entries: list[tuple[str, str]] = []
    en_entries: list[tuple[str, str]] = []
    for pos, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ReleaseError(f"News item #{pos} must be an object.")
        ru_title = str(item.get("title") or item.get("ru_title") or "").strip()
        ru_body = str(item.get("body") or item.get("ru_body") or "").strip()
        en_title = str(item.get("title_en") or item.get("en_title") or ru_title).strip()
        en_body = str(item.get("body_en") or item.get("en_body") or ru_body).strip()
        if not ru_title or not ru_body:
            raise ReleaseError(f"News item #{pos} requires RU title and RU body.")
        ru_entries.append((ru_title, ru_body))
        en_entries.append((en_title or ru_title, en_body or ru_body))

    if args.max_news:
        ru_entries = ru_entries[:args.max_news]
        en_entries = en_entries[:args.max_news]
    replace_launcher_news(root, ru_entries, en_entries)
    args.notes = args.notes or f"Apply launcher news list ({len(ru_entries)} items)"
    command_launcher(args)


def command_modpack(args: argparse.Namespace) -> None:
    root = Path(args.path or MODPACK_DIR)
    version = args.version or default_version()
    notes = args.notes or "Modpack update."
    meta = root / "version.json"

    data = read_json(meta)
    data["version"] = version
    data["notes"] = notes
    data.setdefault("zip_url", "https://github.com/sysliveprime-ctrl/anthology-mo2-modpack/archive/refs/heads/main.zip")
    removed = deleted_modpack_files(root)
    if removed:
        data["removed_files"] = removed
    else:
        data.pop("removed_files", None)
    write_json(meta, data)

    commit = commit_push(root, args.message or f"Bump modpack to {version}", args.dry_run)
    print(json.dumps(
        {"type": "modpack", "version": version, "commit": commit, "removed_files": len(removed)},
        ensure_ascii=False,
        indent=2,
    ))


def command_modpack_removed(args: argparse.Namespace) -> None:
    root = Path(args.path or MODPACK_DIR)
    files = deleted_modpack_files(root)
    print(json.dumps(
        {"type": "modpack-removed", "count": len(files), "removed_files": files},
        ensure_ascii=False,
        indent=2,
    ))


def folder_package_id(folder: str) -> str:
    normalized = Path(folder).as_posix().strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")[:40] or "folder"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}"


def validate_folder_package_version(version: str) -> str:
    value = version.strip()
    if not value or not re.fullmatch(r"[0-9A-Za-z._-]+", value):
        raise ReleaseError("Folder package version may contain only letters, digits, '.', '_' and '-'.")
    return value


def selected_modpack_folder(root: Path, value: str) -> tuple[Path, Path]:
    selected = Path(value).expanduser().resolve()
    root_resolved = root.resolve()
    try:
        relative = selected.relative_to(root_resolved)
    except ValueError as exc:
        raise ReleaseError(f"Selected folder must be inside the MO2 mods repository: {root_resolved}") from exc
    if len(relative.parts) != 1 or not selected.is_dir():
        raise ReleaseError("Select one top-level mod folder directly inside MO2 mods.")
    return selected, relative


def folder_package_paths(root: Path, folder: Path, relative: Path, mode: str) -> list[tuple[Path, str]]:
    candidates: list[Path] = []
    if mode == "full":
        candidates = [path for path in folder.rglob("*") if path.is_file()]
    else:
        for part in sorted(MODPACK_ALLOWED_PARTS):
            base = folder / "gamedata" / part
            if base.exists():
                candidates.extend(path for path in base.rglob("*") if path.is_file())

    files: list[tuple[Path, str]] = []
    for path in candidates:
        rel = path.relative_to(root).as_posix()
        parts = Path(rel).parts
        if any(part in {".git", ".github", ".vscode", "__pycache__"} for part in parts):
            continue
        if any(marker in rel.casefold() for marker in MODPACK_REMOVED_EXCLUDE_MARKERS):
            continue
        files.append((path, rel))
    files.sort(key=lambda item: item[1].casefold())
    if not files:
        scope = "all files" if mode == "full" else "gamedata/configs, scripts or textures"
        raise ReleaseError(f"Selected folder contains no package files in scope: {scope}")
    return files


def build_folder_package_zip(package_id: str, version: str, files: list[tuple[Path, str]]) -> tuple[Path, str]:
    asset_name = f"anthology-folder-{package_id}-{version}.zip"
    output_dir = Path(tempfile.gettempdir()) / "anthology-folder-packages"
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / asset_name
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, relative in files:
            archive.write(source, relative)
    return zip_path, asset_name


def folder_package_entries(data: dict) -> list[dict]:
    raw = data.get("folder_packages", [])
    if raw in (None, ""):
        return []
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ReleaseError("version.json folder_packages must be a list of objects.")
    return list(raw)


def ensure_folder_package_git_ready(root: Path, meta: Path, dry_run: bool) -> None:
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture=True).strip()
    if branch != "main":
        raise ReleaseError(f"Folder package publishing requires branch main, current branch: {branch}")
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root, capture=True).strip()
    if staged:
        raise ReleaseError("Unrelated staged changes exist. Commit or unstage them before folder package publishing.")
    meta_status = run(["git", "status", "--porcelain=v1", "--", meta.name], cwd=root, capture=True).strip()
    if meta_status:
        raise ReleaseError(f"{meta.name} already has local changes; resolve them before publishing a folder package.")
    if dry_run:
        print("DRY RUN: skip remote synchronization gate")
        return
    run(["git", "fetch", "origin", "main", "--prune"], cwd=root)
    counts = run(["git", "rev-list", "--left-right", "--count", "HEAD...origin/main"], cwd=root, capture=True).strip().split()
    if len(counts) != 2 or counts != ["0", "0"]:
        ahead = counts[0] if counts else "?"
        behind = counts[1] if len(counts) > 1 else "?"
        raise ReleaseError(f"Local main must match origin/main before publishing (ahead={ahead}, behind={behind}).")


def command_modpack_folder(args: argparse.Namespace) -> None:
    root = Path(args.path or MODPACK_DIR)
    meta = root / "version.json"
    version = validate_folder_package_version(args.version or default_version())
    notes = args.notes or "Отдельное обновление мода/фикса."
    mode = args.mode or "standard"
    folder, relative = selected_modpack_folder(root, args.folder)
    package_id = folder_package_id(relative.as_posix())
    files = folder_package_paths(root, folder, relative, mode)
    current_paths = [rel for _source, rel in files]

    data = read_json(meta)
    entries = folder_package_entries(data)
    previous = next((item for item in entries if str(item.get("id", "")) == package_id), None)
    if previous and str(previous.get("version", "")).strip() == version:
        raise ReleaseError(f"Folder package {relative} already uses version {version}; choose a new version.")
    previous_files = {
        Path(str(item).replace("\\", "/")).as_posix()
        for item in (previous or {}).get("files", [])
        if isinstance(item, str)
    }
    removed_files = sorted(previous_files - set(current_paths), key=str.casefold)
    zip_path, asset_name = build_folder_package_zip(package_id, version, files)
    digest = sha256_file(zip_path)
    tag = f"folder-{package_id}-{version}"
    url = f"https://github.com/{MODPACK_REPO}/releases/download/{tag}/{asset_name}"
    entry = {
        "id": package_id,
        "folder": relative.as_posix(),
        "mode": mode,
        "version": version,
        "notes": notes,
        "url": url,
        "asset_name": asset_name,
        "size": zip_path.stat().st_size,
        "sha256": digest,
        "files": current_paths,
        "removed_files": removed_files,
    }

    ensure_folder_package_git_ready(root, meta, args.dry_run)
    if args.dry_run:
        print(json.dumps({"type": "modpack-folder", "dry_run": True, "package": entry, "zip": str(zip_path)}, ensure_ascii=False, indent=2))
        return

    token = github_token()
    release = release_by_tag(MODPACK_REPO, tag, token) or create_release(MODPACK_REPO, tag, token, notes)
    asset = upload_asset(release, zip_path, asset_name, token)

    entries = [item for item in entries if str(item.get("id", "")) != package_id]
    entries.append(entry)
    entries.sort(key=lambda item: str(item.get("folder", "")).casefold())
    data["folder_packages"] = entries
    write_json(meta, data)
    commit = commit_push_paths(
        root,
        [folder, meta],
        args.message or f"Publish folder package {relative.as_posix()} {version}",
        False,
    )
    print(json.dumps(
        {
            "type": "modpack-folder",
            "version": version,
            "folder": relative.as_posix(),
            "mode": mode,
            "commit": commit,
            "asset": asset.get("name"),
            "asset_size": asset.get("size"),
            "file_count": len(current_paths),
            "removed_files": len(removed_files),
        },
        ensure_ascii=False,
        indent=2,
    ))


def command_source(args: argparse.Namespace) -> None:
    root = Path(args.path or SOURCE_DIR)
    version = args.version or default_version()
    notes = args.notes or "Anthology source update."
    message = args.message or f"Update Anthology source {version}: {notes}"

    commit = commit_push(root, message, args.dry_run)
    print(json.dumps({"type": "source", "version": version, "commit": commit, "repo": SOURCE_REPO}, ensure_ascii=False, indent=2))


def db_asset_paths() -> list[tuple[Path, str]]:
    missing_sources: list[str] = []
    paths: dict[str, tuple[Path, str]] = {}
    for folder, base in DB_SOURCE_DIRS.items():
        if not base.is_dir():
            missing_sources.append(f"db/{folder}: {base}")
            continue
        for path in base.rglob("*"):
            if path.is_file():
                rel = Path("db") / folder / path.relative_to(base)
                rel_posix = rel.as_posix()
                key = rel_posix.casefold()
                if key in DB_EXCLUDED_REL_PATHS or key in DB_REMOVED_REL_PATHS:
                    continue
                paths[key] = (path, rel_posix)
    for rel, path in DB_SOURCE_FILES.items():
        key = rel.casefold()
        if key in DB_EXCLUDED_REL_PATHS or key in DB_REMOVED_REL_PATHS:
            continue
        if not path.is_file():
            missing_sources.append(f"{rel}: {path}")
            continue
        paths[key] = (path, rel)
    if missing_sources:
        details = "\n".join(f"  - {item}" for item in missing_sources)
        raise ReleaseError(
            "DB publishing stopped because configured source paths are missing. "
            "Fix assets/update_rules.json before publishing:\n" + details
        )
    return sorted(paths.values(), key=lambda item: item[1].casefold())


def validate_db_manifest_transition(old_entries: dict[str, dict], files: list[dict]) -> None:
    new_paths = {str(entry.get("path", "")).replace("\\", "/").casefold() for entry in files}
    old_paths = {str(path).replace("\\", "/").casefold() for path in old_entries}
    overlap = sorted(new_paths & DB_REMOVED_REL_PATHS)
    if overlap:
        details = "\n".join(f"  - {path}" for path in overlap)
        raise ReleaseError("DB paths cannot be published and removed in the same manifest:\n" + details)
    unexpected = sorted(old_paths - new_paths - DB_REMOVED_REL_PATHS)
    if unexpected:
        details = "\n".join(f"  - {path}" for path in unexpected)
        raise ReleaseError(
            "DB publishing stopped: previously published files disappeared without an explicit "
            "removed_files rule. This usually means a source path is wrong:\n" + details
        )
    if not files:
        raise ReleaseError("DB publishing stopped: the generated manifest has no files.")


def db_asset_name(rel_path: str) -> str:
    name = rel_path.replace("/", "_").replace("[", "").replace("]", "")
    name = re.sub(r"\s+", "_", name)
    return name


def db_entry_asset_url(manifest: dict, entry: dict, target_version: str) -> str:
    explicit = str(entry.get("url", "")).strip()
    if explicit:
        return explicit
    if str(manifest.get("version", "")).strip() == target_version:
        return ""
    base_url = str(manifest.get("base_url", "")).strip()
    asset_name = str(entry.get("asset_name") or db_asset_name(entry["path"])).strip()
    if not base_url:
        return ""
    return base_url.rstrip("/") + "/" + quote(asset_name.replace("\\", "/"), safe="/")


def unchanged_db_entry(current: dict, previous: dict | None) -> bool:
    if not previous:
        return False
    return (
        current.get("size") == previous.get("size")
        and str(current.get("sha256", "")).casefold() == str(previous.get("sha256", "")).casefold()
        and current.get("asset_name") == previous.get("asset_name")
    )


def command_db(args: argparse.Namespace) -> None:
    root = Path(args.path or DB_DIR)
    version = args.version or default_version()
    notes = args.notes or "Anthology Work Git update."
    meta = root / "db_version.json"

    old_data = read_json(meta)
    old_entries = {entry.get("path"): entry for entry in old_data.get("files", []) if isinstance(entry, dict)}
    files = []
    asset_sources: dict[str, Path] = {}
    upload_entries: list[dict] = []
    for path, rel in db_asset_paths():
        asset_sources[rel] = path
        entry = {
            "path": rel,
            "asset_name": db_asset_name(rel),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        old_entry = old_entries.get(rel)
        if unchanged_db_entry(entry, old_entry):
            old_url = db_entry_asset_url(old_data, old_entry, version)
            if old_url:
                entry["url"] = old_url
            else:
                upload_entries.append(entry)
        else:
            upload_entries.append(entry)
        files.append(entry)

    validate_db_manifest_transition(old_entries, files)

    data = old_data
    data["version"] = version
    data["mode"] = "mirror"
    data["base_url"] = f"https://github.com/{DB_REPO}/releases/download/{version}/"
    data["notes"] = notes
    data["files"] = files
    data["removed_files"] = sorted(
        {str(path).replace("\\", "/") for path in DB_RULES.get("removed_files", [])},
        key=str.casefold,
    )
    if args.dry_run:
        print(f"DRY RUN: skip writing {meta}")
    else:
        write_json(meta, data)

    commit = commit_push_paths(root, [meta], args.message or f"Bump Anthology Work Git to {version}", args.dry_run)

    uploaded = []
    if args.manifest_only or args.dry_run:
        print("Skip Anthology Work Git asset upload.")
    else:
        token = github_token()
        release = release_by_tag(DB_REPO, version, token) or create_release(DB_REPO, version, token, notes)
        for entry in upload_entries:
            asset = upload_asset(release, asset_sources[entry["path"]], entry["asset_name"], token)
            uploaded.append({"name": asset.get("name"), "size": asset.get("size")})

    print(json.dumps(
        {"type": "workgit", "version": version, "commit": commit, "assets": uploaded, "file_count": len(files), "reused_assets": len(files) - len(upload_entries)},
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

    launcher_news = sub.add_parser("launcher-news", help="Publish launcher update with a new top news item")
    add_common(launcher_news)
    launcher_news.add_argument("--news-title", required=True, help="Russian/top news title")
    launcher_news.add_argument("--news-body", required=True, help="Russian/top news body")
    launcher_news.add_argument("--news-title-en", help="English news title; Russian title is used when omitted")
    launcher_news.add_argument("--news-body-en", help="English news body; Russian body is used when omitted")
    launcher_news.add_argument("--max-news", type=int, default=7, help="How many news items to keep in launcher")
    launcher_news.add_argument("--skip-build", action="store_true", help="Do not run PyInstaller")
    launcher_news.add_argument("--skip-upload", action="store_true", help="Do not replace latest GitHub release exe")
    launcher_news.set_defaults(func=command_launcher_news)

    launcher_news_list = sub.add_parser("launcher-news-list", help="List current launcher news items")
    launcher_news_list.add_argument("--path", help="Override project/repo path")
    launcher_news_list.add_argument("--lang", choices=["ru", "en"], default="ru", help="Language block to list")
    launcher_news_list.set_defaults(func=command_launcher_news_list)

    launcher_news_edit = sub.add_parser("launcher-news-edit", help="Edit an existing launcher news item and publish launcher")
    add_common(launcher_news_edit)
    launcher_news_edit.add_argument("--index", type=int, required=True, help="1-based news index to edit")
    launcher_news_edit.add_argument("--news-title", required=True, help="Russian news title")
    launcher_news_edit.add_argument("--news-body", required=True, help="Russian news body")
    launcher_news_edit.add_argument("--news-title-en", help="English news title; Russian title is used when omitted")
    launcher_news_edit.add_argument("--news-body-en", help="English news body; Russian body is used when omitted")
    launcher_news_edit.add_argument("--skip-build", action="store_true", help="Do not run PyInstaller")
    launcher_news_edit.add_argument("--skip-upload", action="store_true", help="Do not replace latest GitHub release exe")
    launcher_news_edit.set_defaults(func=command_launcher_news_edit)

    launcher_news_delete = sub.add_parser("launcher-news-delete", help="Delete an existing launcher news item and publish launcher")
    add_common(launcher_news_delete)
    launcher_news_delete.add_argument("--index", type=int, required=True, help="1-based news index to delete")
    launcher_news_delete.add_argument("--skip-build", action="store_true", help="Do not run PyInstaller")
    launcher_news_delete.add_argument("--skip-upload", action="store_true", help="Do not replace latest GitHub release exe")
    launcher_news_delete.set_defaults(func=command_launcher_news_delete)

    launcher_news_apply = sub.add_parser("launcher-news-apply", help="Replace launcher news list and publish launcher once")
    add_common(launcher_news_apply)
    launcher_news_apply.add_argument("--news-json", help="JSON payload with a news list")
    launcher_news_apply.add_argument("--news-file", help="Path to JSON payload with a news list")
    launcher_news_apply.add_argument("--max-news", type=int, default=7, help="How many news items to keep in launcher")
    launcher_news_apply.add_argument("--skip-build", action="store_true", help="Do not run PyInstaller")
    launcher_news_apply.add_argument("--skip-upload", action="store_true", help="Do not replace latest GitHub release exe")
    launcher_news_apply.set_defaults(func=command_launcher_news_apply)

    modpack = sub.add_parser("modpack", help="Publish MO2 modpack update")
    add_common(modpack)
    modpack.set_defaults(func=command_modpack)

    modpack_removed = sub.add_parser("modpack-removed", help="Show deleted MO2 modpack files that will be cleaned on clients")
    modpack_removed.add_argument("--path", help="Override project/repo path")
    modpack_removed.set_defaults(func=command_modpack_removed)

    modpack_folder = sub.add_parser("modpack-folder", help="Publish one top-level MO2 mod folder as a separate package")
    add_common(modpack_folder)
    modpack_folder.add_argument("--folder", required=True, help="Top-level folder inside the MO2 mods repository")
    modpack_folder.add_argument("--mode", choices=["standard", "full"], default="standard", help="Package configs/scripts/textures only or the full folder")
    modpack_folder.set_defaults(func=command_modpack_folder)

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
