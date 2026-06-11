#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path

LABELS = ("Preserved", "Changed", "Unclear")
COLUMNS = ["Task", "Annotated", "Preserved", "Changed", "Unclear", "HSPR", "HSPR excl. unclear"]


def pct(num, den):
    return "0.000" if den == 0 else f"{num / den:.3f}"


def print_markdown(rows):
    print("| " + " | ".join(COLUMNS) + " |")
    print("| " + " | ".join(["---"] * len(COLUMNS)) + " |")
    for row in rows:
        print("| " + " | ".join(str(row[col]) for col in COLUMNS) + " |")


def main():
    parser = argparse.ArgumentParser(description="Summarize three-label STRIKE human preservation annotations.")
    parser.add_argument("result_json", help="Annotator JSON from human_evaluation/eval.py")
    parser.add_argument("--task-field", default="Task")
    args = parser.parse_args()

    with Path(args.result_json).open(encoding="utf-8") as handle:
        data = json.load(handle)

    stats = defaultdict(lambda: {label: 0 for label in LABELS})
    for item in data:
        task = item.get(args.task_field, "Unknown") or "Unknown"
        label = item.get("label", "")
        if label not in LABELS:
            continue
        stats[task][label] += 1

    rows = []
    for task, vals in sorted(stats.items()):
        preserved = vals["Preserved"]
        changed = vals["Changed"]
        unclear = vals["Unclear"]
        annotated = preserved + changed + unclear
        rows.append({
            "Task": task,
            "Annotated": annotated,
            "Preserved": preserved,
            "Changed": changed,
            "Unclear": unclear,
            "HSPR": pct(preserved, annotated),
            "HSPR excl. unclear": pct(preserved, preserved + changed),
        })

    print_markdown(rows)


if __name__ == "__main__":
    main()
