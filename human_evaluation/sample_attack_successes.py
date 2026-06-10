#!/usr/bin/env python3
"""Sample successful attack examples for human semantic-preservation review.

Default target: the 20 applicable Task x Method cells from the setup table,
10 successful examples per cell, models pooled together.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(min(sys.maxsize, 2_147_483_647))

REPO = Path(__file__).resolve().parent.parent

TASKS = ["cd", "vd", "aa", "cs"]
TASK_LABEL = {
    "cd": "CD",
    "vd": "VD",
    "aa": "AA",
    "cs": "CS",
}
TASK_NAME = {
    "cd": "Clone Detection",
    "vd": "Vulnerability Detection",
    "aa": "Authorship Attribution",
    "cs": "Code Summarization",
}
TASK_LANGUAGE = {
    "cd": "java",
    "vd": "c",
    "aa": "python",
    "cs": "java",
}
METHODS = ["mhm", "carrot", "alert", "beam", "coda", "itgen"]
METHOD_LABEL = {
    "mhm": "MHM",
    "carrot": "CARROT",
    "alert": "ALERT",
    "beam": "BeamAttack",
    "coda": "CODA",
    "itgen": "ITGen",
}
MODELS = ["codebert", "codegpt", "codet5"]
MODEL_LABEL = {
    "codebert": "CodeBERT",
    "codegpt": "CodeGPT",
    "codet5": "CodeT5",
}

APPLICABLE = {
    "cd": {"mhm", "carrot", "alert", "beam", "coda", "itgen"},
    "vd": {"mhm", "carrot", "alert", "coda"},
    "aa": {"mhm", "carrot", "alert", "beam", "coda", "itgen"},
    "cs": {"mhm", "carrot", "alert", "beam"},
}

METHOD_PAT = {m: re.compile(rf"(?<![a-z]){m}(?![a-z])", re.I) for m in METHODS}
MODEL_PAT = {m: re.compile(m, re.I) for m in MODELS}
SHARD_PAT = re.compile(r"_s\d+_l\d+")
DEFAULT_SKIP_PAT = re.compile(r"smoke|bleu_tmp|/logs?/|tmp|compile_|semantic_audit|matrix_status", re.I)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def classify_task(path: str) -> str | None:
    p = path.lower()
    name = p.rsplit("/", 1)[-1]

    # Prefer task abbreviations in result filenames for mixed directories such
    # as cd_vd_native_rerun; otherwise fall back to explicit task directories.
    if "python_aa" in name or re.search(r"(^|_)aa(_|$)", name):
        return "aa"
    if re.search(r"(^|_)cs(_|$)", name):
        return "cs"
    if re.search(r"(^|_)vd(_|$)", name):
        return "vd"
    if re.search(r"(^|_)cd(_|$)", name):
        return "cd"

    if "python_aa" in p or "authorship" in p:
        return "aa"
    if "codesummarization" in p:
        return "cs"
    if "vulnerability" in p or "vulnerabilityddetection" in p:
        return "vd"
    if "clonedetection" in p:
        return "cd"
    if "/vd/" in p:
        return "vd"
    if "/aa/" in p or "gcj" in p:
        return "aa"
    if "/cs/" in p:
        return "cs"
    if "/cd/" in p:
        return "cd"
    return None


def classify(path: Path) -> tuple[str, str, str] | None:
    text = str(path)
    task = classify_task(text)
    if task is None:
        return None
    model = next((m for m in MODELS if MODEL_PAT[m].search(text)), None)
    method = next((m for m in METHODS if METHOD_PAT[m].search(path.name)), None)
    if model is None or method is None:
        return None
    if method not in APPLICABLE.get(task, set()):
        return None
    return task, method, model


def is_success(row: dict[str, str]) -> bool:
    value = str(row.get("Type", "")).strip()
    return value not in {"", "0", "None", "none", "[]", "orig_mistake"}


def has_code(row: dict[str, str]) -> bool:
    return bool(row.get("Original Code", "").strip() and row.get("Adversarial Code", "").strip())


def score_path(path: Path, task: str) -> int:
    name = path.name.lower()
    full = str(path).lower()
    score = 0
    if "repro" in name:
        score += 1000
    if task == "aa" and "python_aa" in full:
        score += 800
    if "real_all" in name:
        score += 500
    if "parseable2106_full" in name:
        score += 400
    if "_all" in name or "full" in name or "parseable2106" in name:
        score += 250
    if "archive_before" in full:
        score -= 150
    if "adapted_attacks" in full and task != "aa":
        score -= 100
    if "_repl" in name:
        score -= 300
    if SHARD_PAT.search(name):
        score -= 500
    return score


def discover_csvs(include_archive: bool) -> dict[tuple[str, str, str], list[Path]]:
    roots = [REPO / "evaluation" / "result", REPO / "CodeBERT", REPO / "CodeGPT", REPO / "CodeT5"]
    buckets: dict[tuple[str, str, str], list[tuple[int, Path]]] = defaultdict(list)
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            if path in seen:
                continue
            seen.add(path)
            text = str(path)
            if DEFAULT_SKIP_PAT.search(text):
                continue
            if not include_archive and "archive_before" in text.lower():
                continue
            cell = classify(path)
            if cell is None:
                continue
            buckets[cell].append((score_path(path, cell[0]), path))
    return {
        cell: [path for _, path in sorted(items, key=lambda item: item[0], reverse=True)]
        for cell, items in buckets.items()
    }


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.stat().st_size:
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if is_success(row) and has_code(row)]


def collect_candidates(csvs: dict[tuple[str, str, str], list[Path]], task: str, method: str):
    candidates = []
    summary = []
    for model in MODELS:
        paths = csvs.get((task, method, model), [])
        model_count = 0
        for path in paths:
            rows = read_rows(path)
            if not rows:
                continue
            model_count += len(rows)
            for row in rows:
                candidates.append((model, path, row))
        summary.append({
            "task": TASK_LABEL[task],
            "method": METHOD_LABEL[method],
            "model": MODEL_LABEL[model],
            "candidate_rows": model_count,
            "csvs": ";".join(rel(p) for p in paths[:5]),
        })
    return candidates, summary


def make_sample(task: str, method: str, model: str, path: Path, row: dict[str, str]) -> dict[str, str]:
    fallback_source = row.get("_fallback_source_method", "")
    fallback_suffix = f"-fallback-{fallback_source}" if fallback_source else ""
    return {
        "Sample ID": f"{TASK_LABEL[task]}-{METHOD_LABEL[method]}-{MODEL_LABEL[model]}-{row.get('Index', '')}{fallback_suffix}",
        "Index": row.get("Index", ""),
        "Model": MODEL_LABEL[model],
        "Task": TASK_LABEL[task],
        "Task Name": TASK_NAME[task],
        "Method": METHOD_LABEL[method],
        "Method Key": method,
        "Language": TASK_LANGUAGE[task],
        "Source CSV": rel(path),
        "Original": row.get("Original Code", ""),
        "Adversarial": row.get("Adversarial Code", ""),
        "Type": row.get("Type", ""),
        "Original Label": row.get("Original Label", row.get("Ground Truth", "")),
        "Ground Truth": row.get("Ground Truth", ""),
        "Code2": row.get("Code2", ""),
        "Gold Summary": row.get("Gold Summary", ""),
        "Replaced Identifiers": row.get("Replaced Identifiers", ""),
        "Query Times": row.get("Query Times", ""),
        "Fallback Source Method": fallback_source,
        "Sampling Note": row.get("_sampling_note", ""),
    }


def replacement_count(row: dict[str, str]) -> int:
    replaced = str(row.get("Replaced Identifiers", "")).strip().strip(",")
    if not replaced:
        return 0
    return sum(1 for part in replaced.split(",") if part.strip())


def bleu_drop(row: dict[str, str]) -> float:
    try:
        return float(row.get("Original BLEU", 0) or 0) - float(row.get("Adversarial BLEU", 0) or 0)
    except ValueError:
        return 0.0


def poor_quality_key(item):
    _model, _path, row = item
    return (replacement_count(row), bleu_drop(row), len(row.get("Adversarial Code", "")))


def choose_even_fallback(csvs, task: str, target_n: int, rng: random.Random):
    if task != "cs":
        return []
    source_methods = ["carrot", "alert", "beam"]
    quotas = {model: target_n // len(MODELS) for model in MODELS}
    for model in MODELS[: target_n % len(MODELS)]:
        quotas[model] += 1

    chosen = []
    seen = set()
    for model in MODELS:
        by_method = {}
        for source_method in source_methods:
            rows = []
            for source_path in csvs.get((task, source_method, model), []):
                for row in read_rows(source_path):
                    row = dict(row)
                    row["_fallback_source_method"] = METHOD_LABEL[source_method]
                    row["_sampling_note"] = "CS-MHM fallback: sampled from poorer CS successful attacks because CS-MHM CSVs are empty"
                    rows.append((model, source_path, row))
            rows = dedupe_candidates(rows)
            rows.sort(key=poor_quality_key, reverse=True)
            by_method[source_method] = rows

        available_methods = [m for m in source_methods if by_method.get(m)]
        if not available_methods:
            continue
        cursor = {m: 0 for m in available_methods}
        for slot in range(quotas[model]):
            method_order = available_methods[slot % len(available_methods):] + available_methods[: slot % len(available_methods)]
            picked = None
            for source_method in method_order:
                rows = by_method[source_method]
                while cursor[source_method] < len(rows):
                    candidate = rows[cursor[source_method]]
                    cursor[source_method] += 1
                    key = (candidate[0], candidate[2].get("Index", ""), candidate[2].get("Original Code", ""), candidate[2].get("Adversarial Code", ""))
                    if key not in seen:
                        picked = candidate
                        seen.add(key)
                        break
                if picked is not None:
                    break
            if picked is not None:
                chosen.append(picked)

    if len(chosen) < target_n:
        pool = []
        for model in MODELS:
            for source_method in source_methods:
                for source_path in csvs.get((task, source_method, model), []):
                    for row in read_rows(source_path):
                        row = dict(row)
                        row["_fallback_source_method"] = METHOD_LABEL[source_method]
                        row["_sampling_note"] = "CS-MHM fallback: sampled from poorer CS successful attacks because CS-MHM CSVs are empty"
                        pool.append((model, source_path, row))
        pool = dedupe_candidates(pool)
        pool.sort(key=poor_quality_key, reverse=True)
        for candidate in pool:
            key = (candidate[0], candidate[2].get("Index", ""), candidate[2].get("Original Code", ""), candidate[2].get("Adversarial Code", ""))
            if key in seen:
                continue
            chosen.append(candidate)
            seen.add(key)
            if len(chosen) >= target_n:
                break

    rng.shuffle(chosen)
    return chosen[:target_n]


def dedupe_candidates(candidates):
    seen = set()
    out = []
    for model, path, row in candidates:
        key = (
            row.get("Index", ""),
            row.get("Original Code", ""),
            row.get("Adversarial Code", ""),
            model,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append((model, path, row))
    return out


def write_summary(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["task", "method", "available", "sampled", "status", "model", "candidate_rows", "csvs", "note"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=10, help="samples per applicable Task x Method cell")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="human_evaluation/selected_attack_successes.json")
    parser.add_argument("--summary-out", default="human_evaluation/selected_attack_successes_summary.csv")
    parser.add_argument("--include-archive", action="store_true", help="also use archived CSVs when current outputs are missing")
    parser.add_argument("--allow-short", action="store_true", help="write output even when some cells have fewer than --n candidates")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    csvs = discover_csvs(include_archive=args.include_archive)
    samples = []
    summary_rows: list[dict[str, object]] = []
    missing = []

    for task in TASKS:
        for method in METHODS:
            if method not in APPLICABLE[task]:
                continue
            candidates, model_summary = collect_candidates(csvs, task, method)
            candidates = dedupe_candidates(candidates)
            if len(candidates) >= args.n:
                chosen = rng.sample(candidates, args.n)
                status = "ok"
                note = ""
            elif task == "cs" and method == "mhm":
                chosen = choose_even_fallback(csvs, task, args.n, rng)
                status = "fallback" if len(chosen) >= args.n else "short"
                note = "filled from poorer CS CARROT/ALERT/BeamAttack samples; original CS-MHM CSVs are empty"
                if len(chosen) < args.n:
                    missing.append(f"{TASK_LABEL[task]}-{METHOD_LABEL[method]}: {len(chosen)}/{args.n}")
            else:
                chosen = candidates
                status = "short"
                note = ""
                missing.append(f"{TASK_LABEL[task]}-{METHOD_LABEL[method]}: {len(candidates)}/{args.n}")
            for model, path, row in chosen:
                samples.append(make_sample(task, method, model, path, row))
            summary_rows.append({
                "task": TASK_LABEL[task],
                "method": METHOD_LABEL[method],
                "available": len(candidates),
                "sampled": len(chosen),
                "status": status,
                "note": note,
            })
            summary_rows.extend(model_summary)

    if missing and not args.allow_short:
        write_summary(Path(args.summary_out), summary_rows)
        print("not enough successful rows for all cells:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        print(f"wrote summary to {args.summary_out}", file=sys.stderr)
        return 2

    rng.shuffle(samples)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(samples, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary(Path(args.summary_out), summary_rows)
    print(f"wrote {len(samples)} samples to {out}")
    print(f"wrote summary to {args.summary_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
