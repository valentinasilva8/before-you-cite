"""Sample prompts and the file facts a script writes into data/expected_samples.json."""

from retraction_agent.catalog import Catalog

NANO_DOI = "10.3390/nano10122325"
ALPHAFOLD_DOI = "10.1038/s41586-021-03819-2"
EXACT_TITLE = "Modeling Geometry and Semantics of Physical Damages using IFC"
SHORT_TITLE = "Modeling Geometry and Semantics of Physical Damages"

SAMPLE_1_TURN_1 = (
    "Audit this bibliography against the shipped extract, then Crossref. Do not guess a title.\n\n"
    "1. 10.3390/nano10122325\n"
    "2. 10.1038/s41586-021-03819-2\n"
    "3. Modeling Geometry and Semantics of Physical Damages"
)
SAMPLE_1_TURN_2 = (
    "Yes, use this exact title:\n"
    "Modeling Geometry and Semantics of Physical Damages using IFC"
)
SAMPLE_2 = "Has 10.1038/s41586-021-03819-2 been retracted or corrected?"
SAMPLE_3 = (
    "In the shipped extract, which publishers have the most notice rows? "
    "For the top publishers, list the notice-row counts, the reason tokens, and the dates that look like batches. "
    "Do not compute a rate."
)
INTEGRITY_SAMPLE = """Audit these citations. Use the full citation: title, authors, and link.

1. Atta, Ayman M., et al. Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. Nanomaterials 2020. https://doi.org/10.3390/nano10122325
2. Atta, Ayman M., et al. Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. Nanomaterials 2020. https://doi.org/10.1038/s41586-021-03819-2
3. Vaswani, Ashish, et al. Attention Is All You Need. 2017. https://doi.org/10.48550/arXiv.1706.03762
4. Nobody, N., et al. A paper that was never registered. Journal of Nowhere 2024. https://doi.org/10.9999/not-a-real-work-before-you-cite
5. Modeling Geometry and Semantics of Physical Damages
6. See the news writeup https://www.nytimes.com/2024/01/01/science/example-retraction-story.html
7. https://doi.org/10.3390/nano16050293
8. https://doi.org/10.1039/D1RA07974C
"""

CHATGPT_LINK = (
    "An AI assistant gave me this reference. Can you check that it exists?\n"
    "https://doi.org/10.3390/nano10122325"
)
CHATGPT_CITATION = (
    "Gemini suggested this citation for my paper. Is it real, and has it been retracted?\n"
    "Shu et al. (2012). Signing at the beginning makes ethics salient and decreases "
    "dishonest self-reports in comparison to signing at the end. "
    "https://www.pnas.org/doi/10.1073/pnas.1209746109"
)
CHATGPT_NATURE = (
    "Copilot gave me this link. Is it a real paper?\n"
    "https://www.nature.com/articles/s41586-021-03819-2"
)
CHATGPT_CLEAN = (
    "ChatGPT gave me this source for my essay. Is it real, and has it been retracted?\n"
    "LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521, 436-444. "
    "https://doi.org/10.1038/nature14539"
)

PROMPTS = {
    "doi_link": CHATGPT_LINK,
    "reference_with_doi": CHATGPT_CLEAN,
    "reading_list": INTEGRITY_SAMPLE,
    "publisher_question": SAMPLE_3,
}


def sample_facts(catalog: Catalog) -> dict:
    """Facts the remaining chips cite: the snapshot, the DOI-link record, and the publisher ranking."""
    nano = catalog.lookup_doi(NANO_DOI)
    if nano["total"] != 1 or not nano["rows"]:
        raise RuntimeError("nano DOI did not resolve to one row")
    top = catalog.top_publishers(8)
    return {
        "snapshot": {
            "commit": catalog.commit,
            "commit_short": catalog.commit_short,
            "committed_at": catalog.manifest["committed_at"],
            "rows": catalog.row_count,
            "sha256": catalog.manifest["sha256"],
            "byte_size": catalog.manifest["byte_size"],
            "nature_counts": catalog.nature_counts,
        },
        "doi_link": {
            "nano": nano["rows"][0],
        },
        "publisher_question": {
            "publishers": top["publishers"],
            "note": "Notice rows, reason tokens, and batch dates. Not a rate. Token counts are once per row.",
        },
    }
