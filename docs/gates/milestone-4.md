# Milestone 4 gate

Reviews of this milestone compare against `tortoise/milestone-3`, the last approval.

## Tests

**Passed:** `.venv/bin/pytest` finished with exit code 0.

```
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.15.1
collected 250 items / 4 deselected / 246 selected

tests/test_arithmetic.py ........                                        [  3%]
tests/test_claude_client.py ....................                         [ 11%]
tests/test_confirm.py .........................                          [ 21%]
tests/test_cross_site.py .........                                       [ 25%]
tests/test_extraction_step.py ...............                            [ 31%]
tests/test_finalize.py ..................                                [ 38%]
tests/test_line_matching.py ........................                     [ 48%]
tests/test_metadata.py ........................                          [ 58%]
tests/test_models.py ......                                              [ 60%]
tests/test_money.py ..................                                   [ 67%]
tests/test_price_flags.py ...........                                    [ 72%]
tests/test_reference_api.py ............                                 [ 77%]
tests/test_report_timings.py ....                                        [ 78%]
tests/test_review.py ....................                                [ 86%]
tests/test_startup.py ........                                           [ 90%]
tests/test_status.py ...........                                         [ 94%]
tests/test_upload.py .............                                       [100%]

====================== 246 passed, 4 deselected in 22.40s ======================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 4 is ticked (3 of 3).

## Architecture check

Codex (`gpt-6-sol`) and a fresh Claude agent each compared the code with `docs/ARCHITECTURE.md`.
Neither found work missing from any milestone.

**Both found:** the status line out of date; the test-file script named wrongly
(`make_image_fixtures.py` instead of `make_test_files.py`, which also makes the hostile invoice); the
`ALLOWED_HOSTS` setting undocumented (and missing from the README with `DATA_DIR`); the download's
file-name cleaning undocumented.

**Only Claude found:** `finalize.py` and `reportlab` missing from the file and library lists; the timing
report undocumented; the localhost-only port undocumented; an unknown invoice on the Finalize page or
download answering 409 instead of 404 (code).

**Only Codex found:** the main-parts diagram showing the runner starting suggestions (extraction asks
for them); `is_invoice` described as yes or no (only accepted invoices are stored); the Confirm flow
not showing the status checked first; the file described as sent once per reading (it is sent on each
attempt); the confirmation page reloading reference choices undocumented.

**Document changes applied** for all of the above; all 14 diagrams were checked in a browser and draw.

## Reviews

| Finding | Codex | Claude | Outcome |
|---|---|---|---|
| The on-screen time stays blank if matching ends before the page loads | Yes | | Fixed: Confirm sends the browser to the page that follows matching live; test; checked in the real app |
| The "start over" command names a volume a fresh clone doesn't have | | Yes | Fixed: `docker compose down -v` |
| The last commit wasn't pushed and the fresh-clone check wasn't shown | | Yes | The check had been done (recorded below); everything pushed to GitHub and GitLab at `1b6901e` |
| "Cache applied" doesn't say whether the cache was read | | Yes (unclear) | Renamed "First group warmed the cache"; the cache-read column shows real use |
| The "first" timings weren't cold | | Yes (unclear) | A cold run of the large invoice measured and reported: matching 9.4 seconds on screen |
| The timing report's "repeat" counts from the previous upload | Yes | | Fixed: counts from the first run; test |
| The live tests don't check descriptions and amounts | Yes | | Added; live run passes, 47/47 |
| The hostile live test doesn't check price flags or arithmetic | | Yes | Added; passes |
| The photo live test passes even if reading fails | Yes | | Now required to be read (contents still only recorded) |
| `pytest -m live` without a key silently skips | Yes | | Now fails with a clear message |
| Exported no-match lines are only `null` | | Yes (unclear) | Each line now also says `"no_match": true`; test |
| "Slowest of all" contradicts the table | | Yes | Corrected |
| The mismatched site stated as likely, while the spec allows uncertain | | Yes (unclear) | Reworded |
| Finalize tests never have arithmetic warnings; export test checks keys not values | | Yes | Tests added |
| An unknown invoice on Finalize or the download answers 409 | | Yes (architecture check) | Fixed: 404; test |

After the fixes the suite has 246 tests, all passing; the live tests (4) pass with the real Claude,
SCORE 47/47.

## Author's choices

On 2026-10-20 the author accepted every recommendation, including measuring one cold run of the large
invoice.

**Delivery checks:**
- **Fresh clone:** the public GitHub repository cloned into a scratch folder and started from the README
  alone; the simple invoice was read (6.7 seconds, all three suggestions exact), matched 5 of 5 (3.2
  seconds on screen), finalized, and downloaded as JSON, in a browser with no console errors.
- **Pushed:** GitHub and GitLab both at `1b6901e`.
- **GitLab visibility:** the project is still private; the author changes it in GitLab's settings.

**Measured with the real `claude-opus-5-5`:** live tests SCORE 47/47 with the two expected price flags,
PNG equal to PDF, the photo-like copy read perfectly, the hostile line no match with every other line
correct; matching the large invoice 9.5 seconds on screen (first), 9.4 (repeat) and 9.4 (cold), against
the 30-second target; about 5 cents per invoice.
