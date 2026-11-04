"""Load the gzipped Retraction Watch extract once and index it."""

import csv
import gzip
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from retraction_agent.config import ROOT, limits, load_config
from retraction_agent.normalize import (
    clean_pubmed,
    normalize_doi,
    normalize_title,
    parse_us_date,
    split_semicolon,
)

REQUIRED_COLUMNS = (
    "Record ID",
    "Title",
    "Journal",
    "Publisher",
    "Author",
    "URLS",
    "RetractionDate",
    "RetractionDOI",
    "RetractionPubMedID",
    "OriginalPaperDate",
    "OriginalPaperDOI",
    "OriginalPaperPubMedID",
    "RetractionNature",
    "Reason",
    "Paywalled",
    "Notes",
)

DATA_LIMIT = (
    "No record in this extract is a data limit. It is not a judgment that the work "
    "is reliable, peer-reviewed, or fine."
)

_CATALOG = None


def verify_snapshot(raw: bytes, expected_sha: str, expected_size: int) -> None:
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha:
        raise ValueError(f"Retraction Watch SHA-256 mismatch: {digest}")
    if len(raw) != expected_size:
        raise ValueError(f"Retraction Watch byte size mismatch: {len(raw)} != {expected_size}")


class Catalog:
    def __init__(self, manifest: dict, rows: dict[str, dict], indexes: dict):
        self.manifest = manifest
        self.rows = rows
        self.by_original_doi = indexes["original"]
        self.by_notice_doi = indexes["notice"]
        self.by_title = indexes["title"]
        self.by_journal = indexes["journal"]
        self.by_publisher = indexes["publisher"]
        self.by_author = indexes["author"]
        self.journal_casefold = indexes["journal_casefold"]
        self.publisher_casefold = indexes["publisher_casefold"]
        self.row_count = len(rows)
        self.commit = manifest["commit"]
        self.commit_short = manifest["commit_short"]
        self.nature_counts = dict(manifest["nature_counts"])

    @classmethod
    def load(cls, root: Path | None = None) -> "Catalog":
        config = load_config()
        base = root or ROOT
        manifest_path = base / config["manifest_path"]
        snapshot_path = base / config["snapshot_path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        compressed = snapshot_path.read_bytes()
        raw = gzip.decompress(compressed)
        verify_snapshot(raw, manifest["sha256"], manifest["byte_size"])
        gzip_sha = hashlib.sha256(compressed).hexdigest()
        if gzip_sha != manifest["gzip_sha256"]:
            raise ValueError(f"gzip SHA-256 mismatch: {gzip_sha}")
        rows, indexes, natures = _parse(raw)
        if len(rows) != manifest["row_count"]:
            raise ValueError(f"row count mismatch: {len(rows)} != {manifest['row_count']}")
        if dict(natures) != manifest["nature_counts"]:
            raise ValueError(f"nature counts mismatch: {dict(natures)}")
        return cls(manifest, rows, indexes)

    def _snapshot_fields(self) -> dict:
        return {
            "snapshot": self.commit,
            "snapshot_short": self.commit_short,
            "data_limit": DATA_LIMIT,
        }

    def lookup_doi(self, doi: str) -> dict:
        norm = normalize_doi(doi)
        if not norm:
            return {
                **self._snapshot_fields(),
                "ok": False,
                "error": "empty_or_unavailable_doi",
                "query_doi": doi,
                "total": 0,
                "truncated": False,
                "nature_counts": {},
                "rows": [],
            }
        ids = []
        seen = set()
        for bucket in (self.by_original_doi, self.by_notice_doi):
            for record_id in bucket.get(norm, []):
                if record_id not in seen:
                    seen.add(record_id)
                    ids.append(record_id)
        return self._row_payload(query_key="query_doi", query=norm, ids=ids)

    def lookup_title(self, title: str) -> dict:
        key = normalize_title(title)
        ids = list(self.by_title.get(key, []))
        payload = self._row_payload(query_key="query", query=title, ids=ids)
        payload["normalized_title"] = key
        payload["exact_match"] = payload["total"] > 0
        return payload

    def lookup_author(self, author: str) -> dict:
        key = " ".join((author or "").split()).casefold()
        ids = list(self.by_author.get(key, []))
        payload = self._row_payload(query_key="query_author", query=author, ids=ids)
        payload["match"] = "full author token, casefold, not a substring"
        return payload

    def pattern(self, *, journal: str | None = None, publisher: str | None = None) -> dict:
        if bool(journal) == bool(publisher):
            return {
                **self._snapshot_fields(),
                "ok": False,
                "error": "pass exactly one of journal or publisher",
                "rows": 0,
            }
        field = "journal" if journal else "publisher"
        raw = journal if journal else publisher
        index = self.by_journal if journal else self.by_publisher
        casefold = self.journal_casefold if journal else self.publisher_casefold
        ids = list(index.get(raw, []))
        unique = None
        if not ids:
            options = casefold.get(raw.casefold(), [])
            if len(options) == 1 and options[0] != raw:
                unique = options[0]
        summary = _summarize(self.rows, ids, limits()["top_reason_tokens"])
        return {
            **self._snapshot_fields(),
            "ok": True,
            "field": field,
            "matched": raw if ids else raw,
            "exact": bool(ids),
            "casefold_unique": unique,
            "rows": len(ids),
            "nature_counts": summary["nature_counts"],
            "reason_tokens": summary["reason_tokens"],
            "note": (
                "These are notice rows for one exact string in this extract. "
                "A reason token is counted once per row that carries it, so token counts "
                "sum to more than the row count. One paper can be several rows. This is not a rate."
            ),
        }

    def top_publishers(self, limit: int | None = None) -> dict:
        cap = limits()
        size = cap["top_publishers"] if limit is None else max(1, min(int(limit), 20))
        ranked = sorted(self.by_publisher.items(), key=lambda item: (-len(item[1]), item[0]))
        publishers = []
        for name, ids in ranked[:size]:
            summary = _summarize(self.rows, ids, cap["top_reason_tokens"], cap["top_batch_dates"])
            publishers.append(
                {
                    "publisher": name,
                    "notice_rows": len(ids),
                    "nature_counts": summary["nature_counts"],
                    "reason_tokens": summary["reason_tokens"],
                    "batch_dates": summary["batch_dates"],
                }
            )
        return {
            **self._snapshot_fields(),
            "ok": True,
            "by": "notice rows",
            "not_a_rate": True,
            "limit": size,
            "publishers": publishers,
            "note": (
                "Ranked by notice rows in this extract, not by a rate. "
                "A reason token is counted once per row that carries it. "
                "Batch dates are the retraction dates with the most rows for that publisher string. "
                "One paper can be several rows."
            ),
        }

    def _row_payload(self, *, query_key: str, query: str, ids: list[str]) -> dict:
        cap = limits()["max_rows_returned"]
        natures = Counter(self.rows[record_id]["nature"] for record_id in ids)
        truncated = len(ids) > cap
        shown = ids[:cap]
        return {
            **self._snapshot_fields(),
            "ok": True,
            query_key: query,
            "total": len(ids),
            "truncated": truncated,
            "nature_counts": dict(sorted(natures.items())),
            "record_ids": shown,
            "rows": [] if truncated else [self.rows[record_id] for record_id in shown],
            "truncated_note": (
                "More than 25 rows matched. Totals are for the full match. "
                "Row bodies are omitted. Ask which journal or publisher to narrow to."
                if truncated
                else ""
            ),
        }


def _summarize(rows: dict, ids: list[str], reason_cap: int, date_cap: int = 0) -> dict:
    natures: Counter = Counter()
    reasons: Counter = Counter()
    dates: Counter = Counter()
    for record_id in ids:
        row = rows[record_id]
        natures[row["nature"]] += 1
        for token in row["reasons"]:
            reasons[token] += 1
        if row["retraction_date"]:
            dates[row["retraction_date"]] += 1
    payload = {
        "nature_counts": dict(sorted(natures.items())),
        "reason_tokens": [
            {"token": token, "rows": count} for token, count in reasons.most_common(reason_cap)
        ],
    }
    if date_cap:
        payload["batch_dates"] = [
            {"date": date, "iso": parse_us_date(date), "notice_rows": count}
            for date, count in dates.most_common(date_cap)
        ]
    return payload


def _parse(raw: bytes) -> tuple[dict, dict, Counter]:
    csv.field_size_limit(min(sys.maxsize, 10_000_000))
    text = raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"extract header missing columns: {missing}")
    rows: dict[str, dict] = {}
    original: dict[str, list[str]] = defaultdict(list)
    notice: dict[str, list[str]] = defaultdict(list)
    titles: dict[str, list[str]] = defaultdict(list)
    journals: dict[str, list[str]] = defaultdict(list)
    publishers: dict[str, list[str]] = defaultdict(list)
    authors: dict[str, list[str]] = defaultdict(list)
    journal_casefold: dict[str, set[str]] = defaultdict(set)
    publisher_casefold: dict[str, set[str]] = defaultdict(set)
    natures: Counter = Counter()
    for source in reader:
        record_id = (source.get("Record ID") or "").strip()
        if not record_id:
            continue
        author_tokens = split_semicolon(source.get("Author"))
        row = {
            "record_id": record_id,
            "title": " ".join((source.get("Title") or "").split()),
            "journal": (source.get("Journal") or "").strip(),
            "publisher": (source.get("Publisher") or "").strip(),
            "authors": author_tokens,
            "urls": split_semicolon(source.get("URLS")),
            "retraction_date": (source.get("RetractionDate") or "").strip(),
            "retraction_date_iso": parse_us_date(source.get("RetractionDate")),
            "retraction_doi": normalize_doi(source.get("RetractionDOI")),
            "retraction_doi_raw": (source.get("RetractionDOI") or "").strip(),
            "original_date": (source.get("OriginalPaperDate") or "").strip(),
            "original_date_iso": parse_us_date(source.get("OriginalPaperDate")),
            "original_doi": normalize_doi(source.get("OriginalPaperDOI")),
            "original_doi_raw": (source.get("OriginalPaperDOI") or "").strip(),
            "retraction_pubmed": clean_pubmed(source.get("RetractionPubMedID")),
            "original_pubmed": clean_pubmed(source.get("OriginalPaperPubMedID")),
            "nature": (source.get("RetractionNature") or "").strip(),
            "reasons": split_semicolon(source.get("Reason")),
            "paywalled": (source.get("Paywalled") or "").strip(),
            "notes_present": bool((source.get("Notes") or "").strip()),
        }
        rows[record_id] = row
        natures[row["nature"]] += 1
        if row["original_doi"]:
            original[row["original_doi"]].append(record_id)
        if row["retraction_doi"]:
            notice[row["retraction_doi"]].append(record_id)
        if row["title"]:
            titles[normalize_title(row["title"])].append(record_id)
        if row["journal"]:
            journals[row["journal"]].append(record_id)
            journal_casefold[row["journal"].casefold()].add(row["journal"])
        if row["publisher"]:
            publishers[row["publisher"]].append(record_id)
            publisher_casefold[row["publisher"].casefold()].add(row["publisher"])
        for author in author_tokens:
            authors[author.casefold()].append(record_id)
    indexes = {
        "original": dict(original),
        "notice": dict(notice),
        "title": dict(titles),
        "journal": dict(journals),
        "publisher": dict(publishers),
        "author": dict(authors),
        "journal_casefold": {key: sorted(values) for key, values in journal_casefold.items()},
        "publisher_casefold": {key: sorted(values) for key, values in publisher_casefold.items()},
    }
    return rows, indexes, natures


def get_catalog() -> Catalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = Catalog.load()
    return _CATALOG
