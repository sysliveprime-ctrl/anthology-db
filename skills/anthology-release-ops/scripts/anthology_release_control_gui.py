#!/usr/bin/env python3
"""Small GUI control panel for Anthology release operations."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, simpledialog, ttk


WORKGIT_DIR = Path(r"E:\dev\Anthology-Work-Git")
HELPER = WORKGIT_DIR / "skills" / "anthology-release-ops" / "scripts" / "anthology_release_ops.py"
LAUNCHER_DIR = WORKGIT_DIR / "projects" / "AnthologyLauncher"
MODPACK_DIR = Path(r"D:\Games\ANTHOLOGY\SYS_A.N.T.H.O.L.O.G.Y_mo2_CBT\mods")
ENGINE_DIR = Path(r"E:\dev\xray-monolith")

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


class ReleaseControl(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Anthology Release Control")
        self.geometry("1120x780")
        self.minsize(980, 680)

        self.queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.running = False
        self.news_items: list[dict] = []
        self.news_items_en: list[dict] = []
        self.news_dirty = False
        self.text_context_widget: tk.Entry | tk.Text | None = None
        self.news_selected_index: int | None = None
        self.loading_news_form = False

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
        ttk.Button(row, text="Опубликовать MO2", command=self.publish_mo2, style="Accent.TButton").pack(side="left")

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

        columns = ("index", "title")
        self.news_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        self.news_tree.heading("index", text="#")
        self.news_tree.heading("title", text="Новость")
        self.news_tree.column("index", width=54, stretch=False, anchor="center")
        self.news_tree.column("title", width=300)
        self.news_tree.pack(fill="both", expand=True)
        self.news_tree.bind("<<TreeviewSelect>>", self.on_news_select)

        self.news_ru_title = tk.StringVar()
        self.news_en_title = tk.StringVar()
        self.news_status = tk.StringVar(value="Черновик: без изменений")
        self.news_selected_label = tk.StringVar(value="Выбери новость слева или создай новую.")
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

    def run_git_status(self, root: Path) -> None:
        self.run_command(["git", "status", "--short", "--branch"], root, title=f"git status: {root}")

    def all_git_statuses(self) -> None:
        for root in (WORKGIT_DIR, LAUNCHER_DIR, MODPACK_DIR, ENGINE_DIR):
            self.run_git_status(root)

    def preview_modpack_removed(self) -> None:
        self.run_command([sys.executable, str(HELPER), "modpack-removed"], WORKGIT_DIR, title="MO2 removed_files preview")

    def publish_mo2(self) -> None:
        version = self.ask_version("MO2")
        if not version:
            return
        notes = self.ask_notes("Заметки MO2", "Обновление MO2 модпака.")
        if notes is None:
            return
        if not self.confirm_publish("MO2", version, MODPACK_DIR):
            return
        self.run_command([sys.executable, str(HELPER), "modpack", "--version", version, "--notes", notes], WORKGIT_DIR, title=f"Publish MO2 {version}")

    def publish_db(self) -> None:
        version = self.ask_version("DB")
        if not version:
            return
        notes = self.ask_notes("Заметки DB", "Обновление DB Anthology.")
        if notes is None:
            return
        if not self.confirm_publish("DB", version, WORKGIT_DIR):
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

    def clear_news_form(self, label: str) -> None:
        self.news_tree.selection_remove(self.news_tree.selection())
        self.news_selected_index = None
        self.news_selected_label.set(label)
        self.news_ru_title.set("")
        self.news_en_title.set("")
        self.set_text_value(self.news_ru_body, "")
        self.set_text_value(self.news_en_body, "")
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

    def load_selected_news_into_form(self) -> None:
        item = self.selected_news(warn=False)
        if not item:
            return
        index = int(item["index"])
        en_item = self.english_news_for(index)
        self.news_selected_index = index
        self.news_selected_label.set(f"Выбрана: новость #{index}")
        self.news_ru_title.set(str(item.get("title", "")))
        self.set_text_value(self.news_ru_body, str(item.get("body", "")))
        self.news_en_title.set(str(en_item.get("title", "")))
        self.set_text_value(self.news_en_body, str(en_item.get("body", "")))

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
            "$m=Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/sysliveprime-ctrl/AnthologyLauncher/main/launcher_version.json?t=' + [DateTimeOffset]::Now.ToUnixTimeSeconds(); "
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

    def capture(self, args: list[str], cwd: Path) -> str:
        result = subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return result.stdout.strip()

    def run_command(self, args: list[str], cwd: Path, on_success=None, title: str | None = None) -> None:
        if self.running:
            messagebox.showwarning("Задача выполняется", "Дождись завершения текущей операции.")
            return
        self.running = True
        self._log("\n" + "=" * 80)
        self._log(title or "Команда")
        self._log("+ " + " ".join(args))

        def work() -> None:
            try:
                result = subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                output = result.stdout or ""
                self.queue.put(("log", output.rstrip()))
                if result.returncode == 0:
                    self.queue.put(("done", "OK"))
                    if on_success:
                        self.queue.put(("callback", on_success))
                        self.queue.put(("callback_arg", output))
                else:
                    self.queue.put(("error", f"Команда завершилась с кодом {result.returncode}"))
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
                self._log("Готово.")
                self.refresh_versions()
            elif kind == "error":
                self.running = False
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
