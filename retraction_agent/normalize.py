"""DOI, title, date, and reason normalization for the frozen extract."""

import re
from datetime import datetime

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)
_EMPTY_DOI = {"", "unavailable", "nan", "none", "null", "n/a", "na"}
_DATE_FORMATS = ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y")
_WS = re.compile(r"\s+")
_ARXIV_VERSION = re.compile(r"(?i)^(10\.48550/arxiv\..+?)v\d+$")
_ARXIV_ABS = re.compile(
    r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?",
    re.IGNORECASE,
)
_ARXIV_BARE = re.compile(
    r"\barXiv[:\s]+([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b",
    re.IGNORECASE,
)
_ARXIV_DOI = re.compile(
    r"10\.48550/arxiv\.([0-9]{4}\.[0-9]{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?",
    re.IGNORECASE,
)


def normalize_doi(value: str | None) -> str | None:
    """Lowercase a DOI and strip a resolver prefix. Blank and unavailable become None."""
    if value is None:
        return None
    text = str(value).strip()
    lowered = text.casefold()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            lowered = text.casefold()
            break
    text = text.strip().strip(".")
    if text.casefold() in _EMPTY_DOI:
        return None
    text = _ARXIV_VERSION.sub(r"\1", text)
    return text.casefold()


def arxiv_doi_from_text(value: str | None) -> str | None:
    """Turn an arXiv abs URL or a bare arXiv id into a DataCite DOI. Drop a v2-style suffix."""
    if not value:
        return None
    for pattern in (_ARXIV_ABS, _ARXIV_DOI, _ARXIV_BARE):
        match = pattern.search(value)
        if match:
            return normalize_doi(f"10.48550/arXiv.{match.group(1)}")
    return None


def normalize_title(value: str | None) -> str:
    """Collapse whitespace and casefold. Punctuation stays, so a shortened title does not match."""
    return _WS.sub(" ", (value or "").strip()).casefold()


def parse_us_date(value: str | None) -> str | None:
    """Parse M/D/YYYY from this extract. 2/6/2010 is February 6, not June 2."""
    text = (value or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def split_semicolon(value: str | None) -> list[str]:
    """Split a semicolon list and drop the empty token left by a trailing semicolon."""
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def clean_pubmed(value: str | None) -> str | None:
    text = (value or "").strip()
    if text in {"", "0"}:
        return None
    return text
