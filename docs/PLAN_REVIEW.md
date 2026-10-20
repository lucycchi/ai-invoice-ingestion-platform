## Top five issues by impact

- **Extraction cannot pass its reference failure test (rank 1).** The extraction step (Task 6) says: “Task 7 provides `suggest(...)`, which `run_extraction` calls at its end; until Task 7 lands, this task stores no suggestions and moves straight to `awaiting_confirmation`.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:378)) Yet its `test_reference_down_keeps_reading` expects a failed reference call to set `extraction_failed` and Retry to finish metadata matching. With no metadata matcher in this task, that call has no defined place to happen. The task cannot be completed test-first as written. **DEFINITELY WRONG.** **Question:** Should the reference failure and metadata-only Retry test move to metadata matching (Task 7), or should that matcher be built during extraction (Task 6)?

- **Real Claude calls can exceed the stated retry limit (rank 2).** The Claude client (Task 5) specifies “up to three attempts with waits of 1 and 3 seconds.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:353)) The [Anthropic Python SDK retries eligible failures twice by default](https://platform.claude.com/docs/en/api/sdks/python). Three application attempts can therefore make **nine network attempts** for one extraction or matching request. The stand-in’s three-call test would still pass, while latency and paid calls exceed the extraction retry limit (R62) and matching retry limit (R41). **DEFINITELY WRONG.** **Question:** Will the client set SDK `max_retries=0` so the application’s three attempts are the total?

- **Override tests permit a wrong catalog or invoice to be changed (rank 3).** The review screen (Task 11) tests: “`test_override_and_undo`: overriding the `ECG` line to PROC-ECG-Read stores the override…” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:666)) No test posts a catalog ID outside that invoice’s snapshot or a line ID belonging to another invoice. A handler that trusts the picker could pass every listed test while storing an invalid match, or changing a finalized invoice through another invoice’s URL. That breaks overrides from the confirmed catalog (R47), the finalized lock (R33), and the stored catalog ID rule (R54). **DEFINITELY WRONG** as test coverage. **Question:** Will both line ownership and catalog membership be checked inside the override transaction?

- **Invalid alternative IDs are accepted instead of retried (rank 4).** The answer check (Task 9) says: “An alternative ID outside the catalog is dropped from an accepted result rather than failing the line.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:570)) The answer validation rule (R40) says *every catalog ID* must belong to the fetched catalog and a broken answer is resent. This test requires the opposite behavior for alternative IDs; a response can appear accepted after the model supplied a nonexistent item. **DEFINITELY WRONG.** **Question:** Should an invalid alternative make the group fail validation and receive its one answer retry?

- **The fresh-clone check runs before the README is committed (rank 5).** Delivery (Task 14) says “`4. Push: git push`,” then “`5. Fresh-clone check`,” then “`7. Commit and push: "docs: README with run steps, timings and write-up"`.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:819)) The clone in step 5 cannot contain the README edits made in step 3. It can pass while the final run instructions are broken, defeating the fresh-clone requirement (R63). **DEFINITELY WRONG.** **Question:** Will the README commit and push precede the clone check, with any resulting fixes committed and pushed before delivery?

## Full findings by pass

### Tests against requirements

I checked the tests named for every task. The price flags (Task 10) have no material test gap. The other substantive gaps are below; the order and feasibility sections cover the extraction step (Task 6), reference client (Task 2), review screen (Task 11), and delivery (Task 14).

- **Empty strings satisfy the extraction schema.** The Claude client (Task 5) defines the extracted header fields as “all `str | None`.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:307)) Pydantic accepts `""` for that type, and the listed tests do not reject it. The extraction shape (R12) requires a field absent from the invoice to be `null`, never an empty string. **DEFINITELY WRONG** as a schema and test contract.

- **A site-link warning can pass without the confidence downgrade.** Metadata matching (Task 7) tests that `site_link_warning(1, 6, data)` returns text. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:459)) It does not test that a site unlinked to the suggested study drops one confidence level, as the cross-check requirement (R22) demands. **DEFINITELY WRONG** as test coverage.

- **Confirm checks only one kind of unknown choice.** Confirmation (Task 8) tests “`test_confirm_unknown_site`: site 99 answers 422…” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:510)) It tests a study belonging to the wrong sponsor, but no unknown sponsor or unknown study. Those direct posts could be accepted while all listed tests pass, violating server validation of all three choices (R61). The screen test likewise checks labels and a protocol reason, but not the extracted lines, date, or arithmetic warnings required on that screen (R24). **DEFINITELY WRONG** as test coverage.

- **A zero-line invoice can remain stuck in matching.** Line matching (Task 9) tests a 27-line success and several partial failures, including “all 27 lines have results … and the status is `in_review`.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:578)) No test exercises zero extracted lines, which must move straight to `in_review` under the empty-invoice matching rule (R42). **DEFINITELY WRONG** as test coverage.

- **The JSON test omits the override case.** Finalizing (Task 12) specifies one `test_export_contents` for a finalized medium invoice and lists an `override` field. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:724)) If that fixture has no override, the test can pass while the download omits a person’s chosen item or reports the AI item as final. The JSON download (R50) requires both values. **DEFINITELY WRONG** as test coverage.

- **The live test can flag the wrong lines.** The live sample test (Task 13) asserts “exactly two price flags” in aggregate. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:762)) Two flags on incorrect lines would pass, despite the sample answer key and live-test requirement (R56) specifying IRB/Ethics Fees and CT Scan. It also describes checking quantities and unit prices, but not the four printed totals held in its expected-results file. **DEFINITELY WRONG** as test coverage.

- **The API key test covers logs only.** The app skeleton (Task 1) tests that `SECRET123` appears in no log record. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:108)) Later tests cover Claude errors and one JSON export, but no test checks a rendered page or stored record. The key exclusion rule (R4) covers both. **DEFINITELY WRONG** as test coverage.

### Contradictions

- **Invalid alternatives are accepted.** The answer check (Task 9) explicitly drops an invalid alternative and accepts the result. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:570)) This contradicts validation of every catalog ID (R40). **DEFINITELY WRONG.**

- **The six-line failure example conflicts with per-line acceptance.** The line matching test (Task 9) gives group 2 “an unknown ID twice,” then expects “its 6 lines have no result.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:580)) The same task’s `check_answer` returns accepted results *by position*, while the failed-answer rule (R40) says a line still lacking a valid result stays empty. Two readings are plausible: reject the whole group atomically, or keep valid positions after the retry and leave only invalid positions empty. The expected six empty lines assumes the first; the interface suggests the second. **UNCLEAR.**

### Order

- **The fixture recorder is run before it exists.** Reference API client (Task 2) lists `scripts/record_reference_fixtures.py` under files to create, then makes step 1 “Run `scripts/record_reference_fixtures.py`…” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:155)) There is no such script in the repository yet. **DEFINITELY WRONG.**

- **Extraction tests call the next task’s matcher.** Extraction (Task 6) explicitly defers `suggest(...)` to metadata matching (Task 7), while its reference-down test requires that call and a metadata-only Retry. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:378), [test](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:406)) **DEFINITELY WRONG.**

- **The review test needs a later finalize route.** Review screen (Task 11) requires `test_override_and_finalize_race`, in which “a second session tries to finalize.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:671)) The finalize route is first built in finalizing (Task 12). Task 11 cannot run its stated green test at its milestone. **DEFINITELY WRONG.**

- **Delivery verifies an older commit.** The fresh-clone check runs before the final README commit and push. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:819)) **DEFINITELY WRONG.**

Each milestone does end with something visible. The first ends with an upload list whose invoices remain `extracting` until the next milestone; the second ends with a confirmation screen whose matching job is still a no-op. Those are limited demonstrations, but I found no requirement that their later stages work sooner.

### Expected values

**None found wrong.** I recalculated the test examples against the generator and seed data:

| Invoice | Amount check | Expected total |
|---|---:|---:|
| Simple | 400 + 960 + 550 + 95 + 225 | $2,230.00 |
| Medium | 350 + 1,350 + 1,050 + 950 + 950 + 425 + 380 + 440 + 400 + 300 + 550 | $7,145.00 |
| Large | First 24 lines $27,466; last three $375 + $900 + $450 | $29,191.00 |
| Mismatched metadata | 325 + 850 + 1,000 + 475 + 240 + 180 + 150 | $3,220.00 |

The four invoices have 5 + 11 + 27 + 7 = **50** lines; removing the large invoice’s last three no-match lines leaves **47** expected catalog matches. The price examples also agree with half-up rounding: $50 ÷ $500 = 10%; $25 ÷ $450 = 5.555…% → 5.6%; −$25 ÷ $475 = −5.263…% → −5.3%; and −$175 ÷ $650 = −26.923…% → −26.9%. The stated invoice dates, line positions, 100-item catalog count, eight-site count, and newest-upload ordering agree with the supplied data and tests.

### Feasibility

- **The timing script is outside the app image’s build context.** Delivery (Task 14) says to run “`docker compose exec app python scripts/report_timings.py`.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:800)) The app service is built from `./app`, while the script is created under repository-root `scripts/`; that file cannot be copied into the image from the stated build context. **DEFINITELY WRONG.**

- **A 10 MB image can exceed Claude’s request limit.** Upload validation (Task 4) says “The 10 MB check runs before anything else.” ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:277)) Its test rejects only 10 MB *plus one byte*. The [Claude API’s image limit is 10 MB after base64 encoding](https://platform.claude.com/docs/en/build-with-claude/vision); a 10 MB raw image becomes about 13.3 MB encoded. An upload the app accepts can therefore fail extraction, contrary to the image-size rule (R8). **DEFINITELY WRONG.**

- **The SDK request budget is unspecified.** Claude client (Task 5) says to implement `client.messages.parse` with timeouts and retries. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:352)) The [SDK requires `max_tokens`](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), but neither extraction nor matching specifies a value or tests one. Two readings are plausible: the builder chooses a limit, possibly too short for 27 lines, or the call is made without it and fails before reaching Claude. **UNCLEAR.**

- **Line matching is several test-first cycles presented as one.** Line matching (Task 9) says one implementation step fetches a snapshot, counts tokens, chooses cache warming, runs a five-worker pool, checks and retries answers, saves partial results, and advances status. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:599)) A failure in that single red-to-green cycle will not identify which behavior broke; the step is too broad to build task by task as requested. **DEFINITELY WRONG** for the stated test-first method.

### Risks

- **Nested retries increase paid calls and waiting time.** The Claude client’s three attempts sit on top of the SDK’s two default retries unless disabled. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:353); [SDK behavior](https://platform.claude.com/docs/en/api/sdks/python)) This is bounded, but at nine requests per failed group it can turn a nominal 60-second-per-call policy into minutes and multiply paid attempts across five groups. No monetary budget is stated in the spec or decisions, so I cannot claim a specific budget breach. **DEFINITELY WRONG.**

- **Status-dependent override inputs are untested.** The review route accepts a `line_id` and `catalog_item_id`, but its tests cover only a legitimate item and a `none` choice. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:651)) A forged pair could silently put a plausible-looking item from another catalog on a line, or write through the wrong invoice’s status check. **DEFINITELY WRONG** as test coverage.

- **The catch-all failure reason may expose input or a key.** Extraction (Task 6) calls `fail` with `Unexpected error: …` for any uncaught exception. ([plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PLAN.md:375)) Two readings are plausible: the ellipsis means a fixed, sanitized error code, or it means interpolating the raw exception into a page-visible status reason. The latter can disclose invoice text or credentials supplied by a library exception and conflict with the key exclusion rule (R4). **UNCLEAR.**

## Clarifying questions, in build-changing order

1. For extraction (Task 6), should metadata matching and its reference-failure Retry move into that task, or should the failing test wait for metadata matching (Task 7)?
2. For answer validation (Task 9), after a group’s second invalid answer, should valid positions be kept or should all six positions be discarded?
3. Will the Claude client (Task 5) disable SDK retries and specify separate `max_tokens` limits for extraction and matching?
4. Will the review route (Task 11) reject a line outside the URL’s invoice and an item outside that invoice’s catalog snapshot inside the same transaction?
5. Should the timing report (Task 14) run on the host, or should its script be placed inside the app image?
6. Does `Unexpected error: …` in the background runner (Task 6) mean sanitized text or the raw exception?
## Rulings

Reviewed by Codex (model `gpt-6-sol`) on 2026-10-20. The author accepted all nineteen findings on
2026-10-20, and each is applied to `docs/PLAN.md`. None adds features; they fix task order, tests and
limits.

| Finding | Ruling and change |
|---|---|
| Extraction cannot pass its reference failure test | The reference-down test moved to the metadata task (Task 7), which also now names the Retry and reference failure rules (R30, R35). |
| Real Claude calls can exceed the stated retry limit | The library's retries are off (`max_retries=0`) and every request sets `max_tokens=16000`; a test checks both (Claude client, Task 5). |
| Override tests permit a wrong catalog or invoice to be changed | The override handlers check line ownership and catalog membership inside the transaction, with tests for a foreign line (404) and a foreign item (422) (review screen, Task 11). |
| Invalid alternative IDs are accepted instead of retried | Reverted: an invalid alternative fails the line's check like any other invalid ID (line matching, Task 9). |
| The fresh-clone check runs before the README is committed | The README is committed and pushed first; the clone check repeats until it passes (delivery, Task 14). |
| Empty strings satisfy the extraction schema | Text fields turn empty or blank strings into null, with a test (Task 5). |
| A site-link warning can pass without the confidence downgrade | A test checks the one-level drop (Task 7). |
| Confirm checks only one kind of unknown choice | Tests for an unknown sponsor and study, and for the screen showing number, date, lines and arithmetic result (Task 8). |
| A zero-line invoice can remain stuck in matching | A test that it goes straight to review (Task 9). |
| The JSON test omits the override case | A test exporting an overridden line and a line overridden to no match (Task 12). |
| The live test can flag the wrong lines | The live test names the two flagged lines and checks the four printed totals (Task 13). |
| The API key test covers logs only | A test that the key is in no served page, table column or export (Task 12). |
| The six-line failure example conflicts with per-line acceptance | Valid lines are kept after the resend; only bad lines stay empty. The six-line test now gives all six lines bad IDs, and a new test covers one bad line (Task 9). |
| The fixture recorder is run before it exists | The recorder is written first, then run (Task 2). |
| The review test needs a later finalize route | The override and finalize race test moved to finalizing (Task 12). |
| The timing script is outside the app image's build context | Moved to `app/report_timings.py`, run with `python -m app.report_timings` (Task 14). |
| A 10 MB image can exceed Claude's request limit | Images are limited to 7 MB (PDFs stay at 10 MB), with a test (upload screen, Task 4). |
| The SDK request budget is unspecified | `max_tokens=16000` on every request (Task 5). |
| Line matching is several test-first cycles presented as one | Split into six red-to-green cycles inside the task (Task 9). |
| The catch-all failure reason may expose input or a key | The page shows only the error's type; the full detail goes to the app log, with a test (Task 6). |
