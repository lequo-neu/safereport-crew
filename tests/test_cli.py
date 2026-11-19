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


QUESTION = {"missing": ["state"], "questions": ["Which state should I look at?"]}


def test_planner_answers_come_from_the_flags_first(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("asked although --answer gave it"))
    assert cli.planner_answers(QUESTION, {"state": "Texas"}) == {"state": "Texas"}


def test_planner_answers_are_typed_in_when_no_flag_gives_them(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "Ohio")
    assert cli.planner_answers(QUESTION, {}) == {"state": "Ohio"}


def test_planner_question_without_input_names_the_flag(monkeypatch):
    def no_input(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_input)
    with pytest.raises(SystemExit, match="--answer state=Texas"):
        cli.planner_answers(QUESTION, {})


class OfflineBackend:  # named like the real one: the check is by type name
    pass


def test_the_first_line_says_whether_a_run_can_cost_money():
    offline = {"claude": OfflineBackend(), "gemma_local": OfflineBackend()}
    assert cli.answering(offline, live=False, mode="lowest_cost").endswith("(offline rules, free)")
    assert "LM Studio is not running" in cli.answering(offline, live=True, mode="private")
    assert cli.answering({"gemma_local": object()}, live=True, mode="private").endswith("(local, free)")
    assert "paid calls" in cli.answering({"claude": object()}, live=True, mode="lowest_cost")


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["ui"], {"port": 7860, "live": False, "mode": "lowest_cost"}),
        (["ui", "--live", "--mode", "private"], {"port": 7860, "live": True, "mode": "private"}),
    ],
)
def test_ui_takes_a_starting_mode(monkeypatch, argv, expected):
    import safereport.app

    seen = []
    monkeypatch.setattr(safereport.app, "launch", lambda **kwargs: seen.append(kwargs))
    monkeypatch.setattr(sys, "argv", ["safereport", *argv])
    cli.main()
    assert seen == [expected]
