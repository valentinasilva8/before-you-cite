from retraction_agent.catalog import get_catalog
from retraction_agent.samples import EXACT_TITLE, NANO_DOI, SHORT_TITLE, sample_facts


def test_snapshot_pin_and_counts():
    catalog = get_catalog()
    assert catalog.commit_short == "fb5f174f"
    assert catalog.manifest["sha256"] == "e5351ee51ab3f1da7fe98b3bd6c5c58049b8bff4705949ef6fd4f1a1315dd0ea"
    assert catalog.row_count == 73597
    assert catalog.nature_counts["Retraction"] == 68155
    assert catalog.nature_counts["Expression of concern"] == 3734
    assert catalog.nature_counts["Correction"] == 1545
    assert catalog.nature_counts["Reinstatement"] == 163


def test_nano_row_and_alphafold_absence():
    catalog = get_catalog()
    nano = catalog.lookup_doi("https://doi.org/10.3390/nano10122325")
    assert nano["total"] == 1
    row = nano["rows"][0]
    assert row["record_id"] == "70104"
    assert row["nature"] == "Retraction"
    assert row["retraction_date_iso"] == "2026-02-25"
    assert row["original_date_iso"] == "2020-11-23"
    assert row["retraction_doi"] == "10.3390/nano16050293"
    assert row["reasons"] == [
        "Concerns/Issues about Data",
        "Concerns/Issues about Image",
        "Investigation by Journal/Publisher",
    ]
    assert "" not in row["reasons"]
    assert row["journal"] == "Nanomaterials"
    assert row["publisher"] == "MDPI"
    assert row["notes_present"] is False
    assert catalog.lookup_doi("10.1038/s41586-021-03819-2")["total"] == 0


def test_mixed_case_doi_returns_both_rows_once():
    catalog = get_catalog()
    found = catalog.lookup_doi("10.1039/D1RA07974C")
    assert found["total"] == 2
    assert set(found["record_ids"]) == {"73993", "73988"}
    assert found["nature_counts"]["Expression of concern"] == 1
    assert found["nature_counts"]["Retraction"] == 1


def test_february_6_and_author_token_and_unavailable():
    catalog = get_catalog()
    assert catalog.rows["4036"]["retraction_date"] == "2/6/2010 0:00"
    assert catalog.rows["4036"]["retraction_date_iso"] == "2010-02-06"
    assert "70104" in catalog.by_author["ayman m atta"]
    author = catalog.lookup_author("Ayman M Atta")
    assert author["total"] > 25
    assert author["truncated"] is True
    assert "70104" not in catalog.by_author.get("ayman", [])
    assert "70104" not in catalog.lookup_author("Ayman")["record_ids"]
    assert catalog.lookup_doi("unavailable")["total"] == 0


def test_title_exactness_and_journal_casefold_and_top_publisher():
    catalog = get_catalog()
    exact = catalog.lookup_title(EXACT_TITLE)
    assert exact["total"] == 1
    assert exact["rows"][0]["record_id"] == "70548"
    assert catalog.lookup_title(SHORT_TITLE)["total"] == 0
    fuzzy = catalog.pattern(journal="Journal of Intelligent & Fuzzy Systems")
    assert fuzzy["rows"] == 1609
    plos = catalog.pattern(journal="plos one")
    assert plos["rows"] == 0
    assert plos["casefold_unique"] == "PLoS One"
    assert catalog.pattern(journal="PLoS One")["rows"] == 1680
    top = catalog.top_publishers(8)
    assert top["not_a_rate"] is True
    assert top["publishers"][0]["publisher"] == "Hindawi"
    assert top["publishers"][0]["notice_rows"] == 11524
    assert top["publishers"][0]["batch_dates"][0]["notice_rows"] == 631
    assert "rate" in top["note"]


def test_committed_expected_samples_match_the_file():
    import json
    from pathlib import Path

    saved = json.loads(Path("data/expected_samples.json").read_text(encoding="utf-8"))
    assert saved == sample_facts(get_catalog())


def test_sample_facts_match_file():
    facts = sample_facts(get_catalog())
    assert facts["sample1"]["nano"]["record_id"] == "70104"
    assert facts["sample1"]["alphafold"]["rows"] == 0
    assert facts["sample1"]["short_title"]["rows"] == 0
    assert facts["sample1"]["exact_title"]["record_id"] == "70548"
    assert facts["sample3"]["publishers"][0]["notice_rows"] == 11524
