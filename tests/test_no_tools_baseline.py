from datetime import datetime, timezone
from pathlib import Path

import pytest

from retraction_agent.config import load_config
from retraction_agent.samples import SAMPLE_1_TURN_1, SAMPLE_1_TURN_2, SAMPLE_2, SAMPLE_3
from scripts import no_tools_baseline
from scripts.no_tools_baseline import PROMPTS, SYSTEM, main


def test_prompts_are_the_three_readme_samples():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert PROMPTS == [SAMPLE_1_TURN_1, SAMPLE_2, SAMPLE_3]
    assert PROMPTS[0] is SAMPLE_1_TURN_1
    assert PROMPTS[1] is SAMPLE_2
    assert PROMPTS[2] is SAMPLE_3
    assert SAMPLE_1_TURN_2 not in PROMPTS
    for prompt in PROMPTS:
        assert prompt in readme


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
    assert body.startswith("## Sample 1\n\n" + SAMPLE_1_TURN_1 + "\n\n")
    assert SAMPLE_2 in body
    assert SAMPLE_3 in body
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
    assert [call[0][0]["content"] for call in seen] == [SYSTEM, SYSTEM, SYSTEM]
    assert [call[0][1]["content"] for call in seen] == PROMPTS
    assert [call[1] for call in seen] == [None, None, None]
