"""One Crossref call per DOI and one bibliographic list call per title."""

import json
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from retraction_agent.catalog import get_catalog
from retraction_agent.config import limits, load_config
from retraction_agent.normalize import normalize_doi, normalize_title

API = "https://api.crossref.org/works"


class RateLimiter:
    def __init__(self, rps: float, sleep=time.sleep, clock=time.monotonic):
        self.interval = 1.0 / rps if rps else 0.0
        self.sleep = sleep
        self.clock = clock
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = self.clock()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            self.sleep(delay)


class CrossrefClient:
    def __init__(
        self,
        mailto: str | None = None,
        user_agent: str | None = None,
        timeout_s: float | None = None,
        list_rps: float | None = None,
        doi_rps: float | None = None,
        title_rows: int | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        config = load_config()
        cap = limits()
        urls = config.get("urls") or {}
        self.works_url = urls.get("crossref_works") or API
        self.agency_url = urls.get("crossref_agency") or (API + "/{doi}/agency")
        self.ra_url = urls.get("doi_registration_agency") or "https://doi.org/ra/{doi}"
        self.mailto = mailto or config["crossref_mailto"]
        self.user_agent = user_agent or config["crossref_user_agent"]
        self.timeout_s = timeout_s if timeout_s is not None else cap["crossref_timeout_s"]
        self.title_rows = title_rows or cap["crossref_title_rows"]
        self.list_limiter = RateLimiter(list_rps if list_rps is not None else cap["crossref_list_rps"], sleep, clock)
        self.doi_limiter = RateLimiter(doi_rps if doi_rps is not None else cap["crossref_doi_rps"], sleep, clock)
        self.sleep = sleep
        timeout = httpx.Timeout(self.timeout_s)
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        )

    def close(self) -> None:
        self._client.close()

    def get_work(self, doi: str) -> str:
        """One single-work GET. No second updates-filter call."""
        norm = normalize_doi(doi)
        if not norm:
            return self._dump({"ok": False, "error": "empty_or_unavailable_doi", "doi": doi})
        url = f"{self.works_url}/{quote(norm, safe='/')}"
        payload = self._request(url, {"mailto": self.mailto}, kind="doi")
        if not payload.get("ok"):
            payload["doi"] = norm
            return self._dump(payload)
        message = payload.pop("message")
        return self._dump({"ok": True, "doi": norm, **_work_fields(message), "retrieved_at": _now()})

    def search_title(self, title: str) -> str:
        """One list call: query.bibliographic. Clear only when the top title matches exactly."""
        params = {
            "query.bibliographic": title,
            "rows": self.title_rows,
            "mailto": self.mailto,
            "select": "DOI,title,author,issued,publisher,container-title,type,score",
        }
        payload = self._request(self.works_url, params, kind="list")
        if not payload.get("ok"):
            payload["query"] = title
            return self._dump(payload)
        message = payload.pop("message")
        items = message.get("items") or []
        candidates = []
        for item in items:
            item_title = _first(item.get("title"))
            first_author, _names = _people(item)
            candidates.append(
                {
                    "doi": normalize_doi(item.get("DOI")) or item.get("DOI"),
                    "title": item_title,
                    "first_author": first_author,
                    "year": _issued_year(item),
                    "publisher": item.get("publisher"),
                    "container_title": _first(item.get("container-title")),
                    "type": item.get("type"),
                    "score": item.get("score"),
                }
            )
        return self._dump(
            {
                "ok": True,
                "query": title,
                "clear_match": _clear_match(title, candidates),
                "candidates": candidates,
                "retrieved_at": _now(),
                "note": (
                    "Do not accept the closest-ranked hit on rank alone. Compare its title, first author, "
                    "and year with the pasted citation. A clear_match flag is title equality only."
                ),
            }
        )

    def doi_agency(self, doi: str) -> str:
        """One agency lookup. A Crossref 404 body is plain text, so this does not assume JSON."""
        norm = normalize_doi(doi)
        if not norm:
            return self._dump({"ok": False, "error": "empty_or_unavailable_doi", "doi": doi})
        primary_url = self.agency_url.format(doi=quote(norm, safe="/"))
        primary = self._raw(primary_url, {"mailto": self.mailto}, kind="doi")
        if primary.get("error") in {"timeout", "429"}:
            return self._dump(
                {
                    "ok": False,
                    "doi": norm,
                    "error": primary["error"],
                    "crossref_http_status": primary.get("status"),
                    "crossref_body": primary.get("body"),
                }
            )
        interpreted = _agency_from_crossref(primary.get("json"))
        if interpreted:
            return self._dump(
                {
                    "ok": True,
                    "doi": norm,
                    "source": "crossref",
                    "crossref_http_status": primary.get("status"),
                    "crossref_body": primary.get("body"),
                    **interpreted,
                }
            )
        fallback_url = self.ra_url.format(doi=quote(norm, safe="/"))
        secondary = self._raw(fallback_url, None, kind="doi", accept="application/json")
        fallback = _agency_from_doi_org(secondary.get("json"))
        if secondary.get("error") in {"timeout", "429"} and not fallback.get("registration"):
            return self._dump(
                {
                    "ok": False,
                    "doi": norm,
                    "error": secondary["error"],
                    "crossref_http_status": primary.get("status"),
                    "crossref_body": primary.get("body"),
                    "fallback_http_status": secondary.get("status"),
                    "fallback_body": secondary.get("body"),
                }
            )
        ok = bool(fallback.get("registration"))
        return self._dump(
            {
                "ok": ok,
                "doi": norm,
                "source": "doi.org" if ok else None,
                "crossref_http_status": primary.get("status"),
                "crossref_body": primary.get("body"),
                "fallback_http_status": secondary.get("status"),
                "fallback_body": secondary.get("body"),
                "error": None if ok else (secondary.get("error") or "unparsed"),
                **fallback,
            }
        )

    def _request(self, url: str, params: dict, *, kind: str) -> dict:
        limiter = self.list_limiter if kind == "list" else self.doi_limiter
        try:
            limiter.wait()
            response = self._client.get(url, params=params)
            if response.status_code == 429:
                self.sleep(1.0)
                limiter.wait()
                response = self._client.get(url, params=params)
                if response.status_code == 429:
                    return {"ok": False, "error": "429"}
            if response.status_code != 200:
                return {"ok": False, "error": "http", "status": response.status_code}
            body = response.json()
        except httpx.TimeoutException:
            return {"ok": False, "error": "timeout"}
        except httpx.HTTPError:
            return {"ok": False, "error": "http"}
        except json.JSONDecodeError:
            return {"ok": False, "error": "http"}
        message = body.get("message")
        if not isinstance(message, dict):
            return {"ok": False, "error": "http"}
        return {"ok": True, "message": message}

    def _raw(self, url: str, params: dict | None, *, kind: str, accept: str | None = None) -> dict:
        limiter = self.list_limiter if kind == "list" else self.doi_limiter
        headers = {"Accept": accept} if accept else None
        try:
            limiter.wait()
            response = self._get(url, params, headers)
            if response.status_code == 429:
                self.sleep(1.0)
                limiter.wait()
                response = self._get(url, params, headers)
                if response.status_code == 429:
                    return {"error": "429", "status": 429, "body": (response.text or "")[:800], "json": _maybe_json(response.text)}
            return {
                "status": response.status_code,
                "body": (response.text or "")[:800],
                "json": _maybe_json(response.text),
                "content_type": response.headers.get("content-type"),
            }
        except httpx.TimeoutException:
            return {"error": "timeout", "json": None, "body": None}
        except httpx.HTTPError:
            return {"error": "http", "json": None, "body": None}

    def _get(self, url: str, params: dict | None, headers: dict | None):
        return self._client.get(url, params=params, headers=headers)

    def _dump(self, payload: dict) -> str:
        try:
            catalog = get_catalog()
            payload.setdefault("snapshot", catalog.commit)
            payload.setdefault("snapshot_short", catalog.commit_short)
        except Exception:
            payload.setdefault("snapshot", load_config().get("snapshot_commit", ""))
        payload.pop("abstract", None)
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
        if "abstract" in payload:
            encoded = encoded.replace(str(payload.get("abstract") or ""), "")
        return encoded


def _work_fields(message: dict) -> dict:
    updated_by = [_update(item) for item in message.get("updated-by") or [] if isinstance(item, dict)]
    update_to = [_update(item) for item in message.get("update-to") or [] if isinstance(item, dict)]
    first_author, authors = _people(message)
    return {
        "title": _first(message.get("title")),
        "first_author": first_author,
        "authors": authors,
        "year": _issued_year(message),
        "publisher": message.get("publisher"),
        "container_title": _first(message.get("container-title")),
        "issn": list(message.get("ISSN") or []),
        "type": message.get("type"),
        "updated_by": updated_by,
        "update_to": update_to,
        "relation": _relations(message.get("relation")),
        "date_guidance": (
            "Prefer a retraction-watch updated-by date and record-id. "
            "A publisher updated-by date can be the article date, not the notice. "
            "A has-review relation is a review link, not a notice. "
            "A RETRACTED: title prefix is not a reason."
        ),
    }


def _update(element: dict) -> dict:
    updated = element.get("updated") or {}
    parts = (updated.get("date-parts") or [[]])[0] or []
    date = None
    if len(parts) >= 3 and all(isinstance(part, int) for part in parts[:3]):
        date = f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
    elif parts:
        date = "-".join(str(part) for part in parts)
    record_id = element.get("record-id")
    if record_id is not None:
        record_id = str(record_id)
    return {
        "doi": element.get("DOI"),
        "type": element.get("type"),
        "label": element.get("label"),
        "source": element.get("source"),
        "date": date,
        "record_id": record_id,
    }


def _relations(relation: dict | None) -> list[dict]:
    if not isinstance(relation, dict):
        return []
    found = []
    for name, entries in relation.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            found.append({"relation": name, "id-type": entry.get("id-type"), "id": entry.get("id")})
            if len(found) >= 30:
                return found
    return found


def _clear_match(query: str, candidates: list[dict]) -> bool:
    if not candidates:
        return False
    wanted = normalize_title(query)
    top = normalize_title(candidates[0].get("title"))
    if not wanted or top != wanted:
        return False
    top_doi = candidates[0].get("doi")
    for other in candidates[1:]:
        if normalize_title(other.get("title")) == wanted and other.get("doi") != top_doi:
            return False
    return True


def _agency_from_crossref(parsed) -> dict | None:
    if not isinstance(parsed, dict):
        return None
    message = parsed.get("message")
    if not isinstance(message, dict):
        return None
    agency = message.get("agency")
    if not isinstance(agency, dict) or not agency.get("id"):
        return None
    agency_id = str(agency.get("id"))
    registration = "crossref" if agency_id.casefold() == "crossref" else "other"
    return {"registration": registration, "agency_id": agency_id, "agency_label": agency.get("label")}


def _agency_from_doi_org(parsed) -> dict:
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], dict):
        return {"registration": None}
    item = parsed[0]
    status = str(item.get("status") or "")
    ra = item.get("RA")
    if ra:
        registration = "crossref" if str(ra).casefold() == "crossref" else "other"
        return {"registration": registration, "agency_id": str(ra).casefold(), "agency_label": ra}
    if "does not exist" in status.casefold():
        return {
            "registration": "not_registered",
            "agency_id": None,
            "agency_label": None,
            "registration_status": status,
        }
    return {"registration": None}


def _people(message: dict) -> tuple[str | None, list[str]]:
    authors = message.get("author") or []
    names = []
    first = None
    if not isinstance(authors, list):
        return None, []
    for person in authors:
        if not isinstance(person, dict):
            continue
        family = person.get("family") or ""
        given = person.get("given") or ""
        if person.get("sequence") == "first" and family and first is None:
            first = family
        elif first is None and family:
            first = family
        if family or given:
            names.append(" ".join(part for part in (given, family) if part))
    return first, names[:8]


def _issued_year(message: dict):
    issued = message.get("issued") or message.get("published") or {}
    if not isinstance(issued, dict):
        return None
    parts = (issued.get("date-parts") or [[]])[0] or []
    if parts and isinstance(parts[0], int):
        return parts[0]
    return None


def _maybe_json(text: str | None):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _first(value) -> str | None:
    if isinstance(value, list):
        return value[0] if value else None
    if isinstance(value, str):
        return value
    return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_CLIENT = None


def get_client() -> CrossrefClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = CrossrefClient()
    return _CLIENT
