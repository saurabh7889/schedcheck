"""Tkinter-based GUI viewer for schedule timelines."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Any

from schedcheck.schedule import Schedule
from schedcheck.report import timeline


class ScheduleViewer:
    """GUI application for viewing and comparing schedule timelines."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("schedcheck Schedule Viewer")
        self.root.geometry("1000x700")
        self.root.minsize(800, 500)

        self.current_schedule: Schedule | None = None
        self.comparison_schedule: Schedule | None = None

        self._setup_ui()
        self._setup_bindings()

    def _setup_ui(self) -> None:
        # Main container
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="Open Schedule", command=self._open_schedule).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Open for Comparison", command=self._open_comparison).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Clear Comparison", command=self._clear_comparison).pack(side=tk.LEFT, padx=5)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(toolbar, text="Export Report", command=self._export_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Save As...", command=self._save_as).pack(side=tk.LEFT, padx=5)

        # Content area with paned window
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left panel - Schedule info
        left_frame = ttk.Frame(paned, padding=5)
        paned.add(left_frame, weight=1)

        # Schedule header
        header_frame = ttk.LabelFrame(left_frame, text="Schedule Info", padding=10)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        self.seed_var = tk.StringVar(value="(none)")
        self.choices_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="OK")
        self.failure_var = tk.StringVar(value="")

        ttk.Label(header_frame, text="Seed:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(header_frame, textvariable=self.seed_var, font=("Consolas", 10)).grid(row=0, column=1, sticky=tk.W, pady=2, padx=(10, 0))

        ttk.Label(header_frame, text="Choices:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(header_frame, textvariable=self.choices_var, font=("Consolas", 10)).grid(row=1, column=1, sticky=tk.W, pady=2, padx=(10, 0))

        ttk.Label(header_frame, text="Status:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.status_label = ttk.Label(header_frame, textvariable=self.status_var, font=("Consolas", 10, "bold"))
        self.status_label.grid(row=2, column=1, sticky=tk.W, pady=2, padx=(10, 0))

        # Choice points table
        table_frame = ttk.LabelFrame(left_frame, text="Choice Points", padding=5)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("#", "Index", "Task")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        self.tree.heading("#", text="#")
        self.tree.heading("Index", text="Index")
        self.tree.heading("Task", text="Chosen Task")
        self.tree.column("#", width=50, anchor=tk.CENTER)
        self.tree.column("Index", width=80, anchor=tk.CENTER)
        self.tree.column("Task", width=200, anchor=tk.W)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Failure section
        failure_frame = ttk.LabelFrame(left_frame, text="Failure Details", padding=10)
        failure_frame.pack(fill=tk.X, pady=(10, 0))

        self.failure_text = tk.Text(failure_frame, height=4, wrap=tk.WORD, font=("Consolas", 9))
        self.failure_text.pack(fill=tk.X)
        self.failure_text.config(state=tk.DISABLED)

        # Right panel - Timeline / Comparison
        right_frame = ttk.Frame(paned, padding=5)
        paned.add(right_frame, weight=1)

        # Notebook for tabs
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Timeline tab
        timeline_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(timeline_frame, text="Timeline")

        self.timeline_text = tk.Text(timeline_frame, wrap=tk.WORD, font=("Consolas", 10))
        self.timeline_text.pack(fill=tk.BOTH, expand=True)
        self.timeline_text.config(state=tk.DISABLED)

        # Comparison tab
        compare_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(compare_frame, text="Comparison")

        compare_toolbar = ttk.Frame(compare_frame)
        compare_toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(compare_toolbar, text="Compare with:").pack(side=tk.LEFT)
        self.compare_label = ttk.Label(compare_toolbar, text="(none loaded)", foreground="gray")
        self.compare_label.pack(side=tk.LEFT, padx=10)

        # Side-by-side comparison
        compare_paned = ttk.PanedWindow(compare_frame, orient=tk.HORIZONTAL)
        compare_paned.pack(fill=tk.BOTH, expand=True)

        # Left comparison
        left_compare = ttk.Frame(compare_paned)
        compare_paned.add(left_compare, weight=1)
        ttk.Label(left_compare, text="Current Schedule", font=("", 10, "bold")).pack(anchor=tk.W)
        self.compare_left_text = tk.Text(left_compare, wrap=tk.WORD, font=("Consolas", 9))
        self.compare_left_text.pack(fill=tk.BOTH, expand=True)

        # Right comparison
        right_compare = ttk.Frame(compare_paned)
        compare_paned.add(right_compare, weight=1)
        ttk.Label(right_compare, text="Comparison Schedule", font=("", 10, "bold")).pack(anchor=tk.W)
        self.compare_right_text = tk.Text(right_compare, wrap=tk.WORD, font=("Consolas", 9))
        self.compare_right_text.pack(fill=tk.BOTH, expand=True)

        # Diff view
        diff_frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(diff_frame, text="Diff")
        ttk.Label(diff_frame, text="Differences between schedules:", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        self.diff_text = tk.Text(diff_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.diff_text.pack(fill=tk.BOTH, expand=True)
        self.diff_text.config(state=tk.DISABLED)

        # Status bar
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)

    def _setup_bindings(self) -> None:
        self.root.bind("<Control-o>", lambda e: self._open_schedule())
        self.root.bind("<Control-s>", lambda e: self._save_as())

    def _open_schedule(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Schedule",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._load_schedule(path, is_comparison=False)

    def _open_comparison(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Schedule for Comparison",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._load_schedule(path, is_comparison=True)

    def _load_schedule(self, path: str, is_comparison: bool) -> None:
        try:
            schedule = Schedule.load(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load schedule:\n{e}")
            return

        if is_comparison:
            self.comparison_schedule = schedule
            self.compare_label.config(text=Path(path).name, foreground="black")
            self._update_comparison_view()
        else:
            self.current_schedule = schedule
            self._update_schedule_view(schedule)
            self.status_bar.config(text=f"Loaded: {Path(path).name}")

    def _clear_comparison(self) -> None:
        self.comparison_schedule = None
        self.compare_label.config(text="(none loaded)", foreground="gray")
        self.compare_right_text.config(state=tk.NORMAL)
        self.compare_right_text.delete(1.0, tk.END)
        self.compare_right_text.config(state=tk.DISABLED)
        self.diff_text.config(state=tk.NORMAL)
        self.diff_text.delete(1.0, tk.END)
        self.diff_text.config(state=tk.DISABLED)

    def _update_schedule_view(self, schedule: Schedule) -> None:
        # Update header
        self.seed_var.set(str(schedule.seed) if schedule.seed is not None else "(none)")
        self.choices_var.set(str(len(schedule.choices)))
        self.status_var.set("FAILURE" if schedule.failure else "OK")
        self.status_label.config(foreground="red" if schedule.failure else "green")

        # Update tree
        self.tree.delete(*self.tree.get_children())
        for i, (choice, task) in enumerate(zip(schedule.choices, schedule.tasks), 1):
            self.tree.insert("", tk.END, values=(i, choice, task))

        # Update failure
        self.failure_text.config(state=tk.NORMAL)
        self.failure_text.delete(1.0, tk.END)
        if schedule.failure:
            self.failure_text.insert(tk.END, schedule.failure)
        else:
            self.failure_text.insert(tk.END, "(no failure)")
        self.failure_text.config(state=tk.DISABLED)

        # Update timeline
        self.timeline_text.config(state=tk.NORMAL)
        self.timeline_text.delete(1.0, tk.END)
        self.timeline_text.insert(tk.END, timeline(schedule))
        self.timeline_text.config(state=tk.DISABLED)

        # Update comparison left side
        self.compare_left_text.config(state=tk.NORMAL)
        self.compare_left_text.delete(1.0, tk.END)
        self.compare_left_text.insert(tk.END, timeline(schedule))
        self.compare_left_text.config(state=tk.DISABLED)

    def _update_comparison_view(self) -> None:
        if not self.current_schedule or not self.comparison_schedule:
            return

        # Update right side
        self.compare_right_text.config(state=tk.NORMAL)
        self.compare_right_text.delete(1.0, tk.END)
        self.compare_right_text.insert(tk.END, timeline(self.comparison_schedule))
        self.compare_right_text.config(state=tk.DISABLED)

        # Update diff
        self._compute_diff()

    def _compute_diff(self) -> None:
        if not self.current_schedule or not self.comparison_schedule:
            return

        self.diff_text.config(state=tk.NORMAL)
        self.diff_text.delete(1.0, tk.END)

        a = self.current_schedule
        b = self.comparison_schedule

        diffs = []

        # Compare seeds
        if a.seed != b.seed:
            diffs.append(f"Seed: {a.seed} → {b.seed}")

        # Compare choices
        if a.choices != b.choices:
            max_len = max(len(a.choices), len(b.choices))
            diffs.append(f"Choices length: {len(a.choices)} → {len(b.choices)}")
            for i in range(max_len):
                ca = a.choices[i] if i < len(a.choices) else "(none)"
                cb = b.choices[i] if i < len(b.choices) else "(none)"
                ta = a.tasks[i] if i < len(a.tasks) else "(none)"
                tb = b.tasks[i] if i < len(b.tasks) else "(none)"
                if ca != cb or ta != tb:
                    diffs.append(f"  Step {i+1}: index {ca} ({ta}) → {cb} ({tb})")

        # Compare failures
        if a.failure != b.failure:
            diffs.append(f"Failure: {a.failure or '(none)'} → {b.failure or '(none)'}")

        if diffs:
            self.diff_text.insert(tk.END, "\n".join(diffs))
        else:
            self.diff_text.insert(tk.END, "Schedules are identical.")
        self.diff_text.config(state=tk.DISABLED)

    def _export_report(self) -> None:
        if not self.current_schedule:
            messagebox.showwarning("Warning", "No schedule loaded.")
            return

        path = filedialog.asksaveasfilename(
            title="Export Report",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(timeline(self.current_schedule))
                self.status_bar.config(text=f"Report exported to {Path(path).name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export report:\n{e}")

    def _save_as(self) -> None:
        if not self.current_schedule:
            messagebox.showwarning("Warning", "No schedule loaded.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Schedule As",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            try:
                self.current_schedule.save(path)
                self.status_bar.config(text=f"Saved to {Path(path).name}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save schedule:\n{e}")


def main() -> None:
    """Launch the schedule viewer GUI."""
    root = tk.Tk()
    app = ScheduleViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()