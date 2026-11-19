from __future__ import annotations

import sys

import pytest

from safereport import cli


def test_check_lists_models_and_the_answer_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(sys, "argv", ["safereport", "check"])
    cli.main()
    out = capsys.readouterr().out
    assert "claude-sonnet-5-5" in out
    assert "price unknown" in out
    assert "60 cases, 51 with a standard" in out
