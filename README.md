# Re-eval — Human Evaluation Package

Two authors **independently and blindly** judge, for each sampled attack output,
**whether the change alters the behavior of the original code**. Disagreements go
to a third-person arbiter; we report Cohen's κ.

The samples come from two pools, mixed and shuffled into **one 200-sample blind
set**:

| Pool | Source | Size | Role |
| --- | --- | --- | --- |
| **A** | originally-successful attacks | 20 (method × task) cells × 5 = **100** | motivation numbers |
| **B** | semantic-valid survivors (passed syntax + semantic audit) | same 20 cells × 5 = **100** | validation numbers |

---

## If you are an annotator — start here

Download and extract [annotator_kit.zip](human_evaluation/annotator_kit.zip), or use
the folder [`human_evaluation/annotator_kit/`](human_evaluation/annotator_kit).
The ZIP includes an English README with setup and submission instructions.
Python 3.10+ with Tkinter is required; no models are needed.

```bash
cd human_evaluation/annotator_kit
python -m pip install -r requirement.txt   # Pygments; see the Tkinter note below
python annotate.py
```

Enter your assigned annotator ID. Compare the original and modified code and
answer: **Is the modified code valid and behavior-preserving?**

- **Valid and behavior-preserving**
- **Validity or behavior violation** — select one demonstrated failure mode
  (syntax error, broken binding, scope conflict, broken block structure,
  unsafe insertion, or behavior change).
- **Cannot determine** — insufficient evidence for a clear judgment.

The English GUI includes full diff highlighting, optional notes, saved progress,
and a 10-minute reminder that never selects an answer. Click **Save and next**
to save. Reuse your ID to resume at the first unanswered sample.

When finished, send the JSON file shown at the bottom of the window to the
study coordinator. By default it is stored at
`results/<yourname>_blind_samples_results.json` inside the kit. You can also
use **Export results** to save a copy. The view hides attack methods, models,
and automatic validator verdicts.

> **Tkinter note:** on some Linux systems Tkinter ships via the system package
> manager, not pip (e.g. `sudo apt install python3-tk`).

---

## Repository layout

```text
human_evaluation/
├── annotator_kit/            ← give THIS folder to annotators (self-contained)
│   ├── annotate.py               blind GUI
│   ├── protocol.py               verdict + failure-mode definitions
│   ├── blind_samples.json        the 200 blind samples
│   ├── requirement.txt           pip deps
│   └── README.md                 annotator instructions
│
├── build_combined_blind.py       (maintainer) build the set + package the kit
├── summarize_behavior_change.py  (maintainer) κ + per-pool + RQ4 analysis
├── protocol.py                   source of truth for the taxonomy
└── sample_attack_successes.py / sample_semantic_valid_blind.py   samplers
```

The private key that maps each sample id back to pool / method / model /
validator verdict (`blind_key.csv`) is **not** committed — it stays with the
arbiter.

---

## If you are the arbiter / maintainer

**1. Build the blind set and package the kit** (needs the STRIKE workspace +
result CSVs):

```bash
python -B human_evaluation/build_combined_blind.py --include-archive
```

This writes `annotator_kit/blind_samples.json` (and refreshes the kit's
`protocol.py` and `requirement.txt`; the maintained English README is retained), plus the private `blind_key.csv`
and `blind_summary.csv`.

**2. Collect** each annotator's `<name>_blind_samples_results.json`. You also
annotate a set yourself to serve as the arbiter.

**3. Summarize** — Cohen's κ, third-person arbitration, per-pool numbers, and the
RQ4 failure-mode breakdown:

```bash
python human_evaluation/summarize_behavior_change.py \
  alice_blind_samples_results.json bob_blind_samples_results.json \
  --key human_evaluation/blind_key.csv \
  --arbiter your_blind_samples_results.json
```

- **Pool A** (motivation): `invalid` share = fraction of *reported-successful*
  attacks that actually broke behavior.
- **Pool B** (validation): `valid` share = how often humans confirm the auto
  semantic-validator's surviving examples.

`protocol.py` is the single source of truth for the verdict and failure-mode
taxonomy — edit it there and both the GUI and the summarizer pick it up.
