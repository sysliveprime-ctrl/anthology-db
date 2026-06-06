#!/usr/bin/env python3
"""Интерактивный мастер публикации обновлений Anthology."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import stat
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
LAUNCHER_DIR = WORKGIT_DIR / "projects" / "AnthologyLauncher"
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
DB_SOURCE_FILES = {
    "db/shaders_anthology.xdb0": LIVE_GAME_DIR / "db" / "shaders_anthology.xdb0",
    "db/textures/textures_trees.xdb0": LIVE_GAME_DIR / "db" / "textures" / "textures_trees.xdb0",
    "db/textures/textures_trees.xdb1": LIVE_GAME_DIR / "db" / "textures" / "textures_trees.xdb1",
    "db/textures/textures_trees.xdb3": LIVE_GAME_DIR / "db" / "textures" / "textures_trees.xdb3",
}
DB_EXCLUDED_REL_PATHS = {
    "db/mods/00_modded_exes_gamedata.db0",
}

DB_REPO_URL = "https://github.com/sysliveprime-ctrl/anthology-db.git"
DB_MANIFEST_API = "https://api.github.com/repos/sysliveprime-ctrl/anthology-db/contents/db_version.json?ref=main"
LAUNCHER_MANIFEST_API = "https://api.github.com/repos/sysliveprime-ctrl/AnthologyLauncher/contents/launcher_version.json?ref=main"
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


class RussianArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        text = super().format_help()
        return (
            text.replace("usage:", "использование:")
            .replace("options:", "параметры:")
            .replace("show this help message and exit", "показать эту справку и выйти")
        )


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
        raise PublishError(f"Команда завершилась с кодом {result.returncode}: {' '.join(args)}")
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


def prompt_required(text: str) -> str:
    while True:
        value = input(f"{CYAN}{text}{RESET}: ").strip()
        if value:
            return value
        print(f"{RED}Значение не может быть пустым.{RESET}")


def prompt_multiline(text: str) -> str:
    print(f"{CYAN}{text}{RESET} {DIM}(завершить пустой строкой){RESET}")
    lines = []
    while True:
        line_text = input()
        if not line_text:
            break
        lines.append(line_text.rstrip())
    value = "\n".join(lines).strip()
    if not value:
        raise PublishError(f"{text}: значение не может быть пустым.")
    return value


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
    print(f"{BOLD}{CYAN}  ANTHOLOGY: ЦЕНТР ВЫПУСКА ОБНОВЛЕНИЙ{RESET}")
    print(f"{DIM}  DB-архивы, MO2-модпак, лаунчер, манифесты и GitHub-релизы{RESET}")
    print(f"{MAGENTA}{line('=')}{RESET}\n")


def card_row(label: str, value: str, color: str = RESET) -> None:
    print(f"  {DIM}{label:<16}{RESET} {color}{value}{RESET}")


def current_versions() -> tuple[str, str, str, str]:
    launcher_current = read_json(LAUNCHER_DIR / "launcher_version.json").get("version", "0.0.0.0")
    db_current = read_json(WORKGIT_DIR / "db_version.json").get("version", "0.0.0.0")
    mo2_current = read_json(MODPACK_DIR / "version.json").get("version", "0.0.0.0")
    engine_current = read_json(ENGINE_DIR / "engine_version.json").get("version", "0.0.0.0")
    return launcher_current, db_current, mo2_current, engine_current


def print_dashboard(launcher_current: str, db_current: str, mo2_current: str, engine_current: str) -> None:
    print(f"{BOLD}Текущие версии{RESET}")
    card_row("Лаунчер", launcher_current, GREEN)
    card_row("DB локально", db_current, GREEN)
    card_row("MO2 локально", mo2_current, GREEN)
    card_row("MT движок", engine_current, GREEN)
    print()
    print(f"{BOLD}Что выпускаем?{RESET}")
    print(f"  {CYAN}1{RESET}. Только DB        {DIM}db/configs + db/mods, файлы релиза{RESET}")
    print(f"  {CYAN}2{RESET}. Только MO2       {DIM}MO2 main.zip + version.json{RESET}")
    print(f"  {CYAN}3{RESET}. MT движок        {DIM}сборка, упаковка ZIP, загрузка релиза{RESET}")
    print(f"  {CYAN}4{RESET}. DB + MO2         {DIM}оба контентных канала{RESET}")
    print(f"  {CYAN}5{RESET}. Всё              {DIM}DB + MO2 + MT движок{RESET}")
    print(f"  {CYAN}6{RESET}. Новости лаунчера {DIM}добавить новость сверху и выпустить лаунчер{RESET}")
    print(f"  {CYAN}7{RESET}. Управление новостями {DIM}редактировать или удалить старые новости лаунчера{RESET}")
    print(f"  {CYAN}8{RESET}. Сухой прогон     {DIM}проверки без публикации и загрузки{RESET}")
    print(f"  {CYAN}9{RESET}. Повтор MT upload {DIM}дозалить ZIP в уже созданный релиз{RESET}")
    print(f"  {CYAN}10{RESET}. Выход\n")


def choose_target() -> tuple[str, bool]:
    while True:
        choice = input(f"{BOLD}Выберите действие{RESET} [3]: ").strip().lower() or "3"
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
            "6": ("launcher-news", False),
            "launcher": ("launcher-news", False),
            "launcher-news": ("launcher-news", False),
            "news": ("launcher-news", False),
            "7": ("launcher-news-manage", False),
            "manage-news": ("launcher-news-manage", False),
            "launcher-news-manage": ("launcher-news-manage", False),
            "edit-news": ("launcher-news-manage", False),
            "delete-news": ("launcher-news-manage", False),
            "8": ("all", True),
            "dry": ("all", True),
            "dry-run": ("all", True),
            "9": ("engine-upload", False),
            "engine-upload": ("engine-upload", False),
            "upload-engine": ("engine-upload", False),
            "retry-engine": ("engine-upload", False),
            "retry": ("engine-upload", False),
            "повтор": ("engine-upload", False),
            "10": ("exit", False),
            "exit": ("exit", False),
            "q": ("exit", False),
        }
        if choice in mapping:
            return mapping[choice]
        print(f"{RED}Неизвестный пункт. Используйте 1, 2, 3, 4, 5, 6, 7, 8 или 9.{RESET}")


def print_release_plan(
    target: str,
    dry_run: bool,
    db_version: str | None,
    mo2_version: str | None,
    engine_version: str | None,
) -> None:
    print()
    print(f"{BOLD}План выпуска{RESET}")
    card_row("цель", target.upper(), CYAN)
    card_row("режим", "СУХОЙ ПРОГОН" if dry_run else "ПУБЛИКАЦИЯ", YELLOW if dry_run else GREEN)
    if db_version:
        card_row("версия DB", db_version, GREEN)
    if mo2_version:
        card_row("версия MO2", mo2_version, GREEN)
    if engine_version:
        card_row("версия MT", engine_version, GREEN)
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
    raise PublishError("Не найден токен GitHub в переменных окружения или git credential manager.")


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
        raise PublishError(f"GitHub API вернул ошибку {method} {url}: HTTP {exc.code} {body}") from exc
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
        raise PublishError(f"Не удалось создать релиз {repo}@{tag}")
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
        raise PublishError(f"Не удалось загрузить файл релиза {asset_name}")
    return asset


def upload_release_asset(repo: str, tag: str, release: dict, asset_path: Path, asset_name: str, token: str) -> dict:
    if shutil.which("gh"):
        run(["gh", "release", "upload", tag, str(asset_path), "--repo", repo, "--clobber"])
        refreshed = release_by_tag(repo, tag, token)
        if refreshed:
            for asset in refreshed.get("assets", []):
                if asset.get("name") == asset_name:
                    return asset
        raise PublishError(f"GitHub release asset не найден после загрузки: {asset_name}")
    return upload_asset(release, asset_path, asset_name, token)


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
            if rel.casefold() in DB_EXCLUDED_REL_PATHS:
                continue
            files[rel] = {
                "path": rel,
                "asset_name": db_asset_name(rel),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    for rel, path in DB_SOURCE_FILES.items():
        if path.exists() and rel.casefold() not in DB_EXCLUDED_REL_PATHS:
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
        label = {"added": "добавлено", "changed": "изменено", "removed": "удалено"}.get(key, key)
        print(f"  {label}: {len(items)}")
        for item in items[:12]:
            print(f"    - {item}")
        if len(items) > 12:
            print(f"    ... и ещё {len(items) - 12}")


def summarize_mo2_changes() -> None:
    print("\nGit-статус MO2")
    print(git_status(MODPACK_DIR))
    current = read_json(MODPACK_DIR / "version.json").get("version", "")
    bump = run(
        ["git", "log", "--grep", f"Bump modpack to {current}", "--format=%H", "-1"],
        cwd=MODPACK_DIR,
        capture=True,
    ).strip()
    if bump:
        commits = run(["git", "log", "--oneline", f"{bump}..HEAD"], cwd=MODPACK_DIR, capture=True).strip()
        print(f"\nКоммиты MO2 после версии {current}:")
        print(commits or "  нет")
    else:
        print(f"\nНе удалось найти предыдущий bump-коммит для MO2 версии {current}.")


def _retry_rmtree_on_error(function, path: str, excinfo) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def remove_tree_best_effort(root: Path, attempts: int = 5) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(root, onerror=_retry_rmtree_on_error)
            return True
        except FileNotFoundError:
            return True
        except PermissionError as exc:
            if attempt == attempts:
                print(f"{YELLOW}Не удалось удалить старый временный клон: {root}{RESET}")
                print(f"{DIM}{exc}{RESET}")
                return False
            time.sleep(0.5 * attempt)
    return False


def clean_temp_clone() -> Path:
    root = Path(tempfile.gettempdir()) / "anthology-db-release"
    if root.exists() and not remove_tree_best_effort(root):
        root = Path(tempfile.mkdtemp(prefix="anthology-db-release-"))
        shutil.rmtree(root)
        print(f"{YELLOW}Использую новый временный клон: {root}{RESET}")
    run(["git", "clone", DB_REPO_URL, str(root)])
    name, email = git_user_config(WORKGIT_DIR)
    run(["git", "config", "user.name", name], cwd=root)
    run(["git", "config", "user.email", email], cwd=root)
    return root


def publish_db(version: str, notes: str, yes: bool, dry_run: bool) -> None:
    changes = summarize_db_changes(WORKGIT_DIR / "db_version.json")
    print_change_summary("Живые DB-файлы против текущего манифеста", changes)
    if not any(changes.values()):
        print("DB-манифест уже совпадает с живыми файлами.")
        if not prompt_yes("Всё равно поднять версию DB и загрузить assets?", yes):
            return
    if not prompt_yes(f"Опубликовать DB {version}?", yes):
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
        print(f"Проверена версия DB через API: {manifest.get('version')} ({len(manifest.get('files', []))} файлов)")


def publish_mo2(version: str, notes: str, yes: bool, dry_run: bool) -> None:
    run(["git", "fetch", "origin", "main", "--prune"], cwd=MODPACK_DIR)
    summarize_mo2_changes()
    if not git_short_status(MODPACK_DIR):
        print("\nРабочее дерево MO2 чистое. Версия всё равно будет поднята, чтобы игроки скачали текущий main.zip.")
    if not prompt_yes(f"Опубликовать MO2 {version}?", yes):
        return

    args = [sys.executable, str(HELPER), "modpack", "--version", version, "--notes", notes]
    if dry_run:
        args.append("--dry-run")
    run(args, cwd=WORKGIT_DIR)
    if not dry_run:
        manifest = github_manifest(MO2_MANIFEST_API)
        print(f"Проверена версия MO2 через API: {manifest.get('version')}")


def publish_launcher_news(
    version: str,
    title: str,
    body: str,
    notes: str,
    yes: bool,
    dry_run: bool,
) -> None:
    print("\nGit-статус лаунчера")
    print(git_status(LAUNCHER_DIR))
    print(f"\nПредпросмотр верхней новости лаунчера:\n  {title}\n  {body}")
    if not prompt_yes(f"Опубликовать новость лаунчера {version}?", yes):
        return

    args = [
        sys.executable,
        str(HELPER),
        "launcher-news",
        "--version",
        version,
        "--notes",
        notes,
        "--news-title",
        title,
        "--news-body",
        body,
    ]
    if dry_run:
        args.append("--dry-run")
    run(args, cwd=WORKGIT_DIR)
    if not dry_run:
        manifest = github_manifest(LAUNCHER_MANIFEST_API)
        print(f"Проверена версия лаунчера через API: {manifest.get('version')}")


def launcher_news_list() -> list[dict]:
    output = run([sys.executable, str(HELPER), "launcher-news-list"], cwd=WORKGIT_DIR, capture=True)
    return json.loads(output)["news"]


def publish_launcher_news_manage(version: str, notes: str, yes: bool, dry_run: bool) -> None:
    news = launcher_news_list()
    if not news:
        raise PublishError("Список новостей лаунчера пуст.")

    print("\nТекущие новости лаунчера")
    for item in news:
        body = str(item["body"]).replace("\n", " ")
        if len(body) > 120:
            body = body[:117] + "..."
        print(f"  {item['index']}. {item['title']}")
        print(f"     {DIM}{body}{RESET}")

    action = input(f"{CYAN}Действие{RESET} [edit/delete]: ").strip().lower()
    if action not in {"edit", "delete", "e", "d", "редактировать", "удалить"}:
        raise PublishError("Действие должно быть edit или delete.")

    raw_index = prompt_required("Номер новости")
    try:
        index = int(raw_index)
    except ValueError as exc:
        raise PublishError("Номер новости должен быть числом.") from exc
    selected = next((item for item in news if item["index"] == index), None)
    if not selected:
        raise PublishError(f"Новость с номером {index} не найдена.")

    print(f"\nВыбрана новость #{index}:\n  {selected['title']}\n  {selected['body']}")
    if action in {"delete", "d", "удалить"}:
        if not prompt_yes(f"Удалить новость #{index} и выпустить лаунчер {version}?", yes):
            return
        args = [
            sys.executable,
            str(HELPER),
            "launcher-news-delete",
            "--version",
            version,
            "--notes",
            notes,
            "--index",
            str(index),
        ]
    else:
        title = prompt(str(selected["title"]), "Новый заголовок")
        print(f"{DIM}Оставьте текст пустым, чтобы сохранить старый текст.{RESET}")
        try:
            body = prompt_multiline("Новый текст")
        except PublishError:
            body = str(selected["body"])
        if not prompt_yes(f"Изменить новость #{index} и выпустить лаунчер {version}?", yes):
            return
        args = [
            sys.executable,
            str(HELPER),
            "launcher-news-edit",
            "--version",
            version,
            "--notes",
            notes,
            "--index",
            str(index),
            "--news-title",
            title,
            "--news-body",
            body,
        ]

    if dry_run:
        args.append("--dry-run")
    run(args, cwd=WORKGIT_DIR)
    if not dry_run:
        manifest = github_manifest(LAUNCHER_MANIFEST_API)
        print(f"Проверена версия лаунчера через API: {manifest.get('version')}")


def engine_asset_name(version: str) -> str:
    return f"STALKER-Anomaly-modded-exes-MT-TEST_{version}.zip"


def engine_zip_path(version: str) -> Path:
    return Path(tempfile.gettempdir()) / engine_asset_name(version)


def package_engine_zip(version: str) -> Path:
    if not LIVE_BIN_DIR.exists():
        raise PublishError(f"Не найдена живая папка bin: {LIVE_BIN_DIR}")
    if not LIVE_ENGINE_DB.exists():
        raise PublishError(f"Не найден DB-файл движка: {LIVE_ENGINE_DB}")

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
        raise PublishError(f"Репозиторий движка должен быть на {ENGINE_BRANCH}, текущая ветка: {branch}.")

    print("\nGit-статус MT движка")
    print(git_status(ENGINE_DIR))
    if not skip_build:
        if not prompt_yes("Собрать и развернуть MT движок перед упаковкой?", yes):
            raise PublishError("Сборка/развертывание движка отменены.")
        run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ENGINE_BUILD_SCRIPT), "-Deploy"])
    else:
        print("Сборка/развертывание движка пропущены.")

    zip_path = package_engine_zip(version)
    zip_sha = sha256_file(zip_path)
    print(f"\nZIP движка: {zip_path}")
    print(f"  размер: {zip_path.stat().st_size}")
    print(f"  sha256: {zip_sha}")
    if dry_run:
        print("СУХОЙ ПРОГОН: запись манифеста, коммит, публикация и загрузка движка пропущены.")
        return

    asset_name = engine_asset_name(version)
    manifest_path = ENGINE_DIR / "engine_version.json"
    data = read_json(manifest_path)
    data["version"] = version
    data["mode"] = data.get("mode") or "mt"
    data["label"] = "MT DX11/DX11AVX"
    data["url"] = f"https://github.com/{ENGINE_REPO}/releases/download/{version}/{asset_name}"
    data["notes"] = notes
    write_json(manifest_path, data)

    if not prompt_yes(f"Опубликовать MT движок {version}?", yes):
        return
    run(["git", "add", "-A"], cwd=ENGINE_DIR)
    if git_short_status(ENGINE_DIR):
        run(["git", "commit", "-m", f"Bump MT engine to {version}"], cwd=ENGINE_DIR)
    else:
        print("Нет git-изменений движка для коммита.")
    run(["git", "push", "origin", ENGINE_BRANCH], cwd=ENGINE_DIR)

    token = github_token()
    release = release_by_tag(ENGINE_REPO, version, token) or create_release(ENGINE_REPO, version, token, notes)
    asset = upload_release_asset(ENGINE_REPO, version, release, zip_path, asset_name, token)
    manifest = github_manifest(ENGINE_MANIFEST_API)
    print(f"Проверена версия MT движка через API: {manifest.get('version')}")
    print(f"Загружен файл релиза: {asset.get('name')} ({asset.get('size')} байт)")


def retry_engine_asset_upload(version: str, yes: bool, dry_run: bool) -> None:
    run(["git", "fetch", "origin", ENGINE_BRANCH, "--prune"], cwd=ENGINE_DIR)
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ENGINE_DIR, capture=True).strip()
    if branch != ENGINE_BRANCH:
        raise PublishError(f"Репозиторий движка должен быть на {ENGINE_BRANCH}, текущая ветка: {branch}.")

    manifest_path = ENGINE_DIR / "engine_version.json"
    manifest = read_json(manifest_path)
    manifest_version = str(manifest.get("version", "")).strip()
    if manifest_version and manifest_version != version:
        print(f"{YELLOW}Версия в engine_version.json: {manifest_version}, выбран повтор upload для: {version}{RESET}")

    asset_name = engine_asset_name(version)
    zip_path = engine_zip_path(version)
    if not zip_path.exists():
        print(f"{YELLOW}ZIP не найден в temp: {zip_path}{RESET}")
        if not prompt_yes("Собрать ZIP из текущей live-папки bin для повторной загрузки?", yes):
            return
        zip_path = package_engine_zip(version)

    zip_sha = sha256_file(zip_path)
    print(f"\nZIP MT движка для повтора: {zip_path}")
    print(f"  размер: {zip_path.stat().st_size}")
    print(f"  sha256: {zip_sha}")
    if dry_run:
        print("СУХОЙ ПРОГОН: повторная загрузка asset пропущена.")
        return

    if not prompt_yes(f"Повторно загрузить MT asset {asset_name} в релиз {version}?", yes):
        return

    token = github_token()
    notes = str(manifest.get("notes", "")).strip() or f"MT engine {version}"
    release = release_by_tag(ENGINE_REPO, version, token) or create_release(ENGINE_REPO, version, token, notes)
    asset = upload_release_asset(ENGINE_REPO, version, release, zip_path, asset_name, token)
    remote_manifest = github_manifest(ENGINE_MANIFEST_API)
    print(f"Проверена версия MT движка через API: {remote_manifest.get('version')}")
    print(f"Загружен файл релиза: {asset.get('name')} ({asset.get('size')} байт)")


def parse_args() -> argparse.Namespace:
    parser = RussianArgumentParser(description="Интерактивный мастер публикации обновлений Anthology.")
    parser.add_argument("--target", choices=["db", "mo2", "engine", "engine-upload", "content", "all", "launcher-news", "launcher-news-manage"], help="Что публиковать.")
    parser.add_argument("--version", help="Использовать одну версию для выбранных целей.")
    parser.add_argument("--launcher-version", help="Версия лаунчера.")
    parser.add_argument("--db-version", help="Версия DB.")
    parser.add_argument("--mo2-version", help="Версия MO2.")
    parser.add_argument("--engine-version", help="Версия MT движка.")
    parser.add_argument("--notes", help="Общие заметки для выбранных целей.")
    parser.add_argument("--launcher-notes", help="Заметки лаунчера.")
    parser.add_argument("--db-notes", help="Заметки DB.")
    parser.add_argument("--mo2-notes", help="Заметки MO2.")
    parser.add_argument("--engine-notes", help="Заметки MT движка.")
    parser.add_argument("--news-title", help="Заголовок верхней новости лаунчера.")
    parser.add_argument("--news-body", help="Текст верхней новости лаунчера.")
    parser.add_argument("--skip-engine-build", action="store_true", help="Упаковать текущую live-папку bin без пересборки движка.")
    parser.add_argument("--yes", action="store_true", help="Не спрашивать подтверждения.")
    parser.add_argument("--dry-run", action="store_true", help="Проверить и записать локальные файлы, но пропустить публикацию и загрузку в helper.")
    parser.add_argument("--manage-news", action="store_true", help="Редактировать или удалить старые новости лаунчера.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.manage_news:
        args.target = "launcher-news-manage"
    interactive = not args.target

    while True:
        launcher_current, db_current, mo2_current, engine_current = current_versions()
        dry_run = args.dry_run

        if args.target:
            target = args.target
        else:
            banner()
            print_dashboard(launcher_current, db_current, mo2_current, engine_current)
            target, menu_dry_run = choose_target()
            dry_run = dry_run or menu_dry_run
            if target == "exit":
                print("Отменено.")
                return 0

        if target not in {"db", "mo2", "engine", "engine-upload", "content", "all", "launcher-news", "launcher-news-manage"}:
            raise PublishError("Цель должна быть db, mo2, engine, engine-upload, content, all или launcher-news.")

        launcher_version = None
        db_version = None
        mo2_version = None
        engine_version = None
        launcher_notes = None
        db_notes = None
        mo2_notes = None
        engine_notes = None
        news_title = None
        news_body = None

        if target == "launcher-news-manage":
            default = args.version or args.launcher_version or next_version(launcher_current)
            launcher_version = args.launcher_version or args.version or prompt(default, "Версия лаунчера")
            launcher_notes = args.launcher_notes or args.notes or "Управление новостями лаунчера."

        if target == "launcher-news":
            default = args.version or args.launcher_version or next_version(launcher_current)
            launcher_version = args.launcher_version or args.version or prompt(default, "Версия лаунчера")
            news_title = args.news_title or prompt_required("Заголовок новости лаунчера")
            news_body = args.news_body or prompt_multiline("Текст новости лаунчера")
            launcher_notes = args.launcher_notes or args.notes or f"Новость лаунчера: {news_title}"

        if target in {"db", "content", "all"}:
            default = args.version or args.db_version or next_version(db_current)
            db_version = args.db_version or args.version or prompt(default, "Версия DB")
            db_notes = args.db_notes or args.notes or prompt("Обновление DB Anthology.", "Заметки DB")

        if target in {"mo2", "content", "all"}:
            default = args.version or args.mo2_version or next_version(mo2_current)
            mo2_version = args.mo2_version or args.version or prompt(default, "Версия MO2")
            mo2_notes = args.mo2_notes or args.notes or prompt("Обновление MO2 модпака.", "Заметки MO2")

        if target in {"engine", "engine-upload", "all"}:
            default = args.version or args.engine_version or (engine_current if target == "engine-upload" else next_version(engine_current))
            if target == "engine-upload" and args.yes:
                engine_version = default
            else:
                engine_version = args.engine_version or args.version or prompt(default, "Версия MT движка")
            if target != "engine-upload":
                engine_notes = args.engine_notes or args.notes or prompt("Обновление MT движка.", "Заметки MT движка")

        print_release_plan(target, dry_run, db_version, mo2_version, engine_version)
        if launcher_version:
            card_row("версия лаунчера", launcher_version, GREEN)
        if not prompt_yes("Начать публикацию?", args.yes):
            print("Отменено.")
            if not interactive:
                return 0
            input(f"\n{CYAN}Нажмите Enter, чтобы вернуться в главное меню...{RESET}")
            continue

        if target == "launcher-news" and launcher_version and news_title and news_body and launcher_notes:
            publish_launcher_news(launcher_version, news_title, news_body, launcher_notes, args.yes, dry_run)

        if target == "launcher-news-manage" and launcher_version and launcher_notes:
            publish_launcher_news_manage(launcher_version, launcher_notes, args.yes, dry_run)

        if target in {"db", "content", "all"} and db_version and db_notes is not None:
            publish_db(db_version, db_notes, args.yes, dry_run)

        if target in {"mo2", "content", "all"} and mo2_version and mo2_notes is not None:
            publish_mo2(mo2_version, mo2_notes, args.yes, dry_run)

        if target in {"engine", "all"} and engine_version and engine_notes is not None:
            publish_engine(engine_version, engine_notes, args.yes, dry_run, args.skip_engine_build)

        if target == "engine-upload" and engine_version:
            retry_engine_asset_upload(engine_version, args.yes, dry_run)

        print(f"\n{GREEN}Готово.{RESET}")
        if not interactive:
            return 0
        input(f"\n{CYAN}Нажмите Enter, чтобы вернуться в главное меню...{RESET}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PublishError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        raise SystemExit(1)
