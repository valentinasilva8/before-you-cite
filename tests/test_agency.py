import json

import httpx

from retraction_agent.crossref import CrossrefClient

FAKE = "10.9999/not-a-real-work-before-you-cite"
# Logged 2026-11-04. Content-Type was application/json. The body was this text, not an object.
FAKE_BODY = "Resource not found."
DOI_ORG = [{"DOI": FAKE, "status": "DOI does not exist"}]


def _client(handler):
    return CrossrefClient(
        mailto="vt2450@columbia.edu",
        user_agent="before-you-cite-test",
        timeout_s=8,
        doi_rps=1000,
        transport=httpx.MockTransport(handler),
        sleep=lambda delay: None,
        clock=lambda: 0.0,
    )


def test_fake_doi_404_is_text_then_doi_org_says_it_does_not_exist():
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        if request.url.host == "api.crossref.org":
            return httpx.Response(
                404,
                content=FAKE_BODY.encode(),
                headers={"content-type": "application/json;charset=utf-8"},
            )
        return httpx.Response(200, json=DOI_ORG)

    body = json.loads(_client(handler).doi_agency(FAKE))
    assert body["ok"] is True
    assert body["registration"] == "not_registered"
    assert body["crossref_http_status"] == 404
    assert body["crossref_body"] == FAKE_BODY
    assert body["registration_status"] == "DOI does not exist"
    assert body["fallback_http_status"] == 200
    assert "DOI does not exist" in body["fallback_body"]
    assert body["source"] == "doi.org"
    assert "/works/10.9999/not-a-real-work-before-you-cite/agency" in seen[0]
    assert "doi.org/ra/" in seen[1]


def test_crossref_agency_json_does_not_call_doi_org():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request.url.host)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "message-type": "work-agency",
                "message": {"DOI": "10.3390/nano10122325", "agency": {"id": "crossref", "label": "Crossref"}},
            },
        )

    body = json.loads(_client(handler).doi_agency("10.3390/nano10122325"))
    assert body["registration"] == "crossref"
    assert body["agency_id"] == "crossref"
    assert seen == ["api.crossref.org"]


def test_datacite_agency_is_other_not_suspicious():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "message": {
                    "DOI": "10.48550/arxiv.1706.03762",
                    "agency": {"id": "datacite", "label": "DataCite"},
                },
            },
        )

    body = json.loads(_client(handler).doi_agency("10.48550/arXiv.1706.03762"))
    assert body["registration"] == "other"
    assert body["agency_id"] == "datacite"
    assert body["agency_label"] == "DataCite"
