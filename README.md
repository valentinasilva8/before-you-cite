# Before You Cite

Paste the references a chatbot gave you. Before You Cite checks that each one exists, and whether it has been retracted, corrected, or flagged with an expression of concern.

## Terms

- **Retraction:** a journal or publisher formally withdraws a published paper because of an error, misconduct or another reliability problem. The paper usually stays online, marked as retracted, and its findings should not be relied on.
- **Correction:** a published fix to an error that does not invalidate the paper.
- **Expression of concern:** a notice that the journal doubts or is investigating a paper but has not retracted it.
- **DOI:** the permanent ID of a paper, for example `10.3390/nano10122325`.
- **Notice row:** one entry in the Retraction Watch database. One paper can have several.

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

**Takeaway:** Across these four samples the plain model missed or mislabeled every retracted paper and cannot show its evidence, and it was right only on well-known papers and obvious fakes.

### 1. DOI link

```
An AI assistant gave me this reference. Can you check that it exists?
https://doi.org/10.3390/nano10122325
```

**Expected:** The page shows "1 checked: 1 do not cite." Verdict DO NOT CITE, reason line "Retraction on record". What we found: "The retraction is dated 2026-02-25. The recorded reasons are concerns about data, concerns about image, and investigation by the journal or publisher. Retraction Watch #70104." What to do: "Leave it out of your bibliography." Read as: DOI only, because title, authors and year are not in the paste (badge rules).

**Sources:** Retraction Watch commit `fb5f174f`, record 70104. Crossref record for `10.3390/nano10122325`.

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, run 2026-11-10 15:51 UTC, full file in docs/no_tools_baseline.md)</summary>

> Based on the structure of the DOI provided (`10.3390/nano10122325`), this corresponds to an article published in the open-access journal *Nanomaterials* (published by MDPI). 
> 
> * **`10.3390`** is the publisher prefix for MDPI.
> * **`nano`** refers to the journal *Nanomaterials*.
> * **`10122325`** typically encodes the publication details (Volume 10, Issue 12, and an article sequence or ID number corresponding to 2325).
> 
> In the standard publication system for MDPI's *Nanomaterials*, Volume 10, Issue 12 (December 2020) does indeed contain an article with the identifier/article number 2325 (often formatted in the URL as `nano10122325`). 
> 
> Therefore, **yes, this is a validly structured DOI** for an article in *Nanomaterials*.

</details>

**What's different:** Without tools the model confirmed the DOI looked valid and never mentioned a retraction, so a student would have cited a paper that was retracted on 2026-02-25, while the app returns DO NOT CITE with the retraction date and Retraction Watch record #70104 so the claim can be checked.

### 2. Reference with DOI

```
ChatGPT gave me this source for my essay. Is it real, and has it been retracted?
LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521, 436-444. https://doi.org/10.1038/nature14539
```

**Expected:** The page shows "1 checked: 1 no issues found." Verdict NO ISSUES FOUND, reason line "Record found, no notice". What we found: "We found no retraction or correction, and Crossref has a record that matches your citation. We did not check whether the paper's content is relevant to your case." What to do: "This does not mean the paper is sound. Read it before relying on it." Read as: Title Deep learning, Authors LeCun, Y., Bengio, Y., & Hinton, G., Year 2015, DOI 10.1038/nature14539 (badge rules). Footer: "Retraction Watch found no record for this DOI in snapshot fb5f174f."

**Sources:** Crossref record for `10.1038/nature14539`. Retraction Watch commit `fb5f174f`.

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, run 2026-11-10 15:51 UTC, full file in docs/no_tools_baseline.md)</summary>

> **Yes, this source is real**, and it is one of the most famous and widely cited papers in the field of artificial intelligence. 
> 
> * **Authors:** Yann LeCun, Yoshua Bengio, and Geoffrey Hinton (who later won the Turing Award for their foundational work on deep learning).
> * **Journal:** *Nature*, Vol. 521, pages 436–444 (2015).
> * **Topic:** A landmark overview paper summarizing the breakthroughs, mechanisms, and future potential of deep learning in neural networks.
> 
> **Has it been retracted?**
> **No**, it has not been retracted. It remains a pillar of modern computer science literature and has tens of thousands of citations. You can safely use it in your essay.

</details>

**What's different:** Both reach the same answer, but the plain model can only recall it and would say the same thing if a retraction had been posted after its training data, while the app checks a live registry and a dated snapshot and shows what that answer rests on.

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

The page shows "8 checked: 3 do not cite, 2 doesn't check out, 3 unconfirmed." It also asks you to confirm which title you meant for row 5, with the choices under the table. The page sorts by severity, and Show original order restores your order.

| # | Result | Reason line | What we found |
| --- | --- | --- | --- |
| 1 | DO NOT CITE | Retraction on record | dated 2026-02-25, Retraction Watch #70104 |
| 2 | DOESN'T CHECK OUT | Link is a different paper | the DOI resolves to "Highly accurate protein structure prediction with AlphaFold", Jumper, 2021 |
| 3 | UNCONFIRMED | Exists, no retraction data | DataCite has the paper, but the Retraction Watch file does not cover this publisher, so a retraction could not be checked |
| 4 | DOESN'T CHECK OUT | DOI not found in any registry | no Crossref or DataCite record, so it may be mistyped or invented, but this alone is not proof |
| 5 | UNCONFIRMED | No matching record found | the title did not match one paper, and the page lists choices to confirm |
| 6 | UNCONFIRMED | Not a paper | a news link, not a paper citation, so it was not checked |
| 7 | DO NOT CITE | Link is the retraction notice | this DOI is the retraction notice for record 70104, so the paper was retracted |
| 8 | DO NOT CITE | Retraction on record | expression of concern 2024-09-27, then retraction 2026-07-24, Retraction Watch #73988 |

Row 5 is read by the AI extractor (badge ai). Rows with a DOI are read by the fixed rules.

**Sources:** Retraction Watch commit `fb5f174f` (records 70104, 73988, 73993). Crossref, doi.org and DataCite lookups for each DOI.

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, run 2026-11-10 15:51 UTC, full file in docs/no_tools_baseline.md)</summary>

> Here is an audit of the provided citations, assessing their accuracy, consistency, and validity based on available scholarly records.
> 
> ---
> 
> ### 1. Atta, Ayman M., et al. Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. *Nanomaterials* 2020. 
> * **Link:** `https://doi.org/10.3390/nano10122325`
> * **Audit Result:** **Valid.** 
> * **Notes:** This citation is correct. The DOI properly links to the *Nanomaterials* 2020 article by Ayman M. Atta and colleagues concerning magnetic ionic liquid nanocatalysts and epoxy nanocomposites.
> 
> ---
> 
> ### 2. Atta, Ayman M., et al. Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. *Nanomaterials* 2020. 
> * **Link:** `https://doi.org/10.1038/s41586-021-03819-2`
> * **Audit Result:** **Invalid / Mismatched DOI.** 
> * **Notes:** While the text describes the *Nanomaterials* paper by Atta et al., the attached DOI (`10.1038/s41586-021-03819-2`) belongs to an unrelated article published in *Nature* (specifically, an AlphaFold-related or similar high-profile biology paper, not polymer chemistry/nanomaterials). 
> 
> ---
> 
> ### 3. Vaswani, Ashish, et al. Attention Is All You Need. 2017. 
> * **Link:** `https://doi.org/10.48550/arXiv.1706.03762`
> * **Audit Result:** **Valid.** 
> * **Notes:** This is the landmark 2017 Transformer paper by Vaswani et al. The arXiv identifier and DOI link are correct.
> 
> ---
> 
> ### 4. Nobody, N., et al. A paper that was never registered. *Journal of Nowhere* 2024. 
> * **Link:** `https://doi.org/10.9999/not-a-real-work-before-you-cite`
> * **Audit Result:** **Fabricated / Invalid.** 
> * **Notes:** The authors ("N. Nobody"), journal (*Journal of Nowhere*), and DOI are entirely fictitious placeholders meant to represent a non-existent publication.
> 
> ---
> 
> ### 5. Modeling Geometry and Semantics of Physical Damages
> * **Full Citation / Missing Data:** Incomplete citation. Missing authors, publication year, venue, and link.
> * **Audit Result:** **Incomplete.** 
> * **Notes:** This appears to be a title of a computer vision, civil engineering, or graphics paper (often related to structural crack detection or 3D damage modeling), but without metadata or a link, it cannot be verified.
> 
> ---
> 
> ### 6. See the news writeup 
> * **Full Citation / Missing Data:** Incomplete citation. 
> * **Link:** `https://www.nytimes.com/2024/01/01/science/example-retraction-story.html`
> * **Audit Result:** **Placeholder / Invalid Link.** 
> * **Notes:** This is formatted as a conversational reference to a news article rather than a formal academic citation. Furthermore, the URL uses a generic placeholder date and slug (`example-retraction-story`), meaning it does not point to a real *New York Times* article.
> 
> ---
> 
> ### 7. [Missing Title and Authors]
> * **Link:** `https://doi.org/10.3390/nano16050293`
> * **Audit Result:** **Chronologically/Numerically Invalid or Premature DOI.** 
> * **Notes:** *Nanomaterials* (published by MDPI) volume numbers do not correspond to "nano16" for contemporary years (as of the early 2020s, the journal was in volumes 10–13), and this DOI does not resolve to a legitimate published item in the standard crossref/MDPI registry.
> 
> ---
> 
> ### 8. [Missing Title and Authors]
> * **Link:** `https://doi.org/10.1039/D1RA07974C`
> * **Audit Result:** **Valid (Orphaned Link).** 
> * **Notes:** Although the title and authors are missing from the prompt, the DOI structure (`10.1039/D1RA...`) correctly points to the Royal Society of Chemistry journal *RSC Advances* (specifically, a 2021 publication volume). To be fully compliant, authors and titles must be supplied.

</details>

**What's different:** The three citations that should not be cited (rows 1, 7 and 8) are exactly the ones the plain model got wrong: it passed rows 1 and 8 as valid and called the retraction notice in row 7 an invalid DOI, while the app flags all three with Retraction Watch records #70104 and #73988 (the plain model did catch rows 2 and 4, as the app does).

### 4. Publisher question

```
In the shipped extract, which publishers have the most notice rows? For the top publishers, list the notice-row counts, the reason tokens, and the dates that look like batches. Do not compute a rate.
```

**Expected:**

The page returns one short block per publisher (notice rows, reason tokens, batch-like dates). They are notice counts, not rates.

| Publisher | Notice rows | Top reason token (rows) | Top batch date (rows) |
| --- | ---: | --- | --- |
| Hindawi | 11,524 | Investigation by Journal/Publisher (11115) | 1/24/2024 (631) |
| IEEE: Institute of Electrical and Electronics Engineers | 10,098 | Notice - Limited or No Information (9526) | 6/16/2011 (1271) |
| Elsevier | 8,113 | Investigation by Journal/Publisher (2595) | 6/25/2021 (129) |
| Springer | 5,210 | Investigation by Journal/Publisher (2455) | 9/28/2021 (435) |
| Wiley | 4,455 | Investigation by Journal/Publisher (1690) | 3/20/2024 (263) |
| Springer - Nature Publishing Group | 3,736 | Investigation by Journal/Publisher (2318) | 1/1/2014 (58) |
| Taylor and Francis | 2,158 | Concerns/Issues about Data (699) | 8/23/2023 (145) |
| PLoS | 1,805 | Investigation by Journal/Publisher (615) | 1/11/2023 (50) |

The publisher string `PLoS` (1,805) is not the journal `PLoS One` (1,680). `Springer` and `Springer - Nature Publishing Group` are separate strings in the file.

**Sources:** Retraction Watch commit `fb5f174f`.

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, run 2026-11-10 15:51 UTC, full file in docs/no_tools_baseline.md)</summary>

> I do not have access to the shipped extract, any database records, or specific datasets for this query. Therefore, I cannot list the top publishers, their notice-row counts, reason tokens, or batch dates.

</details>

**What's different:** This question cannot be answered from memory, so the plain model correctly declines, while the app answers it with exact notice counts, reason tokens and batch-like dates from a frozen, hash-pinned snapshot that anyone can reproduce.

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
