# Before You Cite

Paste the references a chatbot gave you. Before You Cite checks that each one exists, and whether it has been retracted, corrected, or flagged with an expression of concern.

| | |
|---|---|
| App | https://before-you-cite-655901547612.europe-west1.run.app |
| Access | Sign in with a Columbia Google account. [CONFIRM graders can get in] |
| Course | IEOR 4570 Project 2 |
| Path | **Deep Research** |
| Author | vt2450 |
| Data | Retraction Watch snapshot `fb5f174f` (2026-11-03), 73,597 notices, plus live Crossref and DataCite lookups |
| Time | A check of 25 references takes about [MEASURE] minutes |

## Questions it answers

1. For a given paper, has it been retracted or corrected, why, and when?
2. Which journals and publishers have the most retraction notices, and how do the reasons differ?

A person's name alone is not a lookup, because names are not unique.

## Path chosen: Deep Research

A lead agent plans each turn, researcher agents do the lookups in their own fresh contexts, and a writer with no tools writes the answer. This fits the topic for four reasons:

- One paste means many independent lookups. Up to 25 references are split into groups of five, and each group gets its own researcher, so no single context has to hold everything.
- The jobs need different tools: searching the Retraction Watch file, counting notices for a journal or publisher, and live calls to Crossref and DataCite. Each researcher only has the tools for its job.
- The writer has no tools, so it can only report what the researchers found. Any record id, DOI or commit it cites must appear in the tool results, or the sentence is dropped.
- Where the answer must be right, code decides. The five result labels are chosen in code from the lookups, and a model cannot pick them.

To see it working, click **Show how the agents worked** under any answer. Each call is listed with its agent name. A call the code made to guarantee a lookup is marked `(harness)`.

## Agents

| Agent | Job | Tools |
|---|---|---|
| Lead | Reads the request and plans who looks up what | `submit_plan` |
| Citation extractor | Reads citation lines the fixed rules cannot read confidently (see below). Runs only when needed | `submit_extractions` |
| Audit researchers (one per 5 references, up to 25) | Search the Retraction Watch file by DOI or exact title | `rw_lookup_doi`, `rw_lookup_title` |
| Pattern researcher | Counts notices for one exact journal or publisher, or ranks publishers | `rw_pattern`, `rw_top_publishers` |
| Crossref researcher | Checks each DOI and title in the live registries. Runs after the file lookups | `doi_agency`, `crossref_doi`, `datacite_work`, `crossref_title` |
| Writer | Writes the summary under the table on a citation check, and the whole answer on a publisher question. Has no tools | none |

Code around the agents merges the parsed references into the plan, runs any lookup a model skipped, and throttles the registry calls.

## How a pasted reference is read

Fixed rules read each line first. They are predictable and never guess.

When a line has no DOI and no recognizable "(Year). Title." pattern, the citation extractor reads it instead, only when `llm_fallback.enabled` is true. It tags the line into labelled fields (title, authors, year, venue, DOI, URL) in one call, and the output is checked before it is used:

- It must return exactly one item for every line it was sent.
- Every field must appear in your pasted line (ignoring capitalization and spacing). If one does not, that line's output is discarded.
- A DOI must be well formed.
- A line that fails is shown as UNCONFIRMED ("We could not read this citation"). It is never dropped and never repaired.

The extractor cannot choose a verdict or look anything up. It can be switched off with `llm_fallback.enabled` in `config/config.json`.

Before you press Run check, the page shows how the fixed rules read each line (badge: rules or unreadable). If a line needs the extractor, it runs when you press Run check, and the answer's Read as line shows the badge ai.

## The five results

- **DO NOT CITE.** A retraction is on record, or the link you pasted is the retraction notice.
- **DOESN'T CHECK OUT.** The link goes to a different paper, or no registry has this DOI. It cannot be cited as written.
- **CHECK FIRST.** A correction, expression of concern, or other notice is on record. Read it before citing.
- **UNCONFIRMED.** The check did not finish: the title did not match one paper, the live lookup did not return, the paper is in a registry with no retraction data (for example arXiv), the line could not be read, or the item is not a paper.
- **NO ISSUES FOUND.** A registry has a record and no retraction or correction was found. This does not check whether the paper's content fits your case, and it is not proof the paper is sound.

## Data

| Source | What it is | Used for | Limits |
|---|---|---|---|
| Retraction Watch database (frozen copy) | Commit `fb5f174f8476824deaf340693f9a819ce5e29ded`, 2026-11-03. 73,597 notices: 68,155 retractions, 3,734 expressions of concern, 1,545 corrections, 163 reinstatements. SHA-256 `e5351ee51ab3f1da7fe98b3bd6c5c58049b8bff4705949ef6fd4f1a1315dd0ea`. CC0, distributed by Crossref | Notices, reasons and dates | Frozen on that date. Corrections and concerns are less complete than retractions. Loaded once when the process starts |
| Crossref REST API (live) | Registry for most journal DOIs | Does the DOI exist, title, author, year, live update notices | Crossref distributes the Retraction Watch data and also serves these live lookups, so it is not an independent second source |
| doi.org registration lookup (live) | Says which registry holds a DOI | Sends each DOI to Crossref or DataCite | |
| DataCite API (live) | Registry for arXiv and similar | Confirms the paper exists | No retraction data |

Abstracts are never stored or quoted. Reason text is the Retraction Watch token list as written.

## Samples

The four samples are the four chips on the page, in the same order and with the same labels. Click the chip with the same name and the prompt is filled in, so nothing has to be pasted. Each sample shows the expected answer and sources, then the same prompt asked to the same model with no tools and no data. Numbers come from `uv run python scripts/fill_expected.py` and are stored in `data/expected_samples.json`.

### 1. DOI link

```
An AI assistant gave me this reference. Can you check that it exists?
https://doi.org/10.3390/nano10122325
```

**Expected:** DO NOT CITE. Retraction dated 2026-02-25, Retraction Watch #70104. Reasons: concerns about data, concerns about image, investigation by journal or publisher. Journal `Nanomaterials`, publisher `MDPI`, notice DOI `10.3390/nano16050293`.

**Sources:** Retraction Watch commit `fb5f174f`, record 70104. Crossref record for `10.3390/nano10122325`.

**No tools** (vertex_ai/gemini-3.5-flash-lite)

> [PASTE NO-TOOLS OUTPUT]

**What's different:** [WRITE ONE SENTENCE AFTER READING BOTH]

### 2. Reference with DOI

```
ChatGPT gave me this source for my essay. Is it real, and has it been retracted?
LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521, 436-444. https://doi.org/10.1038/nature14539
```

**Expected:** NO ISSUES FOUND. [RUN ON THE LIVE APP AND PASTE THE RESULT]

**Sources:** Crossref record for `10.1038/nature14539`. Retraction Watch commit `fb5f174f`.

**No tools**

> [PASTE NO-TOOLS OUTPUT]

**What's different:** [WRITE ONE SENTENCE AFTER READING BOTH]

### 3. Reading list (8)

```
Audit these citations. Use the full citation: title, authors, and link.

1. Atta, Ayman M., et al. Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. Nanomaterials 2020. https://doi.org/10.3390/nano10122325
2. Atta, Ayman M., et al. Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. Nanomaterials 2020. https://doi.org/10.1038/s41586-021-03819-2
3. Vaswani, Ashish, et al. Attention Is All You Need. 2017. https://doi.org/10.48550/arXiv.1706.03762
4. Nobody, N., et al. A paper that was never registered. Journal of Nowhere 2024. https://doi.org/10.9999/not-a-real-work-before-you-cite
5. Modeling Geometry and Semantics of Physical Damages
6. See the news writeup https://www.nytimes.com/2024/01/01/science/example-retraction-story.html
7. https://doi.org/10.3390/nano16050293
8. https://doi.org/10.1039/D1RA07974C
```

**Expected:**

| # | Result | Why |
|---|---|---|
| 1 | DO NOT CITE | Retraction on record, #70104 |
| 2 | DOESN'T CHECK OUT | The title belongs to row 1 but the DOI resolves to AlphaFold (Jumper, 2021) |
| 3 | UNCONFIRMED | DataCite has the arXiv paper, but arXiv has no retraction data |
| 4 | DOESN'T CHECK OUT | No registry has this DOI. It may be invented, but this alone is not proof |
| 5 | UNCONFIRMED | The shortened title did not match one paper. Close titles are offered to confirm |
| 6 | UNCONFIRMED | Not a paper |
| 7 | DO NOT CITE | The DOI is the retraction notice for record 70104 |
| 8 | DO NOT CITE | Expression of concern 2024-09-27, then retraction 2026-07-24, #73988 |

**Sources:** Retraction Watch commit `fb5f174f` (records 70104, 73988, 73993). Crossref, doi.org and DataCite lookups for each DOI.

**No tools**

> [PASTE NO-TOOLS OUTPUT]

**What's different:** [WRITE ONE SENTENCE AFTER READING BOTH]

### 4. Publisher question

```
In the shipped extract, which publishers have the most notice rows? For the top publishers, list the notice-row counts, the reason tokens, and the dates that look like batches. Do not compute a rate.
```

**Expected:** a prose answer. These are notice counts, not rates. A reason token is counted once per row, so token counts sum past the row count.

| Publisher | Notice rows | Top reason token | Top batch date |
| --- | ---: | --- | --- |
| Hindawi | 11524 | Investigation by Journal/Publisher (11115) | 1/24/2024 (631) |
| IEEE: Institute of Electrical and Electronics Engineers | 10098 | Notice - Limited or No Information (9526) | 6/16/2011 (1271) |
| Elsevier | 8113 | Investigation by Journal/Publisher (2595) | 6/25/2021 (129) |
| Springer | 5210 | Investigation by Journal/Publisher (2455) | 9/28/2021 (435) |
| Wiley | 4455 | Investigation by Journal/Publisher (1690) | 3/20/2024 (263) |

The full list is in `data/expected_samples.json`. `PLoS` is the publisher string (1,805 rows). It is not the journal `PLoS One` (1,680).

**Sources:** Retraction Watch commit `fb5f174f`.

**No tools**

> [PASTE NO-TOOLS OUTPUT]

**What's different:** [WRITE ONE SENTENCE AFTER READING BOTH]

## Known limits

- "No issues found" means nothing was found in this data on this date. It is not a quality judgment.
- Corrections and expressions of concern in the file are less complete than retractions.
- A title with no DOI is accepted only on an exact title match in Crossref, and any author or year you pasted must agree. A slightly different title comes back UNCONFIRMED.
- It checks that a paper exists and has no notice. It does not check whether the paper supports your argument.
- The Retraction Watch copy is frozen at 2026-11-03. A later retraction shows only if Crossref's live data has it.
- arXiv and other DataCite papers can be confirmed to exist but cannot be checked for retractions.

## Run it

```
uv sync
uv run app.py
```

The local process binds `127.0.0.1:8000`. Cloud Run starts `uvicorn app:app --host 0.0.0.0 --port $PORT`. There is no API key and no Secret Manager. The model is `vertex_ai/gemini-3.5-flash-lite` in `vertex_location` `global`, from `config/config.json`, using the Cloud Run service account.

`GET /health` returns the row count and the commit. `POST /chat` takes `{"message", "session_id"}` and returns `response`, `session_id`, and `tool_calls`. Each tool call has `agent`, `name`, `args`, and `result` (a string). `POST /clear` drops one session. Sessions live in memory, so the service runs with max instances 1.

## Tests

`uv run pytest` does not call the model or Crossref. It includes a 16-case labelled regression set (`tests/regression_set.json`) covering retractions, wrong links, invented DOIs, corrections, arXiv and unreadable lines, so a parser change cannot quietly turn a retraction into a clean result.

Design details (rate limits, retry rules, how titles are confirmed) are in [docs/DESIGN.md](docs/DESIGN.md).

## Credits

Retraction Watch data, distributed by Crossref under CC0. Crossref and DataCite metadata.
