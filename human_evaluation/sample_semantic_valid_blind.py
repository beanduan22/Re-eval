#!/usr/bin/env python3
"""Sample syntax+semantic-valid attack examples for blind human review.

The public JSON intentionally hides method/model/source metadata. The private
key CSV preserves that mapping for later analysis.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sample_attack_successes import (  # noqa: E402
    APPLICABLE,
    METHOD_LABEL,
    METHODS,
    MODEL_LABEL,
    MODELS,
    TASK_LABEL,
    TASK_LANGUAGE,
    TASK_NAME,
    TASKS,
    collect_candidates,
    dedupe_candidates,
    discover_csvs,
    read_rows,
    rel,
)

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))


def truth(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "pass", "passed"}


def norm_task(value: str) -> str:
    text = str(value or "").lower().replace(" ", "").replace("-", "").replace("_", "")
    if "pythonaa" in text or "authorship" in text or "gcj" in text or text == "aa":
        return "aa"
    if "codesummarization" in text or "summarization" in text or text == "cs":
        return "cs"
    if "vulnerability" in text or text == "vd":
        return "vd"
    if "clonedetection" in text or "clone" in text or text == "cd":
        return "cd"
    return ""


def norm_method(value: str) -> str:
    text = str(value or "").lower()
    if "mhm" in text:
        return "mhm"
    if "carrot" in text:
        return "carrot"
    if "alert" in text or "greedy" in text:
        return "alert"
    if "beam" in text:
        return "beam"
    if "coda" in text or "ident" in text or "struct" in text:
        return "coda"
    if "itgen" in text:
        return "itgen"
    return ""


def norm_model(value: str) -> str:
    text = str(value or "").lower()
    for model in MODELS:
        if model in text:
            return model
    return ""


def audit_passes(row: dict[str, str]) -> bool:
    syntax = truth(row.get("syntax_valid")) or truth(row.get("syntax_pass"))
    semantic = (
        truth(row.get("auto_semantic_pass"))
        or truth(row.get("semantic_audit_pass"))
        or truth(row.get("semantic_pass"))
    )
    return syntax and semantic


def load_valid_audit_keys() -> dict[tuple[str, str, str, str], dict[str, str]]:
    valid = {}
    patterns = [
        "evaluation/result/**/*semantic*detail*.csv",
        "evaluation/result/**/*semantic*validation*detail*.csv",
    ]
    for pattern in patterns:
        for name in glob.glob(pattern, recursive=True):
            path = Path(name)
            with path.open(newline="", encoding="utf-8", errors="replace") as handle:
                for row in csv.DictReader(handle):
                    if not audit_passes(row):
                        continue
                    task = norm_task(row.get("Task") or row.get("task") or str(path))
                    method = norm_method(row.get("Method") or row.get("attack") or row.get("Type"))
                    model = norm_model(row.get("Model") or row.get("model") or row.get("Source CSV"))
                    index = str(row.get("Index") or row.get("index") or "").strip()
                    if task and method and model and index:
                        valid[(task, method, model, index)] = row
    return valid


def read_valid_rows(path: Path, task: str, method: str, model: str, valid_keys) -> list[dict[str, str]]:
    rows = []
    for row in read_rows(path):
        key = (task, method, model, str(row.get("Index", "")).strip())
        if key not in valid_keys:
            continue
        audit = valid_keys[key]
        row = dict(row)
        row["_audit_syntax_valid"] = "true"
        row["_audit_auto_semantic_pass"] = "true"
        row["_audit_source"] = audit.get("Source CSV", "") or audit.get("source_version", "")
        rows.append(row)
    return rows


def collect_valid_candidates(csvs, task: str, method: str, valid_keys):
    candidates = []
    summary = []
    for model in MODELS:
        paths = csvs.get((task, method, model), [])
        model_count = 0
        for path in paths:
            rows = read_valid_rows(path, task, method, model, valid_keys)
            model_count += len(rows)
            for row in rows:
                candidates.append((model, path, row))
        summary.append({
            "task": TASK_LABEL[task],
            "method": METHOD_LABEL[method],
            "model": MODEL_LABEL[model],
            "valid_candidate_rows": model_count,
            "csvs": ";".join(rel(p) for p in paths[:5]),
        })
    return candidates, summary


def choose_even(candidates, n: int, rng: random.Random):
    by_model = {model: [] for model in MODELS}
    for model, path, row in candidates:
        by_model.setdefault(model, []).append((model, path, row))
    for rows in by_model.values():
        rng.shuffle(rows)

    quotas = {model: n // len(MODELS) for model in MODELS}
    for model in MODELS[: n % len(MODELS)]:
        quotas[model] += 1

    chosen = []
    for model in MODELS:
        chosen.extend(by_model.get(model, [])[: min(quotas[model], len(by_model.get(model, [])))])

    if len(chosen) < n:
        used = {(m, r.get("Index", ""), r.get("Original Code", ""), r.get("Adversarial Code", "")) for m, _p, r in chosen}
        rest = []
        for model in MODELS:
            for item in by_model.get(model, []):
                key = (item[0], item[2].get("Index", ""), item[2].get("Original Code", ""), item[2].get("Adversarial Code", ""))
                if key not in used:
                    rest.append(item)
        rng.shuffle(rest)
        chosen.extend(rest[: n - len(chosen)])
    rng.shuffle(chosen)
    return chosen[:n]


def choose_valid_fallback(csvs, task: str, n: int, rng: random.Random, valid_keys):
    source_methods = ["carrot", "alert", "beam"]
    pool = []
    for model in MODELS:
        for source_method in source_methods:
            for path in csvs.get((task, source_method, model), []):
                for row in read_valid_rows(path, task, source_method, model, valid_keys):
                    row = dict(row)
                    row["_fallback_source_method"] = METHOD_LABEL[source_method]
                    row["_sampling_note"] = "blind CS-MHM fallback from syntax+semantic-valid CS rows"
                    pool.append((model, path, row))
    pool = dedupe_candidates(pool)
    return choose_even(pool, n, rng)


def choose_task_fallback(csvs, task: str, target_method: str, n: int, rng: random.Random, valid_keys):
    source_methods = [method for method in METHODS if method in APPLICABLE[task] and method != target_method]
    pool = []
    for model in MODELS:
        for source_method in source_methods:
            for path in csvs.get((task, source_method, model), []):
                for row in read_valid_rows(path, task, source_method, model, valid_keys):
                    row = dict(row)
                    row["_fallback_source_method"] = METHOD_LABEL[source_method]
                    row["_sampling_note"] = f"blind {TASK_LABEL[task]}-{METHOD_LABEL[target_method]} fallback from syntax+semantic-valid {TASK_LABEL[task]} rows"
                    pool.append((model, path, row))
    pool = dedupe_candidates(pool)
    return choose_even(pool, n, rng)


def blind_sample(sample_id: str, task: str, row: dict[str, str]) -> dict[str, object]:
    return {
        "Sample ID": sample_id,
        "Task": TASK_LABEL[task],
        "Task Name": TASK_NAME[task],
        "Language": TASK_LANGUAGE[task],
        "Original": row.get("Original Code", ""),
        "Adversarial": row.get("Adversarial Code", ""),
        "Blind": True,
    }


def key_row(sample_id: str, task: str, method: str, model: str, path: Path, row: dict[str, str], status: str):
    return {
        "Sample ID": sample_id,
        "Task": TASK_LABEL[task],
        "Method": METHOD_LABEL[method],
        "Method Key": method,
        "Model": MODEL_LABEL[model],
        "Index": row.get("Index", ""),
        "Source CSV": rel(path),
        "Audit Source CSV": row.get("_audit_source", ""),
        "Type": row.get("Type", ""),
        "Fallback Source Method": row.get("_fallback_source_method", ""),
        "Sampling Status": status,
        "syntax_valid": row.get("_audit_syntax_valid", "true"),
        "auto_semantic_pass": row.get("_audit_auto_semantic_pass", "true"),
        "Replaced Identifiers": row.get("Replaced Identifiers", ""),
        "Query Times": row.get("Query Times", ""),
    }


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--include-archive", action="store_true")
    parser.add_argument("--out", default="human_evaluation/selected_semantic_valid_blind_samples.json")
    parser.add_argument("--key-out", default="human_evaluation/selected_semantic_valid_blind_key.csv")
    parser.add_argument("--summary-out", default="human_evaluation/selected_semantic_valid_blind_summary.csv")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    csvs = discover_csvs(include_archive=args.include_archive)
    valid_keys = load_valid_audit_keys()
    public_samples = []
    key_rows = []
    summary_rows = []
    sample_counter = 1
    missing = []

    for task in TASKS:
        for method in METHODS:
            if method not in APPLICABLE[task]:
                continue
            candidates, model_summary = collect_valid_candidates(csvs, task, method, valid_keys)
            candidates = dedupe_candidates(candidates)
            status = "ok"
            note = ""
            if len(candidates) >= args.n:
                chosen = choose_even(candidates, args.n, rng)
            elif task == "cs" and method == "mhm":
                chosen = choose_valid_fallback(csvs, task, args.n, rng, valid_keys)
                status = "fallback"
                note = "CS-MHM source CSVs empty; filled from syntax+semantic-valid CS CARROT/ALERT/BeamAttack rows"
            else:
                chosen = choose_even(candidates, args.n, rng)
                if len(chosen) < args.n:
                    supplement = choose_task_fallback(csvs, task, method, args.n, rng, valid_keys)
                    used = {(m, r.get("Index", ""), r.get("Original Code", ""), r.get("Adversarial Code", "")) for m, _p, r in chosen}
                    for item in supplement:
                        key = (item[0], item[2].get("Index", ""), item[2].get("Original Code", ""), item[2].get("Adversarial Code", ""))
                        if key in used:
                            continue
                        chosen.append(item)
                        used.add(key)
                        if len(chosen) >= args.n:
                            break
                status = "fallback" if len(chosen) >= args.n else "short"
                note = "filled from same-task syntax+semantic-valid fallback rows" if status == "fallback" else "not enough syntax+semantic-valid rows with retrievable code"
            if len(chosen) < args.n:
                missing.append(f"{TASK_LABEL[task]}-{METHOD_LABEL[method]}: {len(chosen)}/{args.n}")

            summary_rows.append({
                "task": TASK_LABEL[task],
                "method": METHOD_LABEL[method],
                "available": len(candidates),
                "sampled": len(chosen),
                "status": status,
                "note": note,
            })
            summary_rows.extend(model_summary)

            for model, path, row in chosen:
                sample_id = f"SV{sample_counter:04d}"
                sample_counter += 1
                public_samples.append(blind_sample(sample_id, task, row))
                key_rows.append(key_row(sample_id, task, method, model, path, row, status))

    summary_fields = ["task", "method", "available", "sampled", "status", "model", "valid_candidate_rows", "csvs", "note"]
    if missing:
        write_csv(Path(args.summary_out), summary_rows, summary_fields)
        print("not enough syntax+semantic-valid rows:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 2

    paired = list(zip(public_samples, key_rows))
    rng.shuffle(paired)
    public_samples = [sample for sample, _key in paired]
    key_rows = [key for _sample, key in paired]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(public_samples, indent=2, ensure_ascii=False), encoding="utf-8")

    write_csv(Path(args.key_out), key_rows, [
        "Sample ID",
        "Task",
        "Method",
        "Method Key",
        "Model",
        "Index",
        "Source CSV",
        "Audit Source CSV",
        "Type",
        "Fallback Source Method",
        "Sampling Status",
        "syntax_valid",
        "auto_semantic_pass",
        "Replaced Identifiers",
        "Query Times",
    ])
    write_csv(Path(args.summary_out), summary_rows, summary_fields)

    print(f"wrote {len(public_samples)} blind samples to {out}")
    print(f"wrote key to {args.key_out}")
    print(f"wrote summary to {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
