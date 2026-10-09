#!/usr/bin/env python3


from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import time
from difflib import ndiff
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from pygments import lex
from pygments.lexers import CLexer, JavaLexer, PythonLexer
from pygments.styles import get_style_by_name

from protocol import (
    FAILURE_MODE_KEYS,
    TIMEOUT_SECONDS,
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
    for tag in ("added", "deleted"):
        if tag in text_widget.tag_names():
            text_widget.tag_raise(tag)
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
    for tag in ("added", "deleted"):
        if tag in text_widget.tag_names():
            text_widget.tag_raise(tag)
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
    for tag in ("added", "deleted"):
        if tag in text_widget.tag_names():
            text_widget.tag_raise(tag)
    text_widget.config(state="disabled")


VERDICT_TEXT = {
    "valid": "Valid and behavior-preserving",
    "invalid": "Validity or behavior violation",
    "cannot_determine": "Cannot determine",
}
FAILURE_TEXT = dict(zip(FAILURE_MODE_KEYS, (
    "Syntax error", "Broken binding", "Scope conflict", "Broken block structure", "Unsafe insertion", "Behavior change",
)))
GUIDE = """Your task
Compare the original code on the left with the modified code on the right.
Decide whether the modified code is valid and preserves the original behavior.

Valid and behavior-preserving: no syntax, static-language, or binding errors,
and no change to observable program behavior.
Validity or behavior violation: a demonstrated error or behavior change.
Select one main failure mode; use the note to identify the relevant code.
Cannot determine: insufficient context or evidence to make a clear judgment.
Uncertainty alone does not establish a violation.

Green marks added lines; red marks deleted lines. "Show full diff" shows both.
The code is not executed. Judge independently from the supplied code;
you do not need to guess the attack method or model prediction.
Aim to spend no more than 10 minutes per sample. The timer only reminds you;
it never selects an answer for you.

"Save and next" saves your answer. When navigating or closing with unsaved
changes, you will be asked whether to save. Cancel keeps the current sample open.
Use the same annotator ID next time to load your saved answers and resume
at the first unanswered sample.

Send your result JSON file to the study coordinator when finished.
"Export results" saves a copy. You can also stop and resume before finishing.
Use a different ID for each annotator and complete the task independently.
"""


def valid_username(name):
    return bool(name) and len(name) <= 64 and all(c.isalnum() or c in "_-" for c in name)


def load_samples(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("The sample file must be a non-empty JSON list.")
    ids = set()
    for row in data:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) for k in ("Sample ID", "Original", "Adversarial")):
            raise ValueError("Each sample must contain string fields: Sample ID, Original, and Adversarial.")
        sid = row["Sample ID"]
        if not sid or sid in ids:
            raise ValueError("Sample IDs must be non-empty and unique.")
        ids.add(sid)
    return data


def atomic_write(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temp = Path(f.name)
            json.dump(records, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def show_guide(root):
    dialog = tk.Toplevel(root)
    dialog.title("Annotation guide")
    dialog.geometry("760x590")
    box = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, padx=20, pady=16, font=("TkDefaultFont", 12))
    box.pack(fill=tk.BOTH, expand=True)
    box.insert("1.0", GUIDE)
    box.config(state="disabled")
    ttk.Button(dialog, text="Got it", command=dialog.destroy).pack(pady=10)


class UsernamePrompt:
    def __init__(self, root):
        self.root, self.username = root, None
        root.title("Code Annotation · Start")
        root.geometry("600x340")
        frame = ttk.Frame(root, padding=28)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Code Annotation", font=("TkDefaultFont", 22, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Compare original and modified code to assess validity and behavior preservation.", wraplength=520).pack(anchor="w", pady=(10, 18))
        ttk.Label(frame, text="Annotator ID (use the same ID to resume)").pack(anchor="w")
        self.entry = ttk.Entry(frame, font=("TkDefaultFont", 14))
        self.entry.pack(fill=tk.X, pady=8)
        self.entry.focus_set()
        ttk.Label(frame, text="Use letters, numbers, underscores, or hyphens. Results stay on this computer.").pack(anchor="w")
        actions = ttk.Frame(frame)
        actions.pack(fill=tk.X, pady=22)
        ttk.Button(actions, text="Read annotation guide", command=lambda: show_guide(root)).pack(side=tk.LEFT)
        ttk.Button(actions, text="Start / Resume", command=self.start).pack(side=tk.RIGHT)
        self.entry.bind("<Return>", lambda _e: self.start())

    def start(self):
        name = self.entry.get().strip()
        if not valid_username(name):
            messagebox.showerror("Invalid ID", "Enter 1–64 letters, numbers, underscores, or hyphens.", parent=self.root)
            return
        self.username = name
        self.root.destroy()


class CodeReviewer:
    def __init__(self, root, username, data_path, results_dir=None):
        if not valid_username(username):
            raise ValueError("Invalid annotator ID.")
        self.root, self.username = root, username
        self.data_path = Path(data_path).resolve()
        self.data = load_samples(self.data_path)
        filename = f"{username}_{self.data_path.stem}_results.json"
        self.result_path = (Path(results_dir) if results_dir else self.data_path.parent / "results") / filename
        self.result_path = self.result_path.resolve()
        # Continue files written by the earlier desktop application in the working directory.
        legacy = Path.cwd() / filename
        if results_dir is None and not self.result_path.exists() and legacy.exists():
            self.result_path = legacy.resolve()
        self.results = self.load_results()
        self.result_index_by_key = {row["Sample ID"]: i for i, row in enumerate(self.results)}
        self.index = next((i for i, r in enumerate(self.data) if r["Sample ID"] not in self.result_index_by_key), 0)
        self.diff_mode = False
        self.timer_id = None
        root.title(f"Code Annotation · {username}")
        root.geometry("1380x900")
        root.minsize(1040, 740)
        root.protocol("WM_DELETE_WINDOW", self.close)

        header = ttk.Frame(root, padding=(16, 12))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Code Annotation", font=("TkDefaultFont", 18, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text=f"Annotator: {username}").pack(side=tk.LEFT, padx=22)
        ttk.Button(header, text="Annotation guide", command=lambda: show_guide(root)).pack(side=tk.RIGHT)
        ttk.Button(header, text="Export results…", command=self.export_results).pack(side=tk.RIGHT, padx=8)
        progress = ttk.Frame(root, padding=(16, 0, 16, 8))
        progress.pack(fill=tk.X)
        self.progress_label = ttk.Label(progress)
        self.progress_label.pack(side=tk.LEFT)
        self.progressbar = ttk.Progressbar(progress, maximum=len(self.data), length=220)
        self.progressbar.pack(side=tk.RIGHT)

        # Pack controls before the expanding code area so they remain visible on resize.
        footer = ttk.Frame(root, padding=(16, 8))
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        self.feedback_label = ttk.Label(footer, foreground="#176344")
        self.feedback_label.pack(anchor="w")
        ttk.Label(footer, text=f"Result file: {self.result_path}", wraplength=1000).pack(anchor="w", pady=(4, 0))
        bottom = ttk.Frame(root, padding=(16, 10))
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bottom, text="Is the modified code valid and behavior-preserving?", font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
        choices = ttk.Frame(bottom)
        choices.pack(fill=tk.X, pady=8)
        self.verdict_var, self.fm_var, self.note_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for value in VERDICTS:
            ttk.Radiobutton(choices, text=VERDICT_TEXT[value], variable=self.verdict_var, value=value,
                            command=self.update_choices).pack(side=tk.LEFT, padx=(0, 28))
        self.fm_frame = ttk.Frame(bottom)
        self.fm_frame.pack(fill=tk.X)
        ttk.Label(self.fm_frame, text="Failure mode (required for a violation):").grid(row=0, column=0, columnspan=3, sticky="w")
        self.failure_buttons = []
        for i, key in enumerate(FAILURE_MODE_KEYS):
            button = ttk.Radiobutton(self.fm_frame, text=FAILURE_TEXT[key], variable=self.fm_var, value=key)
            button.grid(row=1 + i // 3, column=i % 3, sticky="w", padx=(0, 26), pady=3)
            self.failure_buttons.append(button)
        notes = ttk.Frame(bottom)
        notes.pack(fill=tk.X, pady=8)
        ttk.Label(notes, text="Note (optional): ").pack(side=tk.LEFT)
        self.note_entry = ttk.Entry(notes, textvariable=self.note_var)
        self.note_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        actions = ttk.Frame(bottom)
        actions.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(actions, text="Previous", command=self.prev_code).pack(side=tk.LEFT)
        ttk.Button(actions, text="Next unanswered", command=self.next_unanswered).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="Finish annotation", command=self.check_completion).pack(side=tk.RIGHT)
        ttk.Button(actions, text="Save and next →", command=self.next_code).pack(side=tk.RIGHT, padx=8)
        ttk.Button(actions, text="Save", command=self.save_score).pack(side=tk.RIGHT)

        code_header = ttk.Frame(root, padding=(16, 4))
        code_header.pack(fill=tk.X)
        self.sample_label = ttk.Label(code_header)
        self.sample_label.pack(side=tk.LEFT)
        self.timer_label = ttk.Label(code_header)
        self.timer_label.pack(side=tk.RIGHT, padx=12)
        self.diff_button = ttk.Button(code_header, text="Show full diff", command=self.toggle_diff_view)
        self.diff_button.pack(side=tk.RIGHT)
        panes = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        self.text_left = self.make_text(panes, "Original code")
        self.text_right = self.make_text(panes, "Modified code · Green: added / Red: deleted")
        self.show_code()
        self.tick()
        root.bind("<Control-s>", self.save_shortcut)

    def make_text(self, panes, title):
        frame = ttk.Frame(panes)
        panes.add(frame, weight=1)
        ttk.Label(frame, text=title, padding=(4, 6)).pack(anchor="w")
        horizontal = ttk.Scrollbar(frame, orient=tk.HORIZONTAL)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        widget = scrolledtext.ScrolledText(frame, wrap=tk.NONE, bg="#272822", fg="#f8f8f2",
                                          font=("TkFixedFont", 11), padx=12, pady=10,
                                          xscrollcommand=horizontal.set)
        widget.pack(fill=tk.BOTH, expand=True)
        horizontal.config(command=widget.xview)
        return widget

    def load_results(self):
        if not self.result_path.exists():
            return []
        records = json.loads(self.result_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("Existing results are not a JSON list. The file has not been overwritten.")
        allowed = {row["Sample ID"] for row in self.data}
        seen = set()
        for row in records:
            if not isinstance(row, dict):
                raise ValueError("Existing results contain an invalid record. The file has not been overwritten.")
            sid = row.get("Sample ID")
            if not isinstance(sid, str) or sid not in allowed or sid in seen or row.get("verdict") not in VERDICTS:
                raise ValueError("Existing results contain duplicate, invalid, or unrelated sample records. The file has not been overwritten.")
            if row["verdict"] == "invalid" and row.get("failure_mode") not in FAILURE_MODE_KEYS:
                raise ValueError("An existing violation is missing a valid failure mode. The file has not been overwritten.")
            elapsed = row.get("elapsed_seconds", 0)
            if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError("Existing results contain invalid annotation times. The file has not been overwritten.")
            if not isinstance(row.get("note", ""), str):
                raise ValueError("Existing results contain an invalid note. The file has not been overwritten.")
            seen.add(sid)
        return records

    def update_choices(self):
        invalid = self.verdict_var.get() == "invalid"
        if not invalid:
            self.fm_var.set("")
        for button in self.failure_buttons:
            button.config(state=tk.NORMAL if invalid else tk.DISABLED)

    def answers(self):
        return (self.verdict_var.get(), self.fm_var.get(), self.note_var.get().strip())

    def show_feedback(self, text):
        self.feedback_label.config(text=text)

    def update_progress(self):
        done = len(self.results)
        self.progress_label.config(text=f"Saved {done} / {len(self.data)} · Remaining: {len(self.data) - done}")
        self.progressbar["value"] = done

    def save_score(self):
        verdict, failure, note = self.answers()
        if verdict not in VERDICTS:
            self.show_feedback("Choose a verdict before saving.")
            return False
        if verdict == "invalid" and failure not in FAILURE_MODE_KEYS:
            self.show_feedback("Select a demonstrated failure mode before saving.")
            return False
        item = self.data[self.index]
        now = time.monotonic()
        elapsed = self.elapsed_before + now - self.sample_started_at
        record = {"Sample ID": item["Sample ID"], "Task": item.get("Task", ""),
                  "verdict": verdict, "failure_mode": failure if verdict == "invalid" else "",
                  "note": note, "elapsed_seconds": round(elapsed, 1),
                  "timed_out": self.timed_out or elapsed >= TIMEOUT_SECONDS}
        records = list(self.results)
        existing = self.result_index_by_key.get(item["Sample ID"])
        if existing is None:
            records.append(record)
        else:
            records[existing] = record
        try:
            atomic_write(self.result_path, records)
        except OSError as exc:
            messagebox.showerror("Save failed", f"Check folder permissions and disk space. Your current answer is still in the form.\n\n{exc}", parent=self.root)
            return False
        self.results = records
        self.result_index_by_key = {row["Sample ID"]: i for i, row in enumerate(records)}
        self.elapsed_before, self.sample_started_at = elapsed, now
        self.timed_out = record["timed_out"]
        self.saved_answers = self.answers()
        self.update_progress()
        self.show_feedback(f"Saved {item['Sample ID']}. You can close and resume later.")
        return True

    def save_shortcut(self, _event):
        self.save_score()
        return "break"

    def leave_sample(self):
        if self.answers() == self.saved_answers:
            return True
        choice = messagebox.askyesnocancel("Save current answer?", "You have unsaved changes. Save them?\nYes: save; No: discard changes; Cancel: keep editing.", parent=self.root)
        if choice is False:
            self.verdict_var.set(self.saved_answers[0])
            self.fm_var.set(self.saved_answers[1])
            self.note_var.set(self.saved_answers[2])
            self.update_choices()
            return True
        return self.save_score() if choice is True else False

    def render_code(self):
        item = self.data[self.index]
        language = item.get("Language", "java")
        highlight_code(self.text_left, item["Original"], language)
        render = highlight_diff if self.diff_mode else highlight_adv_with_added
        render(self.text_right, item["Original"], item["Adversarial"], language)

    def toggle_diff_view(self):
        self.diff_mode = not self.diff_mode
        self.diff_button.config(text="Show modified code only" if self.diff_mode else "Show full diff")
        self.render_code()

    def show_code(self):
        item = self.data[self.index]
        self.render_code()
        self.sample_label.config(text=f"Sample {self.index + 1} · {item['Sample ID']} · {item.get('Task Name', item.get('Task', ''))} · {item.get('Language', '')}")
        existing = self.result_index_by_key.get(item["Sample ID"])
        prior = self.results[existing] if existing is not None else {}
        self.verdict_var.set(prior.get("verdict", ""))
        self.fm_var.set(prior.get("failure_mode", ""))
        self.note_var.set(prior.get("note", ""))
        self.update_choices()
        self.saved_answers = self.answers()
        self.elapsed_before = prior.get("elapsed_seconds", 0)
        self.sample_started_at = time.monotonic()
        self.timed_out = prior.get("timed_out", False)
        self.update_progress()
        self.show_feedback("Saved answer loaded. You can edit it." if prior else "Judge independently. Choose 'Cannot determine' if unsure.")
        self.update_timer()

    def next_code(self):
        if not self.save_score():
            return
        if self.index < len(self.data) - 1:
            self.index += 1
            self.show_code()
        else:
            self.check_completion()

    def prev_code(self):
        if self.index > 0 and self.leave_sample():
            self.index -= 1
            self.show_code()

    def next_unanswered(self):
        if not self.leave_sample():
            return
        for offset in range(1, len(self.data) + 1):
            index = (self.index + offset) % len(self.data)
            if self.data[index]["Sample ID"] not in self.result_index_by_key:
                self.index = index
                self.show_code()
                return
        self.show_feedback("All samples are saved. Click 'Finish annotation' for submission details.")

    def check_completion(self):
        if not self.leave_sample():
            return False
        missing = len(self.data) - len(self.results)
        if missing:
            messagebox.showinfo("Not finished yet", f"{missing} samples remain. Click 'Next unanswered' to continue.\nSaved answers will be available next time.", parent=self.root)
            return False
        messagebox.showinfo("Annotation complete", f"Thank you! All {len(self.data)} samples are saved.\nSend this file to the study coordinator:\n\n{self.result_path}\n\nYou can also use 'Export results' to save a copy.", parent=self.root)
        return True

    def export_results(self):
        if not self.leave_sample():
            return
        if not self.results:
            self.show_feedback("Save at least one annotation first.")
            return
        destination = filedialog.asksaveasfilename(parent=self.root, title="Export saved annotations",
            initialfile=self.result_path.name, defaultextension=".json", filetypes=[("JSON", "*.json")])
        if destination:
            if Path(destination).resolve() == self.data_path:
                messagebox.showerror("Cannot export", "Choose another location. The sample file cannot be overwritten.", parent=self.root)
                return
            try:
                atomic_write(Path(destination), self.results)
            except OSError as exc:
                messagebox.showerror("Export failed", str(exc), parent=self.root)
                return
            self.show_feedback(f"Exported {len(self.results)} / {len(self.data)} samples: {destination}")

    def update_timer(self):
        elapsed = self.elapsed_before + time.monotonic() - self.sample_started_at
        remaining = max(0, int(TIMEOUT_SECONDS - elapsed))
        mm, ss = divmod(remaining, 60)
        if elapsed >= TIMEOUT_SECONDS:
            self.timed_out = True
            self.timer_label.config(text="10 minutes elapsed; choose 'Cannot determine' if unsure", foreground="#a43c28")
        else:
            self.timer_label.config(text=f"Suggested time left {mm:02d}:{ss:02d}", foreground="#555555")

    def tick(self):
        self.update_timer()
        self.timer_id = self.root.after(1000, self.tick)

    def close(self):
        if self.leave_sample():
            if self.timer_id is not None:
                self.root.after_cancel(self.timer_id)
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="Offline desktop application for code annotation")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Blind sample JSON file")
    parser.add_argument("--results-dir", help="Result directory (default: results/ next to the sample file)")
    parser.add_argument("--username", help="Annotator ID; opens the login window if omitted")
    args = parser.parse_args()
    if args.username and not valid_username(args.username):
        parser.error("Annotator IDs must contain 1–64 letters, numbers, underscores, or hyphens.")
    username = args.username
    if not username:
        prompt_root = tk.Tk()
        prompt = UsernamePrompt(prompt_root)
        prompt_root.mainloop()
        username = prompt.username
    if username:
        root = tk.Tk()
        root.withdraw()
        try:
            CodeReviewer(root, username, args.data, args.results_dir)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot open annotation task", f"{exc}\n\nPlease contact the study coordinator who provided this kit.", parent=root)
            root.destroy()
            return 1
        root.deiconify()
        root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
