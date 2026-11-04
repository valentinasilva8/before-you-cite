from retraction_agent.normalize import arxiv_doi_from_text, normalize_doi, normalize_title, parse_us_date, split_semicolon
from retraction_agent.planning import chunk


def test_doi_prefix_case_and_unavailable():
    assert normalize_doi("https://doi.org/10.1039/D1RA07974C") == "10.1039/d1ra07974c"
    assert normalize_doi("http://dx.doi.org/10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("doi:10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("unavailable") is None
    assert normalize_doi("Unavailable") is None
    assert normalize_doi("  ") is None


def test_us_date_is_month_first():
    assert parse_us_date("2/6/2010 0:00") == "2010-02-06"
    assert parse_us_date("11/23/2020 0:00") == "2020-11-23"


def test_trailing_semicolon_is_not_a_reason():
    assert split_semicolon("Concerns/Issues about Data;Concerns/Issues about Image;") == [
        "Concerns/Issues about Data",
        "Concerns/Issues about Image",
    ]


def test_arxiv_ids_drop_the_version_suffix():
    assert arxiv_doi_from_text("https://arxiv.org/abs/1706.03762v2") == "10.48550/arxiv.1706.03762"
    assert arxiv_doi_from_text("arXiv:1706.03762v2") == "10.48550/arxiv.1706.03762"
    assert normalize_doi("10.48550/arXiv.1706.03762v2") == "10.48550/arxiv.1706.03762"


def test_title_whitespace_and_chunking():
    assert normalize_title("  Foo \n  Bar ") == "foo bar"
    parts = chunk(list(range(25)), 5)
    assert len(parts) == 5
    assert parts[0] == [0, 1, 2, 3, 4]
    assert parts[-1] == [20, 21, 22, 23, 24]
