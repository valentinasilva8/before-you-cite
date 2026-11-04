"""Model and Crossref stand-ins for tests that must not touch the network."""

import json


class _Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class ToolCall:
    def __init__(self, name, arguments, call_id="call-1"):
        self.id = call_id
        self.function = _Function(name, arguments if isinstance(arguments, str) else json.dumps(arguments))


class Reply:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        dumped = []
        for call in self.tool_calls or []:
            dumped.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
            )
        return {"role": "assistant", "content": self.content, "tool_calls": dumped or None}


class FakeCrossref:
    def __init__(self, events=None, error=None, clear_match=False):
        self.events = events
        self.error = error
        self.clear_match = clear_match
        self.work_calls = []
        self.title_calls = []
        self.agency_calls = []

    def doi_agency(self, doi):
        self.agency_calls.append(doi)
        if self.events is not None:
            self.events.append("agency")
        return json.dumps(
            {
                "ok": True,
                "doi": doi,
                "registration": "crossref",
                "agency_id": "crossref",
                "agency_label": "Crossref",
                "source": "crossref",
                "crossref_http_status": 200,
            }
        )

    def get_work(self, doi):
        self.work_calls.append(doi)
        if self.events is not None:
            self.events.append("crossref")
        if self.error:
            return json.dumps(
                {
                    "ok": False,
                    "error": self.error,
                    "doi": doi,
                    "snapshot": "fb5f174f8476824deaf340693f9a819ce5e29ded",
                    "snapshot_short": "fb5f174f",
                }
            )
        return json.dumps(
            {
                "ok": True,
                "doi": doi,
                "title": "Fixture title",
                "publisher": "Fixture Publisher",
                "container_title": "Fixture Journal",
                "issn": ["0000-0000"],
                "type": "journal-article",
                "updated_by": [],
                "update_to": [],
                "relation": [],
                "snapshot": "fb5f174f8476824deaf340693f9a819ce5e29ded",
                "snapshot_short": "fb5f174f",
                "retrieved_at": "2026-11-04T00:00:00Z",
            }
        )

    def search_title(self, title):
        self.title_calls.append(title)
        if self.events is not None:
            self.events.append("crossref-title")
        if self.error:
            return json.dumps({"ok": False, "error": self.error, "query": title})
        return json.dumps(
            {
                "ok": True,
                "query": title,
                "clear_match": self.clear_match,
                "candidates": [
                    {
                        "doi": "10.9999/guess",
                        "title": title + " and more words",
                        "publisher": "Fixture Publisher",
                    }
                ],
                "snapshot": "fb5f174f8476824deaf340693f9a819ce5e29ded",
                "snapshot_short": "fb5f174f",
                "retrieved_at": "2026-11-04T00:00:00Z",
            }
        )


class TracingCatalog:
    def __init__(self, inner, events):
        self._inner = inner
        self.events = events

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def lookup_doi(self, doi):
        self.events.append("csv")
        return self._inner.lookup_doi(doi)

    def lookup_title(self, title):
        self.events.append("csv")
        return self._inner.lookup_title(title)


DRAFT = (
    "Record 70104 in snapshot fb5f174f is a Retraction for DOI 10.3390/nano10122325. "
    "Record 99999999 was made up. "
    "The paper is fine. "
    "DOI 10.1234/notreal was retracted. "
    "Record 70548 is a Retraction."
)


def scripted_complete(draft=DRAFT):
    """Lead submits an empty dispatch. Researchers stop without tools. The writer returns draft."""
    state = {"lead": 0, "writer_tools": []}

    def complete(messages, tools):
        system = messages[0]["content"]
        if system.startswith("You are the lead"):
            state["lead"] += 1
            if state["lead"] == 1:
                return Reply("", [ToolCall("submit_plan", {"action": "dispatch", "references": []})])
            return Reply("planned")
        if system.startswith("You are the writer"):
            state["writer_tools"].append(tools)
            return Reply(draft)
        return Reply("done")

    complete.state = state
    return complete
