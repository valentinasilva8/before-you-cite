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
| Access | Sign in with a Columbia Google account. |
| Course | IEOR 4570 Project 2 |
| Path | **Deep Research** |
| Author | vt2450 |
| Data | Retraction Watch snapshot `fb5f174f` (2026-11-03), 73,597 notices, plus live Crossref and DataCite lookups |

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
| Writer | Writes the summary under the table on a citation check. A top-publishers ranking is written in code, not by this agent. Has no tools | none |

Code around the agents merges the parsed references into the plan, runs any lookup a model skipped, and throttles the registry calls.

## Samples

The four samples are the four chips on the page. Click the chip with the same name and the prompt is filled in. Each sample shows the expected answer and sources, then the same prompt asked to the same model with no tools and no data. Numbers come from `uv run python scripts/fill_expected.py` and are stored in `data/expected_samples.json`.

**Takeaway:** Across these four samples the plain model missed or mislabeled every retracted paper and cannot show its evidence, and it was right only on well-known papers and obvious fakes.

### 1. DOI link

```
An AI assistant gave me this reference. Can you check that it exists?
https://doi.org/10.3390/nano10122325
```

**Expected:** The page shows "1 checked: 1 do not cite." Verdict DO NOT CITE, reason line "Retraction on record". What we found: "The retraction is dated 2026-02-25. The recorded reasons are concerns about data, concerns about image, and investigation by the journal or publisher. Retraction Watch #70104." What to do: "Leave it out of your bibliography." Read as: "DOI 10.3390/nano10122325" and "Only a DOI was pasted.", badge "rules".

**Sources:** Retraction Watch commit `fb5f174f`, record 70104. Crossref record for `10.3390/nano10122325`.

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, full file in docs/no_tools_baseline.md)</summary>

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

**What's different:** Without tools the model confirmed the DOI looked valid and never mentioned a retraction, so a student would have cited a retracted paper, while the app returns DO NOT CITE with Retraction Watch record #70104 so the claim can be checked.

### 2. Reference with DOI

```
ChatGPT gave me this source for my essay. Is it real, and has it been retracted?
LeCun, Y., Bengio, Y., & Hinton, G. (2015). Deep learning. Nature, 521, 436-444. https://doi.org/10.1038/nature14539
```

**Expected:** The page shows "1 checked: 1 no issues found." Verdict NO ISSUES FOUND, reason line "Record found, no notice". What we found: "We found no retraction or correction, and Crossref has a record that matches your citation. We did not check whether the paper's content is relevant to your case." What to do: "This does not mean the paper is sound. Read it before relying on it." Read as: Title Deep learning, Authors LeCun, Y., Bengio, Y., & Hinton, G., Year 2015, DOI 10.1038/nature14539 (badge rules). Under the table: "Retraction Watch snapshot fb5f174f, 73597 rows", then "No issues found never means a paper is reliable. This tool checks that a registry has a record for a citation, and whether a retraction or correction is on record. It does not check whether the paper supports your claim."

**Sources:** Crossref record for `10.1038/nature14539`. Retraction Watch commit `fb5f174f`.

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, full file in docs/no_tools_baseline.md)</summary>

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

The page shows "8 checked: 3 do not cite, 2 doesn't check out, 3 unconfirmed." The page sorts by severity, and Show original order restores your order.

| # | Result | Reason line | What we found |
| --- | --- | --- | --- |
| 1 | DO NOT CITE | Retraction on record | The retraction is dated 2026-02-25. The recorded reasons are concerns about data, concerns about image, and investigation by the journal or publisher. Retraction Watch #70104. |
| 2 | DOESN'T CHECK OUT | Link is a different paper | This link goes to a different paper than the one you pasted. The pasted title is Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. The DOI resolves to Highly accurate protein structure prediction with AlphaFold, Jumper, 2021. |
| 3 | UNCONFIRMED | Exists, no retraction data | DataCite has this paper. The Retraction Watch file does not cover this publisher, so a retraction or correction could not be checked. |
| 4 | DOESN'T CHECK OUT | DOI not found in any registry | No registry (Crossref or DataCite) has a record for this DOI. It may be mistyped or invented, but this alone is not proof. |
| 5 | UNCONFIRMED | No matching record found | This title did not match one paper. |
| 6 | UNCONFIRMED | Not a paper | This is not a paper citation, for example a news article, so it was not checked. |
| 7 | DO NOT CITE | Link is the retraction notice | This DOI is the retraction notice, so the paper was retracted. Retraction Watch #70104. |
| 8 | DO NOT CITE | Retraction on record | An expression of concern was recorded earlier, on 2024-09-27. The retraction is dated 2026-07-24. The recorded reasons are duplication of data, duplication of an image, and original data or images not provided. Retraction Watch #73988. |

Rows 1, 2, 3, 4, 7 and 8 have a DOI and are read by the fixed rules. Rows 5 and 6 have no DOI, so on Run check both are sent to the AI reader. Row 5 keeps its title and ends UNCONFIRMED, and What to do says "We didn't find a paper with a similar title to this one Modeling Geometry and Semantics of Physical Damages. Paste the full title, authors, and DOI, then run the check again." Row 6 is read by the AI, but the rules mark it as not a paper, so the AI result is discarded and the row shows no ai badge.

**Sources:** Retraction Watch commit `fb5f174f` (records 70104, 73988, 73993). Crossref, doi.org and DataCite lookups for each DOI.

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, full file in docs/no_tools_baseline.md)</summary>

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

**What's different:** The three citations that should not be cited (rows 1, 7 and 8) are exactly the ones the plain model got wrong: it passed rows 1 and 8 as valid and called the retraction notice in row 7 an invalid DOI, while the app flags all three with Retraction Watch records #70104 and #73988.

### 4. Publisher question

```
In the shipped extract, which publishers have the most notice rows? For the top publishers, list the notice-row counts, the reason tokens, and the dates that look like batches. Do not compute a rate.
```

**Expected:**

The page returns one short block per publisher.

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

<details><summary>No tools answer (vertex_ai/gemini-3.5-flash-lite, full file in docs/no_tools_baseline.md)</summary>

> I do not have access to the shipped extract, any database records, or specific datasets for this query. Therefore, I cannot list the top publishers, their notice-row counts, reason tokens, or batch dates.

</details>

**What's different:** This question cannot be answered from memory, so the plain model correctly declines, while the app answers it from a frozen, hash-pinned snapshot.

## How a pasted reference is read

Fixed rules read each line first.

When a line has no DOI and no recognizable "(Year). Title." pattern, the AI reader (the citation extractor agent) reads it instead. It tags the line into labelled fields (title, authors, year, venue, DOI, URL), and the output is checked before it is used:

- It must return exactly one item for every line it was sent.
- Every field must appear in your pasted line (ignoring capitalization and spacing).
- A DOI must be well formed.
- A line whose AI reading fails these checks is shown as UNCONFIRMED ("We could not read this citation"). It is never dropped and never repaired.
- If the AI reader returns no reading at all, the fixed rules' reading of the line stands.

The extractor cannot choose a verdict or look anything up. It can be switched off with `llm_fallback.enabled` in `config/config.json`.

Before you press Run check, the page shows how the fixed rules read each line (badge: rules or unreadable). If a line needs the extractor, it runs when you press Run check, and the answer's Read as line shows the badge ai.

## How the AI reader works

Paste these two lines:

```
Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites
10.3390/nano10122325
```

What I saw on 2026-11-10, in 3 of 3 runs: the page says "2 checked: 2 do not cite". Row 1 (the title only) shows the ai badge, and its Read as line shows authors, year and DOI as "not found in your paste". Row 2 (the DOI) shows the rules badge. Both rows are DO NOT CITE, Retraction Watch #70104. The two rows are the same paper on purpose.

The AI reader turned a bare title into a checkable citation, and the verdict comes from the registry data, not from the AI.

To see it, open **Show how the agents worked** and find the `citation-extractor` call named `submit_extractions`. Its args hold `items`, the fields the AI returned for each line (`raw_line_index`, `title`, `authors`, `year`, `venue`, `doi`, `url`). Its result has `ok`, `parsed_by` and `items`, and each item has `raw_line_index`, `passed_copy_check` and `parsed_by`. `passed_copy_check` means the text passed the verbatim check, not that the reading was used.

## Similar titles

When a title has no DOI and does not match one paper, the page lists up to three of the top five Crossref title results that share at least half of their content words with your title. You can click one to check it. Try this line, a near miss of a real title:

```
Krizhevsky, A. (2017). ImageNet classification with deep convolutional networks.
```

On 2026-11-10, in 3 of 3 live Crossref searches, the row was UNCONFIRMED ("No matching record found") and the same three choices were offered under the table, in this order:

1. ImageNet classification with deep convolutional neural networks (DOI 10.1145/3065386)
2. Comparison of Regularization Methods for ImageNet Classification with Deep Convolutional Neural Networks (DOI 10.1016/j.aasri.2014.05.013)
3. Deep Convolutional Spiking Neural Networks for Image Classification (DOI 10.18122/td.1782.boisestate)

The first is the real paper. Clicking it runs the check again for that title and DOI, which came back NO ISSUES FOUND.

## The five results

- **DO NOT CITE.** A retraction is on record, or the link you pasted is the retraction notice.
- **DOESN'T CHECK OUT.** The link goes to a different paper, or no registry has this DOI. It cannot be cited as written.
- **CHECK FIRST.** A correction, expression of concern, or other notice is on record. Read it before citing.
- **UNCONFIRMED.** The check did not finish: the title did not match one paper, the live lookup did not return, the paper is in a registry with no retraction data (for example arXiv), the line could not be read, or the item is not a paper.
- **NO ISSUES FOUND.** A registry has a record and no retraction or correction was found.

## Data

| Source | What it is | Used for | Limits |
|---|---|---|---|
| Retraction Watch database (frozen copy) | Commit `fb5f174f8476824deaf340693f9a819ce5e29ded`, 2026-11-03. 73,597 notices: 68,155 retractions, 3,734 expressions of concern, 1,545 corrections, 163 reinstatements. SHA-256 `e5351ee51ab3f1da7fe98b3bd6c5c58049b8bff4705949ef6fd4f1a1315dd0ea`. CC0, distributed by Crossref | Notices, reasons and dates | Frozen on that date. |
| Crossref REST API (live) | Registry for most journal DOIs | Does the DOI exist, title, author, year, live update notices | Crossref distributes the Retraction Watch data and also serves these live lookups, so it is not an independent second source |
| doi.org registration lookup (live) | Says which registry holds a DOI | Sends each DOI to Crossref or DataCite | |
| DataCite API (live) | Registry for arXiv and similar | Confirms the paper exists | No retraction data |

## Known limits

- "No issues found" means nothing was found in this data on this date. It is not a quality judgment.
- Corrections and expressions of concern in the file are less complete than retractions.
- It checks that a paper exists and has no notice. It does not check whether the paper supports your argument.
- The Retraction Watch copy is frozen at 2026-11-03. A later retraction shows only if Crossref's live data has it.
- arXiv and other DataCite papers can be confirmed to exist but cannot be checked for retractions.

## Run it

```
uv sync
uv run app.py
```

The local process binds `127.0.0.1:8000`. Cloud Run starts `uvicorn app:app --host 0.0.0.0 --port $PORT`. The model is `vertex_ai/gemini-3.5-flash-lite` in `vertex_location` `global`, from `config/config.json`, using the Cloud Run service account.

`GET /health` returns the row count and the commit. `POST /chat` takes `{"message", "session_id"}` and returns `response`, `session_id`, and `tool_calls`. Each tool call has `agent`, `name`, `args`, and `result` (a string). `POST /clear` drops one session. Sessions live in memory, so the service runs with max instances 1.

## Tests

`uv run pytest` does not call the model or Crossref. It includes an 18-case labelled regression set (`tests/regression_set.json`) covering retractions, wrong links, invented DOIs, corrections, arXiv and unreadable lines, so a parser change cannot quietly turn a retraction into a clean result.

Design details (rate limits, retry rules, how titles are confirmed) are in [docs/DESIGN.md](docs/DESIGN.md).

## Credits

Retraction Watch data, distributed by Crossref under CC0. Crossref and DataCite metadata.
