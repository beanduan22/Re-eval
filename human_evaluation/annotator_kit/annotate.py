#!/usr/bin/env python3
"""Blind behavior-change annotation GUI.

For each sample the annotator answers one question:

    "Does this change alter the behavior of the original code?"

Verdicts: Unchanged (valid) / Changed (invalid) / Cannot determine.
Choosing ``invalid`` reveals a single-select failure-mode tag (feeds RQ4) plus
an optional note. A soft 10-minute per-sample timer nudges the annotator toward
``Cannot determine`` when it expires. The view is blind: only task name + sample
id show.
"""
from __future__ import annotations

import argparse
import json
import time
from difflib import ndiff
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext

from pygments import lex
from pygments.lexers import CLexer, JavaLexer, PythonLexer
from pygments.styles import get_style_by_name

from protocol import (
    FAILURE_MODES,
    FAILURE_MODE_KEYS,
    TIMEOUT_SECONDS,
    VERDICT_LABEL,
    VERDICTS,
)

DEFAULT_DATA = Path(__file__).with_name("blind_samples.json")
STYLE = get_style_by_name("monokai")
LEXERS = {"c": CLexer, "java": JavaLexer, "python": PythonLexer}


def lexer_for(language):
    return LEXERS.get(str(language).strip().lower(), JavaLexer)()


def ensure_token_tag(text_widget, token):
    tag = str(token)
    style_str = STYLE.styles.get(token)
    try:
        text_widget.tag_configure(tag)
    except tk.TclError:
        pass
    if not style_str:
        return tag
    kwargs = {}
    for part in style_str.split():
        if part.startswith("bg:"):
            kwargs["background"] = part[3:]
        elif part.startswith("#"):
            kwargs["foreground"] = part
    if kwargs:
        try:
            text_widget.tag_configure(tag, **kwargs)
        except tk.TclError:
            pass
    return tag


def insert_lexed(text_widget, code, language, extra_tags=()):
    for token, content in lex(code, lexer_for(language)):
        text_widget.insert(tk.END, content, (ensure_token_tag(text_widget, token), *extra_tags))


def highlight_code(text_widget, code, language):
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    insert_lexed(text_widget, code, language)
    text_widget.config(state="disabled")


def highlight_adv_with_added(text_widget, orig_code, adv_code, language):
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.tag_configure("added", background="#1b3d1b")
    for line in ndiff(orig_code.splitlines(), adv_code.splitlines()):
        if line.startswith("? ") or line.startswith("- "):
            continue
        tags = ("added",) if line.startswith("+ ") else ()
        insert_lexed(text_widget, line[2:] + "\n", language, tags)
    text_widget.config(state="disabled")


def highlight_diff(text_widget, orig_code, adv_code, language):
    text_widget.config(state="normal")
    text_widget.delete("1.0", tk.END)
    text_widget.tag_configure("added", background="#1b3d1b")
    text_widget.tag_configure("deleted", background="#4a1a1a")
    for line in ndiff(orig_code.splitlines(), adv_code.splitlines()):
        if line.startswith("? "):
            continue
        tags = ()
        if line.startswith("+ "):
            tags = ("added",)
        elif line.startswith("- "):
            tags = ("deleted",)
        insert_lexed(text_widget, line[2:] + "\n", language, tags)
    text_widget.config(state="disabled")


class UsernamePrompt:
    def __init__(self, root):
        self.root = root
        self.username = None
        root.title("Behavior-Change Annotation Login")
        root.geometry("400x180")
        tk.Label(root, text="Enter your username:", font=("Arial", 12)).pack(pady=20)
        self.entry = tk.Entry(root, font=("Arial", 12))
        self.entry.pack(pady=5)
        self.entry.focus_set()
        tk.Button(root, text="Start", command=self.start).pack(pady=10)
        self.entry.bind("<Return>", lambda _e: self.start())

    def start(self):
        name = self.entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a username before starting.")
            return
        self.username = name
        self.root.destroy()


class CodeReviewer:
    def __init__(self, root, username, data_path):
        self.root = root
        self.username = username
        self.data_path = Path(data_path)
        self.result_path = Path(f"{username}_{self.data_path.stem}_results.json")
        self.diff_mode = False
        self.index = 0
        self.sample_started_at = time.monotonic()
        self.timed_out = False

        self.data = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.results = self.load_results()
        self.result_index_by_key = {self.result_key(row): i for i, row in enumerate(self.results)}

        root.title(f"Behavior-Change Annotation - User: {username}")
        root.geometry("1320x820")
        self.container = tk.Frame(root, bg="#1e1e1e")
        self.container.pack(fill=tk.BOTH, expand=True)

        self.label_left = tk.Label(self.container, text="Original code", bg="#1e1e1e", fg="#cccccc", font=("Arial", 11, "bold"))
        self.label_right = tk.Label(self.container, text="Adversarial code (diff highlighted)", bg="#1e1e1e", fg="#cccccc", font=("Arial", 11, "bold"))
        self.label_left.place(relx=0.0, rely=0.0, relwidth=0.5, relheight=0.04)
        self.label_right.place(relx=0.5, rely=0.0, relwidth=0.5, relheight=0.04)

        self.text_left = self.make_text()
        self.text_right = self.make_text()
        self.text_left.place(relx=0, rely=0.04, relwidth=0.5, relheight=0.74)
        self.text_right.place(relx=0.5, rely=0.04, relwidth=0.5, relheight=0.74)

        bottom = tk.Frame(root, bg="#f5f5f5")
        bottom.place(relx=0, rely=0.78, relwidth=1, relheight=0.22)

        # Row 1: progress + timer + the question.
        row1 = tk.Frame(bottom, bg="#f5f5f5")
        row1.pack(fill=tk.X, padx=10, pady=(6, 2))
        self.progress_label = tk.Label(row1, text="", font=("Arial", 10, "bold"), fg="#0078D7", bg="#f5f5f5")
        self.progress_label.pack(side=tk.LEFT)
        self.timer_label = tk.Label(row1, text="", font=("Arial", 10), fg="#333333", bg="#f5f5f5")
        self.timer_label.pack(side=tk.LEFT, padx=12)
        self.diff_button = tk.Button(row1, text="Diff View: OFF", command=self.toggle_diff_view)
        self.diff_button.pack(side=tk.RIGHT)

        tk.Label(bottom, text="Does this change alter the behavior of the original code?", font=("Arial", 12, "bold"), bg="#f5f5f5").pack(anchor="w", padx=10, pady=(4, 2))

        # Row 2: the three verdict buttons.
        row2 = tk.Frame(bottom, bg="#f5f5f5")
        row2.pack(fill=tk.X, padx=10)
        self.verdict_var = tk.StringVar(value="")
        self.verdict_buttons = {}
        for verdict in VERDICTS:
            label = self.make_choice_label(row2, VERDICT_LABEL[verdict], lambda v=verdict: self.set_verdict(v))
            label.pack(side=tk.LEFT, padx=4)
            self.verdict_buttons[verdict] = label

        # Row 3: failure-mode radios (shown only when invalid is chosen).
        self.fm_frame = tk.Frame(bottom, bg="#f5f5f5")
        self.fm_frame.pack(fill=tk.X, padx=10, pady=(4, 2))
        self.fm_var = tk.StringVar(value="")
        tk.Label(self.fm_frame, text="Failure mode:", font=("Arial", 10, "bold"), bg="#f5f5f5").pack(side=tk.LEFT)
        for key, text in FAILURE_MODES:
            tk.Radiobutton(
                self.fm_frame, text=text, value=key, variable=self.fm_var,
                font=("Arial", 9), bg="#f5f5f5", anchor="w", selectcolor="#ffd",
            ).pack(side=tk.LEFT, padx=2)

        # Row 4: note + navigation.
        row4 = tk.Frame(bottom, bg="#f5f5f5")
        row4.pack(fill=tk.X, padx=10, pady=(4, 4))
        tk.Label(row4, text="Note (optional):", font=("Arial", 10), bg="#f5f5f5").pack(side=tk.LEFT)
        self.note_var = tk.StringVar(value="")
        tk.Entry(row4, textvariable=self.note_var, font=("Arial", 10), width=48).pack(side=tk.LEFT, padx=6)
        tk.Button(row4, text="Next", command=self.next_code).pack(side=tk.RIGHT, padx=6)
        tk.Button(row4, text="Previous", command=self.prev_code).pack(side=tk.RIGHT, padx=6)
        tk.Button(row4, text="Save", command=self.save_score).pack(side=tk.RIGHT, padx=6)

        self.feedback_label = tk.Label(root, text="", font=("Arial", 9), bg="#222222", fg="white")
        self.show_code()
        self.tick()

    def make_text(self):
        return scrolledtext.ScrolledText(
            self.container, wrap=tk.WORD, bg="#272822", fg="#ffffff",
            font=("Consolas", 10), padx=10, pady=10, borderwidth=0,
        )

    def make_choice_label(self, parent, text, command):
        label = tk.Label(parent, text=text, font=("Arial", 12, "bold"), fg="black", bg="#e9e9e9", cursor="hand2", padx=10, pady=4, relief="raised", bd=2)
        label.bind("<Button-1>", lambda _event: command())
        label.bind("<Enter>", lambda _event: label.config(bg="#dcecff"))
        label.bind("<Leave>", lambda _event: self.update_colors())
        return label

    # ---- result persistence -------------------------------------------------
    def load_results(self):
        if not self.result_path.exists():
            return []
        try:
            loaded = json.loads(self.result_path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, list) else []
        except Exception:
            return []

    def item_key(self, item):
        return (item.get("Sample ID", ""),)

    def result_key(self, item):
        return (item.get("Sample ID", ""),)

    # ---- verdict / failure-mode state ---------------------------------------
    def set_verdict(self, value):
        self.verdict_var.set(value)
        if value != "invalid":
            self.fm_var.set("")
        self.update_colors()

    def update_colors(self):
        selected = self.verdict_var.get()
        for verdict, label in self.verdict_buttons.items():
            if verdict == selected:
                label.config(bg="#0078D7", fg="white", relief="sunken")
            else:
                label.config(bg="#e9e9e9", fg="black", relief="raised")
        # Failure-mode row only matters for invalid.
        state = "normal" if selected == "invalid" else "disabled"
        for child in self.fm_frame.winfo_children():
            if isinstance(child, tk.Radiobutton):
                child.config(state=state)

    def show_feedback(self, msg):
        self.feedback_label.config(text=msg)
        self.feedback_label.place(relx=0.98, rely=0.97, anchor="se")
        self.root.after(1200, self.feedback_label.place_forget)

    def save_score(self):
        verdict = self.verdict_var.get()
        if verdict not in VERDICTS:
            self.show_feedback("Please choose Unchanged / Changed / Cannot determine first")
            return False
        failure_mode = self.fm_var.get() if verdict == "invalid" else ""
        if verdict == "invalid" and failure_mode not in FAILURE_MODE_KEYS:
            self.show_feedback("'Changed (invalid)' requires selecting a failure mode")
            return False

        item = self.data[self.index]
        record = {
            "Sample ID": item.get("Sample ID", ""),
            "Task": item.get("Task", ""),
            "verdict": verdict,
            "failure_mode": failure_mode,
            "note": self.note_var.get().strip(),
            "elapsed_seconds": round(time.monotonic() - self.sample_started_at, 1),
            "timed_out": self.timed_out,
        }
        key = self.item_key(item)
        existing = self.result_index_by_key.get(key)
        if existing is None:
            self.results.append(record)
            self.result_index_by_key[key] = len(self.results) - 1
        else:
            self.results[existing] = record
        self.result_path.write_text(json.dumps(self.results, indent=2, ensure_ascii=False), encoding="utf-8")
        self.show_feedback(f"Sample {self.index + 1} saved")
        return True

    # ---- navigation ----------------------------------------------------------
    def toggle_diff_view(self):
        self.diff_mode = not self.diff_mode
        self.diff_button.config(text=f"Diff View: {'ON' if self.diff_mode else 'OFF'}")
        self.show_code()

    def next_code(self):
        if not self.save_score():
            return
        if self.index < len(self.data) - 1:
            self.index += 1
            self.show_code()
            return
        if messagebox.askyesno("Finish", "You reached the last sample.\nFinish now?"):
            self.check_completion()

    def prev_code(self):
        if self.index > 0:
            self.index -= 1
            self.show_code()
        else:
            self.show_feedback("Already at the first sample")

    def check_completion(self):
        missing = [self.item_key(item) for item in self.data if self.result_index_by_key.get(self.item_key(item)) is None]
        if missing:
            messagebox.showwarning("Incomplete", f"Some samples are not annotated yet.\nMissing: {len(missing)}")
            return False
        messagebox.showinfo("Completed", "All samples annotated.")
        self.root.destroy()
        return True

    # ---- soft per-sample timer ----------------------------------------------
    def tick(self):
        elapsed = time.monotonic() - self.sample_started_at
        remaining = TIMEOUT_SECONDS - elapsed
        if remaining > 0:
            mm, ss = divmod(int(remaining), 60)
            self.timer_label.config(text=f"Time left {mm:02d}:{ss:02d}", fg="#333333" if remaining > 60 else "#d00000")
        else:
            self.timed_out = True
            self.timer_label.config(text="Time up -> suggest 'Cannot determine'", fg="#d00000")
            if not self.verdict_var.get():
                self.set_verdict("cannot_determine")
        self.root.after(1000, self.tick)

    # ---- rendering -----------------------------------------------------------
    def show_code(self):
        item = self.data[self.index]
        orig = item.get("Original", "")
        adv = item.get("Adversarial", "")
        language = item.get("Language", "java")
        highlight_code(self.text_left, orig, language)
        if self.diff_mode:
            highlight_diff(self.text_right, orig, adv, language)
        else:
            highlight_adv_with_added(self.text_right, orig, adv, language)

        task_name = item.get("Task Name", item.get("Task", ""))
        self.progress_label.config(text=f"Sample {self.index + 1} / {len(self.data)}    Task: {task_name}")
        self.root.title(f"Behavior-Change Annotation - {self.index + 1}/{len(self.data)} - User: {self.username}")

        # Restore any prior annotation for this sample.
        self.verdict_var.set("")
        self.fm_var.set("")
        self.note_var.set("")
        existing = self.result_index_by_key.get(self.item_key(item))
        if existing is not None:
            prior = self.results[existing]
            self.verdict_var.set(prior.get("verdict", ""))
            self.fm_var.set(prior.get("failure_mode", ""))
            self.note_var.set(prior.get("note", ""))
        self.update_colors()

        # Reset the per-sample timer.
        self.sample_started_at = time.monotonic()
        self.timed_out = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="blind sample JSON (from build_combined_blind.py)")
    args = parser.parse_args()
    prompt_root = tk.Tk()
    prompt = UsernamePrompt(prompt_root)
    prompt_root.mainloop()
    if prompt.username:
        root = tk.Tk()
        CodeReviewer(root, prompt.username, args.data)
        root.mainloop()


if __name__ == "__main__":
    main()
