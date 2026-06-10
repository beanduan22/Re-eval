#!/usr/bin/env python3
"""Tkinter GUI for semantic-preservation review of sampled attack successes."""

from __future__ import annotations

import argparse
import json
from difflib import ndiff
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext

from pygments import lex
from pygments.lexers import CLexer, JavaLexer, PythonLexer
from pygments.styles import get_style_by_name

DEFAULT_DATA = Path(__file__).with_name("selected_attack_successes.json")
STYLE = get_style_by_name("monokai")
LEXERS = {
    "c": CLexer,
    "java": JavaLexer,
    "python": PythonLexer,
}


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
        root.title("Code Evaluation Login")
        root.geometry("400x180")
        tk.Label(root, text="Enter your username:", font=("Arial", 12)).pack(pady=20)
        self.entry = tk.Entry(root, font=("Arial", 12))
        self.entry.pack(pady=5)
        tk.Button(root, text="Start Evaluation", command=self.start).pack(pady=10)

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

        self.data = json.loads(self.data_path.read_text(encoding="utf-8"))
        self.results = self.load_results()
        self.result_index_by_key = {self.result_key(row): i for i, row in enumerate(self.results)}

        root.title(f"Code Evaluation - User: {username}")
        root.geometry("1320x780")
        self.container = tk.Frame(root, bg="#1e1e1e")
        self.container.pack(fill=tk.BOTH, expand=True)

        self.label_left = tk.Label(self.container, text="Original Code", bg="#1e1e1e", fg="#cccccc", font=("Arial", 11, "bold"))
        self.label_right = tk.Label(self.container, text="Adversarial Code", bg="#1e1e1e", fg="#cccccc", font=("Arial", 11, "bold"))
        self.label_left.place(relx=0.0, rely=0.0, relwidth=0.5, relheight=0.04)
        self.label_right.place(relx=0.5, rely=0.0, relwidth=0.5, relheight=0.04)

        self.text_left = self.make_text()
        self.text_right = self.make_text()
        self.text_left.place(relx=0, rely=0.04, relwidth=0.5, relheight=0.84)
        self.text_right.place(relx=0.5, rely=0.04, relwidth=0.5, relheight=0.84)

        bottom = tk.Frame(root, bg="#f5f5f5")
        bottom.place(relx=0, rely=0.88, relwidth=1, relheight=0.12)
        self.progress_label = tk.Label(bottom, text="", font=("Arial", 10, "bold"), fg="#0078D7", bg="#f5f5f5")
        self.progress_label.pack(side=tk.LEFT, padx=10)
        self.meta_label = tk.Label(bottom, text="", font=("Arial", 9), fg="#333333", bg="#f5f5f5", wraplength=520, justify=tk.LEFT)
        self.meta_label.pack(side=tk.LEFT, padx=6)

        tk.Label(bottom, text="Preservation:", font=("Arial", 10, "bold"), bg="#f5f5f5").pack(side=tk.LEFT, padx=(5, 2))
        self.label_var = tk.StringVar(value="")
        self.choice_labels = []
        for choice in ("Preserved", "Changed", "Unclear"):
            label = self.make_rating_label(bottom, choice, lambda v=choice: self.set_label(v))
            label.pack(side=tk.LEFT, padx=3)
            self.choice_labels.append(label)

        tk.Button(bottom, text="Previous", command=self.prev_code).pack(side=tk.RIGHT, padx=6)
        tk.Button(bottom, text="Save and Next", command=self.next_code).pack(side=tk.RIGHT, padx=6)
        tk.Button(bottom, text="Save", command=self.save_score).pack(side=tk.RIGHT, padx=6)
        self.diff_button = tk.Button(bottom, text="Diff View: OFF", command=self.toggle_diff_view)
        self.diff_button.pack(side=tk.RIGHT, padx=6)
        self.feedback_label = tk.Label(root, text="", font=("Arial", 9), bg="#222222", fg="white")
        self.show_code()

    def make_text(self):
        return scrolledtext.ScrolledText(
            self.container,
            wrap=tk.WORD,
            bg="#272822",
            fg="#ffffff",
            font=("Consolas", 10),
            padx=10,
            pady=10,
            borderwidth=0,
        )

    def make_rating_label(self, parent, text, command):
        label = tk.Label(parent, text=text, font=("Arial", 12, "bold"), fg="black", bg="#f5f5f5", cursor="hand2", padx=6)
        label.bind("<Button-1>", lambda _event: command())
        label.bind("<Enter>", lambda _event: label.config(fg="#ff4d4f"))
        label.bind("<Leave>", lambda _event: self.update_colors())
        return label

    def load_results(self):
        if not self.result_path.exists():
            return []
        try:
            loaded = json.loads(self.result_path.read_text(encoding="utf-8"))
            return loaded if isinstance(loaded, list) else []
        except Exception:
            return []

    def item_key(self, item):
        sample_id = item.get("Sample ID", "")
        if sample_id:
            return (sample_id,)
        return (
            item.get("Task", ""),
            item.get("Method", ""),
            item.get("Model", ""),
            str(item.get("Index", "")),
            item.get("Source CSV", ""),
        )

    def result_key(self, item):
        sample_id = item.get("Sample ID", "")
        if sample_id:
            return (sample_id,)
        return (
            item.get("Task", ""),
            item.get("Method", ""),
            item.get("Model", ""),
            str(item.get("Index", "")),
            item.get("Source CSV", ""),
        )

    def set_label(self, value):
        self.label_var.set(value)
        self.update_colors()

    def update_colors(self):
        selected = self.label_var.get()
        for label in self.choice_labels:
            label.config(fg="#d00000" if label.cget("text") == selected else "black")
            label.config(relief="sunken" if label.cget("text") == selected else "flat")

    def show_feedback(self, msg):
        self.feedback_label.config(text=msg)
        self.feedback_label.place(relx=0.95, rely=0.95, anchor="se")
        self.root.after(1200, self.feedback_label.place_forget)

    def save_score(self):
        label = self.label_var.get()
        if label not in {"Preserved", "Changed", "Unclear"}:
            self.show_feedback("Please choose Preserved, Changed, or Unclear before saving")
            return False

        item = self.data[self.index]
        record = {
            "Sample ID": item.get("Sample ID", ""),
            "Index": item.get("Index", ""),
            "Model": item.get("Model", ""),
            "Task": item.get("Task", ""),
            "Method": item.get("Method", ""),
            "Language": item.get("Language", ""),
            "Source CSV": item.get("Source CSV", ""),
            "Blind": item.get("Blind", False),
            "label": label,
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
        if messagebox.askyesno("Evaluation Completed", "You reached the last sample.\nDo you want to finish now?"):
            self.check_completion()

    def prev_code(self):
        if self.index > 0:
            self.index -= 1
            self.show_code()
        else:
            self.show_feedback("First sample reached")

    def check_completion(self):
        missing = [self.item_key(item) for item in self.data if self.result_index_by_key.get(self.item_key(item)) is None]
        if missing:
            messagebox.showwarning("Incomplete", f"You have not rated all samples.\nMissing: {len(missing)}")
            return False
        messagebox.showinfo("Completed", "All samples are rated.")
        self.root.destroy()
        return True

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

        self.progress_label.config(text=f"Sample {self.index + 1} / {len(self.data)}")
        if item.get("Blind", False):
            self.meta_label.config(
                text=(
                    f"{item.get('Task Name', item.get('Task', ''))} | "
                    f"{language} | {item.get('Sample ID', '')}"
                )
            )
        else:
            fallback = item.get("Fallback Source Method", "")
            fallback_text = f" | fallback: {fallback}" if fallback else ""
            self.meta_label.config(
                text=(
                    f"{item.get('Task Name', item.get('Task', ''))} | {item.get('Method', '')}{fallback_text} | "
                    f"{item.get('Model', '')} | Index {item.get('Index', '')} | {language} | "
                    f"{item.get('Source CSV', '')}"
                )
            )
        self.root.title(f"Code Evaluation - {self.index + 1}/{len(self.data)} - User: {self.username}")
        self.label_var.set("")
        existing = self.result_index_by_key.get(self.item_key(item))
        if existing is not None:
            self.label_var.set(self.results[existing].get("label", ""))
        self.update_colors()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="sample JSON file")
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
