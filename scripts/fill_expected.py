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
    nano = facts["sample1"]["nano"]
    title = facts["sample1"]["exact_title"]
    lines = [
        "### Sample 1. Bibliography, two turns",
        "",
        "Turn 1:",
        "",
        "```",
        facts["sample1"]["turn1"],
        "```",
        "",
        "Turn 2, same session:",
        "",
        "```",
        facts["sample1"]["turn2"],
        "```",
        "",
        f"Nano DOI `{nano['original_doi']}`. Record `{nano['record_id']}`. "
        f"Nature `{nano['nature']}`. Journal `{nano['journal']}`. Publisher `{nano['publisher']}`. "
        f"Original date `{nano['original_date']}` (`{nano['original_date_iso']}`). "
        f"Notice date `{nano['retraction_date']}` (`{nano['retraction_date_iso']}`). "
        f"Notice DOI `{nano['retraction_doi_raw']}`. "
        f"Original PubMed `{nano['original_pubmed']}`. Notice PubMed `{nano['retraction_pubmed']}`. "
        f"Paywalled `{nano['paywalled']}`. Notes present `{nano['notes_present']}`. "
        f"Reason tokens: {'; '.join(nano['reasons'])}.",
        "",
        f"AlphaFold DOI `{facts['sample1']['alphafold']['doi']}` has "
        f"{facts['sample1']['alphafold']['rows']} rows in this extract. "
        "No record is a data limit. The answer does not call the paper fine, reliable, or unretracted.",
        "",
        f"The shortened title `{facts['sample1']['short_title']['query']}` has "
        f"{facts['sample1']['short_title']['rows']} exact rows. "
        f"Turn 1 must not cite record `{title['record_id']}`. "
        "Crossref `query.bibliographic` is one list call. If `clear_match` is false, the chat asks for confirmation and does not cite a candidate.",
        "",
        f"Turn 2 uses the exact title. Record `{title['record_id']}`. Nature `{title['nature']}`. "
        f"Journal `{title['journal']}`. Publisher `{title['publisher']}`. "
        f"Notice date `{title['retraction_date']}` (`{title['retraction_date_iso']}`). "
        f"Original DOI raw `{title['original_doi_raw'] or 'blank'}`. "
        f"Notice DOI raw `{title['retraction_doi_raw'] or 'blank'}`. "
        f"Reason tokens: {'; '.join(title['reasons'])}.",
        "",
        "### Sample 2. No record",
        "",
        "```",
        facts["sample2"]["prompt"],
        "```",
        "",
        f"DOI `{facts['sample2']['doi']}` has {facts['sample2']['rows']} rows in commit "
        f"`{facts['snapshot']['commit_short']}`. "
        "The answer cites that zero count, the commit, and whatever the one Crossref work call returned. "
        "A `has-review` relation is a review, not a notice. Absence is not a verdict that the paper is fine.",
        "",
        "### Sample 3. Publishers, not rates",
        "",
        "```",
        facts["sample3"]["prompt"],
        "```",
        "",
        "Ranked by notice rows in this extract. A reason token is counted once per row, so token counts sum past the row count. "
        "Batch dates are the retraction dates with the most rows for that publisher string. This is not a rate.",
        "",
        "| Publisher | Notice rows | Top reason token | Top batch date |",
        "| --- | ---: | --- | --- |",
    ]
    for publisher in facts["sample3"]["publishers"]:
        reason = publisher["reason_tokens"][0]
        batch = publisher["batch_dates"][0]
        lines.append(
            f"| {publisher['publisher']} | {publisher['notice_rows']} | "
            f"{reason['token']} ({reason['rows']}) | {batch['date']} ({batch['notice_rows']}) |"
        )
    lines.append("")
    lines.append("Full nature counts, reason tokens, and batch dates are in `data/expected_samples.json`.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
