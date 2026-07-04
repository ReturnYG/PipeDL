from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .api import LocalApiServer
from .config import DEFAULT_HOST, DEFAULT_PORT, get_paths
from .demo import demo_experiment
from .models import ExperimentCreate, SHELL_BASH, SUPPORTED_SHELLS
from .scheduler import Scheduler
from .storage import Storage, read_tail


class PipeDLApp(tk.Tk):
    def __init__(self, storage: Storage, scheduler: Scheduler, api_server: LocalApiServer):
        super().__init__()
        self.storage = storage
        self.scheduler = scheduler
        self.api_server = api_server
        self.selected_id: str | None = None
        self._refresh_after_id: str | None = None
        self.card_widgets: dict[str, dict] = {}
        self._rendered_ids: list[str] = []
        self.colors = {
            "bg": "#f4f7fb",
            "panel": "#ffffff",
            "panel_alt": "#f8fafc",
            "border": "#d9e2ec",
            "text": "#172033",
            "muted": "#64748b",
            "running": "#2563eb",
            "paused": "#d97706",
            "queued": "#7c3aed",
            "succeeded": "#059669",
            "failed": "#dc2626",
            "stopped": "#ea580c",
            "cancelled": "#6b7280",
            "selected": "#e8f1ff",
        }
        self.title("PipeDL")
        self.geometry("1240x780")
        self.minsize(980, 640)
        self.configure(bg=self.colors["bg"])
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        self.style = ttk.Style(self)
        self.style.configure("TFrame", background=self.colors["bg"])
        self.style.configure("Panel.TFrame", background=self.colors["panel"])
        self.style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        self.style.configure("Panel.TLabel", background=self.colors["panel"], foreground=self.colors["text"])
        self.style.configure("Muted.Panel.TLabel", background=self.colors["panel"], foreground=self.colors["muted"])
        self.style.configure("Title.TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 18, "bold"))
        self.style.configure("Summary.TLabel", background=self.colors["bg"], foreground=self.colors["muted"], font=("Segoe UI", 10))
        self.style.configure("TButton", padding=(10, 5))
        self.style.configure("Accent.TButton", padding=(12, 6))
        self.style.configure("Danger.TButton", padding=(10, 5))

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=(18, 14), style="TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="PipeDL", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.summary_var = tk.StringVar(value="PipeDL starting...")
        ttk.Label(top, textvariable=self.summary_var, style="Summary.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Button(top, text="Pause Queue", command=self.pause_queue).grid(row=0, column=1, rowspan=2, padx=4)
        ttk.Button(top, text="Continue Queue", command=self.resume_queue).grid(row=0, column=2, rowspan=2, padx=4)
        ttk.Button(top, text="Stop Current", command=self.stop_current).grid(row=0, column=3, rowspan=2, padx=4)

        add = tk.Frame(self, bg=self.colors["panel"], highlightthickness=1, highlightbackground=self.colors["border"])
        add.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        add.columnconfigure(5, weight=1)
        self.name_var = tk.StringVar(value="")
        self.shell_var = tk.StringVar(value=SHELL_BASH)
        self.cwd_var = tk.StringVar(value=".")
        self.command_var = tk.StringVar()
        ttk.Label(add, text="Add Experiment", style="Panel.TLabel", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        ttk.Label(add, text="Name", style="Muted.Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(12, 4))
        ttk.Entry(add, textvariable=self.name_var, width=18).grid(row=1, column=1, padx=4, pady=(0, 12))
        ttk.Label(add, text="Shell", style="Muted.Panel.TLabel").grid(row=1, column=2, sticky="w")
        ttk.Combobox(
            add,
            textvariable=self.shell_var,
            values=sorted(SUPPORTED_SHELLS),
            width=12,
            state="readonly",
        ).grid(row=1, column=3, padx=4, pady=(0, 12))
        ttk.Label(add, text="CWD", style="Muted.Panel.TLabel").grid(row=1, column=4, sticky="w")
        ttk.Entry(add, textvariable=self.cwd_var).grid(row=1, column=5, sticky="ew", padx=4, pady=(0, 12))
        ttk.Label(add, text="Command", style="Muted.Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(12, 4), pady=(0, 12))
        ttk.Entry(add, textvariable=self.command_var).grid(
            row=2, column=1, columnspan=5, sticky="ew", padx=4, pady=(0, 12)
        )
        ttk.Button(add, text="Queue", command=self.add_experiment).grid(
            row=2, column=6, padx=(4, 6), pady=(0, 12)
        )
        ttk.Button(add, text="Demo x5", command=self.add_demo_queue).grid(
            row=2, column=7, padx=(0, 12), pady=(0, 12)
        )

        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 18))

        left = ttk.Frame(main, style="TFrame")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Experiment Queue", style="Title.TLabel", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        list_shell = tk.Frame(left, bg=self.colors["bg"])
        list_shell.grid(row=1, column=0, sticky="nsew")
        list_shell.columnconfigure(0, weight=1)
        list_shell.rowconfigure(0, weight=1)
        self.queue_region = list_shell
        self.card_canvas = tk.Canvas(
            list_shell,
            bg=self.colors["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.card_scrollbar = ttk.Scrollbar(list_shell, orient=tk.VERTICAL, command=self.card_canvas.yview)
        self.cards_frame = tk.Frame(self.card_canvas, bg=self.colors["bg"])
        self.cards_frame.bind(
            "<Configure>",
            lambda _event: self.card_canvas.configure(scrollregion=self.card_canvas.bbox("all")),
        )
        self.cards_window = self.card_canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.card_canvas.configure(yscrollcommand=self.card_scrollbar.set)
        self.card_canvas.grid(row=0, column=0, sticky="nsew")
        self.card_scrollbar.grid(row=0, column=1, sticky="ns")
        self.card_canvas.bind("<Configure>", self._resize_cards_window)
        self.bind_all("<MouseWheel>", self._on_mousewheel)
        self.bind_all("<Button-4>", self._on_mousewheel)
        self.bind_all("<Button-5>", self._on_mousewheel)
        main.add(left, weight=1)

        right = ttk.Frame(main, style="TFrame")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.detail_var = tk.StringVar(value="Select an experiment.")
        detail = tk.Frame(right, bg=self.colors["panel"], highlightthickness=1, highlightbackground=self.colors["border"])
        detail.grid(row=0, column=0, sticky="ew")
        detail.columnconfigure(0, weight=1)
        ttk.Label(detail, textvariable=self.detail_var, justify=tk.LEFT, style="Panel.TLabel").grid(
            row=0, column=0, sticky="ew", padx=12, pady=10
        )
        tabs = ttk.Notebook(right)
        tabs.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.stdout_text = tk.Text(tabs, wrap=tk.NONE, height=20, bg="#0f172a", fg="#dbeafe", insertbackground="#dbeafe")
        self.stderr_text = tk.Text(tabs, wrap=tk.NONE, height=20, bg="#1f1115", fg="#fee2e2", insertbackground="#fee2e2")
        tabs.add(self.stdout_text, text="stdout")
        tabs.add(self.stderr_text, text="stderr")
        main.add(right, weight=2)

    def add_experiment(self) -> None:
        command = self.command_var.get().strip()
        if not command:
            messagebox.showerror("PipeDL", "Command is required.")
            return
        self.storage.add_experiment(
            ExperimentCreate(
                name=self.name_var.get().strip(),
                command=command,
                shell=self.shell_var.get(),
                cwd=self.cwd_var.get().strip() or ".",
                created_by="gui",
            )
        )
        self.command_var.set("")
        self.refresh()

    def add_demo_queue(self) -> None:
        for index in range(1, 6):
            self.storage.add_experiment(demo_experiment(index))
        self.refresh()
        messagebox.showinfo("PipeDL", "Added 5 simulated training commands to the queue.")

    def refresh(self) -> None:
        if self._refresh_after_id:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        summary = self.storage.summary()
        self.summary_var.set(
            "API http://%s:%s | running=%s paused=%s queued=%s succeeded=%s failed=%s stopped=%s queue_paused=%s"
            % (
                DEFAULT_HOST,
                DEFAULT_PORT,
                summary["running"],
                summary["paused_processes"],
                summary["queued"],
                summary["succeeded"],
                summary["failed"],
                summary["stopped"],
                summary["paused"],
            )
        )
        experiments = self.storage.list_experiments()
        if self.selected_id and not any(exp["id"] == self.selected_id for exp in experiments):
            self.selected_id = None
        self.render_cards(experiments, bool(summary["paused"]))
        self.update_details()
        self._refresh_after_id = self.after(1500, self.refresh)

    def render_cards(self, experiments: list[dict], queue_paused: bool) -> None:
        if not experiments:
            if self._rendered_ids:
                self._clear_cards()
            if not self.card_widgets.get("__empty__"):
                empty = tk.Frame(
                    self.cards_frame,
                    bg=self.colors["panel"],
                    highlightthickness=1,
                    highlightbackground=self.colors["border"],
                )
                empty.pack(fill=tk.X, pady=(0, 10))
                tk.Label(
                    empty,
                    text="No experiments yet. Add a command above or submit one with the CLI.",
                    bg=self.colors["panel"],
                    fg=self.colors["muted"],
                    font=("Segoe UI", 10),
                    anchor="w",
                ).pack(fill=tk.X, padx=14, pady=18)
                self.card_widgets["__empty__"] = {"card": empty}
            return

        if "__empty__" in self.card_widgets:
            self.card_widgets["__empty__"]["card"].destroy()
            del self.card_widgets["__empty__"]

        ids = [exp["id"] for exp in experiments]
        queued_ids = [exp["id"] for exp in experiments if exp["status"] == "queued"]
        if ids != self._rendered_ids:
            self._clear_cards()
            self._rendered_ids = ids
            for index, exp in enumerate(experiments, start=1):
                self._create_card(exp, index, queued_ids, queue_paused)
            return

        for index, exp in enumerate(experiments, start=1):
            self._update_card(exp, index, queued_ids, queue_paused)

    def _clear_cards(self) -> None:
        for child in self.cards_frame.winfo_children():
            child.destroy()
        self.card_widgets.clear()
        self._rendered_ids = []

    def _create_card(self, exp: dict, index: int, queued_ids: list[str], queue_paused: bool) -> None:
        selected = exp["id"] == self.selected_id
        bg = self.colors["selected"] if selected else self.colors["panel"]
        border = self._status_color(exp["status"]) if selected or exp["status"] == "running" else self.colors["border"]
        card = tk.Frame(self.cards_frame, bg=bg, highlightthickness=1, highlightbackground=border)
        card.pack(fill=tk.X, pady=(0, 10))
        card.columnconfigure(1, weight=1)
        self._attach_card_select(card, exp["id"])

        stripe = tk.Frame(card, bg=self._status_color(exp["status"]), width=5)
        stripe.grid(row=0, column=0, rowspan=3, sticky="nsw")
        self._attach_card_select(stripe, exp["id"])

        header = tk.Frame(card, bg=bg)
        header.grid(row=0, column=1, sticky="ew", padx=12, pady=(10, 2))
        header.columnconfigure(1, weight=1)
        self._attach_card_select(header, exp["id"])
        status_label = tk.Label(
            header,
            text=self._status_label(exp["status"]),
            bg=self._status_color(exp["status"]),
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=2,
        )
        status_label.grid(row=0, column=0, sticky="w")
        self._attach_card_select(status_label, exp["id"])
        name_label = tk.Label(
            header,
            text=exp["name"],
            bg=bg,
            fg=self.colors["text"],
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        name_label.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self._attach_card_select(name_label, exp["id"])

        meta = self._meta_text(exp, index)
        meta_label = tk.Label(
            card,
            text=meta,
            bg=bg,
            fg=self.colors["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        )
        meta_label.grid(row=1, column=1, sticky="ew", padx=12)
        self._attach_card_select(meta_label, exp["id"])
        command_label = tk.Label(
            card,
            text=self._command_hint(exp),
            bg=bg,
            fg=self.colors["text"],
            font=("Consolas", 9),
            anchor="w",
            justify=tk.LEFT,
        )
        command_label.grid(row=2, column=1, sticky="ew", padx=12, pady=(4, 10))
        self._attach_card_select(command_label, exp["id"])

        actions = tk.Frame(card, bg=bg)
        actions.grid(row=0, column=2, rowspan=3, sticky="e", padx=10, pady=10)
        self._add_card_actions(actions, exp, queued_ids, queue_paused)
        self.card_widgets[exp["id"]] = {
            "card": card,
            "stripe": stripe,
            "header": header,
            "status_label": status_label,
            "name_label": name_label,
            "meta_label": meta_label,
            "command_label": command_label,
            "actions": actions,
            "status": exp["status"],
            "selected": selected,
            "queue_paused": queue_paused,
            "top_available": exp["id"] in queued_ids and queued_ids.index(exp["id"]) != 0,
        }

    def _update_card(self, exp: dict, index: int, queued_ids: list[str], queue_paused: bool) -> None:
        refs = self.card_widgets.get(exp["id"])
        if not refs:
            self._create_card(exp, index, queued_ids, queue_paused)
            return

        selected = exp["id"] == self.selected_id
        bg = self.colors["selected"] if selected else self.colors["panel"]
        border = self._status_color(exp["status"]) if selected or exp["status"] == "running" else self.colors["border"]
        refs["card"].configure(bg=bg, highlightbackground=border)
        refs["stripe"].configure(bg=self._status_color(exp["status"]))
        refs["header"].configure(bg=bg)
        refs["status_label"].configure(text=self._status_label(exp["status"]), bg=self._status_color(exp["status"]))
        refs["name_label"].configure(text=exp["name"], bg=bg)
        refs["meta_label"].configure(text=self._meta_text(exp, index), bg=bg)
        refs["command_label"].configure(text=self._command_hint(exp), bg=bg)
        refs["actions"].configure(bg=bg)

        top_available = exp["id"] in queued_ids and queued_ids.index(exp["id"]) != 0
        actions_changed = (
            refs["status"] != exp["status"]
            or refs["queue_paused"] != queue_paused
            or refs["top_available"] != top_available
        )
        if actions_changed:
            self._add_card_actions(refs["actions"], exp, queued_ids, queue_paused)
            refs["status"] = exp["status"]
            refs["queue_paused"] = queue_paused
            refs["top_available"] = top_available
        refs["selected"] = selected

    def _add_card_actions(self, parent: tk.Frame, exp: dict, queued_ids: list[str], queue_paused: bool) -> None:
        for child in parent.winfo_children():
            child.destroy()
        status = exp["status"]
        if status == "running":
            self._action_button(parent, "Pause", self.pause_current)
            self._action_button(parent, "Stop", self.stop_current)
            self._action_button(parent, "Delete", lambda exp_id=exp["id"]: self.delete_experiment(exp_id))
        elif status == "paused":
            self._action_button(parent, "Continue", self.resume_current)
            self._action_button(parent, "Stop", self.stop_current)
            self._action_button(parent, "Delete", lambda exp_id=exp["id"]: self.delete_experiment(exp_id))
        elif status == "queued":
            if queue_paused:
                self._action_button(parent, "Continue Queue", self.resume_queue)
            else:
                self._action_button(parent, "Pause Queue", self.pause_queue)
            row = tk.Frame(parent, bg=parent["bg"])
            row.pack(side=tk.TOP, fill=tk.X, pady=2)
            self._action_button(row, "Up", lambda exp_id=exp["id"]: self.shift_experiment(exp_id, -1), side=tk.LEFT, fill=None, padx=(0, 3))
            self._action_button(row, "Down", lambda exp_id=exp["id"]: self.shift_experiment(exp_id, 1), side=tk.LEFT, fill=None, padx=(3, 0))
            self._action_button(parent, "Cancel", lambda exp_id=exp["id"]: self.cancel_experiment(exp_id))
            self._action_button(parent, "Delete", lambda exp_id=exp["id"]: self.delete_experiment(exp_id))
        elif status in {"failed", "stopped", "cancelled", "succeeded"}:
            self._action_button(parent, "Retry", lambda exp_id=exp["id"]: self.retry_experiment(exp_id))
            self._action_button(parent, "Select", lambda exp_id=exp["id"]: self.select_experiment(exp_id))
            self._action_button(parent, "Delete", lambda exp_id=exp["id"]: self.delete_experiment(exp_id))
        if status == "queued" and exp["id"] in queued_ids and queued_ids.index(exp["id"]) != 0:
            self._action_button(parent, "Top", lambda exp_id=exp["id"]: self.move_experiment(exp_id, 1))

    def _action_button(self, parent: tk.Widget, text: str, command, side=tk.TOP, fill=tk.X, padx=0) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command)
        button.pack(side=side, fill=fill, padx=padx, pady=2)
        return button

    def select_experiment(self, exp_id: str) -> None:
        previous_id = self.selected_id
        self.selected_id = exp_id
        self.update_details()
        experiments = self.storage.list_experiments()
        queued_ids = [exp["id"] for exp in experiments if exp["status"] == "queued"]
        queue_paused = self.storage.queue_paused()
        for exp in experiments:
            if exp["id"] in {previous_id, exp_id}:
                self._update_card(exp, experiments.index(exp) + 1, queued_ids, queue_paused)

    def update_details(self) -> None:
        if not self.selected_id:
            self.detail_var.set("Select an experiment to inspect command details and logs.")
            self.stdout_text.delete("1.0", tk.END)
            self.stderr_text.delete("1.0", tk.END)
            return
        exp = self.storage.get_experiment(self.selected_id)
        if not exp:
            return
        self.detail_var.set(
            "ID: {id}\nStatus: {status} | PID: {pid} | Exit: {exit_code}\nCWD: {cwd}\nCommand: {command}".format(
                **exp
            )
        )
        self.stdout_text.delete("1.0", tk.END)
        self.stdout_text.insert(tk.END, read_tail(exp["stdout_path"]))
        self.stderr_text.delete("1.0", tk.END)
        self.stderr_text.insert(tk.END, read_tail(exp["stderr_path"]))

    def pause_queue(self) -> None:
        self.storage.set_queue_paused(True)
        self.refresh()

    def resume_queue(self) -> None:
        self.storage.set_queue_paused(False)
        self.refresh()

    def stop_current(self) -> None:
        if not self.scheduler.stop_current():
            messagebox.showinfo("PipeDL", "No running experiment.")
        self.refresh()

    def pause_current(self) -> None:
        if not self.scheduler.pause_current():
            messagebox.showinfo("PipeDL", "No running experiment to pause.")
        self.refresh()

    def resume_current(self) -> None:
        if not self.scheduler.resume_current():
            messagebox.showinfo("PipeDL", "No paused experiment to continue.")
        self.refresh()

    def cancel_experiment(self, exp_id: str) -> None:
        self.storage.cancel_queued(exp_id)
        self.refresh()

    def delete_experiment(self, exp_id: str) -> None:
        exp = self.storage.get_experiment(exp_id)
        if not exp:
            return
        if exp["status"] in {"running", "paused"}:
            confirmed = messagebox.askyesno(
                "Delete active process?",
                "This experiment is active. Deleting it will stop the process and remove its logs. Continue?",
            )
            if not confirmed:
                return
        elif exp["status"] == "queued":
            confirmed = messagebox.askyesno(
                "Delete queued command?",
                "Delete this queued command and remove its logs?",
            )
            if not confirmed:
                return
        self.scheduler.delete_experiment(exp_id)
        if self.selected_id == exp_id:
            self.selected_id = None
        self.refresh()

    def retry_experiment(self, exp_id: str) -> None:
        new_exp = self.storage.retry_experiment(exp_id)
        if not new_exp:
            messagebox.showinfo("PipeDL", "Retry is only available for finished experiments.")
            return
        self.selected_id = new_exp["id"]
        self.refresh()

    def move_experiment(self, exp_id: str, position: int) -> None:
        self.storage.move_queued(exp_id, position)
        self.refresh()

    def shift_experiment(self, exp_id: str, delta: int) -> None:
        queued = [exp for exp in self.storage.list_experiments() if exp["status"] == "queued"]
        ids = [exp["id"] for exp in queued]
        if exp_id not in ids:
            return
        new_pos = ids.index(exp_id) + 1 + delta
        self.storage.move_queued(exp_id, new_pos)
        self.refresh()

    def _resize_cards_window(self, event) -> None:
        self.card_canvas.itemconfigure(self.cards_window, width=event.width)

    def _attach_card_select(self, widget: tk.Widget, exp_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, item_id=exp_id: self.select_experiment(item_id), add="+")

    def _on_mousewheel(self, event) -> None:
        if not self._event_in_queue_region(event):
            return
        if event.num == 4:
            self.card_canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.card_canvas.yview_scroll(3, "units")
        else:
            delta = int(-1 * (event.delta / 120))
            self.card_canvas.yview_scroll(delta, "units")

    def _event_in_queue_region(self, event) -> bool:
        widget = self.queue_region
        left = widget.winfo_rootx()
        top = widget.winfo_rooty()
        right = left + widget.winfo_width()
        bottom = top + widget.winfo_height()
        return left <= event.x_root <= right and top <= event.y_root <= bottom

    def _status_color(self, status: str) -> str:
        return self.colors.get(status, self.colors["muted"])

    def _status_label(self, status: str) -> str:
        return status.upper()

    def _meta_text(self, exp: dict, index: int) -> str:
        parts = [
            f"#{index}",
            f"shell: {exp['shell']}",
            f"cwd: {self._clip(exp['cwd'], 44)}",
        ]
        if exp["pid"]:
            parts.append(f"pid: {exp['pid']}")
        if exp["exit_code"] is not None:
            parts.append(f"exit: {exp['exit_code']}")
        parts.append(f"by: {exp['created_by']}")
        return "   ".join(parts)

    def _command_hint(self, exp: dict) -> str:
        tags = exp.get("tags") or ""
        if tags:
            return f"tags: {self._clip(tags, 42)}"
        command = exp.get("command") or ""
        first = command.strip().split(maxsplit=1)[0] if command.strip() else "command"
        return f"command: {first} ... (select to view full command)"

    def _clip(self, text: str | None, max_len: int) -> str:
        text = text or ""
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "..."

    def on_close(self) -> None:
        if self._refresh_after_id:
            self.after_cancel(self._refresh_after_id)
        self.api_server.stop()
        self.scheduler.shutdown()
        self.destroy()


def run_app() -> None:
    paths = get_paths()
    storage = Storage(paths)
    scheduler = Scheduler(storage)
    api_server = LocalApiServer(storage, scheduler)
    scheduler.start()
    try:
        api_server.start()
    except OSError as exc:
        raise SystemExit(f"Cannot start PipeDL local API on {DEFAULT_HOST}:{DEFAULT_PORT}: {exc}") from exc
    app = PipeDLApp(storage, scheduler, api_server)
    app.mainloop()
