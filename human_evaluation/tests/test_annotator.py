"""Data-loss regression tests; no display server is required."""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

KIT = Path(__file__).resolve().parents[1] / "annotator_kit"
sys.path.insert(0, str(KIT))
spec = importlib.util.spec_from_file_location("reeval_annotate", KIT / "annotate.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
sys.path.pop(0)


class Variable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.fixture
def reviewer(tmp_path):
    obj = app.CodeReviewer.__new__(app.CodeReviewer)
    obj.root = Mock()
    obj.result_path = tmp_path / "results" / "r1.json"
    obj.data = [
        {"Sample ID": "H0001", "Task": "AA", "Original": "x = 1", "Adversarial": "y = 1"},
        {"Sample ID": "H0002", "Task": "VD", "Original": "int x;", "Adversarial": "int y;"},
    ]
    obj.data_path = tmp_path / "blind_samples.json"
    obj.data_path.write_text(json.dumps(obj.data))
    obj.results = []
    obj.result_index_by_key = {}
    obj.index = 0
    obj.verdict_var, obj.fm_var, obj.note_var = Variable(), Variable(), Variable()
    obj.saved_answers = ("", "", "")
    obj.elapsed_before = 0
    obj.sample_started_at = app.time.monotonic() - 5
    obj.timed_out = False
    obj.failure_buttons = []
    obj.feedback_label = Mock()
    obj.progress_label = Mock()
    obj.sample_label = Mock()
    obj.timer_label = Mock()
    obj.progressbar = {}
    obj.diff_button = Mock()
    obj.render_code = Mock()
    obj.diff_mode = False
    return obj


def test_save_reload_and_edit_without_duplicate(reviewer):
    reviewer.verdict_var.set("valid")
    reviewer.note_var.set("Local rename")
    assert reviewer.save_score()
    loaded = reviewer.load_results()
    assert loaded[0]["verdict"] == "valid"
    assert loaded[0]["note"] == "Local rename"
    reviewer.verdict_var.set("invalid")
    reviewer.fm_var.set("binding_broken")
    assert reviewer.save_score()
    assert len(reviewer.load_results()) == 1
    assert reviewer.load_results()[0]["failure_mode"] == "binding_broken"


def test_invalid_requires_reason(reviewer):
    reviewer.verdict_var.set("invalid")
    assert not reviewer.save_score()
    assert not reviewer.result_path.exists()


def test_diff_toggle_preserves_draft_and_timer(reviewer):
    reviewer.verdict_var.set("invalid")
    reviewer.fm_var.set("behavior_changed")
    reviewer.note_var.set("Change under review")
    before = (reviewer.answers(), reviewer.sample_started_at)
    reviewer.toggle_diff_view()
    assert (reviewer.answers(), reviewer.sample_started_at) == before
    assert reviewer.diff_mode


@pytest.mark.parametrize("choice, moved, saved", [(True, True, True), (False, True, False), (None, False, False)])
def test_previous_handles_unsaved_answer(reviewer, monkeypatch, choice, moved, saved):
    reviewer.index = 1
    reviewer.verdict_var.set("cannot_determine")
    monkeypatch.setattr(app.messagebox, "askyesnocancel", lambda *a, **kw: choice)
    reviewer.prev_code()
    assert reviewer.index == (0 if moved else 1)
    assert reviewer.result_path.exists() == saved
    if saved:
        assert reviewer.results[0]["Sample ID"] == "H0002"


def test_failed_atomic_save_preserves_disk_memory_and_draft(reviewer, monkeypatch):
    reviewer.verdict_var.set("valid")
    assert reviewer.save_score()
    original = reviewer.result_path.read_bytes()
    reviewer.verdict_var.set("cannot_determine")
    monkeypatch.setattr(app.os, "replace", Mock(side_effect=OSError("disk failure")))
    monkeypatch.setattr(app.messagebox, "showerror", Mock())
    assert not reviewer.save_score()
    assert reviewer.result_path.read_bytes() == original
    assert reviewer.results[0]["verdict"] == "valid"
    assert reviewer.verdict_var.get() == "cannot_determine"
    assert list(reviewer.result_path.parent.iterdir()) == [reviewer.result_path]


def test_corrupt_result_is_not_silently_reset(reviewer):
    reviewer.result_path.parent.mkdir()
    reviewer.result_path.write_text("{broken")
    with pytest.raises(ValueError):
        reviewer.load_results()
    assert reviewer.result_path.read_text() == "{broken"


def test_resume_locates_missing_sample_and_reloads_saved_answer(reviewer):
    reviewer.verdict_var.set("valid")
    assert reviewer.save_score()
    reviewer.next_unanswered()
    assert reviewer.index == 1 and reviewer.answers() == ("", "", "")
    reviewer.prev_code()
    assert reviewer.index == 0 and reviewer.verdict_var.get() == "valid"


def test_timer_never_selects_an_answer(reviewer):
    reviewer.sample_started_at = app.time.monotonic() - app.TIMEOUT_SECONDS - 1
    reviewer.update_timer()
    assert reviewer.timed_out
    assert reviewer.verdict_var.get() == ""


def test_export_matches_summary_input(reviewer, tmp_path, monkeypatch):
    reviewer.verdict_var.set("valid")
    assert reviewer.save_score()
    destination = tmp_path / "export.json"
    monkeypatch.setattr(app.filedialog, "asksaveasfilename", lambda **kw: str(destination))
    reviewer.export_results()
    rows = json.loads(destination.read_text())
    assert rows == reviewer.results
    assert {row["Sample ID"]: row["verdict"] for row in rows} == {"H0001": "valid"}


def test_duplicate_samples_rejected(tmp_path):
    path = tmp_path / "samples.json"
    row = {"Sample ID": "same", "Original": "", "Adversarial": ""}
    path.write_text(json.dumps([row, row]))
    with pytest.raises(ValueError, match="unique"):
        app.load_samples(path)


def test_bundled_samples_and_usernames():
    assert len(app.load_samples(KIT / "blind_samples.json")) == 200
    assert app.valid_username("annotator_01")
    assert not app.valid_username("../other")
