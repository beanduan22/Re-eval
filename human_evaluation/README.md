# Human Evaluation — blind behavior-change protocol

Two annotators independently and blindly judge, for each sampled attack output,
**whether the change alters the behavior of the original code**. Disagreements
go to a third-person arbiter; we report Cohen's κ.

## Two pools, mixed into one blind set

| Pool | Source | Size | Role |
| --- | --- | --- | --- |
| **A** | all *originally-successful* rows | 20 cells (method × task) × 5 = **100** | motivation numbers |
| **B** | *semantic-valid survivors* (passed syntax + semantic audit) | same 20 cells × 5 = **100**, short cells filled by same-task valid fallback | validation numbers |

The 20 cells are the applicable `method × task` combinations from the setup table
(CodeBERT/CodeGPT/CodeT5 pooled and shuffled within each cell). The two pools are
**mixed and shuffled into one 200-sample blind presentation**. Annotators never
see the pool, the attack method, the model, the source CSV, or the
auto-validator's verdict — only the task name and a neutral sample id.

## Folder split

```
human_evaluation/
├── annotator_kit/        ← hand THIS whole folder to annotators (self-contained)
│   ├── annotate.py           the blind GUI
│   ├── protocol.py           verdict + failure-mode definitions
│   ├── blind_samples.json    the 200 blind samples
│   ├── requirement.txt       pip deps (pygments)
│   └── README.md             annotator-facing instructions
│
├── build_combined_blind.py     (private) builds the set + packages the kit
├── summarize_behavior_change.py(private) arbiter analysis: κ + per-pool + RQ4
├── blind_key.csv               (PRIVATE) sample id → pool / method / model / validator
├── blind_summary.csv           (private) per-cell counts
└── protocol.py / sample_*.py   (private) source of truth + samplers
```

Annotators only ever see `annotator_kit/`. The key, samplers, and summarizer stay
with you (the arbiter).

## 1. Build the blind set + package the kit (arbiter)

```bash
python -B human_evaluation/build_combined_blind.py --include-archive
```

This writes `annotator_kit/blind_samples.json` (and refreshes `protocol.py`,
`requirement.txt`, `README.md` inside the kit), plus the **private**
`blind_key.csv` and `blind_summary.csv` in `human_evaluation/`.

Use `--n` to change samples-per-cell (default 5 ⇒ 100 per pool), `--seed` to
change the draw, and `--allow-short` to write even if some cells are underfilled.

## 2. Annotate (each annotator, from inside `annotator_kit/`)

```bash
cd human_evaluation/annotator_kit
pip install -r requirement.txt
python annotate.py
```

For every sample the GUI asks **“这个改动是否改变了原代码的行为?”** with one choice:

- **没改变 (valid)** — behavior preserved (a legitimate adversarial example).
- **改变了 (invalid)** — behavior changed. Reveals a single-select **failure-mode**
  tag (feeds RQ4): 语法损坏 / 绑定破坏 / 作用域冲突 / 块结构破坏 / 不安全插入 / 无法确认的改写.
- **无法确定 (cannot_determine)** — cannot confidently judge.

A soft **10-minute per-sample timer** nudges toward *无法确定* on expiry (it never
overwrites an existing choice). An optional free-text note is recorded per sample.

Output: `<username>_blind_samples_results.json`.

## 3. Summarize (Cohen's κ + arbitration + per-pool + RQ4)

```bash
python human_evaluation/summarize_behavior_change.py \
  alice_blind_samples_results.json bob_blind_samples_results.json \
  --key human_evaluation/blind_key.csv \
  --arbiter carol_blind_samples_results.json   # optional third-person arbitration
```

Reports:

- **Inter-annotator agreement + Cohen's κ** on the 3-class verdict.
- **Pool A** (motivation): `invalid` share = fraction of *reported-successful*
  attacks that actually broke behavior.
- **Pool B** (validation): `valid` share = how often humans confirm the auto
  semantic-validator's surviving examples.
- **RQ4**: failure-mode distribution among final-invalid samples, by method.

`protocol.py` is the single source of truth for verdict and failure-mode keys —
edit the taxonomy there and both the GUI and the summarizer pick it up.

---

### Legacy single-label protocol

The earlier 3-label (Preserved / Changed / Unclear) per-task flow still lives in
`eval.py`, `sample_strike_samples.py`, and `summarize_preservation_eval.py`. It is
superseded by the blind behavior-change protocol above.
