"""Fallback extraction accepts only text that was actually pasted."""

import json

from retraction_agent.extract import apply_llm_fallback, fallback_settings, is_confident, is_hard
from retraction_agent.planning import finalize_plan, parse_references
from tests.fakes import Reply, ToolCall

SHU = (
    "Signing at the beginning makes ethics salient and decreases "
    "dishonest self-reports in comparison to signing at the end"
)
PASTED = "Coastal erosion and sediment transport in deltas is the pasted title here."


def _item(index, **fields):
    base = {
        "raw_line_index": index,
        "title": "",
        "authors": "",
        "year": "",
        "venue": "",
        "doi": "",
        "url": "",
    }
    base.update(fields)
    return base


def _complete(items):
    def complete(messages, tools):
        if any(item.get("role") == "tool" for item in messages):
            return Reply("done")
        return Reply("", [ToolCall("submit_extractions", {"items": items})])

    return complete


def _apply(text, items):
    plan = finalize_plan(text, {"action": "dispatch", "references": []}, [])
    calls = apply_llm_fallback(text, plan, _complete(items))
    return plan["references"], calls


def test_fallback_settings_come_from_config():
    settings = fallback_settings()
    assert settings["enabled"] is True
    assert settings["max_lines"] == 25
    assert settings["model"] == "vertex_ai/gemini-3.5-flash-lite"
    assert settings["temperature"] == 0


def test_the_extractor_call_sends_the_configured_temperature(monkeypatch):
    from retraction_agent import extract

    sent = {}

    class _Choice:
        message = Reply("done")

    class _Response:
        choices = [_Choice()]

    def fake_completion(**kwargs):
        sent.update(kwargs)
        return _Response()

    monkeypatch.setattr(extract.litellm, "completion", fake_completion)
    extract.fallback_complete([{"role": "user", "content": "x"}], extract.EXTRACT_TOOLS)
    assert sent["temperature"] == 0
    assert sent["model"] == "vertex_ai/gemini-3.5-flash-lite"


def test_bare_doi_is_one_confident_reference():
    line = "10.1073/pnas.1209746109"
    assert parse_references(line) == [{"doi": "10.1073/pnas.1209746109"}]
    assert is_confident(line)
    assert not is_hard(line)


def test_good_extraction_copies_the_pasted_title():
    refs, calls = _apply(PASTED, [_item(0, title=PASTED.rstrip("."))])
    assert refs == [{"title": PASTED.rstrip("."), "parsed_by": "llm"}]
    assert calls[0]["agent"] == "citation-extractor"
    result = json.loads(calls[0]["result"])
    assert result["parsed_by"] == "llm"
    assert result["items"][0]["passed_copy_check"] is True
    assert "accepted" not in result["items"][0]


def test_a_rejected_line_does_not_pass_the_copy_check():
    _refs, calls = _apply(PASTED, [_item(0, title="An invented title that is not in the line")])
    assert json.loads(calls[0]["result"])["items"][0]["passed_copy_check"] is False


def test_a_model_that_corrects_a_title_is_rejected():
    refs, _calls = _apply(
        PASTED,
        [_item(0, title="Coastal erosion and sediment transport in river deltas is the pasted title here.")],
    )
    assert refs == [{"raw": PASTED, "unparsed": True, "parsed_by": "llm"}]
    assert "river" not in refs[0]["raw"]


def test_a_model_that_invents_a_doi_is_rejected():
    refs, _calls = _apply(PASTED, [_item(0, title=PASTED.rstrip("."), doi="10.9999/invented-not-in-the-line")])
    assert refs == [{"raw": PASTED, "unparsed": True, "parsed_by": "llm"}]
    assert all("doi" not in ref for ref in refs)


def test_a_short_item_count_rejects_every_hard_line():
    text = (
        "Pasted line one is about coastal erosion and sediment transport.\n"
        "Pasted line two is about glacier mass balance trends over decades."
    )
    refs, _calls = _apply(
        text,
        [_item(0, title="Pasted line one is about coastal erosion and sediment transport.")],
    )
    assert [ref.get("unparsed") for ref in refs] == [True, True]
    assert all(ref.get("parsed_by") == "llm" for ref in refs)
    assert all("title" not in ref for ref in refs)


def test_mla_entry_uses_the_quoted_title():
    line = (
        'Shu, Lisa L., et al. "Signing at the beginning makes ethics salient and decreases '
        'dishonest self-reports in comparison to signing at the end." Proceedings of the '
        "National Academy of Sciences, vol. 109, no. 38, 2012, pp. 15197-15200."
    )
    refs, _calls = _apply(
        line,
        [_item(0, title=SHU, authors="Shu, Lisa L., et al.", year="2012", venue="Proceedings of the National Academy of Sciences")],
    )
    assert refs[0]["title"] == SHU
    assert refs[0]["parsed_by"] == "llm"
    assert refs[0]["year"] == "2012"


def test_vancouver_entry_uses_the_title_after_the_authors():
    line = (
        "Shu LL, Mazar N, Gino F, Ariely D, Bazerman MH. "
        "Signing at the beginning makes ethics salient and decreases dishonest self-reports "
        "in comparison to signing at the end. Proc Natl Acad Sci. 2012;109(38):15197-15200."
    )
    assert is_hard(line)
    refs, _calls = _apply(line, [_item(0, title=SHU, authors="Shu LL", year="2012", venue="Proc Natl Acad Sci")])
    assert refs[0]["title"] == SHU
    assert refs[0]["parsed_by"] == "llm"
    assert "Bazerman" not in refs[0]["title"]


def test_bibtex_entry_keeps_only_a_doi_that_was_pasted():
    line = (
        "@article{shu2012, author={Shu, Lisa L.}, title={Signing at the beginning makes ethics "
        "salient and decreases dishonest self-reports in comparison to signing at the end}, "
        "year={2012}, doi={10.1073/pnas.1209746109}}"
    )
    assert is_hard(line)
    refs, _calls = _apply(
        line,
        [_item(0, title=SHU, authors="Shu, Lisa L.", year="2012", doi="10.1073/pnas.1209746109")],
    )
    assert refs[0]["doi"] == "10.1073/pnas.1209746109"
    assert refs[0]["title"] == SHU
    assert refs[0]["parsed_by"] == "llm"


def test_a_stub_that_returns_the_whole_line_strips_markers_and_keeps_news():
    """The live model copied the pasted line, including the list number and the news URL."""
    from retraction_agent.extract import _lines
    from retraction_agent.samples import INTEGRITY_SAMPLE
    from retraction_agent.verdicts import build_verdicts

    lines = _lines(INTEGRITY_SAMPLE)

    def complete(messages, tools):
        if any(item.get("role") == "tool" for item in messages):
            return Reply("done")
        payload = json.loads(messages[1]["content"])
        items = []
        for entry in payload["lines"]:
            original = lines[entry["raw_line_index"]]
            items.append(
                _item(
                    entry["raw_line_index"],
                    title=original,
                    year="2024" if "2024" in original else "",
                )
            )
        return Reply("", [ToolCall("submit_extractions", {"items": items})])

    plan = finalize_plan(INTEGRITY_SAMPLE, {"action": "dispatch", "references": []}, [])
    calls = apply_llm_fallback(INTEGRITY_SAMPLE, plan, complete)
    assert len(calls) == 1
    row5 = plan["references"][4]
    row6 = plan["references"][5]
    assert row5["title"] == "Modeling Geometry and Semantics of Physical Damages"
    assert "5." not in row5["title"]
    assert row6 == {
        "not_checkable": True,
        "raw": "See the news writeup https://www.nytimes.com/2024/01/01/science/example-retraction-story.html",
    }
    verdict = build_verdicts([row6], [], "fb5f174f")[0]
    assert verdict["label"] == "UNCONFIRMED"
    assert verdict["reason"] == "Not a paper"
    plain = "Coastal erosion and sediment transport in deltas is the pasted title here."
    plain_refs, _calls = _apply(plain, [_item(0, title=plain)])
    assert plain_refs == [{"title": plain, "parsed_by": "llm"}]


def test_list_markers_are_stripped_from_the_returned_title():
    title = "Coastal erosion and sediment transport in deltas is the pasted title here."
    for line in (f"5) {title}", f"[5] {title}", f"- {title}", f"• {title}"):
        refs, _calls = _apply(line, [_item(0, title=line)])
        assert refs[0]["title"] == title
        assert refs[0]["parsed_by"] == "llm"


def test_a_title_that_still_contains_a_url_is_not_searched():
    line = (
        '"Coastal erosion report https://www.nytimes.com/2024/01/01/science/'
        'example-retraction-story.html and the rest of the quoted title"'
    )
    refs, _calls = _apply(line, [_item(0, title=line.strip('"'), year="2024")])
    assert refs[0]["not_checkable"] is True
    assert "title" not in refs[0]
    assert "doi" not in refs[0]


def test_a_confident_doi_line_does_not_call_the_model():
    def complete(messages, tools):
        raise AssertionError("confident line was sent to the model")

    plan = finalize_plan(
        "https://doi.org/10.1038/s41586-021-03819-2",
        {"action": "dispatch", "references": []},
        [],
    )
    assert apply_llm_fallback("https://doi.org/10.1038/s41586-021-03819-2", plan, complete) == []
