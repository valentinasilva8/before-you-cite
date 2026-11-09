"""Ask the configured model with no tools. Prints the answer, or exits 2 when Vertex auth is missing.

The README keeps a placeholder until this command is run where the Cloud Run service account can call Vertex.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retraction_agent.config import load_config
from retraction_agent.llm import complete
from retraction_agent.samples import SAMPLE_1_TURN_1, SAMPLE_2, SAMPLE_3

PROMPTS = [
    ("Sample 1 turn 1", SAMPLE_1_TURN_1),
    ("Sample 2", SAMPLE_2),
    ("Sample 3", SAMPLE_3),
]


def main() -> None:
    config = load_config()
    system = (
        "Answer from what you already know. You have no tools and no extract. "
        "Do not invent record ids, notice DOIs, or exact row counts."
    )
    try:
        for label, prompt in PROMPTS:
            reply = complete(
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                None,
            )
            print(f"## {label}")
            print(reply.content or "")
            print()
    except Exception as exc:
        print(f"NO_TOOLS_UNAVAILABLE {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
