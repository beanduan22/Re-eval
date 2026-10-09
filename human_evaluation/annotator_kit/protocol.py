#!/usr/bin/env python3


from __future__ import annotations


VERDICTS = ("valid", "invalid", "cannot_determine")

VERDICT_LABEL = {
    "valid": "Language-valid and behavior-preserving",
    "invalid": "Demonstrated validity or behavior violation",
    "cannot_determine": "Cannot determine",
}


FAILURE_MODES = (
    ("syntax_broken", "Syntax broken"),
    ("binding_broken", "Binding broken"),
    ("scope_conflict", "Scope conflict"),
    ("block_structure_broken", "Block structure broken"),
    ("unsafe_insertion", "Unsafe insertion"),
    ("behavior_changed", "Demonstrated behavior change"),
)

FAILURE_MODE_KEYS = tuple(key for key, _label in FAILURE_MODES)
FAILURE_MODE_LABEL = dict(FAILURE_MODES)


POOL_A = "A"
POOL_B = "B"
POOL_C = "C"


TIMEOUT_SECONDS = 10 * 60
