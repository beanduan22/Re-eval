#!/usr/bin/env python3
"""Build the combined blind annotation set for the behavior-change protocol.

Two pools, mixed and shuffled into one blind presentation:

* Pool A (motivation): originally-successful rows, 20 applicable Task x Method
  cells x ``--n`` each, models pooled and shuffled within a cell.
* Pool B (validation): syntax+semantic-valid survivors, the same 20 cells x
  ``--n`` each; short cells are filled with same-task valid fallback rows.

With the default ``--n 5`` that is 100 + 100 = 200 samples.

The public JSON hides pool, method, model, source, and the auto-validator
verdict. The private key CSV preserves all of it for later analysis (Cohen's
kappa, per-pool numbers, RQ4 failure modes).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANNOTATOR_KIT = HERE / "annotator_kit"

ANNOTATOR_README = """# Behavior-change annotation

Thanks for annotating. You only need this folder.

## Install

```bash
pip install -r requirement.txt
```

## Annotate

```bash
python annotate.py
```

Enter your name, then for each of the 200 samples answer
**"Does this change alter the behavior of the original code?"**:

- **Unchanged (valid)** — behavior preserved.
- **Changed (invalid)** — behavior changed; then pick one failure mode.
- **Cannot determine** — cannot confidently judge.

A soft 10-minute per-sample timer nudges toward *Cannot determine* when it runs out. An
optional note is recorded per sample. Your progress is saved continuously to
`<yourname>_blind_samples_results.json`.

## Send back

When done, send back the single file `<yourname>_blind_samples_results.json`.
"""

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sample_attack_successes as A  # noqa: E402
import sample_semantic_valid_blind as B  # noqa: E402
from protocol import POOL_A, POOL_B  # noqa: E402

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))


def cell_iter():
    for task in A.TASKS:
        for method in A.METHODS:
            if method in A.APPLICABLE[task]:
                yield task, method


def build_pool_a(csvs, n: int, rng: random.Random):
    """Originally-successful rows. Returns (records, short_cells)."""
    records = []
    short = []
    for task, method in cell_iter():
        candidates, _ = A.collect_candidates(csvs, task, method)
        candidates = A.dedupe_candidates(candidates)
        if len(candidates) >= n:
            chosen = rng.sample(candidates, n)  # pooled across models => shuffled
        elif task == "cs" and method == "mhm":
            chosen = A.choose_even_fallback(csvs, task, n, rng)
        else:
            chosen = candidates
        if len(chosen) < n:
            short.append(f"{A.TASK_LABEL[task]}-{A.METHOD_LABEL[method]}: {len(chosen)}/{n}")
        for model, path, row in chosen:
            records.append({
                "pool": POOL_A,
                "validator": "successful",
                "task": task,
                "method": method,
                "model": model,
                "path": path,
                "row": row,
            })
    return records, short


def build_pool_b(csvs, valid_keys, n: int, rng: random.Random):
    """Syntax+semantic-valid survivors. Returns (records, short_cells)."""
    records = []
    short = []
    for task, method in cell_iter():
        candidates, _ = B.collect_valid_candidates(csvs, task, method, valid_keys)
        candidates = A.dedupe_candidates(candidates)
        if len(candidates) >= n:
            chosen = B.choose_even(candidates, n, rng)
        elif task == "cs" and method == "mhm":
            chosen = B.choose_valid_fallback(csvs, task, n, rng, valid_keys)
        else:
            chosen = B.choose_even(candidates, n, rng)
            if len(chosen) < n:
                supplement = B.choose_task_fallback(csvs, task, method, n, rng, valid_keys)
                used = {_dedup_key(m, r) for m, _p, r in chosen}
                for m, p, r in supplement:
                    if _dedup_key(m, r) in used:
                        continue
                    chosen.append((m, p, r))
                    used.add(_dedup_key(m, r))
                    if len(chosen) >= n:
                        break
        if len(chosen) < n:
            short.append(f"{A.TASK_LABEL[task]}-{A.METHOD_LABEL[method]}: {len(chosen)}/{n}")
        for model, path, row in chosen:
            records.append({
                "pool": POOL_B,
                "validator": "semantic_valid",
                "task": task,
                "method": method,
                "model": model,
                "path": path,
                "row": row,
            })
    return records, short


def _dedup_key(model, row):
    return (model, row.get("Index", ""), row.get("Original Code", ""), row.get("Adversarial Code", ""))


def public_sample(sample_id: str, rec: dict) -> dict:
    task = rec["task"]
    row = rec["row"]
    return {
        "Sample ID": sample_id,
        "Task": A.TASK_LABEL[task],
        "Task Name": A.TASK_NAME[task],
        "Language": A.TASK_LANGUAGE[task],
        "Original": row.get("Original Code", ""),
        "Adversarial": row.get("Adversarial Code", ""),
        "Blind": True,
    }


def key_row(sample_id: str, rec: dict) -> dict:
    task, method, model, row = rec["task"], rec["method"], rec["model"], rec["row"]
    return {
        "Sample ID": sample_id,
        "Pool": rec["pool"],
        "Validator": rec["validator"],
        "Task": A.TASK_LABEL[task],
        "Method": A.METHOD_LABEL[method],
        "Method Key": method,
        "Model": A.MODEL_LABEL[model],
        "Index": row.get("Index", ""),
        "Source CSV": A.rel(rec["path"]),
        "Type": row.get("Type", ""),
        "Fallback Source Method": row.get("_fallback_source_method", ""),
        "Sampling Note": row.get("_sampling_note", ""),
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=5, help="samples per cell per pool (20 cells => 20*n per pool)")
    parser.add_argument("--seed", type=int, default=20260611)
    parser.add_argument("--include-archive", action="store_true")
    parser.add_argument("--out", default="human_evaluation/annotator_kit/blind_samples.json",
                        help="blind sample JSON; goes in the annotator kit (public)")
    parser.add_argument("--key-out", default="human_evaluation/blind_key.csv",
                        help="private key CSV; keep this away from annotators")
    parser.add_argument("--summary-out", default="human_evaluation/blind_summary.csv",
                        help="private per-cell summary CSV")
    parser.add_argument("--allow-short", action="store_true", help="write output even if some cells are short")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    csvs = A.discover_csvs(include_archive=args.include_archive)
    valid_keys = B.load_valid_audit_keys()

    pool_a, short_a = build_pool_a(csvs, args.n, rng)
    pool_b, short_b = build_pool_b(csvs, valid_keys, args.n, rng)

    short = [f"[A] {item}" for item in short_a] + [f"[B] {item}" for item in short_b]
    if short and not args.allow_short:
        print("not enough rows for all cells (use --include-archive or --allow-short):", file=sys.stderr)
        for item in short:
            print(f"  {item}", file=sys.stderr)
        return 2

    records = pool_a + pool_b
    rng.shuffle(records)

    public, key = [], []
    for i, rec in enumerate(records, start=1):
        sample_id = f"H{i:04d}"
        public.append(public_sample(sample_id, rec))
        key.append(key_row(sample_id, rec))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(public, indent=2, ensure_ascii=False), encoding="utf-8")

    write_csv(Path(args.key_out), key, [
        "Sample ID", "Pool", "Validator", "Task", "Method", "Method Key",
        "Model", "Index", "Source CSV", "Type", "Fallback Source Method", "Sampling Note",
    ])

    # Per-cell summary across both pools.
    summary = {}
    for rec in records:
        cell = (rec["pool"], A.TASK_LABEL[rec["task"]], A.METHOD_LABEL[rec["method"]])
        summary[cell] = summary.get(cell, 0) + 1
    summary_rows = [
        {"pool": pool, "task": task, "method": method, "sampled": count}
        for (pool, task, method), count in sorted(summary.items())
    ]
    write_csv(Path(args.summary_out), summary_rows, ["pool", "task", "method", "sampled"])

    # Refresh the self-contained annotator kit when the blind set lands in it.
    if out.resolve().parent == ANNOTATOR_KIT:
        for name in ("protocol.py", "requirement.txt"):
            src = HERE / name
            if src.exists():
                shutil.copy2(src, ANNOTATOR_KIT / name)
        (ANNOTATOR_KIT / "README.md").write_text(ANNOTATOR_README, encoding="utf-8")

    n_a = sum(1 for r in records if r["pool"] == POOL_A)
    n_b = sum(1 for r in records if r["pool"] == POOL_B)
    print(f"wrote {len(public)} blind samples (Pool A={n_a}, Pool B={n_b}) to {out}")
    print(f"  -> hand the folder '{out.parent}' to annotators")
    print(f"wrote PRIVATE key to {args.key_out} (do NOT share)")
    print(f"wrote PRIVATE summary to {args.summary_out}")
    if short:
        print("WARNING: short cells (written anyway due to --allow-short):", file=sys.stderr)
        for item in short:
            print(f"  {item}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
