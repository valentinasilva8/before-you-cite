import pytest

from retraction_agent.citations import (
    CONFIRM_NOTE,
    asks_for_rate,
    confirmation_question,
    corpus_from,
    drop_rate_claims,
    enforce_citations,
    strip_units,
)
from retraction_agent.samples import PROMPTS

SNAPSHOT = "fb5f174f8476824deaf340693f9a819ce5e29ded"
RESULTS = [
    '{"snapshot": "fb5f174f8476824deaf340693f9a819ce5e29ded", "snapshot_short": "fb5f174f", '
    '"query_doi": "10.3390/nano10122325", "record_id": "70104", "total": 1}'
]


def test_regenerate_once_then_strip():
    calls = {"n": 0}

    def regenerate(previous, problems):
        calls["n"] += 1
        assert problems
        return previous

    draft = (
        "Record 70104 in snapshot fb5f174f matches DOI 10.3390/nano10122325. "
        "Record 99999999 was invented. "
        "The paper is fine."
    )
    text = enforce_citations(draft, RESULTS, SNAPSHOT, [], regenerate)
    assert calls["n"] == 1
    assert "70104" in text
    assert "10.3390/nano10122325" in text
    assert "99999999" not in text
    assert "fine" not in text.casefold()


def test_retraction_watch_number_not_in_results_is_dropped():
    draft = (
        "Retraction Watch #70104 is a retraction for DOI 10.3390/nano10122325. "
        "Retraction Watch #99999 shows this paper was retracted in 1999. "
        "Retraction Watch record 88888 is a correction. "
        "Retraction Watch: 77777 is an expression of concern. "
        "Retraction Watch 66666 is a retraction."
    )
    text = enforce_citations(draft, RESULTS, SNAPSHOT, [], None)
    assert "70104" in text
    for invented in ("99999", "88888", "77777", "66666"):
        assert invented not in text


def test_year_after_retraction_watch_is_not_a_record_id():
    text = strip_units("The Retraction Watch 2026 extract has a notice for this DOI.", corpus_from(RESULTS, SNAPSHOT), [])
    assert "2026" in text


@pytest.mark.parametrize(
    "message",
    [
        "What is the retraction rate of Hindawi?",
        "What percent of Elsevier papers are retracted?",
        "Which journal has the highest retraction rate?",
        "Is 2% of PLoS One retracted?",
    ],
)
def test_a_rate_question_asks_for_a_rate(message):
    assert asks_for_rate(message)


@pytest.mark.parametrize(
    "message",
    [
        PROMPTS["publisher_question"],
        'How many retraction notices does the publisher "Springer Nature" have in the extract? Do not compute a rate.',
        "Which publishers have the most notice rows? I don't want rates.",
        "Has 10.1038/s41586-021-03819-2 been retracted or corrected?",
        "Can you generate an accurate count for Hindawi?",
    ],
)
def test_saying_not_a_rate_is_not_asking_for_one(message):
    assert not asks_for_rate(message)


def test_rate_claims_are_dropped_and_not_a_rate_stays():
    text, dropped = drop_rate_claims(
        "Hindawi has 11,524 notice rows. Hindawi has a retraction rate of 3 percent. "
        "That is 15% of the extract. The rate of retraction for Hindawi is high. This is not a rate."
    )
    assert dropped
    assert text == "Hindawi has 11,524 notice rows.\nThis is not a rate."


def test_an_answer_without_rate_claims_is_unchanged():
    answer = "PLoS One has 1680 notice rows in snapshot fb5f174f.\nThese are notice counts, not rates."
    assert drop_rate_claims(answer) == (answer, False)


def test_data_limit_sentence_is_kept():
    kept = strip_units(
        "No record is a data limit, not a judgment that the work is reliable.",
        corpus_from(RESULTS, SNAPSHOT),
        [],
    )
    assert "data limit" in kept


def test_unconfirmed_candidate_status_is_removed():
    pending = [{"query": "short title", "candidates": [{"doi": "10.9999/guess", "title": "Guess"}]}]
    draft = "DOI 10.9999/guess was retracted. The candidate 10.9999/guess is not confirmed."
    text = strip_units(draft, corpus_from(['"doi": "10.9999/guess"'], SNAPSHOT), pending)
    assert "retracted" not in text.casefold()
    assert "not confirmed" in text


def test_confirmation_question_lists_candidates():
    text = confirmation_question([{"query": "Short", "candidates": [{"title": "Longer", "doi": "10.1000/abc"}]}])
    assert "Query: Short" in text
    assert "1. Longer" in text
    assert "DOI: 10.1000/abc" in text
    assert CONFIRM_NOTE.startswith("Confirm which title you meant.")
