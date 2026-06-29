#!/usr/bin/env python3
"""Small GUI control panel for Anthology release operations."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk


WORKGIT_DIR = Path(
    os.environ.get("ANTHOLOGY_WORKGIT_DIR", str(Path(__file__).resolve().parents[3]))
)
GAME_ROOT = Path(
    os.environ.get(
        "ANTHOLOGY_GAME_ROOT",
        r"X:\S.T.A.L.K.E.R\A.N.T.H.O.L.O.G.Y\ANTHOLOGY",
    )
)
HELPER = WORKGIT_DIR / "skills" / "anthology-release-ops" / "scripts" / "anthology_release_ops.py"
LAUNCHER_DIR = WORKGIT_DIR / "projects" / "AnthologyLauncher"
MODPACK_DIR = Path(
    os.environ.get(
        "ANTHOLOGY_MODPACK_DIR",
        str(GAME_ROOT / "SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT" / "mods"),
    )
)
ENGINE_DIR = Path(
    os.environ.get(
        "ANTHOLOGY_ENGINE_DIR",
        str(WORKGIT_DIR.parent.parent / "projects" / "xray-monolith"),
    )
)
UPDATE_RULES_FILE = LAUNCHER_DIR / "assets" / "update_rules.json"
LIVE_GAME_DIR = Path(
    os.environ.get(
        "ANTHOLOGY_LIVE_GAME_DIR",
        str(GAME_ROOT / "Anomaly-1.5.3-Anthology 2.1"),
    )
)
DB_SOURCE_DIRS = {
    "configs": LIVE_GAME_DIR / "db" / "configs",
    "mods": LIVE_GAME_DIR / "db" / "mods",
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


def read_update_rules() -> dict:
    if not UPDATE_RULES_FILE.exists():
        return {"mo2": {"allowed_parts": ["configs", "scripts", "textures"], "managed_full_folders": []}, "db": {"source_dirs": {}, "source_files": {}, "excluded_rel_paths": []}}
    return json.loads(UPDATE_RULES_FILE.read_text(encoding="utf-8-sig"))


def write_update_rules(data: dict) -> None:
    data.setdefault("mo2", {}).setdefault("allowed_parts", ["configs", "scripts", "textures"])
    data.setdefault("mo2", {}).setdefault("managed_standard_folders", [])
    data.setdefault("mo2", {}).setdefault("managed_full_folders", [])
    data.setdefault("db", {}).setdefault("source_dirs", {})
    data.setdefault("db", {}).setdefault("source_files", {})
    data.setdefault("db", {}).setdefault("removed_files", [])
    data.setdefault("db", {}).setdefault("excluded_rel_paths", ["db/mods/00_modded_exes_gamedata.db0"])
    UPDATE_RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    UPDATE_RULES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mo2_folder_from_path(value: str) -> str:
    path = Path(value.strip().strip('"'))
    if not path:
        return ""
    try:
        return path.relative_to(MODPACK_DIR).as_posix()
    except ValueError:
        return path.as_posix()


def db_rel_from_source(path: Path) -> str:
    db_root = LIVE_GAME_DIR / "db"
    rel = path.relative_to(db_root).as_posix()
    return f"db/{rel}"


def ensure_full_folder_gitignore(folder: str) -> None:
    gitignore = MODPACK_DIR / ".gitignore"
    text = gitignore.read_text(encoding="utf-8-sig") if gitignore.exists() else ""
    escaped = "".join(f"\\{char}" if char in "[]" else char for char in folder)
    line = f"!{escaped}/**"
    if line not in text.splitlines():
        gitignore.write_text(text.rstrip() + "\n\n# Launcher-managed full-folder MO2 rule.\n" + line + "\n", encoding="utf-8")


def ensure_standard_folder_gitignore(folder: str) -> None:
    gitignore = MODPACK_DIR / ".gitignore"
    text = gitignore.read_text(encoding="utf-8-sig") if gitignore.exists() else ""
    escaped = "".join(f"\\{char}" if char in "[]" else char for char in folder)
    lines = [
        f"!{escaped}/",
        f"!{escaped}/gamedata/",
        f"!{escaped}/gamedata/configs/**",
        f"!{escaped}/gamedata/scripts/**",
        f"!{escaped}/gamedata/textures/**",
    ]
    existing = set(text.splitlines())
    missing = [line for line in lines if line not in existing]
    if missing:
        gitignore.write_text(text.rstrip() + "\n\n# Launcher-managed standard MO2 rule.\n" + "\n".join(missing) + "\n", encoding="utf-8")

COLORS = {
    "bg": "#0f1417",
    "panel": "#151b1f",
    "panel_2": "#101518",
    "border": "#2c3a40",
    "text": "#e9f0f2",
    "muted": "#9eabb1",
    "accent": "#3fd0c2",
    "accent_2": "#2f91ff",
    "primary": "#1f8f77",
    "primary_hover": "#28a88e",
    "button": "#223039",
    "button_hover": "#2b3d49",
    "danger": "#a94442",
    "danger_hover": "#c45755",
    "disabled": "#657178",
    "log_bg": "#070a0c",
    "log_text": "#d7f7ee",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def db_asset_name(rel_path: str) -> str:
    return rel_path.replace("/", "_").replace("[", "").replace("]", "").replace(" ", "_")


def live_db_files() -> dict[str, dict]:
    files: dict[str, dict] = {}
    missing_sources: list[str] = []
    rules = read_update_rules().get("db", {})
    source_dirs = dict(DB_SOURCE_DIRS)
    source_dirs.update({key: Path(value) for key, value in rules.get("source_dirs", {}).items()})
    source_files = dict(DB_SOURCE_FILES)
    source_files.update({key: Path(value) for key, value in rules.get("source_files", {}).items()})
    excluded = {path.casefold() for path in DB_EXCLUDED_REL_PATHS}
    excluded.update(path.casefold() for path in rules.get("excluded_rel_paths", []))
    removed = {str(path).replace("\\", "/").casefold() for path in rules.get("removed_files", [])}
    for folder, base in source_dirs.items():
        if not base.is_dir():
            missing_sources.append(f"db/{folder}: {base}")
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = (Path("db") / folder / path.relative_to(base)).as_posix()
            if rel.casefold() in excluded or rel.casefold() in removed:
                continue
            files[rel] = {
                "path": rel,
                "asset_name": db_asset_name(rel),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    for rel, path in source_files.items():
        key = rel.casefold()
        if key in excluded or key in removed:
            continue
        if not path.is_file():
            missing_sources.append(f"{rel}: {path}")
            continue
        files[rel] = {
            "path": rel,
            "asset_name": db_asset_name(rel),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    if missing_sources:
        details = "\n".join(f"  - {item}" for item in missing_sources)
        raise RuntimeError(
            "DB publication is blocked because source paths are missing. "
            "Fix update_rules.json:\n" + details
        )
    return files


def summarize_db_changes(manifest_path: Path) -> dict[str, list[str]]:
    current = {entry["path"]: entry for entry in read_json(manifest_path).get("files", [])}
    live = live_db_files()
    rules = read_update_rules().get("db", {})
    added = sorted(set(live) - set(current))
    removed = sorted(set(current) - set(live))
    rule_removed = sorted({str(path).replace("\\", "/") for path in rules.get("removed_files", [])}, key=str.casefold)
    changed = sorted(
        path
        for path in set(live) & set(current)
        if live[path].get("size") != current[path].get("size")
        or live[path].get("sha256") != current[path].get("sha256")
    )
    return {"added": added, "changed": changed, "removed": removed, "rule_removed": rule_removed}


def format_db_changes(changes: dict[str, list[str]], limit: int = 28) -> str:
    labels = [("added", "Добавлено"), ("changed", "Изменено"), ("removed", "Удалено из манифеста"), ("rule_removed", "Будет удалено у игроков")]
    lines: list[str] = []
    remaining = limit
    for key, label in labels:
        values = changes.get(key, [])
        if not values:
            lines.append(f"{label}: 0")
            continue
        lines.append(f"{label}: {len(values)}")
        shown = values[: max(0, remaining)]
        for value in shown:
            lines.append(f"  {value}")
        remaining -= len(shown)
        if len(shown) < len(values):
            lines.append(f"  ... еще {len(values) - len(shown)}")
    return "\n".join(lines)


def summarize_git_changes(root: Path) -> dict[str, list[str]]:
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "status", "--porcelain=v1", "-z"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    items = [item for item in result.stdout.decode("utf-8", errors="replace").split("\0") if item]
    changes = {"added": [], "changed": [], "removed": [], "renamed": [], "untracked": []}
    index = 0
    while index < len(items):
        item = items[index]
        status = item[:2]
        path = item[3:]
        index += 1
        if "R" in status or "C" in status:
            new_path = items[index] if index < len(items) else path
            index += 1
            changes["renamed"].append(f"{path} -> {new_path}")
        elif status == "??":
            changes["untracked"].append(path)
        elif "D" in status:
            changes["removed"].append(path)
        elif "A" in status:
            changes["added"].append(path)
        else:
            changes["changed"].append(path)
    for values in changes.values():
        values.sort(key=str.casefold)
    return changes


def format_git_changes(changes: dict[str, list[str]], limit: int = 34) -> str:
    labels = [
        ("changed", "Изменено"),
        ("added", "Добавлено"),
        ("removed", "Удалено"),
        ("renamed", "Переименовано"),
        ("untracked", "Новые файлы/папки"),
    ]
    lines: list[str] = []
    remaining = limit
    for key, label in labels:
        values = changes.get(key, [])
        if not values:
            lines.append(f"{label}: 0")
            continue
        lines.append(f"{label}: {len(values)}")
        shown = values[: max(0, remaining)]
        for value in shown:
            lines.append(f"  {value}")
        remaining -= len(shown)
        if len(shown) < len(values):
            lines.append(f"  ... еще {len(values) - len(shown)}")
    return "\n".join(lines)


class MultilineDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, title: str, label: str, initial: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.configure(bg=COLORS["bg"])
        self.result: str | None = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text=label).pack(anchor="w", padx=12, pady=(12, 6))
        self.text = scrolledtext.ScrolledText(
            self,
            width=72,
            height=12,
            wrap="word",
            bg=COLORS["log_bg"],
            fg=COLORS["log_text"],
            insertbackground=COLORS["log_text"],
            selectbackground="#245d55",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.text.pack(fill="both", expand=True, padx=12, pady=6)
        self.text.insert("1.0", initial)
        self._build_context_menu()
        self._bind_text_shortcuts()

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Отмена", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="Вставить", command=self._paste).pack(side="left")
        ttk.Button(buttons, text="Выделить всё", command=self._select_all).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Очистить", command=self._clear).pack(side="left", padx=(6, 0))

        self.bind("<Escape>", lambda _event: self._cancel())
        self.geometry("720x360")
        self.text.focus_set()
        self.wait_window(self)

    def _build_context_menu(self) -> None:
        self.context_menu = tk.Menu(
            self,
            tearoff=False,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            activebackground=COLORS["button_hover"],
            activeforeground=COLORS["text"],
        )
        self.context_menu.add_command(label="Вставить", command=self._paste)
        self.context_menu.add_command(label="Копировать", command=lambda: self.text.event_generate("<<Copy>>"))
        self.context_menu.add_command(label="Вырезать", command=lambda: self.text.event_generate("<<Cut>>"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Выделить всё", command=self._select_all)

    def _bind_text_shortcuts(self) -> None:
        for sequence in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
            self.text.bind(sequence, lambda _event: self._paste_event())
        self.text.bind("<<Paste>>", lambda _event: self._paste_event())
        for sequence in ("<Control-c>", "<Control-C>"):
            self.text.bind(sequence, lambda event: self._text_event(event, "<<Copy>>"))
        for sequence in ("<Control-x>", "<Control-X>"):
            self.text.bind(sequence, lambda event: self._text_event(event, "<<Cut>>"))
        for sequence in ("<Control-a>", "<Control-A>"):
            self.text.bind(sequence, lambda _event: self._select_all_event())
        self.text.bind("<Control-KeyPress>", self._control_key_event)
        self.text.bind("<KeyPress>", self._any_key_event)
        self.text.bind("<Button-3>", self._show_context_menu)
        self.text.bind("<Button-2>", self._show_context_menu)

    def _any_key_event(self, event) -> str | None:
        if bool(int(getattr(event, "state", 0) or 0) & 0x4):
            return self._control_key_event(event)
        return None

    def _control_key_event(self, event) -> str | None:
        key = str(event.keysym).lower()
        char = str(getattr(event, "char", "")).lower()
        keycode = int(getattr(event, "keycode", 0) or 0)
        if key in ("v", "м", "cyrillic_em") or char in ("v", "м") or keycode == 86:
            return self._paste_event()
        if key in ("c", "с", "cyrillic_es") or char in ("c", "с") or keycode == 67:
            return self._text_event(event, "<<Copy>>")
        if key in ("x", "ч", "cyrillic_che") or char in ("x", "ч") or keycode == 88:
            return self._text_event(event, "<<Cut>>")
        if key in ("a", "ф", "cyrillic_ef") or char in ("a", "ф") or keycode == 65:
            return self._select_all_event()
        return None

    def _show_context_menu(self, event) -> str:
        self.text.focus_set()
        self.context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _text_event(self, event, virtual_event: str) -> str:
        event.widget.event_generate(virtual_event)
        return "break"

    def _paste_event(self) -> str:
        self._paste()
        return "break"

    def _select_all_event(self) -> str:
        self._select_all()
        return "break"

    def _paste(self) -> None:
        try:
            value = self.clipboard_get()
        except tk.TclError:
            return
        try:
            self.text.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.text.insert("insert", value)
        self.text.focus_set()

    def _select_all(self) -> None:
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "1.0")
        self.text.see("insert")
        self.text.focus_set()

    def _clear(self) -> None:
        self.text.delete("1.0", "end")
        self.text.focus_set()

    def _ok(self) -> None:
        self.result = self.text.get("1.0", "end").strip()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class SingleLineDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, title: str, label: str, initial: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(True, False)
        self.configure(bg=COLORS["bg"])
        self.result: str | None = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text=label).pack(anchor="w", padx=12, pady=(12, 6))
        self.value = tk.StringVar(value=initial)
        self.entry = tk.Entry(
            self,
            textvariable=self.value,
            width=86,
            bg=COLORS["log_bg"],
            fg=COLORS["log_text"],
            insertbackground=COLORS["log_text"],
            selectbackground="#245d55",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.entry.pack(fill="x", padx=12, pady=6)
        self._bind_shortcuts()

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="Вставить", command=self._paste).pack(side="left")
        ttk.Button(buttons, text="Выделить всё", command=self._select_all).pack(side="left", padx=(6, 0))

        self.bind("<Return>", lambda _event: self._ok())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.geometry("720x138")
        self.entry.focus_set()
        self.entry.icursor("end")
        self.wait_window(self)

    def _bind_shortcuts(self) -> None:
        for sequence in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
            self.entry.bind(sequence, lambda _event: self._paste_event())
        self.entry.bind("<<Paste>>", lambda _event: self._paste_event())
        for sequence in ("<Control-a>", "<Control-A>"):
            self.entry.bind(sequence, lambda _event: self._select_all_event())
        self.entry.bind("<Control-KeyPress>", self._control_key_event)

    def _control_key_event(self, event) -> str | None:
        key = str(event.keysym).lower()
        char = str(getattr(event, "char", "")).lower()
        keycode = int(getattr(event, "keycode", 0) or 0)
        if key in ("v", "м", "cyrillic_em") or char in ("v", "м") or keycode == 86:
            return self._paste_event()
        if key in ("a", "ф", "cyrillic_ef") or char in ("a", "ф") or keycode == 65:
            return self._select_all_event()
        return None

    def _paste_event(self) -> str:
        self._paste()
        return "break"

    def _select_all_event(self) -> str:
        self._select_all()
        return "break"

    def _paste(self) -> None:
        try:
            value = self.clipboard_get()
        except tk.TclError:
            return
        try:
            self.entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.entry.insert("insert", value)
        self.entry.focus_set()

    def _select_all(self) -> None:
        self.entry.selection_range(0, "end")
        self.entry.icursor("end")
        self.entry.focus_set()

    def _ok(self) -> None:
        self.result = self.value.get().strip()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class ReleaseControl(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Anthology Release Control")
        self.geometry("1120x780")
        self.minsize(980, 680)

        self.queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running = False
        self.command_output: list[str] = []
        self.news_items: list[dict] = []
        self.news_items_en: list[dict] = []
        self.news_dirty = False
        self.text_context_widget: tk.Entry | tk.Text | None = None
        self.news_selected_index: int | None = None
        self.loading_news_form = False
        self.news_drag_index: int | None = None
        self.news_drag_target: int | None = None
        self.news_drag_source_title = ""
        self.news_drag_ghost: tk.Toplevel | None = None

        self._build_style()
        self._build_ui()
        self.after(100, self._drain_queue)
        self.refresh_versions(refresh_news=True)

    def _build_style(self) -> None:
        self.configure(bg=COLORS["bg"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 10), background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("Card.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("Muted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
        style.configure("CardMuted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"])
        style.configure("Status.TLabel", font=("Segoe UI Semibold", 10), background=COLORS["bg"], foreground=COLORS["accent"])
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 17), background=COLORS["bg"], foreground=COLORS["accent"])
        style.configure("Version.TLabel", font=("Segoe UI Semibold", 10), background=COLORS["panel_2"], foreground=COLORS["text"], padding=(10, 5))

        style.configure("TButton", font=("Segoe UI Semibold", 9), padding=(12, 7), borderwidth=0, relief="flat", background=COLORS["button"], foreground=COLORS["text"])
        style.map("TButton", background=[("active", COLORS["button_hover"]), ("disabled", "#1a2228")], foreground=[("disabled", COLORS["disabled"])])
        style.configure("Accent.TButton", background=COLORS["primary"], foreground="#f4fffc")
        style.map("Accent.TButton", background=[("active", COLORS["primary_hover"]), ("disabled", "#1a2b29")], foreground=[("disabled", COLORS["disabled"])])
        style.configure("Danger.TButton", background=COLORS["danger"], foreground="#fff1f1")
        style.map("Danger.TButton", background=[("active", COLORS["danger_hover"]), ("disabled", "#2a2020")], foreground=[("disabled", COLORS["disabled"])])

        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(16, 8), background="#1b242a", foreground=COLORS["muted"], borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", COLORS["panel"]), ("active", "#24313a")], foreground=[("selected", COLORS["accent"]), ("active", COLORS["text"])])
        style.configure("TLabelframe", background=COLORS["panel"], bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"])
        style.configure("TLabelframe.Label", font=("Segoe UI Semibold", 11), background=COLORS["bg"], foreground=COLORS["accent"])
        style.configure("Treeview", background=COLORS["panel_2"], fieldbackground=COLORS["panel_2"], foreground=COLORS["text"], rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), background="#223039", foreground=COLORS["text"], padding=(8, 7))
        style.map("Treeview", background=[("selected", "#23584f")], foreground=[("selected", "#ffffff")])

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(18, 14, 18, 8))
        header.pack(fill="x")
        ttk.Label(header, text="ANTHOLOGY: центр выпуска обновлений", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Обновить статусы", command=self.refresh_versions).pack(side="right")

        version_box = ttk.Frame(self, padding=(18, 0, 18, 12))
        version_box.pack(fill="x")
        self.version_vars = {
            "launcher": tk.StringVar(value="Лаунчер: ..."),
            "mo2": tk.StringVar(value="MO2: ..."),
            "db": tk.StringVar(value="DB: ..."),
            "engine": tk.StringVar(value="MT: ..."),
        }
        for var in self.version_vars.values():
            ttk.Label(version_box, textvariable=var, style="Version.TLabel").pack(side="left", padx=(0, 10))

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        main = ttk.Frame(paned)
        paned.add(main, weight=3)
        log_frame = ttk.Labelframe(paned, text="Лог")
        paned.add(log_frame, weight=1)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        self._build_content_tab()
        self._build_launcher_tab()
        self._build_engine_tab()
        self._build_status_tab()

        self.log = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            wrap="word",
            bg=COLORS["log_bg"],
            fg=COLORS["log_text"],
            insertbackground=COLORS["log_text"],
            selectbackground="#245d55",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            font=("Consolas", 10),
        )
        self.log.pack(fill="both", expand=True, padx=10, pady=10)
        progress_row = ttk.Frame(log_frame)
        progress_row.pack(fill="x", padx=10, pady=(0, 10))
        self.command_status = tk.StringVar(value="Статус: готово")
        ttk.Label(progress_row, textvariable=self.command_status, style="Status.TLabel", width=42, anchor="w").pack(side="left", padx=(0, 10))
        self.command_progress = ttk.Progressbar(progress_row, mode="indeterminate", length=260)
        self.command_progress.pack(side="left", fill="x", expand=True)
        self._build_text_context_menu()
        self._log("Готово. Нажми кнопку, выбери версию/заметки, проверь подтверждение.")

    def _build_text_context_menu(self) -> None:
        self.text_context_menu = tk.Menu(
            self,
            tearoff=False,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            activebackground=COLORS["button_hover"],
            activeforeground=COLORS["text"],
        )
        self.text_context_menu.add_command(label="Вставить", command=lambda: self.menu_text_action("paste"))
        self.text_context_menu.add_command(label="Копировать", command=lambda: self.menu_text_action("copy"))
        self.text_context_menu.add_command(label="Вырезать", command=lambda: self.menu_text_action("cut"))
        self.text_context_menu.add_separator()
        self.text_context_menu.add_command(label="Выделить всё", command=lambda: self.menu_text_action("select_all"))

    def _build_content_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="MO2 / DB")

        mo2 = ttk.Labelframe(tab, text="MO2 модпак", padding=14)
        mo2.pack(fill="x", pady=(0, 14))
        ttk.Label(mo2, text="Публикует папку mods в anthology-mo2-modpack main.zip.", style="CardMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(mo2)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Git-статус", command=lambda: self.run_git_status(MODPACK_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Что удалится", command=self.preview_modpack_removed).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Опубликовать мод/фикс", command=self.publish_modpack_folder, style="Accent.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Опубликовать весь MO2", command=self.publish_mo2, style="Accent.TButton").pack(side="left")

        rules = ttk.Labelframe(tab, text="Правила заливки", padding=14)
        rules.pack(fill="x", pady=(0, 14))
        ttk.Label(rules, text="Настройки обновляемых MO2-папок и отдельных DB-файлов. После изменения правил выпусти новый лаунчер, потом контент.", style="CardMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(rules)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Показать правила", command=self.show_update_rules).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="MO2 папка стандарт", command=self.add_mo2_standard_rule).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="MO2 папка целиком", command=self.add_mo2_full_rule).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Убрать MO2 правило", command=self.remove_mo2_rule).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Удалить MO2 файл", command=self.delete_mo2_file, style="Danger.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Удалить MO2 папку", command=self.delete_mo2_folder, style="Danger.TButton").pack(side="left")
        row = ttk.Frame(rules)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Добавить DB файл", command=self.add_db_file_rule).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Убрать DB файл", command=self.remove_db_file_rule).pack(side="left", padx=(0, 8))

        db = ttk.Labelframe(tab, text="DB / Work Git", padding=14)
        db.pack(fill="x")
        ttk.Label(db, text="Сканирует live db/configs, db/mods и shaders_anthology.xdb0, затем грузит release assets.", style="CardMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(db)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Git-статус", command=lambda: self.run_git_status(WORKGIT_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Опубликовать DB", command=self.publish_db, style="Accent.TButton").pack(side="left")

    def _build_launcher_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Лаунчер и новости")

        launcher = ttk.Labelframe(tab, text="Лаунчер", padding=14)
        launcher.pack(fill="x", pady=(0, 14))
        ttk.Label(launcher, text="Сборка exe, commit/push и замена AnomalyLauncher.exe в latest release. exe_url всегда пишется с ?v=версия.", style="CardMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(launcher)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Git-статус лаунчера", command=lambda: self.run_git_status(LAUNCHER_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Проверить manifest/exe", command=self.check_launcher_public).pack(side="left", padx=(0, 8))

        news = ttk.Labelframe(tab, text="Новости лаунчера", padding=14)
        news.pack(fill="both", expand=True)
        top = ttk.Frame(news)
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="Обновить список", command=self.refresh_news).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Новая новость", command=self.new_news_draft).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Сохранить текст", command=self.edit_news).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Удалить выбранную", command=self.delete_news, style="Danger.TButton").pack(side="left")
        ttk.Button(top, text="Опубликовать черновик", command=self.publish_news_changes, style="Accent.TButton").pack(side="right")

        editor = ttk.PanedWindow(news, orient="horizontal")
        editor.pack(fill="both", expand=True)

        list_frame = ttk.Frame(editor)
        editor.add(list_frame, weight=1)
        form = ttk.Frame(editor, padding=(14, 0, 0, 0))
        editor.add(form, weight=3)

        self.news_drag_label = tk.StringVar(value="Перетащи новость мышкой, чтобы поменять порядок.")
        ttk.Label(list_frame, textvariable=self.news_drag_label, style="Muted.TLabel").pack(anchor="w", pady=(0, 6))

        columns = ("index", "title")
        self.news_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        self.news_tree.heading("index", text="#")
        self.news_tree.heading("title", text="Новость")
        self.news_tree.column("index", width=54, stretch=False, anchor="center")
        self.news_tree.column("title", width=300)
        self.news_tree.pack(fill="both", expand=True)
        self.news_tree.tag_configure("drag_target", background="#2b7165", foreground="#ffffff")
        self.news_tree.tag_configure("drag_source", background="#31424a", foreground="#ffffff")
        self.news_tree.bind("<<TreeviewSelect>>", self.on_news_select)
        self.news_tree.bind("<ButtonPress-1>", self.on_news_drag_start)
        self.news_tree.bind("<B1-Motion>", self.on_news_drag_motion)
        self.news_tree.bind("<ButtonRelease-1>", self.on_news_drag_drop)

        self.news_ru_title = tk.StringVar()
        self.news_en_title = tk.StringVar()
        self.news_status = tk.StringVar(value="Черновик: без изменений")
        self.news_selected_label = tk.StringVar(value="Выбери новость слева или создай новую.")
        self.news_ru_title.trace_add("write", lambda *_args: self.update_news_list_title_from_form())
        self.news_en_title.trace_add("write", lambda *_args: self.update_news_list_title_from_form())
        ttk.Label(form, textvariable=self.news_status, style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        ttk.Label(form, textvariable=self.news_selected_label, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        self._form_entry(form, "RU заголовок", self.news_ru_title)
        self.news_ru_body = self._form_text(form, "RU текст", height=6)
        self._form_entry(form, "EN title", self.news_en_title)
        self.news_en_body = self._form_text(form, "EN body", height=6)

    def _build_engine_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="MT движок")

        box = ttk.Labelframe(tab, text="MT engine", padding=14)
        box.pack(fill="x")
        ttk.Label(box, text="Сборка/упаковка движка и повторный upload ZIP в release.", style="CardMuted.TLabel").pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Git-статус", command=lambda: self.run_git_status(ENGINE_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Опубликовать MT", command=self.publish_engine, style="Accent.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Повторить upload ZIP", command=self.retry_engine_upload).pack(side="left")

    def _build_status_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(tab, text="Статусы")
        ttk.Label(tab, text="Быстрая проверка рабочих деревьев перед публикацией.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(tab)
        row.pack(fill="x")
        ttk.Button(row, text="Все git-статусы", command=self.all_git_statuses).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Проверить публичный launcher", command=self.check_launcher_public).pack(side="left")

    def _form_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        entry = tk.Entry(
            parent,
            textvariable=variable,
            bg=COLORS["log_bg"],
            fg=COLORS["log_text"],
            insertbackground=COLORS["log_text"],
            selectbackground="#245d55",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.bind_text_input_shortcuts(entry)
        entry.pack(fill="x", pady=(0, 10))

    def _form_text(self, parent: ttk.Frame, label: str, height: int) -> tk.Text:
        ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        text = tk.Text(
            parent,
            height=height,
            wrap="word",
            bg=COLORS["log_bg"],
            fg=COLORS["log_text"],
            insertbackground=COLORS["log_text"],
            selectbackground="#245d55",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.bind_text_input_shortcuts(text)
        text.pack(fill="both", expand=True, pady=(0, 10))
        return text

    def bind_text_input_shortcuts(self, widget: tk.Entry | tk.Text) -> None:
        for sequence in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
            widget.bind(sequence, self.paste_into_text_input)
        widget.bind("<<Paste>>", self.paste_into_text_input)
        for sequence in ("<Control-c>", "<Control-C>"):
            widget.bind(sequence, self.copy_from_text_input)
        widget.bind("<<Copy>>", self.copy_from_text_input)
        for sequence in ("<Control-x>", "<Control-X>"):
            widget.bind(sequence, self.cut_from_text_input)
        widget.bind("<<Cut>>", self.cut_from_text_input)
        for sequence in ("<Control-a>", "<Control-A>"):
            widget.bind(sequence, self.select_all_text_input)
        widget.bind("<Control-KeyPress>", self.control_key_text_input)
        widget.bind("<KeyPress>", self.any_key_text_input)
        widget.bind("<Button-3>", self.show_text_context_menu)
        widget.bind("<Button-2>", self.show_text_context_menu)

    def is_control_pressed(self, event) -> bool:
        return bool(int(getattr(event, "state", 0) or 0) & 0x4)

    def is_key(self, event, latin: str, cyrillic_keysym: str, cyrillic_letter: str, vk_code: int) -> bool:
        key = str(getattr(event, "keysym", "")).lower()
        char = str(getattr(event, "char", "")).lower()
        keycode = int(getattr(event, "keycode", 0) or 0)
        return key in (latin, cyrillic_keysym.lower(), cyrillic_letter) or char in (latin, cyrillic_letter) or keycode == vk_code

    def any_key_text_input(self, event) -> str | None:
        if self.is_control_pressed(event):
            return self.control_key_text_input(event)
        return None

    def control_key_text_input(self, event) -> str | None:
        if self.is_key(event, "v", "Cyrillic_em", "м", 86):
            return self.paste_into_text_input(event)
        if self.is_key(event, "c", "Cyrillic_es", "с", 67):
            return self.copy_from_text_input(event)
        if self.is_key(event, "x", "Cyrillic_che", "ч", 88):
            return self.cut_from_text_input(event)
        if self.is_key(event, "a", "Cyrillic_ef", "ф", 65):
            return self.select_all_text_input(event)
        return None

    def show_text_context_menu(self, event) -> str:
        self.text_context_widget = event.widget
        event.widget.focus_set()
        self.text_context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def menu_text_action(self, action: str) -> None:
        widget = self.text_context_widget or self.focus_get()
        if not isinstance(widget, (tk.Entry, tk.Text)):
            return
        event = type("TextMenuEvent", (), {"widget": widget})()
        if action == "paste":
            self.paste_into_text_input(event)
        elif action == "copy":
            self.copy_from_text_input(event)
        elif action == "cut":
            self.cut_from_text_input(event)
        elif action == "select_all":
            self.select_all_text_input(event)

    def paste_into_text_input(self, event) -> str:
        widget = event.widget
        try:
            value = self.clipboard_get()
        except tk.TclError:
            return "break"
        if isinstance(widget, tk.Text):
            try:
                widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            widget.insert("insert", value)
        else:
            try:
                widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            widget.insert("insert", value)
        widget.focus_set()
        return "break"

    def copy_from_text_input(self, event) -> str:
        widget = event.widget
        try:
            value = widget.get("sel.first", "sel.last") if isinstance(widget, tk.Text) else widget.selection_get()
        except tk.TclError:
            return "break"
        self.clipboard_clear()
        self.clipboard_append(value)
        return "break"

    def cut_from_text_input(self, event) -> str:
        widget = event.widget
        self.copy_from_text_input(event)
        try:
            if isinstance(widget, tk.Text):
                widget.delete("sel.first", "sel.last")
            else:
                widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        return "break"

    def select_all_text_input(self, event) -> str:
        widget = event.widget
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "1.0")
            widget.see("insert")
        else:
            widget.selection_range(0, "end")
            widget.icursor("end")
        widget.focus_set()
        return "break"

    def refresh_versions(self, refresh_news: bool = False) -> None:
        def work() -> None:
            for key, path, label in (
                ("launcher", LAUNCHER_DIR / "launcher_version.json", "Лаунчер"),
                ("mo2", MODPACK_DIR / "version.json", "MO2"),
                ("db", WORKGIT_DIR / "db_version.json", "DB"),
                ("engine", ENGINE_DIR / "engine_version.json", "MT"),
            ):
                try:
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                    self.queue.put(("version", f"{key}|{label}: {data.get('version', '?')}"))
                except Exception as exc:
                    self.queue.put(("version", f"{key}|{label}: ошибка ({exc})"))
            if refresh_news:
                self.queue.put(("call", "refresh_news_silent"))

        threading.Thread(target=work, daemon=True).start()

    def refresh_news(self) -> None:
        has_draft_changes = self.news_dirty or self.news_form_differs_from_index(self.news_selected_index)
        if has_draft_changes and not messagebox.askyesno("Новости", "В черновике есть неопубликованные изменения.\n\nСбросить их и заново загрузить новости из лаунчера?"):
            return
        self.run_command(
            [sys.executable, str(HELPER), "launcher-news-list"],
            WORKGIT_DIR,
            on_success=lambda _out: self.refresh_news_silent(),
            title="Список новостей",
        )

    def refresh_news_silent(self) -> None:
        if self.running:
            return

        def work() -> None:
            try:
                ru = subprocess.run(
                    [sys.executable, str(HELPER), "launcher-news-list", "--lang", "ru"],
                    cwd=str(WORKGIT_DIR),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                en = subprocess.run(
                    [sys.executable, str(HELPER), "launcher-news-list", "--lang", "en"],
                    cwd=str(WORKGIT_DIR),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                if ru.returncode == 0 and en.returncode == 0:
                    self.queue.put(("news_json", json.dumps({"ru": ru.stdout or "", "en": en.stdout or ""})))
                else:
                    self.queue.put(("log", ((ru.stdout or "") + "\n" + (en.stdout or "")).strip()))
            except Exception as exc:
                self.queue.put(("log", f"Не удалось тихо обновить новости: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _load_news_json(self, output: str) -> None:
        try:
            payload = json.loads(output)
            if "ru" in payload and "en" in payload:
                ru_payload = json.loads(payload["ru"])
                en_payload = json.loads(payload["en"])
            else:
                ru_payload = payload
                en_output = subprocess.run(
                    [sys.executable, str(HELPER), "launcher-news-list", "--lang", "en"],
                    cwd=str(WORKGIT_DIR),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                ).stdout
                en_payload = json.loads(en_output)
            self.news_items = ru_payload.get("news", [])
            self.news_items_en = en_payload.get("news", [])
            self.news_dirty = False
        except Exception as exc:
            messagebox.showerror("Новости", f"Не удалось прочитать список новостей:\n{exc}")
            return
        self.render_news_tree(select_index=1 if self.news_items else None)

    def render_news_tree(self, select_index: int | None = None) -> None:
        self.loading_news_form = True
        try:
            self.news_tree.delete(*self.news_tree.get_children())
            en_by_index = {int(item["index"]): item for item in self.news_items_en}
            for item in self.news_items:
                en_item = en_by_index.get(int(item["index"]), {})
                ru_title = item.get("title", "") or "(новая новость)"
                en_title = en_item.get("title", "") or "draft"
                self.news_tree.insert(
                    "",
                    "end",
                    iid=str(item["index"]),
                    values=(item["index"], f"{ru_title} / {en_title}"),
                )
            if select_index is not None and self.news_tree.exists(str(select_index)):
                self.news_tree.selection_set(str(select_index))
                self.news_tree.see(str(select_index))
                self.load_selected_news_into_form()
            elif self.news_items and not self.news_tree.selection():
                self.news_tree.selection_set(str(self.news_items[0]["index"]))
                self.load_selected_news_into_form()
            elif not self.news_items:
                self.clear_news_form("Список пустой. Нажми 'Новая новость', чтобы добавить черновик.")
            self.update_news_status()
        finally:
            self.loading_news_form = False

    def update_news_status(self) -> None:
        state = "есть неопубликованные изменения" if self.news_dirty else "без неопубликованных изменений"
        self.news_status.set(f"Черновик: {len(self.news_items)} новостей, {state}")

    def reindex_news_items(self) -> None:
        en_by_index = {int(item["index"]): item for item in self.news_items_en}
        new_ru: list[dict] = []
        new_en: list[dict] = []
        for new_index, item in enumerate(self.news_items, start=1):
            old_index = int(item["index"])
            en_item = en_by_index.get(old_index, {})
            new_ru.append({"index": new_index, "title": item.get("title", ""), "body": item.get("body", "")})
            new_en.append({"index": new_index, "title": en_item.get("title", item.get("title", "")), "body": en_item.get("body", item.get("body", ""))})
        self.news_items = new_ru
        self.news_items_en = new_en

    def move_news_item(self, source_index: int, target_index: int) -> int:
        if source_index == target_index:
            return source_index
        old_ru = list(self.news_items)
        old_en_by_index = {int(item["index"]): item for item in self.news_items_en}
        source_pos = next((pos for pos, item in enumerate(old_ru) if int(item["index"]) == source_index), None)
        target_pos = next((pos for pos, item in enumerate(old_ru) if int(item["index"]) == target_index), None)
        if source_pos is None or target_pos is None:
            return source_index

        item = old_ru.pop(source_pos)
        old_ru.insert(target_pos, item)
        new_ru: list[dict] = []
        new_en: list[dict] = []
        new_selected_index = 1
        for new_index, ru_item in enumerate(old_ru, start=1):
            old_index = int(ru_item["index"])
            en_item = old_en_by_index.get(old_index, {})
            if old_index == source_index:
                new_selected_index = new_index
            new_ru.append({"index": new_index, "title": ru_item.get("title", ""), "body": ru_item.get("body", "")})
            new_en.append({"index": new_index, "title": en_item.get("title", ru_item.get("title", "")), "body": en_item.get("body", ru_item.get("body", ""))})
        self.news_items = new_ru
        self.news_items_en = new_en
        self.news_dirty = True
        return new_selected_index

    def run_git_status(self, root: Path) -> None:
        self.run_command(["git", "status", "--short", "--branch"], root, title=f"git status: {root}")

    def all_git_statuses(self) -> None:
        for root in (WORKGIT_DIR, LAUNCHER_DIR, MODPACK_DIR, ENGINE_DIR):
            self.run_git_status(root)

    def show_update_rules(self) -> None:
        self._log(json.dumps(read_update_rules(), ensure_ascii=False, indent=2))

    def add_mo2_standard_rule(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(MODPACK_DIR), title="Выбери MO2 папку для стандартной заливки")
        if not selected:
            return
        folder = mo2_folder_from_path(selected)
        data = read_update_rules()
        rules = data.setdefault("mo2", {})
        values = set(rules.setdefault("managed_standard_folders", []))
        values.add(folder)
        rules["managed_standard_folders"] = sorted(values, key=str.casefold)
        write_update_rules(data)
        ensure_standard_folder_gitignore(folder)
        self._log(f"MO2 standard rule added: {folder}")

    def add_mo2_full_rule(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(MODPACK_DIR), title="Выбери MO2 папку для полной заливки")
        if not selected:
            return
        folder = mo2_folder_from_path(selected)
        data = read_update_rules()
        rules = data.setdefault("mo2", {})
        values = set(rules.setdefault("managed_full_folders", []))
        values.add(folder)
        rules["managed_full_folders"] = sorted(values, key=str.casefold)
        write_update_rules(data)
        ensure_full_folder_gitignore(folder)
        self._log(f"MO2 full-folder rule added: {folder}")

    def remove_mo2_rule(self) -> None:
        folder = filedialog.askdirectory(initialdir=str(MODPACK_DIR), title="Выбери MO2 папку, для которой убрать правило")
        if not folder:
            return
        folder = mo2_folder_from_path(folder)
        data = read_update_rules()
        rules = data.setdefault("mo2", {})
        removed = False
        for key in ("managed_standard_folders", "managed_full_folders"):
            values = rules.setdefault(key, [])
            kept = [value for value in values if value.casefold() != folder.casefold()]
            removed = removed or len(kept) != len(values)
            rules[key] = kept
        write_update_rules(data)
        self._log(f"MO2 rule removed: {folder}" if removed else f"MO2 rule not found: {folder}")

    def delete_mo2_file(self) -> None:
        selected = filedialog.askopenfilename(initialdir=str(MODPACK_DIR), title="Выбери MO2 файл для удаления")
        if not selected:
            return
        self._delete_mo2_path(Path(selected), expect_dir=False)

    def delete_mo2_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(MODPACK_DIR), title="Выбери MO2 папку для удаления")
        if not selected:
            return
        self._delete_mo2_path(Path(selected), expect_dir=True)

    def _delete_mo2_path(self, path: Path, expect_dir: bool) -> None:
        try:
            resolved = path.resolve()
            root = MODPACK_DIR.resolve()
            if not resolved.is_relative_to(root):
                messagebox.showerror("MO2 delete", f"Путь вне модпака:\n{resolved}")
                return
            if expect_dir and not resolved.is_dir():
                messagebox.showerror("MO2 delete", f"Это не папка:\n{resolved}")
                return
            if not expect_dir and not resolved.is_file():
                messagebox.showerror("MO2 delete", f"Это не файл:\n{resolved}")
                return
            rel = resolved.relative_to(root).as_posix()
            if not messagebox.askyesno("MO2 delete", f"Удалить локально?\n\n{rel}\n\nСледующий MO2 релиз удалит это у игроков через removed_files."):
                return
            if expect_dir:
                shutil.rmtree(resolved)
            else:
                resolved.unlink()
            self._log(f"MO2 deleted locally: {rel}")
        except Exception as exc:
            messagebox.showerror("MO2 delete", str(exc))

    def add_db_file_rule(self) -> None:
        selected = filedialog.askopenfilenames(initialdir=str(LIVE_GAME_DIR / "db"), title="Выбери DB файл(ы) для заливки")
        if not selected:
            return
        data = read_update_rules()
        db = data.setdefault("db", {})
        source_files = db.setdefault("source_files", {})
        removed = set(db.setdefault("removed_files", []))
        added = []
        for item in selected:
            path = Path(item)
            try:
                rel = db_rel_from_source(path)
            except ValueError:
                messagebox.showerror("DB rule", f"Файл должен быть внутри:\n{LIVE_GAME_DIR / 'db'}\n\n{path}")
                continue
            source_files[rel] = str(path)
            removed.discard(rel)
            added.append(rel)
        db["removed_files"] = sorted(removed, key=str.casefold)
        write_update_rules(data)
        self._log("DB file rule added:\n" + "\n".join(f"  {rel}" for rel in added))

    def remove_db_file_rule(self) -> None:
        selected = filedialog.askopenfilenames(initialdir=str(LIVE_GAME_DIR / "db"), title="Выбери DB файл(ы), которые убрать из заливки")
        if not selected:
            return
        data = read_update_rules()
        db = data.setdefault("db", {})
        source_files = db.setdefault("source_files", {})
        removed = set(db.setdefault("removed_files", []))
        removed_now = []
        for item in selected:
            path = Path(item)
            try:
                rel = db_rel_from_source(path)
            except ValueError:
                messagebox.showerror("DB rule", f"Файл должен быть внутри:\n{LIVE_GAME_DIR / 'db'}\n\n{path}")
                continue
            source_files.pop(rel, None)
            removed.add(rel)
            removed_now.append(rel)
        db["removed_files"] = sorted(removed, key=str.casefold)
        write_update_rules(data)
        self._log("DB file rule removed and marked for player deletion:\n" + "\n".join(f"  {rel}" for rel in removed_now))

    def preview_modpack_removed(self) -> None:
        self.run_command([sys.executable, str(HELPER), "modpack-removed"], WORKGIT_DIR, title="MO2 removed_files preview")

    def publish_mo2(self) -> None:
        version = self.ask_version("MO2")
        if not version:
            return
        notes = self.ask_notes("Заметки MO2", "Обновление MO2 модпака.")
        if notes is None:
            return
        if not self.confirm_publish_mo2(version):
            return
        self.run_command([sys.executable, str(HELPER), "modpack", "--version", version, "--notes", notes], WORKGIT_DIR, title=f"Publish MO2 {version}")

    def publish_modpack_folder(self) -> None:
        selected_value = filedialog.askdirectory(
            initialdir=str(MODPACK_DIR),
            title="Выбери одну верхнеуровневую папку мода/фикса",
        )
        if not selected_value:
            return
        selected = Path(selected_value).resolve()
        try:
            relative = selected.relative_to(MODPACK_DIR.resolve())
        except ValueError:
            messagebox.showerror("Мод/фикс", f"Папка должна находиться внутри:\n{MODPACK_DIR}")
            return
        if len(relative.parts) != 1 or not selected.is_dir():
            messagebox.showerror("Мод/фикс", "Выбери верхнеуровневую папку непосредственно внутри MO2 mods.")
            return

        full = messagebox.askyesnocancel(
            "Режим отдельного пакета",
            "Что включить в отдельный пакет?\n\n"
            "Да — всю папку целиком.\n"
            "Нет — только gamedata/configs, gamedata/scripts и gamedata/textures.\n"
            "Отмена — ничего не делать.",
        )
        if full is None:
            return
        mode = "full" if full else "standard"
        version = self.ask_version("мода/фикса")
        if not version:
            return
        notes = self.ask_notes("Заметки отдельного мода/фикса", f"Обновление {relative.as_posix()}.")
        if notes is None:
            return
        status = self.capture(
            ["git", "-c", "core.quotePath=false", "status", "--short", "--", relative.as_posix()],
            MODPACK_DIR,
        )
        mode_label = "папка целиком" if mode == "full" else "configs/scripts/textures"
        message = (
            f"Опубликовать отдельный мод/фикс?\n\n"
            f"Папка:\n{relative.as_posix()}\n\n"
            f"Версия: {version}\n"
            f"Режим: {mode_label}\n\n"
            f"Изменения выбранной папки:\n{status or '(Git не видит изменений)'}\n\n"
            "Будет создан отдельный ZIP. В commit попадут только выбранная папка и version.json. "
            "Остальные локальные изменения не будут добавлены.\n\n"
            "Важно: игрокам сначала нужен лаунчер с поддержкой отдельных пакетов."
        )
        if not messagebox.askyesno("Подтверждение отдельного пакета", message):
            return
        self.run_command(
            [
                sys.executable,
                str(HELPER),
                "modpack-folder",
                "--folder",
                str(selected),
                "--mode",
                mode,
                "--version",
                version,
                "--notes",
                notes,
            ],
            WORKGIT_DIR,
            title=f"Publish folder package {relative.as_posix()} {version}",
        )

    def publish_db(self) -> None:
        version = self.ask_version("DB")
        if not version:
            return
        notes = self.ask_notes("Заметки DB", "Обновление DB Anthology.")
        if notes is None:
            return
        if not self.confirm_publish_db(version):
            return
        self.run_command([sys.executable, str(HELPER), "workgit", "--version", version, "--notes", notes], WORKGIT_DIR, title=f"Publish DB {version}")

    def publish_engine(self) -> None:
        version = self.ask_version("MT")
        if not version:
            return
        notes = self.ask_notes("Заметки MT", "Обновление MT движка.")
        if notes is None:
            return
        if not messagebox.askyesno("MT engine", "Собрать, упаковать и опубликовать MT engine?\n\nЭто тяжёлая операция."):
            return
        wizard = WORKGIT_DIR / "skills" / "anthology-release-ops" / "scripts" / "anthology_publish_wizard.py"
        self.run_command(
            [sys.executable, str(wizard), "--target", "engine", "--engine-version", version, "--engine-notes", notes, "--yes"],
            WORKGIT_DIR,
            title=f"Publish MT {version}",
        )

    def retry_engine_upload(self) -> None:
        version = self.ask_version("MT", allow_current=True)
        if not version:
            return
        if not messagebox.askyesno("MT upload", f"Повторно загрузить ZIP для версии {version}?"):
            return
        wizard = WORKGIT_DIR / "skills" / "anthology-release-ops" / "scripts" / "anthology_publish_wizard.py"
        self.run_command(
            [sys.executable, str(wizard), "--target", "engine-upload", "--engine-version", version, "--yes"],
            WORKGIT_DIR,
            title=f"Retry MT upload {version}",
        )

    def add_news(self) -> None:
        title, body, title_en, body_en = self.news_form_values()
        if not title or not body:
            messagebox.showwarning("Новости", "Заполни хотя бы RU заголовок и RU текст.")
            return
        self.news_items.insert(0, {"index": 0, "title": title, "body": body})
        self.news_items_en.insert(0, {"index": 0, "title": title_en, "body": body_en})
        self.reindex_news_items()
        self.news_dirty = True
        self.render_news_tree(select_index=1)

    def selected_news(self, warn: bool = True) -> dict | None:
        selection = self.news_tree.selection()
        if not selection:
            if warn:
                messagebox.showwarning("Новости", "Сначала выбери новость в списке слева.")
            return None
        index = int(selection[0])
        return next((item for item in self.news_items if int(item["index"]) == index), None)

    def english_news_for(self, index: int) -> dict:
        return next((item for item in self.news_items_en if int(item["index"]) == index), {})

    def set_text_value(self, widget: tk.Text, value: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    def text_value(self, widget: tk.Text) -> str:
        return widget.get("1.0", "end").strip()

    def news_form_values(self) -> tuple[str, str, str, str]:
        title = self.news_ru_title.get().strip()
        body = self.text_value(self.news_ru_body)
        title_en = self.news_en_title.get().strip() or title
        body_en = self.text_value(self.news_en_body) or body
        return title, body, title_en, body_en

    def update_news_list_title_from_form(self) -> None:
        if self.loading_news_form or self.news_selected_index is None:
            return
        index = self.news_selected_index
        item = next((entry for entry in self.news_items if int(entry["index"]) == index), None)
        if not item or not self.news_tree.exists(str(index)):
            return
        ru_title = self.news_ru_title.get().strip()
        en_title = self.news_en_title.get().strip() or ru_title
        changed = item.get("title", "") != ru_title
        item["title"] = ru_title
        en_item = self.english_news_for(index)
        if en_item:
            changed = changed or en_item.get("title", "") != en_title
            en_item["title"] = en_title
        else:
            self.news_items_en.append({"index": index, "title": en_title, "body": self.text_value(self.news_en_body)})
            changed = True
        visible_ru = ru_title or "(новая новость)"
        visible_en = en_title or "draft"
        self.news_tree.item(str(index), values=(index, f"{visible_ru} / {visible_en}"))
        if changed:
            self.news_dirty = True
            self.update_news_status()

    def clear_news_form(self, label: str) -> None:
        self.news_tree.selection_remove(self.news_tree.selection())
        self.news_selected_index = None
        self.news_selected_label.set(label)
        self.loading_news_form = True
        try:
            self.news_ru_title.set("")
            self.news_en_title.set("")
            self.set_text_value(self.news_ru_body, "")
            self.set_text_value(self.news_en_body, "")
        finally:
            self.loading_news_form = False
        self.update_news_status()

    def new_news_draft(self) -> None:
        self.save_news_form_to_index(self.news_selected_index, validate=False)
        self.news_items.insert(0, {"index": 0, "title": "", "body": ""})
        self.news_items_en.insert(0, {"index": 0, "title": "", "body": ""})
        self.reindex_news_items()
        self.news_dirty = True
        self.render_news_tree(select_index=1)
        self.news_selected_label.set("Новая новость в черновике: заполни поля справа и нажми 'Сохранить текст'.")

    def on_news_select(self, _event=None) -> None:
        if self.loading_news_form:
            return
        self.save_news_form_to_index(self.news_selected_index, validate=False)
        self.load_selected_news_into_form()

    def news_index_from_event(self, event) -> int | None:
        row = self.news_tree.identify_row(event.y)
        if not row:
            return None
        try:
            return int(row)
        except ValueError:
            return None

    def on_news_drag_start(self, event) -> None:
        self.news_drag_index = self.news_index_from_event(event)
        self.news_drag_target = self.news_drag_index
        if self.news_drag_index is None:
            return
        item = next((entry for entry in self.news_items if int(entry["index"]) == self.news_drag_index), {})
        self.news_drag_source_title = str(item.get("title", "")) or "(новая новость)"
        self.news_tree.configure(cursor="hand2")
        self.set_news_drag_tags(source=self.news_drag_index, target=self.news_drag_index)
        self.news_drag_label.set(f"Тащишь #{self.news_drag_index}: {self.news_drag_source_title}")
        self.show_news_drag_ghost(event)

    def on_news_drag_motion(self, event) -> None:
        if self.news_drag_index is not None:
            self.move_news_drag_ghost(event)
        target = self.news_index_from_event(event)
        if target is None or self.news_drag_index is None:
            return
        self.news_drag_target = target
        self.set_news_drag_tags(source=self.news_drag_index, target=target)
        self.news_drag_label.set(f"Тащишь #{self.news_drag_index} -> позиция #{target}: {self.news_drag_source_title}")
        if self.news_tree.exists(str(target)):
            self.news_tree.selection_set(str(target))
            self.news_tree.see(str(target))

    def on_news_drag_drop(self, event) -> None:
        source = self.news_drag_index
        target = self.news_index_from_event(event) or self.news_drag_target
        self.news_drag_index = None
        self.news_drag_target = None
        self.news_tree.configure(cursor="")
        self.clear_news_drag_tags()
        self.hide_news_drag_ghost()
        if source is None or target is None or source == target:
            self.news_drag_label.set("Перетащи новость мышкой, чтобы поменять порядок.")
            return
        self.save_news_form_to_index(self.news_selected_index, validate=False)
        new_index = self.move_news_item(source, target)
        self.render_news_tree(select_index=new_index)
        self.news_drag_label.set(f"Готово: новость теперь на позиции #{new_index}.")
        self.news_selected_label.set(f"Новость перемещена на позицию #{new_index}. Черновик ещё не опубликован.")

    def set_news_drag_tags(self, source: int, target: int) -> None:
        self.clear_news_drag_tags()
        if self.news_tree.exists(str(source)):
            self.news_tree.item(str(source), tags=("drag_source",))
        if target != source and self.news_tree.exists(str(target)):
            self.news_tree.item(str(target), tags=("drag_target",))

    def clear_news_drag_tags(self) -> None:
        for iid in self.news_tree.get_children():
            self.news_tree.item(iid, tags=())

    def show_news_drag_ghost(self, event) -> None:
        self.hide_news_drag_ghost()
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        ghost.attributes("-topmost", True)
        ghost.configure(bg=COLORS["accent"])
        label = tk.Label(
            ghost,
            text=f"#{self.news_drag_index}  {self.news_drag_source_title}",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            padx=12,
            pady=7,
            width=46,
            anchor="w",
            font=("Segoe UI Semibold", 9),
        )
        label.pack(padx=1, pady=1)
        self.news_drag_ghost = ghost
        self.move_news_drag_ghost(event)

    def move_news_drag_ghost(self, event) -> None:
        if not self.news_drag_ghost:
            return
        self.news_drag_ghost.geometry(f"+{event.x_root + 14}+{event.y_root + 14}")

    def hide_news_drag_ghost(self) -> None:
        if self.news_drag_ghost:
            try:
                self.news_drag_ghost.destroy()
            except tk.TclError:
                pass
            self.news_drag_ghost = None

    def load_selected_news_into_form(self) -> None:
        item = self.selected_news(warn=False)
        if not item:
            return
        index = int(item["index"])
        en_item = self.english_news_for(index)
        self.news_selected_index = index
        self.news_selected_label.set(f"Выбрана: новость #{index}")
        self.loading_news_form = True
        try:
            self.news_ru_title.set(str(item.get("title", "")))
            self.set_text_value(self.news_ru_body, str(item.get("body", "")))
            self.news_en_title.set(str(en_item.get("title", "")))
            self.set_text_value(self.news_en_body, str(en_item.get("body", "")))
        finally:
            self.loading_news_form = False

    def save_news_form_to_index(self, index: int | None, validate: bool = True) -> bool:
        if index is None:
            return True
        item = next((entry for entry in self.news_items if int(entry["index"]) == index), None)
        if not item:
            return True
        title, body, title_en, body_en = self.news_form_values()
        if validate and (not title or not body):
            messagebox.showwarning("Новости", "Заполни хотя бы RU заголовок и RU текст.")
            return False
        changed = (
            item.get("title", "") != title
            or item.get("body", "") != body
        )
        item["title"] = title
        item["body"] = body
        en_item = self.english_news_for(index)
        if en_item:
            changed = changed or en_item.get("title", "") != title_en or en_item.get("body", "") != body_en
            en_item["title"] = title_en
            en_item["body"] = body_en
        else:
            self.news_items_en.append({"index": index, "title": title_en, "body": body_en})
            changed = True
        if changed:
            self.news_dirty = True
        return True

    def news_form_differs_from_index(self, index: int | None) -> bool:
        if index is None:
            return False
        item = next((entry for entry in self.news_items if int(entry["index"]) == index), None)
        if not item:
            return False
        title, body, title_en, body_en = self.news_form_values()
        en_item = self.english_news_for(index)
        return (
            item.get("title", "") != title
            or item.get("body", "") != body
            or en_item.get("title", "") != title_en
            or en_item.get("body", "") != body_en
        )

    def edit_news(self) -> None:
        item = self.selected_news()
        if not item:
            return
        index = int(item["index"])
        if not self.save_news_form_to_index(index, validate=True):
            return
        self.render_news_tree(select_index=index)

    def delete_news(self) -> None:
        self.save_news_form_to_index(self.news_selected_index, validate=False)
        item = self.selected_news()
        if not item:
            return
        index = int(item["index"])
        if not messagebox.askyesno("Удалить новость", f"Удалить новость #{index}?\n\n{item['title']}"):
            return
        self.news_items = [entry for entry in self.news_items if int(entry["index"]) != index]
        self.news_items_en = [entry for entry in self.news_items_en if int(entry["index"]) != index]
        self.reindex_news_items()
        self.news_dirty = True
        next_index = min(index, len(self.news_items)) if self.news_items else None
        self.render_news_tree(select_index=next_index)

    def news_payload(self) -> str:
        en_by_index = {int(item["index"]): item for item in self.news_items_en}
        news = []
        for item in self.news_items:
            index = int(item["index"])
            en_item = en_by_index.get(index, {})
            title = str(item.get("title", "")).strip()
            body = str(item.get("body", "")).strip()
            title_en = str(en_item.get("title", title)).strip() or title
            body_en = str(en_item.get("body", body)).strip() or body
            news.append({"title": title, "body": body, "title_en": title_en, "body_en": body_en})
        return json.dumps({"news": news}, ensure_ascii=False)

    def write_news_payload_file(self) -> Path:
        handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".json", prefix="anthology_launcher_news_")
        with handle:
            handle.write(self.news_payload())
        return Path(handle.name)

    def publish_news_changes(self) -> None:
        if not self.save_news_form_to_index(self.news_selected_index, validate=False):
            return
        self.render_news_tree(select_index=self.news_selected_index)
        if not self.news_items:
            messagebox.showwarning("Новости", "Список новостей пустой. Оставь хотя бы одну новость.")
            return
        for index, item in enumerate(self.news_items, start=1):
            if not str(item.get("title", "")).strip() or not str(item.get("body", "")).strip():
                messagebox.showwarning("Новости", f"Новость #{index} без RU заголовка или RU текста.")
                return
        version = self.ask_version("лаунчера")
        if not version:
            return
        notes = self.ask_notes("Заметки лаунчера", "Обновление новостей лаунчера.")
        if notes is None:
            return
        if not self.confirm_publish(f"список новостей лаунчера ({len(self.news_items)} шт.)", version, LAUNCHER_DIR):
            return
        payload_file = self.write_news_payload_file()
        self.run_command(
            [
                sys.executable,
                str(HELPER),
                "launcher-news-apply",
                "--version",
                version,
                "--notes",
                notes,
                "--news-file",
                str(payload_file),
            ],
            WORKGIT_DIR,
            on_success=lambda _out, path=payload_file: self.publish_news_done(path),
            title=f"Publish launcher news list {version}",
        )

    def publish_news_done(self, payload_file: Path | None = None) -> None:
        if payload_file:
            try:
                payload_file.unlink(missing_ok=True)
            except OSError:
                pass
        self.news_dirty = False
        self.update_news_status()
        self.refresh_news_silent()

    def check_launcher_public(self) -> None:
        script = (
            "$m=Invoke-RestMethod -Uri ('https://raw.githubusercontent.com/sysliveprime-ctrl/AnthologyLauncher/main/launcher_version.json?t=' + ([DateTimeOffset]::Now).ToUnixTimeSeconds()); "
            "$out=Join-Path $env:TEMP 'AnomalyLauncher_gui_check.exe'; "
            "Invoke-WebRequest -Uri $m.exe_url -OutFile $out -UseBasicParsing; "
            "$i=Get-Item $out; $h=(Get-FileHash -Algorithm SHA256 $out).Hash; "
            "[pscustomobject]@{version=$m.version; exe_url=$m.exe_url; size=$i.Length; sha256=$h} | Format-List"
        )
        self.run_command(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], WORKGIT_DIR, title="Проверка public launcher manifest/exe")

    def ask_version(self, label: str, allow_current: bool = False) -> str | None:
        default = time.strftime("%Y.%m.%d.1")
        value = simpledialog.askstring("Версия", f"Версия {label}:", initialvalue=default, parent=self)
        if not value and allow_current:
            return None
        return value.strip() if value else None

    def ask_notes(self, title: str, default: str) -> str | None:
        value = MultilineDialog(self, title, "Заметки:", initial=default).result
        return value

    def confirm_publish(self, target: str, version: str, root: Path) -> bool:
        status = self.capture(["git", "status", "--short", "--branch"], root)
        message = (
            f"Опубликовать {target} версии {version}?\n\n"
            f"Рабочая папка:\n{root}\n\n"
            f"Git status:\n{status or '(чисто)'}\n\n"
            "Проверь внимательно. После OK команда может сделать commit/push/upload."
        )
        return messagebox.askyesno("Подтверждение публикации", message)

    def confirm_publish_db(self, version: str) -> bool:
        try:
            changes = summarize_db_changes(WORKGIT_DIR / "db_version.json")
            summary = format_db_changes(changes)
        except Exception as exc:
            summary = f"Не удалось собрать список DB-изменений:\n{exc}"
        message = (
            f"Опубликовать DB версии {version}?\n\n"
            "Источник DB:\n"
            f"{LIVE_GAME_DIR / 'db'}\n\n"
            "Будут опубликованы только DB assets из правил:\n"
            "  db/configs/*\n"
            "  db/mods/*\n"
            "  db/shaders_anthology.xdb0\n"
            "  db/textures/textures_trees.xdb0\n"
            "  db/textures/textures_trees.xdb1\n"
            "  db/textures/textures_trees.xdb3\n\n"
            f"DB изменения:\n{summary}\n\n"
            "После OK команда обновит db_version.json, сделает commit/push только этого манифеста и загрузит release assets."
        )
        return messagebox.askyesno("Подтверждение публикации DB", message)

    def confirm_publish_mo2(self, version: str) -> bool:
        try:
            changes = summarize_git_changes(MODPACK_DIR)
            summary = format_git_changes(changes)
        except Exception as exc:
            summary = f"Не удалось собрать список MO2-изменений:\n{exc}"
        message = (
            f"Опубликовать MO2 версии {version}?\n\n"
            "Рабочая папка:\n"
            f"{MODPACK_DIR}\n\n"
            f"MO2 изменения:\n{summary}\n\n"
            "После OK команда обновит version.json, сделает commit/push и игроки получат новый main.zip."
        )
        return messagebox.askyesno("Подтверждение публикации MO2", message)

    def capture(self, args: list[str], cwd: Path) -> str:
        result = subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return result.stdout.strip()

    def run_command(self, args: list[str], cwd: Path, on_success=None, title: str | None = None) -> None:
        if self.running:
            messagebox.showwarning("Задача выполняется", "Дождись завершения текущей операции.")
            return
        self.running = True
        self.command_output = []
        self.command_status.set(f"Статус: выполняется - {title or 'команда'}")
        self.command_progress.start(12)
        self._log("\n" + "=" * 80)
        self._log(title or "Команда")
        self._log("+ " + " ".join(args))

        def work() -> None:
            try:
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                env["PYTHONUTF8"] = "1"
                process = subprocess.Popen(
                    args,
                    cwd=str(cwd),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    bufsize=1,
                    env=env,
                )
                assert process.stdout is not None
                for line in process.stdout:
                    self.command_output.append(line)
                    text = line.rstrip()
                    if text:
                        self.queue.put(("log", text))
                returncode = process.wait()
                output = "".join(self.command_output)
                if returncode == 0:
                    self.queue.put(("done", "OK"))
                    if on_success:
                        self.queue.put(("callback", on_success))
                        self.queue.put(("callback_arg", output))
                else:
                    tail = "\n".join(output.strip().splitlines()[-18:])
                    detail = f"Команда завершилась с кодом {returncode}"
                    if tail:
                        detail += "\n\nПоследний вывод:\n" + tail
                    self.queue.put(("error", detail))
            except Exception as exc:
                self.queue.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()
    def _drain_queue(self) -> None:
        callback = None
        while True:
            try:
                kind, value = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._log(value)
            elif kind == "version":
                key, text = value.split("|", 1)
                self.version_vars[key].set(text)
            elif kind == "done":
                self.running = False
                self.command_progress.stop()
                self.command_status.set("Статус: готово")
                self._log("Готово.")
                self.refresh_versions()
            elif kind == "error":
                self.running = False
                self.command_progress.stop()
                self.command_status.set("Статус: ошибка")
                self._log("ОШИБКА: " + value)
                messagebox.showerror("Ошибка", value)
            elif kind == "callback":
                callback = value
            elif kind == "callback_arg" and callback:
                callback(value)
                callback = None
            elif kind == "news_json":
                self._load_news_json(value)
            elif kind == "call" and value == "refresh_news_silent":
                self.refresh_news_silent()
        self.after(100, self._drain_queue)

    def _log(self, text: str) -> None:
        if not text:
            return
        self.log.insert("end", text + "\n")
        self.log.see("end")


def main() -> int:
    app = ReleaseControl()
    if "--smoke-test" in sys.argv:
        app.after(500, app.destroy)
    app.mainloop()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
