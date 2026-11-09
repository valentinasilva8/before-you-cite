"""One public DataCite GET per DOI. Anonymous calls did not send a rate-limit header."""

import json
import time
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from retraction_agent.config import limits, load_config
from retraction_agent.crossref import RateLimiter
from retraction_agent.normalize import normalize_doi

# Measured 2026-11-04: GET /dois/10.48550/arxiv.1706.03762 is 200 with data.attributes.
# GET /dois/10.48550/arXiv.9999.99999 is 404 {"errors":[{"status":"404","title":"...doesn't exist."}]}.
# Neither response included a rate-limit header, so the throttle is the config value.


class DataCiteClient:
    def __init__(
        self,
        base_template: str | None = None,
        rps: float | None = None,
        timeout_s: float | None = None,
        user_agent: str | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        config = load_config()
        cap = limits()
        urls = config.get("urls") or {}
        self.template = base_template or urls.get("datacite_doi") or "https://api.datacite.org/dois/{doi}"
        self.rps = rps if rps is not None else cap["datacite_rps"]
        self.timeout_s = timeout_s if timeout_s is not None else cap["crossref_timeout_s"]
        self.limiter = RateLimiter(self.rps, sleep, clock)
        self.sleep = sleep
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(self.timeout_s),
            follow_redirects=True,
            headers={
                "User-Agent": user_agent or config["crossref_user_agent"],
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def get_work(self, doi: str) -> str:
        norm = normalize_doi(doi)
        if not norm:
            return _dump({"ok": False, "error": "empty_or_unavailable_doi", "doi": doi, "throttle_rps": self.rps})
        url = self.template.format(doi=quote(norm, safe="/"))
        raw = self._raw(url)
        payload = {
            "doi": norm,
            "throttle_rps": self.rps,
            "http_status": raw.get("status"),
            "rate_limit_headers": raw.get("rate_limit_headers") or {},
            "rate_limit_headers_present": bool(raw.get("rate_limit_headers")),
            "retrieved_at": _now(),
        }
        if raw.get("error") in {"timeout", "429"}:
            payload["ok"] = False
            payload["error"] = raw["error"]
            payload["body"] = raw.get("body")
            return _dump(payload)
        parsed = raw.get("json")
        if raw.get("status") == 200 and isinstance(parsed, dict) and isinstance(parsed.get("data"), dict):
            data = parsed["data"]
            attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
            title, first_author, year = _identity(attributes)
            payload.update(
                {
                    "ok": True,
                    "response_keys": sorted(parsed.keys()),
                    "data_keys": sorted(data.keys()),
                    "attribute_keys": sorted(attributes.keys()),
                    "title": title,
                    "first_author": first_author,
                    "year": year,
                }
            )
            return _dump(payload)
        payload["ok"] = False
        if isinstance(parsed, dict) and isinstance(parsed.get("errors"), list):
            payload["errors"] = parsed["errors"][:5]
        else:
            payload["body"] = raw.get("body")
            payload["error"] = raw.get("error") or "http"
        return _dump(payload)

    def _raw(self, url: str) -> dict:
        try:
            self.limiter.wait()
            response = self._client.get(url)
            if response.status_code == 429:
                self.sleep(1.0)
                self.limiter.wait()
                response = self._client.get(url)
                if response.status_code == 429:
                    return {
                        "error": "429",
                        "status": 429,
                        "body": (response.text or "")[:500],
                        "json": _maybe_json(response.text),
                        "rate_limit_headers": _rate_headers(response),
                    }
            return {
                "status": response.status_code,
                "body": (response.text or "")[:800],
                "json": _maybe_json(response.text),
                "rate_limit_headers": _rate_headers(response),
            }
        except httpx.TimeoutException:
            return {"error": "timeout", "json": None, "body": None, "rate_limit_headers": {}}
        except httpx.HTTPError:
            return {"error": "http", "json": None, "body": None, "rate_limit_headers": {}}


def _identity(attributes: dict) -> tuple[str | None, str | None, int | None]:
    titles = attributes.get("titles") or []
    title = None
    if titles and isinstance(titles[0], dict):
        title = titles[0].get("title")
    creators = attributes.get("creators") or []
    first = None
    if creators and isinstance(creators[0], dict):
        first = creators[0].get("familyName")
        if not first and creators[0].get("name"):
            first = str(creators[0]["name"]).split(",")[0].strip()
    year = attributes.get("publicationYear")
    if isinstance(year, str) and year.isdigit():
        year = int(year)
    if not isinstance(year, int):
        year = None
    return title, first, year


def _rate_headers(response: httpx.Response) -> dict:
    found = {}
    for key, value in response.headers.items():
        lowered = key.lower()
        if "ratelimit" in lowered or "rate-limit" in lowered or "retry-after" in lowered:
            found[key] = value
    return found


def _maybe_json(text: str | None):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_CLIENT = None


def get_datacite() -> DataCiteClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = DataCiteClient()
    return _CLIENT
