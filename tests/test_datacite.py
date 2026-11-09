import json

import httpx

from retraction_agent.datacite import DataCiteClient


class Clock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, delay):
        self.slept.append(delay)
        self.now += delay


ATTENTION = {
    "data": {
        "id": "10.48550/arxiv.1706.03762",
        "type": "dois",
        "attributes": {
            "doi": "10.48550/arxiv.1706.03762",
            "titles": [{"title": "Attention Is All You Need"}],
            "creators": [
                {"name": "Vaswani, Ashish", "givenName": "Ashish", "familyName": "Vaswani"}
            ],
            "publicationYear": 2017,
        },
    }
}
MISSING = {"errors": [{"status": "404", "title": "The resource you are looking for doesn't exist."}]}


def test_real_arxiv_shape_and_missing_rate_limit_header():
    def handler(request: httpx.Request):
        assert request.url.path == "/dois/10.48550/arxiv.1706.03762"
        return httpx.Response(200, json=ATTENTION, headers={"content-type": "application/json; charset=utf-8"})

    client = DataCiteClient(rps=1000, timeout_s=8, transport=httpx.MockTransport(handler), sleep=lambda _d: None, clock=lambda: 0.0)
    body = json.loads(client.get_work("10.48550/arXiv.1706.03762v2"))
    assert body["ok"] is True
    assert body["title"] == "Attention Is All You Need"
    assert body["first_author"] == "Vaswani"
    assert body["year"] == 2017
    assert body["rate_limit_headers"] == {}
    assert body["rate_limit_headers_present"] is False
    assert "titles" in body["attribute_keys"]


def test_fake_arxiv_id_is_the_logged_404_object():
    def handler(request: httpx.Request):
        return httpx.Response(404, json=MISSING)

    client = DataCiteClient(rps=1000, timeout_s=8, transport=httpx.MockTransport(handler), sleep=lambda _d: None, clock=lambda: 0.0)
    body = json.loads(client.get_work("10.48550/arXiv.9999.99999"))
    assert body["ok"] is False
    assert body["http_status"] == 404
    assert body["errors"][0]["title"] == "The resource you are looking for doesn't exist."
    assert body["rate_limit_headers_present"] is False
    assert "title" not in body


def test_throttle_comes_from_config_when_no_header_is_sent():
    clock = Clock()

    def handler(request: httpx.Request):
        return httpx.Response(200, json=ATTENTION)

    client = DataCiteClient(rps=2, timeout_s=8, transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock.clock)
    client.get_work("10.48550/arxiv.1706.03762")
    client.get_work("10.48550/arxiv.1706.03762")
    assert clock.slept[0] == 0.5
