# How a check runs

The lead plans the turn and does not answer from memory. `finalize_plan` unions the references read by fixed rules with the lead's plan.

- Audit researchers, in chunks of five and at most 25 references, search the extract by DOI or exact title. They do not look people up by name.
- The pattern researcher counts notice rows for one exact journal or publisher string, or ranks publishers by notice rows, reason tokens, and batch dates. That ranking is not a rate.
- The Crossref researcher runs only after those extract lookups. For each DOI it calls `doi_agency` first (`api.crossref.org/works/{doi}/agency`, then `doi.org/ra/{doi}` when that body is not an agency record). A Crossref DOI gets one work GET. A DataCite DOI, including `10.48550/arXiv`, gets one public DataCite GET and is not treated as suspicious.
- One `query.bibliographic` list call per title. A ranked hit is accepted only when its title, first author, and year agree with the paste. List calls are capped at 3 per second, the DataCite client at 2 per second, timeout 8 seconds, one 429 retry.
- A title that is not an exact match is confirmed in the session only when a Crossref candidate shares at least half of its words with the pasted title. At most three candidates are shown. If none qualify, the answer says no close match was found. A candidate is not cited as a guess.
- Verdicts are chosen in code from the record status, the extract rows, and the Crossref update fields. The writer does not choose them. On a citation audit the response is a count line, a markdown table, and a footer, plus at most three writer sentences. On a journal or publisher question the writer answers in prose, with tool names and status codes left out.
- The harness runs every lookup even if a model skips a call. A call the harness fills in is labeled with a `(harness)` suffix on the agent name. The writer has no tools. A cited record id, DOI, or commit has to appear in the tool results. If it does not, the writer is asked once to fix it, and the leftover sentence is dropped. Two research rounds, eight tool rounds per researcher.
- A topic with no DOI, title, journal, or publisher gets one question back. A person's name alone gets one sentence that names are not unique, and a request for a DOI, title, journal, or publisher.
- No record in the extract is a data limit. It is not proof the paper is sound. A DOI no agency has is a signal to check by hand, not proof. The check does not say whether the paper supports a claim made about it.

The extract is Retraction Watch data for 2026-11-03, distributed by Crossref under CC0. Commit `fb5f174f8476824deaf340693f9a819ce5e29ded` (`fb5f174f`, 2026-11-03T23:00:12Z). Uncompressed SHA-256 `e5351ee51ab3f1da7fe98b3bd6c5c58049b8bff4705949ef6fd4f1a1315dd0ea`, 67,868,852 bytes, 73,597 rows (68,155 retractions, 3,734 expressions of concern, 1,545 corrections, 163 reinstatements). The gzip is `data/retraction_watch.csv.gz`. It is loaded when the process starts. A request does not download it.

Crossref member metadata is used as facts. Abstracts are not stored or quoted. Reason text is the Retraction Watch token list, not a paraphrase such as "fraud." Publisher strings are quoted as the file wrote them and, when Crossref returns, as Crossref wrote them.
