# Behavior-change annotation

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
