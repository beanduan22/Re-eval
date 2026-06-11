#!/usr/bin/env python3
"""Shared constants for the blind behavior-change annotation protocol.

The annotation question is: "Does this change alter the behavior of the
original code?" Annotators pick exactly one verdict; only ``invalid`` carries a
failure-mode tag (these feed RQ4).

Keep verdict / failure-mode keys identical across the GUI and the summarizer so
the two never drift.
"""
from __future__ import annotations

# Verdicts. Stored as the stable English key; the GUI shows the bilingual label.
VERDICTS = ("valid", "invalid", "cannot_determine")

VERDICT_LABEL = {
    "valid": "没改变 (valid)",
    "invalid": "改变了 (invalid)",
    "cannot_determine": "无法确定",
}

# Failure-mode taxonomy for RQ4. Single-select, only meaningful when the verdict
# is ``invalid``. (key, bilingual GUI label).
FAILURE_MODES = (
    ("syntax_broken", "语法损坏 (syntax broken)"),
    ("binding_broken", "绑定破坏 (binding broken)"),
    ("scope_conflict", "作用域冲突 (scope conflict)"),
    ("block_structure_broken", "块结构破坏 (block structure broken)"),
    ("unsafe_insertion", "不安全插入 (unsafe insertion)"),
    ("unconfirmable_rewrite", "无法确认的改写 (unconfirmable rewrite)"),
)

FAILURE_MODE_KEYS = tuple(key for key, _label in FAILURE_MODES)
FAILURE_MODE_LABEL = dict(FAILURE_MODES)

# Pools. A = motivation (originally successful), B = validation (semantic-valid).
POOL_A = "A"
POOL_B = "B"

# Per-sample soft time budget. On expiry the GUI nudges the annotator to mark
# the sample ``cannot_determine`` (it never overwrites an existing choice).
TIMEOUT_SECONDS = 10 * 60
