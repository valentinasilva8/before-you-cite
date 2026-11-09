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


def test_bare_doi_is_one_confident_reference():
    line = "10.1073/pnas.1209746109"
    assert parse_references(line) == [{"doi": "10.1073/pnas.1209746109"}]
    assert is_confident(line)
    assert not is_hard(line)


def test_good_extraction_copies_the_pasted_title():
    refs, calls = _apply(PASTED, [_item(0, title=PASTED.rstrip("."))])
    assert refs == [{"title": PASTED.rstrip("."), "parsed_by": "llm"}]
    assert calls[0]["agent"] == "citation-extractor"
    assert json.loads(calls[0]["result"])["parsed_by"] == "llm"


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


def test_a_confident_doi_line_does_not_call_the_model():
    def complete(messages, tools):
        raise AssertionError("confident line was sent to the model")

    plan = finalize_plan(
        "https://doi.org/10.1038/s41586-021-03819-2",
        {"action": "dispatch", "references": []},
        [],
    )
    assert apply_llm_fallback("https://doi.org/10.1038/s41586-021-03819-2", plan, complete) == []
