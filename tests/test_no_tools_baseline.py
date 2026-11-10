from datetime import datetime, timezone

import pytest

from retraction_agent.config import load_config
from retraction_agent.samples import PROMPTS as SAMPLE_PROMPTS
from scripts import no_tools_baseline
from scripts.no_tools_baseline import LABELS, PROMPTS, SYSTEM, main


def test_prompts_equal_the_sample_entries():
    assert PROMPTS is SAMPLE_PROMPTS
    assert PROMPTS == SAMPLE_PROMPTS
    assert list(PROMPTS) == [
        "doi_link",
        "reference_with_doi",
        "reading_list",
        "publisher_question",
    ]
    assert list(LABELS) == list(PROMPTS)


def test_missing_vertex_auth_exits_2_without_writing(monkeypatch, capsys, tmp_path):
    output = tmp_path / "no_tools_baseline.md"
    monkeypatch.setattr(no_tools_baseline, "OUTPUT", output)

    def missing(messages, tools):
        raise RuntimeError("default credentials were not found")

    monkeypatch.setattr(no_tools_baseline, "complete", missing)
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "NO_TOOLS_UNAVAILABLE RuntimeError: default credentials were not found\n"
    assert not output.exists()


def test_a_real_run_prints_and_writes_the_answer_unchanged(monkeypatch, capsys, tmp_path):
    output = tmp_path / "docs" / "no_tools_baseline.md"
    monkeypatch.setattr(no_tools_baseline, "OUTPUT", output)
    answers = [
        "first answer, kept whole.\n\nsecond paragraph.   ",
        "sample two answer",
        "sample three answer\n",
        "publisher answer, not trimmed.  ",
    ]
    seen = []

    def complete(messages, tools):
        seen.append((messages, tools))
        return type("Reply", (), {"content": answers[len(seen) - 1]})()

    monkeypatch.setattr(no_tools_baseline, "complete", complete)

    class Clock:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 11, 10, 14, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(no_tools_baseline, "datetime", Clock)
    main()
    config = load_config()
    body = capsys.readouterr().out
    document = output.read_text(encoding="utf-8")
    for key, prompt in PROMPTS.items():
        assert f"## {LABELS[key]}\n\n{prompt}\n\n" in body
    for answer in answers:
        assert answer in body
        assert answer in document
    assert document.startswith(
        "# No-tools baseline\n\n"
        f"Model: {config['model']}\n\n"
        f"vertex_location: {config['vertex_location']}\n\n"
        "Run: 2026-11-10 14:30:00 UTC\n\n"
    )
    assert document.endswith(body)
    assert [call[0][0]["content"] for call in seen] == [SYSTEM, SYSTEM, SYSTEM, SYSTEM]
    assert [call[0][1]["content"] for call in seen] == list(PROMPTS.values())
    assert [call[1] for call in seen] == [None, None, None, None]
