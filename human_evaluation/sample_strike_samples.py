#!/usr/bin/env python3
import argparse
import csv
import sys

csv.field_size_limit(sys.maxsize)
import json
import random
from pathlib import Path


def is_success(row):
    value = str(row.get("Type", "")).strip()
    return value not in {"", "0", "None", "none", "[]"}


def infer_task(path: Path) -> str:
    text = str(path)
    if "CloneDetection" in text:
        return "Clone"
    if "Vulnerability" in text or "VulnerabilityDdetection" in text:
        return "Vulnerability"
    if "CodeSummarization" in text:
        return "Summarization"
    return path.stem


def main():
    parser = argparse.ArgumentParser(description="Sample successful STRIKE rows for three-label human annotation.")
    parser.add_argument("csv_paths", nargs="+", help="STRIKE result CSV files")
    parser.add_argument("--n", type=int, default=50, help="Samples per input CSV")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="human_evaluation/selected_samples.json")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    output = []
    for csv_name in args.csv_paths:
        csv_path = Path(csv_name)
        with csv_path.open(newline="", encoding="utf-8", errors="replace") as handle:
            rows = [row for row in csv.DictReader(handle) if is_success(row)]
        if len(rows) > args.n:
            rows = rng.sample(rows, args.n)
        task = infer_task(csv_path)
        for row in rows:
            output.append({
                "Index": row.get("Index", ""),
                "Model": csv_path.parts[0] if csv_path.parts else "",
                "Task": task,
                "Method": "strike",
                "Original": row.get("Original Code", ""),
                "Adversarial": row.get("Adversarial Code", ""),
                "Original Label": row.get("Original Label", ""),
                "Code2": row.get("Code2", ""),
                "Gold Summary": row.get("Gold Summary", ""),
            })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)
    print(f"wrote {len(output)} samples to {out}")


if __name__ == "__main__":
    main()
