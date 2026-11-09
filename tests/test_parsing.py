"""Citation lines the bibliography parser used to misread or drop."""

from pathlib import Path

from retraction_agent.orchestrate import handle_turn
from retraction_agent.planning import finalize_plan, parse_references
from retraction_agent.verdicts import build_verdicts, render_verdict_response
from tests.fakes import FakeCrossref, scripted_complete

ROOT = Path(__file__).resolve().parents[1]


def test_apa_title_is_the_sentence_after_the_year():
    line = (
        "Smith, J., & Jones, A. (2020). A Real Paper Title Here. "
        "Some Journal, 12(3), 1-10."
    )
    ref = parse_references(line)[0]
    assert ref["title"] == "A Real Paper Title Here"
    assert ref["author"] == "Smith, J., & Jones, A."
    assert ref["year"] == "2020"
    assert "Smith" not in ref["title"]
    assert "doi" not in ref


def test_shu_et_al_title_follows_the_year_marker():
    ref = parse_references("Shu et al. (2012). Coastal erosion and sediment. Venue.")[0]
    assert ref["title"] == "Coastal erosion and sediment"
    assert ref["year"] == "2012"
    assert ref["author"] == "Shu et al."
    assert "doi" not in ref


def test_conversational_text_around_a_link_is_not_the_title():
    line = (
        "Can you check this link ChatGPT gave me? "
        "https://doi.org/10.1038/s41586-021-03819-2"
    )
    refs = parse_references(line)
    assert refs == [{"doi": "10.1038/s41586-021-03819-2"}]
    assert "title" not in refs[0]
    assert "ChatGPT" not in refs[0].get("title", "")


def test_nature_article_url_becomes_a_doi():
    refs = parse_references("https://www.nature.com/articles/s41586-021-03819-2")
    assert refs == [{"doi": "10.1038/s41586-021-03819-2"}]


def test_pnas_science_and_wiley_urls_keep_the_doi_they_already_contain():
    cases = {
        "https://www.pnas.org/doi/10.1073/pnas.2115211118": "10.1073/pnas.2115211118",
        "https://www.science.org/doi/10.1126/science.abj8754": "10.1126/science.abj8754",
        "https://onlinelibrary.wiley.com/doi/10.1002/anie.202000111": "10.1002/anie.202000111",
    }
    for url, doi in cases.items():
        refs = parse_references(url)
        assert refs == [{"doi": doi}]
        assert "title" not in refs[0]


def test_other_publisher_urls_stay_not_checkable():
    line = "See the news writeup https://www.nytimes.com/2024/01/01/science/example-retraction-story.html"
    ref = parse_references(line)[0]
    assert ref["not_checkable"] is True
    assert "doi" not in ref
    assert "title" not in ref


def test_quoted_title_inside_a_sentence_is_the_title():
    ref = parse_references('Does this exist? "Attention Is All You Need" by Vaswani')[0]
    assert ref["title"] == "Attention Is All You Need"
    assert "Does this exist" not in ref["title"]
    assert "doi" not in ref


def test_unparsed_reference_is_kept_and_shown_as_could_not_verify():
    line = "1. Smith, J. (2012)."
    refs = parse_references(line)
    assert refs == [{"raw": "Smith, J. (2012).", "unparsed": True}]
    plan = finalize_plan(line, {"action": "dispatch", "references": []}, [])
    assert plan["references"] == refs
    verdicts = build_verdicts(plan["references"], [], "fb5f174f")
    assert verdicts[0]["label"] == "UNCONFIRMED"
    assert verdicts[0]["reason"] == "Could not read this citation"
    rendered = render_verdict_response(verdicts)
    assert "we could not read this citation" in rendered.casefold()
    result = handle_turn(
        {"messages": []},
        line,
        complete_fn=scripted_complete("Snapshot fb5f174f."),
        crossref=FakeCrossref(),
    )
    assert "UNCONFIRMED" in result["response"]
    assert "we could not read this citation" in result["response"].casefold()


def test_readme_sample_lines_keep_the_pasted_title():
    readme = (ROOT / "README.md").read_text()
    atta = next(
        line.strip()
        for line in readme.splitlines()
        if "Magnetic Ionic Liquid" in line and "10.3390/nano10122325" in line
    )
    short = next(
        line.strip()
        for line in readme.splitlines()
        if line.strip().startswith("5. Modeling Geometry and Semantics of Physical Damages")
    )
    atta_ref = parse_references(atta)[0]
    assert atta_ref["doi"] == "10.3390/nano10122325"
    assert atta_ref["title"].startswith("Magnetic Ionic Liquid")
    assert atta_ref["author"].endswith("et al.")
    short_ref = parse_references(short)[0]
    assert short_ref == {"title": "Modeling Geometry and Semantics of Physical Damages"}
