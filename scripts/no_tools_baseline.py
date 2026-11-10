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
from retraction_agent.samples import SAMPLE_1_TURN_1, SAMPLE_2, SAMPLE_3

# README Samples 1, 2, and 3. Sample 1 has a second turn; this run uses turn 1 only.
PROMPTS = [SAMPLE_1_TURN_1, SAMPLE_2, SAMPLE_3]

SYSTEM = (
    "Answer from what you already know. You have no tools and no extract. "
    "Do not invent record ids, notice DOIs, or exact row counts."
)

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "no_tools_baseline.md"


def render_samples(pairs: list[tuple[str, str]]) -> str:
    blocks = []
    for index, (prompt, answer) in enumerate(pairs, start=1):
        blocks.append(f"## Sample {index}\n\n{prompt}\n\n{answer}")
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
    pairs: list[tuple[str, str]] = []
    try:
        for prompt in PROMPTS:
            reply = complete(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                None,
            )
            answer = reply.content if isinstance(reply.content, str) else ""
            pairs.append((prompt, answer))
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
