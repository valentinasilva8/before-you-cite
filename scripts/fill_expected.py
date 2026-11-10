"""Write data/expected_samples.json from the frozen extract. Not used during a request."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retraction_agent.catalog import get_catalog
from retraction_agent.config import ROOT
from retraction_agent.samples import sample_facts


def main() -> None:
    facts = sample_facts(get_catalog())
    path = ROOT / "data" / "expected_samples.json"
    path.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(render(facts))


def render(facts: dict) -> str:
    nano = facts["doi_link"]["nano"]
    snap = facts["snapshot"]
    lines = [
        f"Snapshot `{snap['commit_short']}` ({snap['committed_at']}). "
        f"{snap['rows']} rows. SHA-256 `{snap['sha256']}`.",
        "",
        "### DOI link",
        "",
        f"Nano DOI `{nano['original_doi']}`. Record `{nano['record_id']}`. "
        f"Nature `{nano['nature']}`. Journal `{nano['journal']}`. Publisher `{nano['publisher']}`. "
        f"Original date `{nano['original_date']}` (`{nano['original_date_iso']}`). "
        f"Notice date `{nano['retraction_date']}` (`{nano['retraction_date_iso']}`). "
        f"Notice DOI `{nano['retraction_doi_raw']}`. "
        f"Reason tokens: {'; '.join(nano['reasons'])}.",
        "",
        "### Publisher question",
        "",
        "Ranked by notice rows in this extract. A reason token is counted once per row, so token counts sum past the row count. "
        "Batch dates are the retraction dates with the most rows for that publisher string. This is not a rate.",
        "",
        "| Publisher | Notice rows | Top reason token | Top batch date |",
        "| --- | ---: | --- | --- |",
    ]
    for publisher in facts["publisher_question"]["publishers"]:
        reason = publisher["reason_tokens"][0]
        batch = publisher["batch_dates"][0]
        lines.append(
            f"| {publisher['publisher']} | {publisher['notice_rows']} | "
            f"{reason['token']} ({reason['rows']}) | {batch['date']} ({batch['notice_rows']}) |"
        )
    lines.append("")
    lines.append("The full ranking, reason tokens, and batch dates are in `data/expected_samples.json`.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
