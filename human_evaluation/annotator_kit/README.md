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
**“这个改动是否改变了原代码的行为?”**:

- **没改变 (valid)** — behavior preserved.
- **改变了 (invalid)** — behavior changed; then pick one failure mode.
- **无法确定 (cannot_determine)** — cannot confidently judge.

A soft 10-minute per-sample timer nudges toward *无法确定* when it runs out. An
optional note is recorded per sample. Your progress is saved continuously to
`<yourname>_blind_samples_results.json`.

## Send back

When done, send back the single file `<yourname>_blind_samples_results.json`.
