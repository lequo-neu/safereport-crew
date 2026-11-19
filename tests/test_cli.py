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


# Every flag the README documents for `ask` parses and reaches the handler.
@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["ask", "Write a lockout talk"], ("Write a lockout talk", "lowest_cost", False, [], False)),
        (["ask", "Plan this week", "--approve", "--answer", "state=Texas", "--mode", "private"],
         ("Plan this week", "private", True, ["state=Texas"], False)),
        (["ask", "A narrative", "--live"], ("A narrative", "lowest_cost", False, [], True)),
    ],
)  # fmt: skip
def test_ask_accepts_every_documented_flag(monkeypatch, argv, expected):
    seen = []
    monkeypatch.setattr(cli, "ask", lambda request, mode, approve, answers, live=False: seen.append(
        (request, mode, approve, answers, live)))  # fmt: skip
    monkeypatch.setattr(sys, "argv", ["safereport", *argv])
    cli.main()
    assert seen == [expected]
