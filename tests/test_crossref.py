import json

import httpx

from retraction_agent.crossref import CrossrefClient, _clear_match


class Clock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, delay):
        self.slept.append(delay)
        self.now += delay


def _client(handler, clock=None, **kwargs):
    clock = clock or Clock()
    return CrossrefClient(
        mailto="vt2450@columbia.edu",
        user_agent="before-you-cite-test",
        timeout_s=8,
        list_rps=kwargs.get("list_rps", 3),
        doi_rps=kwargs.get("doi_rps", 1000),
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.clock,
    ), clock


def test_clear_match_is_exact_title_only():
    assert _clear_match("Same Title", [{"title": "Same Title", "doi": "10.1000/x"}])
    assert not _clear_match("Same", [{"title": "Same Title", "doi": "10.1000/x"}])
    assert not _clear_match(
        "Same Title",
        [{"title": "Same Title", "doi": "10.1000/a"}, {"title": "Same Title", "doi": "10.1000/b"}],
    )


def test_one_doi_get_drops_abstract_and_keeps_the_slash():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["agent"] = request.headers.get("user-agent")
        return httpx.Response(
            200,
            json={
                "message": {
                    "DOI": "10.3390/nano10122325",
                    "title": ["RETRACTED: Example"],
                    "abstract": "<jats:p>secret abstract</jats:p>",
                    "publisher": "MDPI AG",
                    "container-title": ["Nanomaterials"],
                    "ISSN": ["2079-4991"],
                    "type": "journal-article",
                    "updated-by": [
                        {"DOI": "10.3390/nano16050293", "type": "retraction", "source": "publisher", "updated": {"date-parts": [[2020, 11, 24]]}},
                        {
                            "DOI": "10.3390/nano16050293",
                            "type": "retraction",
                            "source": "retraction-watch",
                            "record-id": 70104,
                            "updated": {"date-parts": [[2026, 2, 25]]},
                        },
                    ],
                    "relation": {"has-review": [{"id-type": "doi", "id": "10.3410/example"}]},
                }
            },
        )

    client, _clock = _client(handler)
    body = json.loads(client.get_work("10.3390/nano10122325"))
    assert "/works/10.3390/nano10122325" in seen["url"]
    assert "%2F" not in seen["url"].split("?")[0]
    assert "mailto=vt2450%40columbia.edu" in seen["url"] or "mailto=vt2450@columbia.edu" in seen["url"]
    assert seen["agent"] == "before-you-cite-test"
    assert body["ok"] is True
    assert "secret" not in json.dumps(body)
    assert "abstract" not in body
    watch = [item for item in body["updated_by"] if item["source"] == "retraction-watch"]
    assert watch[0]["date"] == "2026-02-25"
    assert watch[0]["record_id"] == "70104"
    assert body["relation"][0]["relation"] == "has-review"
    assert "publisher updated-by date" in body["date_guidance"]


def test_429_retries_once():
    hits = {"n": 0}

    def handler(request: httpx.Request):
        hits["n"] += 1
        if hits["n"] == 1:
            return httpx.Response(429, json={"message": "slow"})
        return httpx.Response(200, json={"message": {"DOI": "10.1000/ok", "title": ["Ok"]}})

    client, clock = _client(handler)
    body = json.loads(client.get_work("10.1000/ok"))
    assert hits["n"] == 2
    assert 1.0 in clock.slept
    assert body["ok"] is True


def test_second_429_stops():
    hits = {"n": 0}

    def handler(request: httpx.Request):
        hits["n"] += 1
        return httpx.Response(429, json={"message": "slow"})

    client, _clock = _client(handler)
    body = json.loads(client.get_work("10.1000/ok"))
    assert hits["n"] == 2
    assert body["error"] == "429"


def test_timeout_and_list_rate():
    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("slow")

    client, _clock = _client(timeout_handler)
    assert json.loads(client.get_work("10.1000/ok"))["error"] == "timeout"

    clock = Clock()

    def ok(request: httpx.Request):
        return httpx.Response(200, json={"message": {"items": [{"DOI": "10.1000/t", "title": ["Other title"], "score": 1}]}})

    client, clock = _client(ok, clock=clock, list_rps=3)
    for _ in range(3):
        client.search_title("A title that is not exact")
    assert clock.slept[0] == pytest_approx(1 / 3)


def pytest_approx(value):
    import pytest

    return pytest.approx(value, rel=0.02)
