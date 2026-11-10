"""The README Samples section and the chips are the same four prompts, in the same order."""

import re
from pathlib import Path

from retraction_agent.samples import PROMPTS

ROOT = Path(__file__).resolve().parents[1]
HEADINGS = ["DOI link", "Reference with DOI", "Reading list (8)", "Publisher question"]


def _shown(text: str) -> str:
    """The prompt text, without a single trailing newline.

    A markdown fence ends its last line with a newline before the closing fence.
    The reading-list prompt is a triple-quoted string, so it carries that same newline.
    The other three prompts do not. One trailing newline is not another line of the prompt.
    """
    if text.endswith("\n"):
        return text[:-1]
    return text


def test_readme_sample_prompts_match_the_chips():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Samples", 1)[1].split("## Known limits", 1)[0]
    headings = re.findall(r"^### \d+\. (.+)$", section, flags=re.MULTILINE)
    fences = re.findall(r"```\n(.*?)```", section, flags=re.DOTALL)
    prompts = list(PROMPTS.values())
    assert headings == HEADINGS
    assert list(PROMPTS) == [
        "doi_link",
        "reference_with_doi",
        "reading_list",
        "publisher_question",
    ]
    assert len(fences) == len(prompts) == 4
    assert [_shown(fence) for fence in fences] == [_shown(prompt) for prompt in prompts]
