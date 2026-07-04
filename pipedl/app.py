from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from .api import LocalApiServer
from .config import DEFAULT_HOST, DEFAULT_PORT, get_paths
from .demo import demo_experiment
from .models import ExperimentCreate, SHELL_BASH, SUPPORTED_SHELLS
from .scheduler import Scheduler
from .storage import Storage, read_tail
from .updater import UpdateInfo, check_for_update, download_update, launch_installer


class PipeDLApp(tk.Tk):
    def __init__(self, storage: Storage, scheduler: Scheduler, api_server: LocalApiServer):
        super().__init__()
        self.storage = storage
        self.scheduler = scheduler
        self.api_server = api_server
        self._closing = False
        self.selected_id: str | None = None
        self._refresh_after_id: str | None = None
        self.card_widgets: dict[str, dict] = {}
        self._rendered_ids: list[str] = []
        self.dragging_exp_id: str | None = None
        self.drag_preview: tk.Toplevel | None = None
        self.drag_placeholder: tk.Frame | None = None
        self.drag_placeholder_position: int | None = None
        self.current_drop_position: int | None = None
        self.update_dialog: tk.Toplevel | None = None
        self.update_label_var = tk.StringVar(value="")
        self.update_progress_var = tk.DoubleVar(value=0.0)
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
        self.after(1200, self.check_updates_on_startup)

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
        self.cards_frame.bind("<Configure>", lambda _event: self._sync_card_scrollregion())
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
        self.detail_label = ttk.Label(detail, textvariable=self.detail_var, justify=tk.LEFT, style="Panel.TLabel")
        self.detail_label.grid(
            row=0, column=0, sticky="ew", padx=12, pady=10
        )
        detail.bind("<Configure>", self._resize_detail_label)
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
        if self.dragging_exp_id:
            self._refresh_after_id = self.after(1500, self.refresh)
            return
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
        self._destroy_drag_visuals()
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
        card.columnconfigure(2, weight=1)
        self._attach_card_select(card, exp["id"])

        handle = self._create_drag_handle(card, exp, bg)
        handle.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(8, 0), pady=8)

        stripe = tk.Frame(card, bg=self._status_color(exp["status"]), width=5)
        stripe.grid(row=0, column=1, rowspan=3, sticky="nsw", padx=(8, 0))
        self._attach_card_select(stripe, exp["id"])

        header = tk.Frame(card, bg=bg)
        header.grid(row=0, column=2, sticky="ew", padx=12, pady=(10, 2))
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
        meta_label.grid(row=1, column=2, sticky="ew", padx=12)
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
        command_label.grid(row=2, column=2, sticky="ew", padx=12, pady=(4, 10))
        self._attach_card_select(command_label, exp["id"])

        actions = tk.Frame(card, bg=bg)
        actions.grid(row=0, column=3, rowspan=3, sticky="e", padx=10, pady=10)
        self._add_card_actions(actions, exp, queued_ids, queue_paused)
        self.card_widgets[exp["id"]] = {
            "card": card,
            "handle": handle,
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
        }

    def _create_drag_handle(self, parent: tk.Widget, exp: dict, bg: str) -> tk.Label:
        is_draggable = exp["status"] == "queued"
        handle = tk.Label(
            parent,
            text="☰",
            bg=bg,
            fg=self.colors["muted"] if is_draggable else self.colors["border"],
            font=("Segoe UI", 14, "bold"),
            width=2,
            cursor="fleur" if is_draggable else "arrow",
        )
        if is_draggable:
            handle.bind("<ButtonPress-1>", lambda event, exp_id=exp["id"]: self._drag_start(event, exp_id))
            handle.bind("<B1-Motion>", self._drag_motion)
            handle.bind("<ButtonRelease-1>", self._drag_release)
        return handle

    def _drag_start(self, _event, exp_id: str) -> None:
        exp = self.storage.get_experiment(exp_id)
        if not exp or exp["status"] != "queued":
            return
        self.dragging_exp_id = exp_id
        self.selected_id = exp_id
        refs = self.card_widgets.get(exp_id)
        if refs:
            source_y = refs["card"].winfo_rooty()
            refs["card"].configure(bg=self.colors["panel_alt"], highlightbackground=self.colors["queued"], highlightthickness=2)
            refs["handle"].configure(fg=self.colors["queued"])
            self._show_drag_preview(exp, refs["card"])
            self._show_drag_placeholder(refs["card"])
            self.current_drop_position = self._queued_drop_position(source_y, exp_id)
            if self.current_drop_position is not None:
                self._move_drag_placeholder(self.current_drop_position, exp_id)
        self.update_details()

    def _drag_motion(self, event) -> None:
        if not self.dragging_exp_id:
            return
        if self._event_in_queue_region(event):
            self._auto_scroll_during_drag(event.y_root)
        self._move_drag_preview(event.x_root, event.y_root)
        position = self._queued_drop_position(event.y_root, self.dragging_exp_id)
        if position is not None:
            self.current_drop_position = position
            if position != self.drag_placeholder_position:
                self._move_drag_placeholder(position, self.dragging_exp_id)
        refs = self.card_widgets.get(self.dragging_exp_id)
        if refs:
            refs["card"].configure(bg=self.colors["panel_alt"], highlightbackground=self.colors["queued"], highlightthickness=2)

    def _drag_release(self, event) -> None:
        if not self.dragging_exp_id:
            return
        exp_id = self.dragging_exp_id
        self.dragging_exp_id = None
        position = self.current_drop_position or self._queued_drop_position(event.y_root, exp_id)
        self._destroy_drag_visuals()
        self.current_drop_position = None
        if position is not None:
            self.storage.move_queued(exp_id, position)
        self._clear_cards()
        self.refresh()

    def _show_drag_preview(self, exp: dict, source_card: tk.Widget) -> None:
        self._destroy_drag_preview()
        preview = tk.Toplevel(self)
        preview.overrideredirect(True)
        try:
            preview.attributes("-topmost", True)
            preview.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        width = max(320, min(source_card.winfo_width(), 520))
        frame = tk.Frame(preview, bg=self.colors["selected"], highlightthickness=2, highlightbackground=self.colors["queued"])
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            frame,
            text=exp["name"],
            bg=self.colors["selected"],
            fg=self.colors["text"],
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 2))
        tk.Label(
            frame,
            text=self._command_hint(exp),
            bg=self.colors["selected"],
            fg=self.colors["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(0, 10))
        preview.geometry(f"{width}x72+{source_card.winfo_rootx()+16}+{source_card.winfo_rooty()+8}")
        self.drag_preview = preview

    def _move_drag_preview(self, x_root: int, y_root: int) -> None:
        if not self.drag_preview:
            return
        self.drag_preview.geometry(f"+{x_root + 14}+{y_root + 10}")

    def _destroy_drag_preview(self) -> None:
        if self.drag_preview:
            self.drag_preview.destroy()
            self.drag_preview = None

    def _show_drag_placeholder(self, source_card: tk.Widget) -> None:
        self._destroy_drag_placeholder()
        height = max(source_card.winfo_height(), 72)
        placeholder = tk.Frame(
            self.cards_frame,
            bg=self.colors["selected"],
            height=height,
            highlightthickness=2,
            highlightbackground=self.colors["queued"],
        )
        placeholder.pack_propagate(False)
        tk.Label(
            placeholder,
            text="Drop here",
            bg=self.colors["selected"],
            fg=self.colors["queued"],
            font=("Segoe UI", 10, "bold"),
        ).pack(expand=True)
        placeholder.pack(fill=tk.X, pady=(0, 10), before=source_card)
        source_card.pack_forget()
        self.drag_placeholder = placeholder

    def _move_drag_placeholder(self, position: int, dragged_id: str) -> None:
        if not self.drag_placeholder:
            return
        queued = [exp for exp in self.storage.list_experiments() if exp["status"] == "queued" and exp["id"] != dragged_id]
        self.drag_placeholder.pack_forget()
        self.drag_placeholder_position = position
        if not queued:
            self.drag_placeholder.pack(fill=tk.X, pady=(0, 10))
            return
        if position <= 1:
            refs = self.card_widgets.get(queued[0]["id"])
            target = refs["card"] if refs else None
            if target and target.winfo_manager():
                self.drag_placeholder.pack(fill=tk.X, pady=(0, 10), before=target)
            else:
                self.drag_placeholder.pack(fill=tk.X, pady=(0, 10))
        elif position > len(queued):
            refs = self.card_widgets.get(queued[-1]["id"])
            target = refs["card"] if refs else None
            if target and target.winfo_manager():
                self.drag_placeholder.pack(fill=tk.X, pady=(0, 10), after=target)
            else:
                self.drag_placeholder.pack(fill=tk.X, pady=(0, 10))
        else:
            refs = self.card_widgets.get(queued[position - 1]["id"])
            target = refs["card"] if refs else None
            if target and target.winfo_manager():
                self.drag_placeholder.pack(fill=tk.X, pady=(0, 10), before=target)
            else:
                self.drag_placeholder.pack(fill=tk.X, pady=(0, 10))

    def _destroy_drag_placeholder(self) -> None:
        if self.drag_placeholder:
            self.drag_placeholder.destroy()
            self.drag_placeholder = None
        self.drag_placeholder_position = None

    def _destroy_drag_visuals(self) -> None:
        self._destroy_drag_preview()
        self._destroy_drag_placeholder()

    def _queued_drop_position(self, y_root: int, dragged_id: str) -> int | None:
        queued = [exp for exp in self.storage.list_experiments() if exp["status"] == "queued"]
        if not any(exp["id"] == dragged_id for exp in queued):
            return None
        position = 1
        for exp in queued:
            if exp["id"] == dragged_id:
                continue
            refs = self.card_widgets.get(exp["id"])
            if not refs:
                continue
            card = refs["card"]
            midpoint = card.winfo_rooty() + card.winfo_height() / 2
            if y_root < midpoint:
                return position
            position += 1
        return position

    def _auto_scroll_during_drag(self, y_root: int) -> None:
        if not self._cards_can_scroll():
            return
        top = self.queue_region.winfo_rooty()
        bottom = top + self.queue_region.winfo_height()
        margin = 36
        if y_root < top + margin:
            self.card_canvas.yview_scroll(-2, "units")
        elif y_root > bottom - margin:
            self.card_canvas.yview_scroll(2, "units")

    def _update_card(self, exp: dict, index: int, queued_ids: list[str], queue_paused: bool) -> None:
        refs = self.card_widgets.get(exp["id"])
        if not refs:
            self._create_card(exp, index, queued_ids, queue_paused)
            return

        selected = exp["id"] == self.selected_id
        bg = self.colors["selected"] if selected else self.colors["panel"]
        border = self._status_color(exp["status"]) if selected or exp["status"] == "running" else self.colors["border"]
        refs["card"].configure(bg=bg, highlightbackground=border, highlightthickness=1)
        refs["handle"].configure(
            bg=bg,
            fg=self.colors["muted"] if exp["status"] == "queued" else self.colors["border"],
            cursor="fleur" if exp["status"] == "queued" else "arrow",
        )
        refs["stripe"].configure(bg=self._status_color(exp["status"]))
        refs["header"].configure(bg=bg)
        refs["status_label"].configure(text=self._status_label(exp["status"]), bg=self._status_color(exp["status"]))
        refs["name_label"].configure(text=exp["name"], bg=bg)
        refs["meta_label"].configure(text=self._meta_text(exp, index), bg=bg)
        refs["command_label"].configure(text=self._command_hint(exp), bg=bg)
        refs["actions"].configure(bg=bg)

        actions_changed = (
            refs["status"] != exp["status"]
            or refs["queue_paused"] != queue_paused
        )
        if actions_changed:
            self._add_card_actions(refs["actions"], exp, queued_ids, queue_paused)
            refs["status"] = exp["status"]
            refs["queue_paused"] = queue_paused
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
            self._action_button(parent, "Cancel", lambda exp_id=exp["id"]: self.cancel_experiment(exp_id))
            self._action_button(parent, "Delete", lambda exp_id=exp["id"]: self.delete_experiment(exp_id))
        elif status in {"failed", "stopped", "cancelled", "succeeded"}:
            self._action_button(parent, "Retry", lambda exp_id=exp["id"]: self.retry_experiment(exp_id))
            self._action_button(parent, "Select", lambda exp_id=exp["id"]: self.select_experiment(exp_id))
            self._action_button(parent, "Delete", lambda exp_id=exp["id"]: self.delete_experiment(exp_id))

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
        self.detail_var.set(self._detail_text(exp))
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

    def _resize_cards_window(self, event) -> None:
        self.card_canvas.itemconfigure(self.cards_window, width=event.width)
        self._sync_card_scrollregion()

    def _resize_detail_label(self, event) -> None:
        self.detail_label.configure(wraplength=max(320, event.width - 24))

    def _attach_card_select(self, widget: tk.Widget, exp_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, item_id=exp_id: self.select_experiment(item_id), add="+")

    def _on_mousewheel(self, event) -> None:
        if not self._event_in_queue_region(event):
            return
        if not self._cards_can_scroll():
            self.card_canvas.yview_moveto(0)
            return "break"
        if event.num == 4:
            self.card_canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.card_canvas.yview_scroll(3, "units")
        else:
            delta = int(-1 * (event.delta / 120))
            self.card_canvas.yview_scroll(delta, "units")
        self._clamp_card_scroll()
        return "break"

    def _sync_card_scrollregion(self) -> None:
        canvas_width = max(1, self.card_canvas.winfo_width())
        canvas_height = max(1, self.card_canvas.winfo_height())
        content_height = max(self.cards_frame.winfo_reqheight(), self.cards_frame.winfo_height())
        scroll_height = max(canvas_height, content_height)
        self.card_canvas.configure(scrollregion=(0, 0, canvas_width, scroll_height))
        if content_height <= canvas_height:
            self.card_canvas.yview_moveto(0)
        else:
            self._clamp_card_scroll()

    def _cards_can_scroll(self) -> bool:
        canvas_height = max(1, self.card_canvas.winfo_height())
        content_height = max(self.cards_frame.winfo_reqheight(), self.cards_frame.winfo_height())
        return content_height > canvas_height + 1

    def _clamp_card_scroll(self) -> None:
        if not self._cards_can_scroll():
            self.card_canvas.yview_moveto(0)
            return
        first, last = self.card_canvas.yview()
        if first < 0:
            self.card_canvas.yview_moveto(0)
        elif last > 1:
            self.card_canvas.yview_moveto(max(0.0, 1.0 - (last - first)))

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

    def _detail_text(self, exp: dict) -> str:
        display_index = self._display_index(exp["id"])
        lines = [
            f"Name: {exp['name']}",
            f"ID: {exp['id']}",
            f"Display #: {display_index} | Queue position: {exp['queue_position']}",
            f"Status: {exp['status']} | PID: {exp['pid']} | Process group: {exp['process_group']} | Exit: {exp['exit_code']}",
            f"Shell: {exp['shell']}",
            f"CWD: {exp['cwd']}",
            f"Created by: {exp['created_by']}",
            f"Tags: {exp.get('tags') or ''}",
            f"Notes: {exp.get('notes') or ''}",
            f"Created: {exp['created_at']} | Started: {exp['started_at']} | Ended: {exp['ended_at']} | Updated: {exp['updated_at']}",
            f"stdout: {exp['stdout_path']}",
            f"stderr: {exp['stderr_path']}",
            f"Command: {exp['command']}",
        ]
        return "\n".join(lines)

    def _display_index(self, exp_id: str) -> int:
        for index, exp in enumerate(self.storage.list_experiments(), start=1):
            if exp["id"] == exp_id:
                return index
        return 0

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

    def check_updates_on_startup(self) -> None:
        if self._closing:
            return
        thread = threading.Thread(target=self._check_updates_worker, daemon=True)
        thread.start()

    def _check_updates_worker(self) -> None:
        try:
            info = check_for_update(__version__)
        except Exception:
            return
        if info:
            self._run_on_ui(lambda update=info: self._prompt_update(update))

    def _prompt_update(self, info: UpdateInfo) -> None:
        confirmed = messagebox.askyesno(
            "PipeDL Update",
            "PipeDL {version} is available.\n\nDownload and install it now?".format(version=info.version),
        )
        if confirmed:
            self._start_update_download(info)

    def _start_update_download(self, info: UpdateInfo) -> None:
        self._show_update_dialog(info)
        thread = threading.Thread(target=self._download_update_worker, args=(info,), daemon=True)
        thread.start()

    def _show_update_dialog(self, info: UpdateInfo) -> None:
        self._close_update_dialog()
        dialog = tk.Toplevel(self)
        dialog.title("Updating PipeDL")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        dialog.configure(bg=self.colors["panel"])
        dialog.columnconfigure(0, weight=1)
        self.update_label_var.set(f"Downloading PipeDL {info.version}...")
        ttk.Label(dialog, textvariable=self.update_label_var, style="Panel.TLabel").grid(
            row=0, column=0, sticky="ew", padx=18, pady=(16, 8)
        )
        progress = ttk.Progressbar(dialog, variable=self.update_progress_var, maximum=100, length=360)
        progress.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 16))
        self.update_progress_var.set(0)
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        self.update_dialog = dialog

    def _download_update_worker(self, info: UpdateInfo) -> None:
        try:
            installer_path = download_update(info, progress_callback=self._update_download_progress)
        except Exception as exc:
            self._run_on_ui(lambda error=exc: self._show_update_error(error))
            return
        self._run_on_ui(lambda path=installer_path: self._install_update(path))

    def _update_download_progress(self, downloaded: int, total: int) -> None:
        if total <= 0:
            return
        percent = min(100.0, downloaded / total * 100)
        self._run_on_ui(lambda value=percent: self.update_progress_var.set(value))

    def _install_update(self, installer_path) -> None:
        self.update_label_var.set("Starting installer...")
        self.update_progress_var.set(100)
        try:
            launch_installer(installer_path)
        except Exception as exc:
            self._show_update_error(exc)
            return
        self.on_close()

    def _show_update_error(self, exc: Exception) -> None:
        self._close_update_dialog()
        messagebox.showerror("PipeDL Update", f"Could not install the update.\n\n{exc}")

    def _close_update_dialog(self) -> None:
        if self.update_dialog:
            self.update_dialog.destroy()
            self.update_dialog = None

    def _run_on_ui(self, callback) -> None:
        if self._closing:
            return
        try:
            self.after(0, callback)
        except (RuntimeError, tk.TclError):
            pass

    def on_close(self) -> None:
        self._closing = True
        self._close_update_dialog()
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
