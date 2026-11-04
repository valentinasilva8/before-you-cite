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

The local process binds `127.0.0.1:8000`. Cloud Run starts `uvicorn app:app --host 0.0.0.0 --port $PORT`. `PORT` is the only environment variable. There is no API key and no Secret Manager. The model is `vertex_ai/gemini-3.5-flash-lite` in `vertex_location` `global`, from `config/config.json`, using the Cloud Run service account.

`GET /health` returns the row count and the commit. `POST /chat` takes `{"message", "session_id"}` and returns `response`, `session_id`, and `tool_calls`. Each tool call has `agent`, `name`, `args`, and `result`. `result` is a string. `POST /clear` drops one session. Sessions live in memory on that instance. Deploy with max instances 1 so a second turn hits the same process.

## Agents

The lead plans the turn. It does not answer from memory. Plan merging is partly code: `finalize_plan` unions regex-parsed references with the Lead's plan. Audit researchers, in chunks of five and at most 25 references, search the extract by DOI or exact title. They do not look people up by name. The pattern researcher counts notice rows for one exact journal or publisher string, or ranks publishers by notice rows, reason tokens, and batch dates. That ranking is not a rate. The crossref researcher runs only after those extract lookups. For each DOI it calls `doi_agency` first (`api.crossref.org/works/{doi}/agency`, then `doi.org/ra/{doi}` when that body is not an agency record). A Crossref DOI gets one work GET. A DataCite DOI, including `10.48550/arXiv`, gets one public DataCite GET and is not treated as suspicious. One `query.bibliographic` list call per title. A ranked hit is not accepted until its title, first author, and year are compared with the pasted citation. List calls are capped at 3 per second, the DataCite client at 2 per second, timeout 8 seconds, one 429 retry. A title that is not an exact match is confirmed in the session. It is not cited as a guess. The harness guarantees every lookup runs even if a model skips a call. A call the harness fills in is labeled with a `(harness)` suffix on the agent name. The writer has no tools. A cited record id, DOI, or commit has to appear in the tool results. If it does not, the writer is asked once to fix it, and the leftover sentence is dropped. Two research rounds, eight tool rounds per researcher. A topic with no DOI, title, journal, or publisher gets one question back. A person's name alone gets one sentence that names are not unique, and a request for a DOI, title, journal, or publisher. No record is a data limit, never a safe result. A DOI no agency has is a signal to check by hand, not proof. The check covers existence and integrity, not whether the paper supports a claim made about it.

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

Nano DOI `10.3390/nano10122325`. Record `70104`. Nature `Retraction`. Journal `Nanomaterials`. Publisher `MDPI`. Original date `11/23/2020 0:00` (`2020-11-23`). Notice date `2/25/2026 0:00` (`2026-02-25`). Notice DOI `10.3390/nano16050293`. Original PubMed `33255359`. Notice PubMed `41746171`. Paywalled `No`. Notes present `False`. Reason tokens: Concerns/Issues about Data; Concerns/Issues about Image; Investigation by Journal/Publisher.

AlphaFold DOI `10.1038/s41586-021-03819-2` has 0 rows in this extract. No record is a data limit. The answer does not call the paper fine, reliable, or unretracted.

The shortened title `Modeling Geometry and Semantics of Physical Damages` has 0 exact rows. Turn 1 must not cite record `70548`. Crossref `query.bibliographic` is one list call. If `clear_match` is false, the chat asks for confirmation and does not cite a candidate.

Turn 2 uses the exact title. Record `70548`. Nature `Retraction`. Journal `EG-ICE 2020 Workshop on Intelligent Computing in Engineering`. Publisher `Technische Universitat Berlin`. Notice date `10/18/2023 0:00` (`2023-10-18`). Original DOI raw `unavailable`. Notice DOI raw `unavailable`. Reason tokens: Legal Reasons and/or Threats.

Crossref fields for the nano DOI and the AlphaFold DOI are whatever the live call returns on that request. The notice date to cite is the retraction-watch `updated-by` element, not a publisher element whose date is the article date. A `RETRACTED:` title prefix is not a reason. A `has-review` relation is a review, not a notice.

### Sample 2. No record

```
Has 10.1038/s41586-021-03819-2 been retracted or corrected?
```

DOI `10.1038/s41586-021-03819-2` has 0 rows in commit `fb5f174f`. The answer cites that zero count, the commit, and whatever the one Crossref work call returned. A `has-review` relation is a review, not a notice. Absence is not a verdict that the paper is fine.

### Sample 3. Publishers, not rates

```
In the shipped extract, which publishers have the most notice rows? For the top publishers, list the notice-row counts, the reason tokens, and the dates that look like batches. Do not compute a rate.
```

Ranked by notice rows in this extract. A reason token is counted once per row, so token counts sum past the row count. Batch dates are the retraction dates with the most rows for that publisher string. This is not a rate.

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

Statuses are decided before any retraction sentence. Measured on 2026-11-04:

1. Retracted paper. DOI `10.3390/nano10122325` is Crossref. Record `70104`, nature `Retraction`. The pasted title, first author Atta, and year 2020 are what the citation says. A Crossref title with a `RETRACTED:` prefix still matches that title. The notice date to cite is the retraction-watch date on record `70104`, `2026-02-25`.
2. Identity mismatch. The pasted citation is the nano paper, but the link is `10.1038/s41586-021-03819-2`, which resolves to AlphaFold (Jumper, 2021, "Highly accurate protein structure prediction with AlphaFold"). The answer quotes both sides. It does not apply AlphaFold's empty extract row, or the nano retraction, to the other paper. This DOI has 0 extract rows. That zero is a data limit for the resolved DOI only.
3. arXiv paper. `10.48550/arXiv.1706.03762` is DataCite, not Crossref. Crossref notices are unavailable, and that is not suspicious. DataCite returns title "Attention Is All You Need", first author Vaswani, year 2017, which matches the paste. The extract has 0 rows for this DOI. Empty is not clean. Status `exists_no_integrity_source`, and the sentence is: found and matches the citation; we have no retraction or correction source for arXiv, so integrity was not checked. `https://arxiv.org/abs/1706.03762v2` and `arXiv:1706.03762v2` normalize to the same DOI, with the version suffix removed.
4. Fake DOI `10.9999/not-a-real-work-before-you-cite`. Crossref agency returned HTTP 404, content type `application/json`, body the plain text `Resource not found.` (not a JSON object). `https://doi.org/ra/10.9999/not-a-real-work-before-you-cite` returned HTTP 200 `[{"DOI":"10.9999/not-a-real-work-before-you-cite","status":"DOI does not exist"}]`. Status `doi_not_registered`. The extract has 0 rows. Not registered is a signal to check by hand, not proof.
5. Short title with no DOI. 0 exact extract rows, and a shortened title is not a Crossref match. Status `title_unverified`. The wording is "could not verify". Record `70548` is not cited unless the user confirms the full title.
6. A news link with no DOI and no paper title. Status `not_checkable`.
7. Notice DOI `10.3390/nano16050293` is in the extract as the notice DOI of record `70104`. There is no pasted title to compare.
8. DOI `10.1039/D1RA07974C` matches two extract rows: record `73993` Expression of concern and record `73988` Retraction. Both natures are reported.

A DataCite GET for `10.48550/arxiv.1706.03762` returned HTTP 200 with `data.attributes.titles`, `creators`, and `publicationYear`. A GET for `10.48550/arXiv.9999.99999` returned HTTP 404 `{"errors":[{"status":"404","title":"The resource you are looking for doesn't exist."}]}`. Neither response had a rate-limit header, so the client waits at `datacite_rps` 2 in `config/config.json`. If a DataCite body does resolve and its title, first author, or year differs from the paste, the status is `identity_mismatch`.

## No-tools output from vertex_ai/gemini-3.5-flash-lite

PLACEHOLDER. Vertex auth was not available in this build, so this section does not contain a model answer. Do not treat any invented paragraph as the no-tools baseline. On a machine whose service account can call Vertex, run `uv run python scripts/no_tools_baseline.py` and paste the three answers here, under the same model, with no tools.

## Tests

`uv run pytest` does not call the model and does not call Crossref. The extract checks, the chat keys, the chunking, the CSV-before-Crossref order, the citation strip, and the title-confirmation rule are covered there.
