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
    "valid": "Unchanged (valid)",
    "invalid": "Changed (invalid)",
    "cannot_determine": "Cannot determine",
}

# Failure-mode taxonomy for RQ4. Single-select, only meaningful when the verdict
# is ``invalid``. (key, GUI label).
FAILURE_MODES = (
    ("syntax_broken", "Syntax broken"),
    ("binding_broken", "Binding broken"),
    ("scope_conflict", "Scope conflict"),
    ("block_structure_broken", "Block structure broken"),
    ("unsafe_insertion", "Unsafe insertion"),
    ("unconfirmable_rewrite", "Unconfirmable rewrite"),
)

FAILURE_MODE_KEYS = tuple(key for key, _label in FAILURE_MODES)
FAILURE_MODE_LABEL = dict(FAILURE_MODES)

# Pools. A = motivation (originally successful), B = validation (semantic-valid).
POOL_A = "A"
POOL_B = "B"

# Per-sample soft time budget. On expiry the GUI nudges the annotator to mark
# the sample ``cannot_determine`` (it never overwrites an existing choice).
TIMEOUT_SECONDS = 10 * 60
