# Re-eval Human Evaluation Package

This repository contains two 200-sample human evaluation sets and a local GUI
for judging whether adversarial code preserves syntax/semantics relative to the
original code.

## Contents

```text
human_evaluation/
  eval_attack_successes.py
  requirement.txt

  sample_attack_successes.py
  selected_attack_successes.json
  selected_attack_successes_summary.csv

  sample_semantic_valid_blind.py
  selected_semantic_valid_blind_samples.json
  selected_semantic_valid_blind_key.csv
  selected_semantic_valid_blind_summary.csv

  ATTACK_SUCCESS_REVIEW.md
```

## Set 1: Successful Attack Samples

File for annotation:

```text
human_evaluation/selected_attack_successes.json
```

This set has 200 examples: 10 examples for each applicable task-method cell
from the study setup table. Models are pooled rather than sampled separately.

`CS-MHM` had empty source CSVs in the local workspace, so its 10 examples are
filled from poorer successful CS attacks. Those rows are marked in the JSON with
`Fallback Source Method` and `Sampling Note`.

Run:

```bash
python human_evaluation/eval_attack_successes.py \
  --data human_evaluation/selected_attack_successes.json
```

## Set 2: Blind Syntax+Semantic-Pass Samples

File for annotation:

```text
human_evaluation/selected_semantic_valid_blind_samples.json
```

This set also has 200 examples: 10 examples for each applicable task-method
cell, sampled from rows that passed stored syntax and semantic audits.

Annotators should only receive:

```text
human_evaluation/selected_semantic_valid_blind_samples.json
```

Do not give annotators this private mapping file:

```text
human_evaluation/selected_semantic_valid_blind_key.csv
```

The blind JSON intentionally omits method, model, source CSV, and original index
fields. The key file restores those fields for later analysis.

Run:

```bash
python human_evaluation/eval_attack_successes.py \
  --data human_evaluation/selected_semantic_valid_blind_samples.json
```

## Install

The GUI uses Tkinter and Pygments.

```bash
pip install -r human_evaluation/requirement.txt
```

On some Linux systems Tkinter is installed through the system package manager
rather than pip.

## Output

The GUI asks for a username and writes:

```text
<username>_<sample_file_stem>_results.json
```

For example:

```text
alice_selected_semantic_valid_blind_samples_results.json
```

Labels are:

- `Preserved`
- `Changed`
- `Unclear`

## Regenerating Samples

The sampler scripts expect the original STRIKE workspace and result CSVs to be
present. They are included here for reproducibility of the sampling procedure,
but the checked-in JSON/CSV sample files are ready to annotate directly.

Successful attack set:

```bash
python -B human_evaluation/sample_attack_successes.py \
  --include-archive \
  --out human_evaluation/selected_attack_successes.json \
  --summary-out human_evaluation/selected_attack_successes_summary.csv
```

Blind syntax+semantic-pass set:

```bash
python -B human_evaluation/sample_semantic_valid_blind.py \
  --include-archive \
  --out human_evaluation/selected_semantic_valid_blind_samples.json \
  --key-out human_evaluation/selected_semantic_valid_blind_key.csv \
  --summary-out human_evaluation/selected_semantic_valid_blind_summary.csv
```
