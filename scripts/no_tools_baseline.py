"""Ask the configured model with no tools. Prints the answers, or exits 2 when Vertex auth is missing.

The README keeps a placeholder until this command is run where the Cloud Run service account can call Vertex.
A successful run also writes docs/no_tools_baseline.md. A failed run does not write that file.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retraction_agent.config import load_config
from retraction_agent.llm import complete
from retraction_agent.samples import PROMPTS

# Chip labels, in the same order as PROMPTS. The prompt text is not copied here.
LABELS = {
    "doi_link": "DOI link",
    "reference_with_doi": "Reference with DOI",
    "reading_list": "Reading list (8)",
    "publisher_question": "Publisher question",
}

SYSTEM = (
    "Answer from what you already know. You have no tools and no extract. "
    "Do not invent record ids, notice DOIs, or exact row counts."
)

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "no_tools_baseline.md"


def render_samples(pairs: list[tuple[str, str, str]]) -> str:
    blocks = []
    for label, prompt, answer in pairs:
        blocks.append(f"## {label}\n\n{prompt}\n\n{answer}")
    return "\n\n".join(blocks) + "\n"


def render_document(model: str, vertex_location: str, run_at: datetime, body: str) -> str:
    stamp = run_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    header = (
        "# No-tools baseline\n\n"
        f"Model: {model}\n\n"
        f"vertex_location: {vertex_location}\n\n"
        f"Run: {stamp}\n\n"
    )
    return header + body


def main() -> None:
    config = load_config()
    chips = [(LABELS[key], PROMPTS[key]) for key in PROMPTS]
    pairs: list[tuple[str, str, str]] = []
    try:
        for label, prompt in chips:
            reply = complete(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                None,
            )
            answer = reply.content if isinstance(reply.content, str) else ""
            pairs.append((label, prompt, answer))
    except Exception as exc:
        print(f"NO_TOOLS_UNAVAILABLE {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
    body = render_samples(pairs)
    print(body, end="")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        render_document(config["model"], config["vertex_location"], datetime.now(timezone.utc), body),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
