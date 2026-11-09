"""Before You Cite: a retraction-audit chat over one frozen extract and live Crossref."""

import logging
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from retraction_agent.catalog import get_catalog
from retraction_agent.orchestrate import handle_turn
from retraction_agent.reading import parse_message
from retraction_agent.samples import PROMPTS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("before-you-cite")

CATALOG = get_catalog()
log.info("loaded %s rows from snapshot %s", CATALOG.row_count, CATALOG.commit_short)

# session_id -> messages plus the harness state for in-session title confirmation.
sessions: dict[str, dict] = {}

app = FastAPI(title="Before You Cite")
FRONTEND = Path(__file__).parent / "frontend"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ToolCallOut(BaseModel):
    agent: str
    name: str
    args: dict
    result: str


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list[ToolCallOut] = Field(default_factory=list)


class ParsedItem(BaseModel):
    raw: str = ""
    title: str = ""
    authors: str = ""
    year: str = ""
    doi: str = ""
    url: str = ""
    parsed_by: str
    notes: list[str] = Field(default_factory=list)


class ParseRequest(BaseModel):
    message: str


class ParseResponse(BaseModel):
    items: list[ParsedItem] = Field(default_factory=list)
    truncated: bool = False


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "rows": CATALOG.row_count,
        "commit": CATALOG.commit,
        "commit_short": CATALOG.commit_short,
        "committed_at": CATALOG.manifest["committed_at"],
        "sha256": CATALOG.manifest["sha256"],
    }


@app.get("/samples")
def samples():
    return {
        "commit_short": CATALOG.commit_short,
        "committed_at": CATALOG.manifest["committed_at"],
        "rows": CATALOG.row_count,
        "prompts": PROMPTS,
    }


@app.post("/parse", response_model=ParseResponse)
def parse(request: ParseRequest):
    return parse_message(request.message)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    session = sessions.setdefault(session_id, {"messages": []})
    result = handle_turn(session, request.message)
    return ChatResponse(response=result["response"], session_id=session_id, tool_calls=result["tool_calls"])


@app.post("/clear")
def clear(session_id: str | None = None):
    if session_id:
        sessions.pop(session_id, None)
    return {"status": "ok"}


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", NoCacheStaticFiles(directory=FRONTEND), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
