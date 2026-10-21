# Milestone 3 gate

Reviews of this milestone compare against `tortoise/milestone-2`, the last approval.

## Tests

**Passed:** `.venv/bin/pytest` finished with exit code 0.

```
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.15.1
collected 224 items

tests/test_arithmetic.py ........                                        [  3%]
tests/test_claude_client.py ....................                         [ 12%]
tests/test_confirm.py .........................                          [ 23%]
tests/test_cross_site.py .........                                       [ 27%]
tests/test_extraction_step.py ...............                            [ 34%]
tests/test_line_matching.py ........................                     [ 45%]
tests/test_metadata.py ........................                          [ 55%]
tests/test_models.py ......                                              [ 58%]
tests/test_money.py ..................                                   [ 66%]
tests/test_price_flags.py ...........                                    [ 71%]
tests/test_reference_api.py ............                                 [ 76%]
tests/test_review.py ....................                                [ 85%]
tests/test_startup.py ........                                           [ 89%]
tests/test_status.py ...........                                         [ 94%]
tests/test_upload.py .............                                       [100%]

============================= 224 passed in 18.49s =============================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 3 is ticked (3 of 3).

## Architecture check

Codex (`gpt-6-sol`) and a fresh Claude agent each compared the code with `docs/ARCHITECTURE.md`.
Neither found milestone 3 work missing.

**Both found:** the status line out of date; the flow saying a failing group is resent (the code
resends only the failed lines); the flow saying only one line is redrawn after an override (the page
reloads); plain meanings missing from text fields in the database diagram.

**Only Claude found:** line matching, not the runner, fetches the catalog and saves results; Retry
reuses the snapshot only when one was saved; the thread pool lives in line matching; the saved price
flag also holds the percentage and sentence; the matching prompt file and `review.py` undocumented;
override refusals missing from the route table; the reference API failing during matching, cache
warming conditions and Retry timing undocumented; the on-screen time recorded on any first view; a
crash leaving the run record blank (code).

**Only Codex found:** choosing the already-selected item records an override (code); the on-screen
time not shown until a reload (code); invalid 4xx requests not being retried undocumented.

**Document changes applied** for all of the above; all 14 diagrams were checked in a browser and draw.

## Reviews

| Finding | Codex | Claude | Outcome |
|---|---|---|---|
| The line picker can change a match by accident (pressing Change on the preselected item; search resetting to No match) | Yes | Yes | Fixed: choosing the AI's suggestion is no override; search starts with a placeholder the server refuses; tests |
| The matching-failed screen hides the lines without a result | | Yes | Fixed: every line listed, "No result yet" on the failed ones; test |
| A stalled worker can save results after the metadata was changed | Yes | | Fixed: each save checks the status in the same write; test |
| The on-screen time can include time nobody was watching | | Yes (unclear) | Fixed: recorded only by the page that followed matching live; test |
| Two on-screen reports at once can overwrite the first | Yes | | Fixed: a write that only succeeds while no time is recorded; test |
| The on-screen time isn't shown until a reload | Yes | | Fixed: the report answers with the updated times; test |
| The cache is reported as used when warming failed | Yes | | Fixed; test |
| An unexpected worker error skips the run record | | Yes | Fixed: caught per group; test |
| A failed run shows a "stored" time | | Yes | Fixed: left empty; test |
| The client's three tries and matching's one resend look like conflicting retry rules | Yes (unclear) | | Kept, and documented as two layers that catch different problems |
| The matching start time isn't checked against the Confirm time | | Yes | Test added |

After the fixes the suite has 224 tests, all passing. In the running app with the real Claude, the
review page for the large invoice still shows 24 matched, 3 no match, 1 price flag, matching in 9.4
seconds on screen (8.4 stored), and a catalog search now starts on "Choose an item…".

## Author's choices

On 2026-10-20 the author accepted every recommendation: fix all code findings test-first, keep the two
retry layers and document them, add the missing tests, and bring the architecture document up to date.

**Real Claude checks in this milestone:** the large invoice matched 27 of 27 lines as expected and the
mismatched invoice 7 of 7 with `claude-opus-5-5`; confirmed in a browser, matching took 8.4 seconds
stored and 9.4 on screen, against the 30-second target, with prompt caching applied.
