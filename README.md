# Before You Cite

Before You Cite checks a paper, a short bibliography, a journal, or a publisher against one frozen Retraction Watch extract, then makes one live Crossref call per DOI and one bibliographic list call per title. It is for someone about to cite that work, and for the course grader who wants the tool log beside the answer. A person's name alone is not a lookup: names are not unique.

No record in the extract is a data limit. It is not a clean bill of health, and it is not a judgment that the paper is reliable.

The extract is Retraction Watch data for 2026-11-03, distributed by Crossref under CC0. Commit `fb5f174f8476824deaf340693f9a819ce5e29ded` (`fb5f174f`, 2026-11-03T23:00:12Z). Uncompressed SHA-256 `e5351ee51ab3f1da7fe98b3bd6c5c58049b8bff4705949ef6fd4f1a1315dd0ea`, 67,868,852 bytes, 73,597 rows (68,155 retractions, 3,734 expressions of concern, 1,545 corrections, 163 reinstatements). The gzip is `data/retraction_watch.csv.gz`. It is loaded when the process starts. A request does not download it.

Crossref member metadata is used as facts. Abstracts are not stored or quoted. Reason text is the Retraction Watch token list, not a paraphrase such as "fraud." Publisher strings are quoted as the file wrote them and, when Crossref returns, as Crossref wrote them.

## How to run

```
uv sync
uv run app.py
```

The local process binds `127.0.0.1:8000`. Cloud Run starts `uvicorn app:app --host 0.0.0.0 --port $PORT`. `PORT` is the only environment variable. There is no API key and no Secret Manager. The model is `vertex_ai/gemini-3.5-flash-lite` in `vertex_location` `global`, from `config/config.json`, using the Cloud Run service account. The deployed service is https://before-you-cite-655901547612.europe-west1.run.app.

`GET /health` returns the row count and the commit. `POST /chat` takes `{"message", "session_id"}` and returns `response`, `session_id`, and `tool_calls`. Each tool call has `agent`, `name`, `args`, and `result`. `result` is a string. `POST /clear` drops one session. Sessions live in memory on that instance. Deploy with max instances 1 so a second turn hits the same process.

## Agents

The lead plans the turn. It does not answer from memory. Plan merging is partly code: `finalize_plan` unions regex-parsed references with the Lead's plan. Audit researchers, in chunks of five and at most 25 references, search the extract by DOI or exact title. They do not look people up by name. The pattern researcher counts notice rows for one exact journal or publisher string, or ranks publishers by notice rows, reason tokens, and batch dates. That ranking is not a rate. The crossref researcher runs only after those extract lookups. For each DOI it calls `doi_agency` first (`api.crossref.org/works/{doi}/agency`, then `doi.org/ra/{doi}` when that body is not an agency record). A Crossref DOI gets one work GET. A DataCite DOI, including `10.48550/arXiv`, gets one public DataCite GET and is not treated as suspicious. One `query.bibliographic` list call per title. A ranked hit is not accepted until its title, first author, and year are compared with the pasted citation. List calls are capped at 3 per second, the DataCite client at 2 per second, timeout 8 seconds, one 429 retry. A title that is not an exact match is confirmed in the session only when a Crossref candidate shares at least half of its words with the pasted title. At most three candidates are shown. If none qualify, the answer says no close match was found. A candidate is not cited as a guess. Verdicts are chosen in code from the record status, the extract rows, and the Crossref update fields. The writer does not choose them. On a citation audit the response is a count line, a markdown table, and a footer, plus at most three writer sentences. On a journal or publisher question the writer answers in prose, with tool names and status codes left out. The harness guarantees every lookup runs even if a model skips a call. A call the harness fills in is labeled with a `(harness)` suffix on the agent name. The writer has no tools. A cited record id, DOI, or commit has to appear in the tool results. If it does not, the writer is asked once to fix it, and the leftover sentence is dropped. Two research rounds, eight tool rounds per researcher. A topic with no DOI, title, journal, or publisher gets one question back. A person's name alone gets one sentence that names are not unique, and a request for a DOI, title, journal, or publisher. No record is a data limit, never a safe result. A DOI no agency has is a signal to check by hand, not proof. The check covers existence and integrity, not whether the paper supports a claim made about it.

## Samples

These fields were filled by `uv run python scripts/fill_expected.py` from the frozen file. The same numbers are in `data/expected_samples.json`.

### Sample 1. Bibliography, two turns

Turn 1:

```
Audit this bibliography against the shipped extract, then Crossref. Do not guess a title.

1. 10.3390/nano10122325
2. 10.1038/s41586-021-03819-2
3. Modeling Geometry and Semantics of Physical Damages
```

Turn 2, same session:

```
Yes, use this exact title:
Modeling Geometry and Semantics of Physical Damages using IFC
```

Turn 1 is the same table format as sample 4, with three rows: DO NOT CITE for `10.3390/nano10122325` (Retraction Watch #70104, notice date 2026-02-25), NO NOTICE FOUND for `10.1038/s41586-021-03819-2` when Crossref returns no update, and COULD NOT VERIFY for the shortened title. The shortened title has 0 exact extract rows, so turn 1 does not cite record 70548. A Crossref candidate is listed only when at least half of its words are in the pasted title, and at most three are shown. If none qualify, the row says: No close match found. Paste the full title, authors, and DOI.

Turn 2 is one row, DO NOT CITE, for the exact title. Retraction Watch #70548, notice date 2023-10-18. Journal `EG-ICE 2020 Workshop on Intelligent Computing in Engineering`. Publisher `Technische Universitat Berlin`. Both DOI fields in the extract are `unavailable`. Reason: legal reasons or threats.

The nano record is journal `Nanomaterials`, publisher `MDPI`, original date `2020-11-23`, notice DOI `10.3390/nano16050293`. A `RETRACTED:` title prefix is not a reason. A `has-review` relation is a review, not a notice. The notice date in the table is the extract date. A retraction row wins over a Crossref update.

### Sample 2. No record

```
Has 10.1038/s41586-021-03819-2 been retracted or corrected?
```

The answer uses the same table as a bibliography, with one row. With no extract row and no Crossref update, the row is NO NOTICE FOUND. A `has-review` relation is a review, not a notice.

```
0 do not cite, 0 need fixing or verifying, 1 no notice found or can't check, 0 not a paper.

| # | Verdict | What we found | What to do |
| --- | --- | --- | --- |
| 1 | NO NOTICE FOUND | The DOI is registered and nothing in the pasted citation disagreed. No notice is on record, snapshot fb5f174f. | This is not a guarantee of quality. |

No notice found never means a paper is reliable. This tool checks that a citation exists and matches, and whether a retraction or correction is on record. It does not check whether the paper supports your claim.
```

The writer may add at most three sentences under that footer. This file does not invent those sentences.

### Sample 3. Publishers, not rates

```
In the shipped extract, which publishers have the most notice rows? For the top publishers, list the notice-row counts, the reason tokens, and the dates that look like batches. Do not compute a rate.
```

This question has no paper references, so the answer stays in prose. Tool names and status codes are left out. The counts below are the extract, not a rate. A reason token is counted once per row, so token counts sum past the row count. Batch dates are the retraction dates with the most rows for that publisher string.

| Publisher | Notice rows | Top reason token | Top batch date |
| --- | ---: | --- | --- |
| Hindawi | 11524 | Investigation by Journal/Publisher (11115) | 1/24/2024 0:00 (631) |
| IEEE: Institute of Electrical and Electronics Engineers | 10098 | Notice - Limited or No Information (9526) | 6/16/2011 0:00 (1271) |
| Elsevier | 8113 | Investigation by Journal/Publisher (2595) | 6/25/2021 0:00 (129) |
| Springer | 5210 | Investigation by Journal/Publisher (2455) | 9/28/2021 0:00 (435) |
| Wiley | 4455 | Investigation by Journal/Publisher (1690) | 3/20/2024 0:00 (263) |
| Springer - Nature Publishing Group | 3736 | Investigation by Journal/Publisher (2318) | 1/1/2014 0:00 (58) |
| Taylor and Francis | 2158 | Concerns/Issues about Data (699) | 8/23/2023 0:00 (145) |
| PLoS | 1805 | Investigation by Journal/Publisher (615) | 1/11/2023 0:00 (50) |

Full nature counts, reason tokens, and batch dates are in `data/expected_samples.json`. `PLoS` here is the publisher string (1,805 notice rows). It is not the journal string `PLoS One` (1,680).

### Sample 4. Eight citations, registration before retraction

Paste the full citation, not the link alone.

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

The verdicts, in order, are DO NOT CITE, WRONG LINK, FOUND CAN'T CHECK RETRACTIONS, NOT FOUND, COULD NOT VERIFY, NOT A PAPER, WRONG KIND OF LINK, DO NOT CITE. The table below is the code-built response for those citations. Row 5 asks which work when a title candidate shares at least half its words with the paste. The writer may add at most three sentences under the footer. This file does not invent those sentences.

```
2 do not cite, 4 need fixing or verifying, 1 no notice found or can't check, 1 not a paper.

| # | Verdict | What we found | What to do |
| --- | --- | --- | --- |
| 1 | DO NOT CITE | Retraction dated 2026-02-25. Reasons: concerns about data, concerns about image, and investigation by the journal or publisher. Retraction Watch #70104, snapshot fb5f174f. | Leave this paper out of the bibliography. |
| 2 | WRONG LINK | The pasted title is Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. The DOI resolves to Highly accurate protein structure prediction with AlphaFold, Jumper, 2021, snapshot fb5f174f. | Use the paper you meant. This link is a different paper. |
| 3 | FOUND CAN'T CHECK RETRACTIONS | found and matches the citation; we have no retraction or correction source for arXiv, so integrity was not checked, snapshot fb5f174f. | An empty extract row is not a clean result. |
| 4 | NOT FOUND | No registration agency has this DOI, snapshot fb5f174f. | This DOI may be mistyped or invented. Check it by hand. It is not proof. |
| 5 | COULD NOT VERIFY | The title could not be verified, snapshot fb5f174f. | Confirm which work you mean, or paste the full title, authors, and DOI. |
| 6 | NOT A PAPER | This item is not a paper citation, snapshot fb5f174f. | It was not checked. |
| 7 | WRONG KIND OF LINK | This DOI is the retraction notice. Retraction Watch #70104, snapshot fb5f174f. | The link is the retraction notice. The original paper is 10.3390/nano10122325, Magnetic Ionic Liquid Nanocatalyst to Improve Mechanical and Thermal Properties of Epoxy Nanocomposites. |
| 8 | DO NOT CITE | An expression of concern was recorded earlier, on 2024-09-27. Retraction dated 2026-07-24. Reasons: duplication of data, duplication of an image, and original data or images not provided. Retraction Watch #73988, snapshot fb5f174f. | Leave this paper out of the bibliography. |

No notice found never means a paper is reliable. This tool checks that a citation exists and matches, and whether a retraction or correction is on record. It does not check whether the paper supports your claim.
```

Measured on 2026-11-04, and still what the table uses: the nano DOI is Crossref and record 70104 is a retraction; the AlphaFold link resolves to Jumper, 2021; the arXiv DOI is DataCite and matches Vaswani, 2017, with 0 extract rows; the fake DOI is not registered (Crossref agency HTTP 404 body `Resource not found.`, and `doi.org/ra` status `DOI does not exist`); the short title has 0 exact rows and record 70548 is not cited; the news URL is not a paper; `10.3390/nano16050293` is the notice DOI of record 70104; `10.1039/D1RA07974C` has an expression of concern on 2024-09-27 (record 73993) and a retraction on 2026-07-24 (record 73988). `https://arxiv.org/abs/1706.03762v2` normalizes to the same DOI, with the version suffix removed. A DataCite body whose title, first author, or year differs from the paste is a wrong link. Neither DataCite response had a rate-limit header, so the client waits at `datacite_rps` 2.

## No-tools output from vertex_ai/gemini-3.5-flash-lite

PLACEHOLDER. Vertex auth was not available in this build, so this section does not contain a model answer. Do not treat any invented paragraph as the no-tools baseline. On a machine whose service account can call Vertex, run `uv run python scripts/no_tools_baseline.py` and paste the three answers here, under the same model, with no tools.

## Tests

`uv run pytest` does not call the model and does not call Crossref. The extract checks, the chat keys, the chunking, the CSV-before-Crossref order, the citation strip, and the title-confirmation rule are covered there.
