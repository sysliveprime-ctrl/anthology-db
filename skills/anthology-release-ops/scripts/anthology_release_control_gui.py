#!/usr/bin/env python3
"""Small GUI control panel for Anthology release operations."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
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


class MultilineDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, title: str, label: str, initial: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.result: str | None = None
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text=label).pack(anchor="w", padx=12, pady=(12, 6))
        self.text = scrolledtext.ScrolledText(self, width=72, height=12, wrap="word")
        self.text.pack(fill="both", expand=True, padx=12, pady=6)
        self.text.insert("1.0", initial)
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

    def _bind_text_shortcuts(self) -> None:
        for sequence in ("<Control-v>", "<Control-V>", "<Shift-Insert>"):
            self.text.bind(sequence, lambda _event: self._paste_event())
        for sequence in ("<Control-c>", "<Control-C>"):
            self.text.bind(sequence, lambda event: self._text_event(event, "<<Copy>>"))
        for sequence in ("<Control-x>", "<Control-X>"):
            self.text.bind(sequence, lambda event: self._text_event(event, "<<Cut>>"))
        for sequence in ("<Control-a>", "<Control-A>"):
            self.text.bind(sequence, lambda _event: self._select_all_event())

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

        self._build_style()
        self._build_ui()
        self.after(100, self._drain_queue)
        self.refresh_versions(refresh_news=True)

    def _build_style(self) -> None:
        self.configure(bg="#111416")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#111416")
        style.configure("TLabel", background="#111416", foreground="#e8ecef")
        style.configure("Muted.TLabel", foreground="#9ba3aa")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 16), foreground="#42d6c5")
        style.configure("Danger.TButton", foreground="#ffdddd")
        style.configure("Accent.TButton", foreground="#eafffb")
        style.configure("TLabelframe", background="#111416", foreground="#dce4e8")
        style.configure("TLabelframe.Label", background="#111416", foreground="#dce4e8")

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(14, 12, 14, 8))
        header.pack(fill="x")
        ttk.Label(header, text="ANTHOLOGY: центр выпуска обновлений", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Обновить статусы", command=self.refresh_versions).pack(side="right")

        version_box = ttk.Frame(self, padding=(14, 0, 14, 8))
        version_box.pack(fill="x")
        self.version_vars = {
            "launcher": tk.StringVar(value="Лаунчер: ..."),
            "mo2": tk.StringVar(value="MO2: ..."),
            "db": tk.StringVar(value="DB: ..."),
            "engine": tk.StringVar(value="MT: ..."),
        }
        for var in self.version_vars.values():
            ttk.Label(version_box, textvariable=var, style="Muted.TLabel").pack(side="left", padx=(0, 24))

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=14, pady=(0, 14))

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

        self.log = scrolledtext.ScrolledText(log_frame, height=12, wrap="word", bg="#080a0b", fg="#d9f5ef", insertbackground="#d9f5ef")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
        self._log("Готово. Нажми кнопку, выбери версию/заметки, проверь подтверждение.")

    def _build_content_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="MO2 / DB")

        mo2 = ttk.Labelframe(tab, text="MO2 модпак", padding=12)
        mo2.pack(fill="x", pady=(0, 12))
        ttk.Label(mo2, text="Публикует D:\\Games\\...\\mods в anthology-mo2-modpack main.zip.", style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(mo2)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Показать git-статус MO2", command=lambda: self.run_git_status(MODPACK_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Предпросмотр удалений", command=self.preview_modpack_removed).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Опубликовать MO2", command=self.publish_mo2, style="Accent.TButton").pack(side="left")

        db = ttk.Labelframe(tab, text="DB / Work Git", padding=12)
        db.pack(fill="x")
        ttk.Label(db, text="Сканирует live db/configs, db/mods и shaders_anthology.xdb0, затем грузит release assets.", style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(db)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Показать git-статус Work Git", command=lambda: self.run_git_status(WORKGIT_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Опубликовать DB", command=self.publish_db, style="Accent.TButton").pack(side="left")

    def _build_launcher_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="Лаунчер и новости")

        launcher = ttk.Labelframe(tab, text="Лаунчер", padding=12)
        launcher.pack(fill="x", pady=(0, 12))
        ttk.Label(launcher, text="Сборка exe, commit/push и замена AnomalyLauncher.exe в latest release. exe_url всегда пишется с ?v=версия.", style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(launcher)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Git-статус лаунчера", command=lambda: self.run_git_status(LAUNCHER_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Проверить публичный manifest/exe", command=self.check_launcher_public).pack(side="left", padx=(0, 8))

        news = ttk.Labelframe(tab, text="Новости лаунчера", padding=12)
        news.pack(fill="both", expand=True)
        top = ttk.Frame(news)
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="Обновить список", command=self.refresh_news).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Добавить сверху", command=self.add_news).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Редактировать выбранную", command=self.edit_news).pack(side="left", padx=(0, 8))
        ttk.Button(top, text="Удалить выбранную", command=self.delete_news, style="Danger.TButton").pack(side="left")

        columns = ("index", "title", "body")
        self.news_tree = ttk.Treeview(news, columns=columns, show="headings", height=12)
        self.news_tree.heading("index", text="#")
        self.news_tree.heading("title", text="Заголовок")
        self.news_tree.heading("body", text="Текст")
        self.news_tree.column("index", width=48, stretch=False, anchor="center")
        self.news_tree.column("title", width=280)
        self.news_tree.column("body", width=620)
        self.news_tree.pack(fill="both", expand=True)

    def _build_engine_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="MT движок")

        box = ttk.Labelframe(tab, text="MT engine", padding=12)
        box.pack(fill="x")
        ttk.Label(box, text="Сборка/упаковка движка и повторный upload ZIP в release.", style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Git-статус engine", command=lambda: self.run_git_status(ENGINE_DIR)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Опубликовать MT", command=self.publish_engine, style="Accent.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Повторить upload ZIP", command=self.retry_engine_upload).pack(side="left")

    def _build_status_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text="Статусы")
        ttk.Label(tab, text="Быстрая проверка рабочих деревьев перед публикацией.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(tab)
        row.pack(fill="x")
        ttk.Button(row, text="Все git-статусы", command=self.all_git_statuses).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Проверить публичный launcher", command=self.check_launcher_public).pack(side="left")

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
        self.run_command([sys.executable, str(HELPER), "launcher-news-list"], WORKGIT_DIR, on_success=self._load_news_json, title="Список новостей")

    def refresh_news_silent(self) -> None:
        if self.running:
            return

        def work() -> None:
            try:
                result = subprocess.run(
                    [sys.executable, str(HELPER), "launcher-news-list"],
                    cwd=str(WORKGIT_DIR),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                if result.returncode == 0:
                    self.queue.put(("news_json", result.stdout or ""))
                else:
                    self.queue.put(("log", (result.stdout or "").rstrip()))
            except Exception as exc:
                self.queue.put(("log", f"Не удалось тихо обновить новости: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def _load_news_json(self, output: str) -> None:
        try:
            payload = json.loads(output)
            self.news_items = payload.get("news", [])
        except Exception as exc:
            messagebox.showerror("Новости", f"Не удалось прочитать список новостей:\n{exc}")
            return
        self.news_tree.delete(*self.news_tree.get_children())
        for item in self.news_items:
            body = str(item.get("body", "")).replace("\n", " ")
            self.news_tree.insert("", "end", iid=str(item["index"]), values=(item["index"], item.get("title", ""), body))

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
        version = self.ask_version("лаунчера")
        if not version:
            return
        title = simpledialog.askstring("Новая новость", "Заголовок:", parent=self)
        if not title:
            return
        body = MultilineDialog(self, "Новая новость", "Текст новости:").result
        if not body:
            return
        notes = f"Новость лаунчера: {title}"
        if not self.confirm_publish("новость лаунчера", version, LAUNCHER_DIR):
            return
        self.run_command(
            [sys.executable, str(HELPER), "launcher-news", "--version", version, "--notes", notes, "--news-title", title, "--news-body", body],
            WORKGIT_DIR,
            on_success=lambda _out: self.refresh_news(),
            title=f"Add launcher news {version}",
        )

    def selected_news(self) -> dict | None:
        selection = self.news_tree.selection()
        if not selection:
            messagebox.showwarning("Новости", "Сначала выбери новость в таблице.")
            return None
        index = int(selection[0])
        return next((item for item in self.news_items if int(item["index"]) == index), None)

    def edit_news(self) -> None:
        item = self.selected_news()
        if not item:
            return
        version = self.ask_version("лаунчера")
        if not version:
            return
        title = simpledialog.askstring("Редактировать новость", "Новый заголовок:", initialvalue=str(item["title"]), parent=self)
        if not title:
            return
        body = MultilineDialog(self, "Редактировать новость", "Новый текст:", initial=str(item["body"])).result
        if not body:
            return
        index = str(item["index"])
        if not self.confirm_publish(f"редактирование новости #{index}", version, LAUNCHER_DIR):
            return
        self.run_command(
            [sys.executable, str(HELPER), "launcher-news-edit", "--version", version, "--notes", f"Редактирование новости #{index}", "--index", index, "--news-title", title, "--news-body", body],
            WORKGIT_DIR,
            on_success=lambda _out: self.refresh_news(),
            title=f"Edit launcher news #{index}",
        )

    def delete_news(self) -> None:
        item = self.selected_news()
        if not item:
            return
        version = self.ask_version("лаунчера")
        if not version:
            return
        index = str(item["index"])
        if not messagebox.askyesno("Удалить новость", f"Удалить новость #{index}?\n\n{item['title']}"):
            return
        if not self.confirm_publish(f"удаление новости #{index}", version, LAUNCHER_DIR):
            return
        self.run_command(
            [sys.executable, str(HELPER), "launcher-news-delete", "--version", version, "--notes", f"Удаление новости #{index}", "--index", index],
            WORKGIT_DIR,
            on_success=lambda _out: self.refresh_news(),
            title=f"Delete launcher news #{index}",
        )

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
