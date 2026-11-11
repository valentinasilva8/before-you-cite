"""The lead's gap round: fires on zero-row strings, stops on done, and drops itself on any failure."""

import json
import time

import pytest

from retraction_agent import gaps
from retraction_agent.catalog import get_catalog
from retraction_agent.orchestrate import handle_turn
from tests.fakes import FakeCrossref, Reply, ToolCall, scripted_complete

SPRINGER = 'How many retraction notices does the publisher "Springer Nature" have in the extract? Do not compute a rate.'
SPRINGER_NPG = "Springer - Nature Publishing Group"
MIXED = 'Check https://doi.org/10.3390/nano10122325 and also count the publisher "IEEE".'
IEEE = "IEEE: Institute of Electrical and Electronics Engineers"
NOTE = "The publisher string is counted as the file spells it."


def settings(**overrides):
    base = {
        "enabled": True,
        "extra_rounds": 1,
        "max_tasks": 3,
        "max_candidates": 5,
        "researcher_tool_rounds": 2,
        "lead_timeout_s": 5,
        "researcher_timeout_s": 5,
        "budget_s": 10,
        "skip_after_s": 60,
    }
    base.update(overrides)
    return base


@pytest.fixture
def gap_on(monkeypatch):
    def apply(**overrides):
        monkeypatch.setattr(gaps, "gap_settings", lambda: settings(**overrides))

    apply()
    return apply


def gap_complete(reply):
    """scripted_complete for every agent, except the gap lead, which gets reply (a Reply or a callable)."""
    base = scripted_complete(NOTE)
    state = {"gap_calls": 0}

    def complete(messages, tools):
        if "back for one more research round" in messages[0]["content"]:
            state["gap_calls"] += 1
            return reply(messages) if callable(reply) else reply
        return base(messages, tools)

    complete.state = state
    return complete


def plan(action, *tasks):
    args = {"action": action}
    if tasks:
        args["tasks"] = [{"field": field, "string": string} for field, string in tasks]
    return Reply("", [ToolCall("submit_gap_plan", args)])


def run(message, complete):
    return handle_turn({"messages": []}, message, complete_fn=complete, catalog=get_catalog(), crossref=FakeCrossref())


def baseline(message, monkeypatch):
    monkeypatch.setattr(gaps, "gap_settings", lambda: settings(enabled=False))
    out = run(message, gap_complete(plan("done")))
    monkeypatch.setattr(gaps, "gap_settings", lambda: settings())
    return out


def round_two(out):
    return [call for call in out["tool_calls"] if call["agent"].startswith("pattern-researcher-r2")]


def test_gap_round_fires_and_counts_the_file_string(gap_on):
    complete = gap_complete(plan("more", ("publisher", SPRINGER_NPG)))
    out = run(SPRINGER, complete)
    assert complete.state["gap_calls"] == 1
    lead = [call for call in out["tool_calls"] if call["name"] == "submit_gap_plan"]
    assert len(lead) == 1 and lead[0]["agent"] == "lead"
    assert lead[0]["args"] == {"action": "more", "tasks": [{"field": "publisher", "string": SPRINGER_NPG}]}
    record = json.loads(lead[0]["result"])
    assert record["accepted"] == [{"field": "publisher", "string": SPRINGER_NPG}]
    assert record["research_round"] == 2
    extra = round_two(out)
    assert [call["name"] for call in extra] == ["rw_pattern"]
    assert extra[0]["args"]["publisher"] == SPRINGER_NPG
    assert json.loads(extra[0]["result"])["rows"] == 3736
    for call in out["tool_calls"]:
        assert set(call) == {"agent", "name", "args", "result"}
        assert isinstance(call["result"], str)
    names = [call["name"] for call in out["tool_calls"]]
    assert names.index("submit_gap_plan") > names.index("rw_pattern")


def test_writer_hears_about_the_later_round_only_when_it_ran(gap_on):
    seen = []

    def spy(reply):
        inner = gap_complete(reply)

        def complete(messages, tools):
            if messages[0]["content"].startswith("You are the writer"):
                seen.append(json.loads(messages[1]["content"]))
            return inner(messages, tools)

        return complete

    run(SPRINGER, spy(plan("more", ("publisher", SPRINGER_NPG))))
    assert seen[-1]["later_round"] == gaps.WRITER_GAP_NOTE
    run(SPRINGER, spy(plan("done")))
    assert "later_round" not in seen[-1]


def test_lead_says_done_adds_only_the_lead_call(gap_on, monkeypatch):
    before = baseline(SPRINGER, monkeypatch)
    out = run(SPRINGER, gap_complete(plan("done")))
    assert round_two(out) == []
    lead = [call for call in out["tool_calls"] if call["name"] == "submit_gap_plan"]
    assert json.loads(lead[0]["result"])["action"] == "done"
    assert [call for call in out["tool_calls"] if call["name"] != "submit_gap_plan"] == before["tool_calls"]
    assert out["response"] == before["response"]


@pytest.mark.parametrize(
    "reply",
    [
        Reply("I think Springer - Nature Publishing Group."),
        Reply("", [ToolCall("submit_plan", {"action": "dispatch"})]),
        Reply("", [ToolCall("submit_gap_plan", "{not json")]),
        plan("maybe"),
        plan("more"),
        plan("more", ("publisher", "Springer Nature Group")),
        plan("more", ("journal", SPRINGER_NPG)),
        plan("more", ("publisher", "Springer Nature")),
        Reply("", [ToolCall("submit_gap_plan", {"action": "done"}), ToolCall("submit_gap_plan", {"action": "done"}, "c2")]),
    ],
)
def test_malformed_gap_plan_keeps_round_one_exactly(gap_on, monkeypatch, reply):
    before = baseline(SPRINGER, monkeypatch)
    out = run(SPRINGER, gap_complete(reply))
    assert out == before


def test_exception_in_the_lead_keeps_round_one_exactly(gap_on, monkeypatch):
    before = baseline(SPRINGER, monkeypatch)

    def boom(messages):
        raise RuntimeError("vertex down")

    assert run(SPRINGER, gap_complete(boom)) == before


def test_exception_building_the_summary_keeps_round_one_exactly(gap_on, monkeypatch):
    before = baseline(SPRINGER, monkeypatch)

    def broken(*args, **kwargs):
        raise KeyError("by_publisher")

    monkeypatch.setattr(gaps, "candidate_strings", broken)
    assert run(SPRINGER, gap_complete(plan("more", ("publisher", SPRINGER_NPG)))) == before


def test_slow_lead_times_out_and_does_not_hold_the_turn(gap_on, monkeypatch):
    before = baseline(SPRINGER, monkeypatch)
    gap_on(lead_timeout_s=0.2)

    def slow(messages):
        time.sleep(2)
        return plan("more", ("publisher", SPRINGER_NPG))

    started = time.monotonic()
    out = run(SPRINGER, gap_complete(slow))
    assert time.monotonic() - started < 1.5
    assert out == before


def test_late_turn_skips_the_gap_round(gap_on, monkeypatch):
    gap_on(skip_after_s=0.0)
    complete = gap_complete(plan("more", ("publisher", SPRINGER_NPG)))
    out = run(SPRINGER, complete)
    assert complete.state["gap_calls"] == 0
    assert round_two(out) == []


def test_flag_off_never_calls_the_gap_lead(monkeypatch):
    monkeypatch.setattr(gaps, "gap_settings", lambda: settings(enabled=False))
    complete = gap_complete(plan("more", ("publisher", SPRINGER_NPG)))
    out = run(SPRINGER, complete)
    assert complete.state["gap_calls"] == 0
    assert not any(call["name"] == "submit_gap_plan" for call in out["tool_calls"])


def test_settings_are_off_without_a_true_flag_and_clamped(monkeypatch):
    def config(block, rounds=2):
        monkeypatch.setattr(gaps, "load_config", lambda: {"gap_round": block} if block is not None else {})
        monkeypatch.setattr(gaps, "limits", lambda: {"max_research_rounds": rounds})
        return gaps.gap_settings()

    assert config(None)["enabled"] is False
    assert config({"enabled": "yes"})["enabled"] is False
    assert config({"enabled": True})["enabled"] is True
    huge = config({"enabled": True, "max_tasks": 99, "budget_s": 999, "lead_timeout_s": 999}, rounds=10)
    assert (huge["max_tasks"], huge["budget_s"], huge["lead_timeout_s"], huge["extra_rounds"]) == (5, 60, 30, 2)
    assert config({"enabled": True}, rounds=1)["extra_rounds"] == 0


def test_task_cap_drops_the_extra_tasks(gap_on):
    gap_on(max_tasks=2)
    candidates = [item["string"] for item in gaps.candidate_strings(get_catalog(), "publisher", "Springer Nature", 5)]
    assert len(candidates) >= 3
    out = run(SPRINGER, gap_complete(plan("more", *[("publisher", name) for name in candidates[:3]])))
    assert len(round_two(out)) == 2
    lead = [call for call in out["tool_calls"] if call["name"] == "submit_gap_plan"][0]
    assert json.loads(lead["result"])["dropped_over_cap"] == 1


def test_round_cap_stops_the_lead_even_when_gaps_remain(gap_on):
    complete = gap_complete(lambda messages: plan("more", ("publisher", json.loads(messages[1]["content"])["gaps"][0]["candidates"][0]["string"])))
    run(SPRINGER, complete)
    assert complete.state["gap_calls"] == 1
    gap_on(extra_rounds=2)
    complete = gap_complete(lambda messages: plan("more", ("publisher", json.loads(messages[1]["content"])["gaps"][0]["candidates"][0]["string"])))
    out = run(SPRINGER, complete)
    assert complete.state["gap_calls"] == 2
    assert {call["agent"].split(" ")[0] for call in out["tool_calls"] if call["agent"].startswith("pattern-researcher-r")} == {
        "pattern-researcher-r2-1",
        "pattern-researcher-r3-1",
    }


def test_duplicate_tasks_run_once(gap_on):
    out = run(SPRINGER, gap_complete(plan("more", ("publisher", SPRINGER_NPG), ("publisher", SPRINGER_NPG))))
    assert len(round_two(out)) == 1


def test_mixed_turn_keeps_every_verdict_and_lookup(gap_on, monkeypatch):
    before = baseline(MIXED, monkeypatch)
    out = run(MIXED, gap_complete(plan("more", ("publisher", IEEE))))
    added = [call for call in out["tool_calls"] if call["name"] == "submit_gap_plan" or call in round_two(out)]
    assert len(added) == 2
    assert [call for call in out["tool_calls"] if call not in added] == before["tool_calls"]
    table = lambda text: text.split("\n\n")[:2]
    assert table(out["response"]) == table(before["response"])
    for name in ("rw_lookup_doi", "doi_agency", "crossref_doi", "record_status"):
        assert [c for c in out["tool_calls"] if c["name"] == name] == [c for c in before["tool_calls"] if c["name"] == name]


@pytest.mark.parametrize(
    "message",
    [
        'In the shipped extract, how many notice rows does the journal "plos one" have? Do not compute a rate.',
        "https://doi.org/10.3390/nano10122325",
        "Which publishers have the most notice rows? Do not compute a rate.",
    ],
)
def test_no_gap_no_lead_call(gap_on, message):
    complete = gap_complete(plan("more", ("publisher", SPRINGER_NPG)))
    run(message, complete)
    assert complete.state["gap_calls"] == 0


def test_timeline_summarizes_the_gap_step_from_what_code_accepted():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").read_text(encoding="utf-8")
    block = js.split("submit_gap_plan(args, result) {", 1)[1].split("\n  },", 1)[0]
    assert "result.accepted" in block and "result.action" in block
    assert "args." not in block and "innerHTML" not in block
    assert "Lead decided no more research was needed." in block
    assert "Lead found a gap and sent" in block


def test_candidates_come_from_the_file():
    catalog = get_catalog()
    assert gaps.candidate_strings(catalog, "publisher", "IEEE", 5)[0]["string"] == IEEE
    assert gaps.candidate_strings(catalog, "publisher", "Taylor & Francis", 5)[0]["string"] == "Taylor and Francis"
    assert gaps.candidate_strings(catalog, "journal", "Journal of Nowhere Studies", 5) == []
