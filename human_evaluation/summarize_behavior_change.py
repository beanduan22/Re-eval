#!/usr/bin/env python3
"""Summarize the blind behavior-change annotations.

Joins two (or more) annotator result files against the private key, then reports:

* Inter-annotator agreement and Cohen's kappa on the 3-class verdict.
* Arbitrated final verdict (agreement, else the arbiter's call).
* Pool A (motivation) numbers: among originally-successful samples, how many
  humans judge the behavior actually changed.
* Pool B (validation) numbers: among semantic-valid survivors, how many humans
  agree the behavior is preserved (and how that compares to the auto-validator).
* RQ4: failure-mode distribution among final-invalid samples, by task and method.

No third-party stats dependency; Cohen's kappa is computed directly.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from protocol import POOL_A, POOL_B, VERDICTS, FAILURE_MODE_LABEL

VERDICT_SHORT = {"valid": "valid", "invalid": "invalid", "cannot_determine": "cannot-det"}


def load_results(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {row.get("Sample ID", ""): row for row in data if row.get("Sample ID")}


def load_key(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["Sample ID"]: row for row in csv.DictReader(handle)}


def cohens_kappa(pairs: list[tuple[str, str]]) -> tuple[float, float]:
    """Return (observed_agreement, kappa) for paired categorical labels."""
    n = len(pairs)
    if n == 0:
        return 0.0, 0.0
    po = sum(1 for a, b in pairs if a == b) / n
    a_counts = Counter(a for a, _ in pairs)
    b_counts = Counter(b for _, b in pairs)
    pe = sum((a_counts.get(c, 0) / n) * (b_counts.get(c, 0) / n) for c in VERDICTS)
    kappa = 0.0 if pe >= 1.0 else (po - pe) / (1 - pe)
    return po, kappa


def final_verdict(verdicts: list[str], arbiter: str | None) -> str:
    present = [v for v in verdicts if v in VERDICTS]
    if present and all(v == present[0] for v in present):
        return present[0]
    if arbiter in VERDICTS:
        return arbiter
    return "disagree"


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def pct(num, den):
    return "0.0%" if den == 0 else f"{100 * num / den:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("annotators", nargs="+", help="annotator result JSON files (2 or more)")
    parser.add_argument("--key", default="human_evaluation/blind_key.csv", help="private key CSV")
    parser.add_argument("--arbiter", help="third-person arbitration result JSON (optional)")
    args = parser.parse_args()

    key = load_key(Path(args.key))
    annotators = [load_results(Path(p)) for p in args.annotators]
    annotator_names = [Path(p).stem for p in args.annotators]
    arbiter = load_results(Path(args.arbiter)) if args.arbiter else {}

    print(f"# Behavior-change annotation summary\n")
    print(f"Key samples: {len(key)} | annotators: {', '.join(annotator_names)}"
          + (f" | arbiter: {Path(args.arbiter).stem}" if args.arbiter else "") + "\n")

    # ---- inter-annotator agreement / Cohen's kappa --------------------------
    print("## Inter-annotator agreement (Cohen's kappa)\n")
    rows = []
    for (i, j) in combinations(range(len(annotators)), 2):
        common = sorted(set(annotators[i]) & set(annotators[j]) & set(key))
        pairs = [(annotators[i][s]["verdict"], annotators[j][s]["verdict"])
                 for s in common
                 if annotators[i][s].get("verdict") in VERDICTS and annotators[j][s].get("verdict") in VERDICTS]
        po, kappa = cohens_kappa(pairs)
        rows.append([f"{annotator_names[i]} vs {annotator_names[j]}", len(pairs), pct(int(po * len(pairs)), len(pairs)), f"{kappa:.3f}"])
    print(md_table(["Pair", "N", "Observed agreement", "Cohen's kappa"], rows) + "\n")

    # ---- arbitrated final verdict per sample --------------------------------
    final = {}
    for sample_id in key:
        verdicts = [a[sample_id]["verdict"] for a in annotators if sample_id in a and a[sample_id].get("verdict") in VERDICTS]
        arb = arbiter.get(sample_id, {}).get("verdict")
        if verdicts:
            final[sample_id] = final_verdict(verdicts, arb)

    # ---- per-pool numbers ----------------------------------------------------
    print("## Per-pool final verdicts\n")
    pool_stats = {POOL_A: Counter(), POOL_B: Counter()}
    for sample_id, verdict in final.items():
        pool = key[sample_id]["Pool"]
        pool_stats.setdefault(pool, Counter())[verdict] += 1

    rows = []
    pool_titles = {POOL_A: "A (motivation: originally successful)", POOL_B: "B (validation: semantic-valid)"}
    for pool in (POOL_A, POOL_B):
        c = pool_stats[pool]
        total = sum(c.values())
        rows.append([
            pool_titles[pool], total,
            f'{c.get("valid", 0)} ({pct(c.get("valid", 0), total)})',
            f'{c.get("invalid", 0)} ({pct(c.get("invalid", 0), total)})',
            f'{c.get("cannot_determine", 0)} ({pct(c.get("cannot_determine", 0), total)})',
            c.get("disagree", 0),
        ])
    print(md_table(["Pool", "N", "valid (behavior preserved)", "invalid (behavior changed)", "cannot-determine", "unresolved"], rows))
    print()
    print("> Pool A reading: `invalid` share = how many *reported-successful* attacks actually broke behavior (motivation).")
    print("> Pool B reading: `valid` share = how often humans confirm the auto semantic-validator's surviving examples (validation).\n")

    # ---- RQ4 failure modes among final-invalid samples ----------------------
    print("## RQ4: failure modes among final-invalid samples\n")

    def pick_failure_mode(sample_id):
        if sample_id in arbiter and arbiter[sample_id].get("verdict") == "invalid" and arbiter[sample_id].get("failure_mode"):
            return arbiter[sample_id]["failure_mode"]
        for a in annotators:
            row = a.get(sample_id)
            if row and row.get("verdict") == "invalid" and row.get("failure_mode"):
                return row["failure_mode"]
        return ""

    overall = Counter()
    by_task = defaultdict(Counter)
    by_method = defaultdict(Counter)
    for sample_id, verdict in final.items():
        if verdict != "invalid":
            continue
        mode = pick_failure_mode(sample_id) or "(untagged)"
        overall[mode] += 1
        by_task[key[sample_id]["Task"]][mode] += 1
        by_method[key[sample_id]["Method"]][mode] += 1

    total_invalid = sum(overall.values())
    rows = [[FAILURE_MODE_LABEL.get(mode, mode), count, pct(count, total_invalid)]
            for mode, count in overall.most_common()]
    print(md_table(["Failure mode", "Count", "Share of invalid"], rows) if rows else "_No final-invalid samples._")
    print()

    if by_method:
        modes = [m for m, _ in overall.most_common()]
        headers = ["Method"] + [FAILURE_MODE_LABEL.get(m, m).split(" (")[0] for m in modes] + ["Total"]
        rows = []
        for method in sorted(by_method):
            counts = by_method[method]
            rows.append([method] + [counts.get(m, 0) for m in modes] + [sum(counts.values())])
        print("### By method\n")
        print(md_table(headers, rows) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
