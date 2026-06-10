# Attack Success Human Evaluation

This workflow samples successful baseline attack outputs for local semantic-preservation review.

## Sample

Strict 200-sample target, using archived CSVs as fallbacks:

```bash
python -B human_evaluation/sample_attack_successes.py \
  --include-archive \
  --out human_evaluation/selected_attack_successes.json \
  --summary-out human_evaluation/selected_attack_successes_summary.csv
```

The target is 10 successful examples for each applicable `Task x Method` cell in the setup table, with CodeBERT/CodeGPT/CodeT5 pooled together.

As of the current workspace, `CS-MHM` has no recoverable successful rows because these files are empty:

- `evaluation/result/cs_mhm_carrot_20260608_AEST/codebert_cs_mhm_20260608_AEST.csv`
- `evaluation/result/cs_mhm_carrot_20260608_AEST/codegpt_cs_mhm_20260608_AEST.csv`
- `evaluation/result/cs_mhm_carrot_20260608_AEST/codet5_cs_mhm_20260608_AEST.csv`

The sampler therefore fills the 10 `CS-MHM` examples from poorer successful CS CARROT/ALERT/BeamAttack rows, split as evenly as possible across models. These rows are marked with `Fallback Source Method` and `Sampling Note` in the JSON, and the summary marks the cell as `fallback`.

If you want to disable this behavior and inspect short cells, use `--allow-short` only after editing the script to remove the `CS-MHM` fallback branch.

## Run GUI

```bash
python human_evaluation/eval_attack_successes.py \
  --data human_evaluation/selected_attack_successes.json
```

The GUI saves annotations to `<username>_selected_attack_successes_results.json`.

## Blind Syntax+Semantic-Pass Sample

Generate the blind 200-sample set from rows that passed the stored syntax and semantic audits:

```bash
python -B human_evaluation/sample_semantic_valid_blind.py \
  --include-archive \
  --out human_evaluation/selected_semantic_valid_blind_samples.json \
  --key-out human_evaluation/selected_semantic_valid_blind_key.csv \
  --summary-out human_evaluation/selected_semantic_valid_blind_summary.csv
```

Give annotators only `selected_semantic_valid_blind_samples.json`. It contains no method, model, source CSV, or original index fields. Keep `selected_semantic_valid_blind_key.csv` private for later analysis.

Run the GUI on the blind sample:

```bash
python human_evaluation/eval_attack_successes.py \
  --data human_evaluation/selected_semantic_valid_blind_samples.json
```

Some target cells lack enough retrievable rows for their own method after filtering by syntax+semantic pass. The sampler fills those from same-task syntax+semantic-valid fallback rows and records this only in the private key and summary.
