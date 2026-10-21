# Milestone 2 gate

Reviews of this milestone compare against `tortoise/milestone-1`, the last approval.

## Tests

**Passed:** `.venv/bin/pytest` finished with exit code 0.

```
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.15.1
collected 169 items

tests/test_arithmetic.py ........                                        [  4%]
tests/test_claude_client.py ....................                         [ 16%]
tests/test_confirm.py .........................                          [ 31%]
tests/test_cross_site.py .........                                       [ 36%]
tests/test_extraction_step.py ...............                            [ 45%]
tests/test_metadata.py ........................                          [ 59%]
tests/test_models.py ......                                              [ 63%]
tests/test_money.py ..................                                   [ 73%]
tests/test_reference_api.py ............                                 [ 81%]
tests/test_startup.py ........                                           [ 85%]
tests/test_status.py ...........                                         [ 92%]
tests/test_upload.py .............                                       [100%]

============================= 169 passed in 8.13s ==============================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 2 is ticked (4 of 4).

## Architecture check

Codex (`gpt-6-sol`) and a fresh Claude agent each compared the code with `docs/ARCHITECTURE.md`.

**Both found:** no milestone 2 work missing; the status line out of date; the catch-all reason and
failure status described wrongly; ID and quantity fields lacking plain meanings in the database
diagram; reference API outages unhandled in Confirm's study's-sponsor lookup and in the study picker
(code). **Disagreement:** the document promised a "metadata" run record the code never writes. Claude
proposed adding it to the code, Codex removing it from the document; the author chose the document,
since the spec asks for timing records of extraction and matching only.

**Only Claude found:** background work is started by the page handlers, not the status guard; the
arithmetic warning text and which lines the total leaves out; several metadata rule details (accents,
the extra company endings, the 10-point lead, one level in total from site evidence, short codes, name
scoring without a protocol); the cross-site guard, the change-metadata warning page, the extraction
prompt file, the broader Claude retries and the duplicate warning's scope were undocumented.

**Only Codex found:** the reading flow ordered storage before the arithmetic checks; unreadable numbers
from Claude being stored as missing was undocumented.

**Document changes applied** for all of the above; all 14 diagrams were checked in a browser and draw.

## Reviews

| Finding | Codex | Claude | Outcome |
|---|---|---|---|
| Site-link and duplicate warnings missing when the confirmation screen first loads | | Yes | Fixed, with tests |
| Line arithmetic compares unrounded products | Yes | Yes | Fixed: rounded to the cent, with tests |
| A near-miss protocol never compares the study name | Yes | Yes (unclear) | Fixed: uncertain with the conflict named, with a test |
| An exact site name hides a conflicting city, state or investigator | Yes | | Fixed: likely with the conflict named, with a test |
| Confirm checks the choices before the status | Yes | Yes (unclear) | Fixed: status first, 409, with a test |
| Reference API outages unhandled in Confirm's owner lookup and the study picker | Yes | Yes | Fixed: 503 with a message, with tests |
| The duplicate warning compares later and re-opened uploads | Yes | Yes (unclear) | Fixed: earlier uploads whose site is still confirmed; changing metadata clears confirmed choices; tests |
| A Retry's reading is timed from the upload | | Yes | Fixed, with a test |
| An unreadable printed total is called "not printed" | | Yes | Fixed: currency forms read, unreadable values reported as such, with tests |
| "NaN" or "Infinity" from Claude crashes the reading | | Yes | Fixed: refused as unreadable, with tests |
| A sponsor taken from the study is always "likely" | | Yes (unclear) | Fixed: never above the study, with a test |
| Tests miss the cases above, and the "likely" check matched CSS class names | Yes | Yes | Tests added; the label check is now exact |

After the fixes the suite has 164 tests, all passing.

**Security fixes made during this milestone** (from the automated security review, outside the four
reviews): the app's port is published on localhost only; form posts from other websites are refused
(403); only the host names `localhost` and `127.0.0.1` are served, blocking DNS rebinding; and a
request's Origin must match the app's own address and port exactly.

## Author's choices

On 2026-10-20 the author accepted every recommendation: fix all code findings test-first, add the
missing tests, change the architecture document to match the code, and remove the "metadata" run
record from the document rather than add it to the code. The security fixes were made as they were
flagged and are listed above for the author to keep or reverse.

**Real Claude check (done after the author added a key):** the first real call failed: the API
rejected the extraction answer shape ("Schema is too complex", HTTP 400), and each of the three tries
took about a minute. Fixed by making every answer field required and nullable, and by not retrying
requests the API rejects as invalid (tests added). Then, with the real `claude-opus-5-5`:

- **Large invoice:** read in 14 seconds (5,933 input and 1,373 output tokens); all 27 lines from both
  pages with exact quantities and prices, total $29,191.00, no arithmetic warnings; Northwind Pharma,
  LUMIN-2024 and Highland Ridge Hospital - Research Unit suggested as exact. Retry after the failed
  attempt worked, timed from the Retry.
- **Mismatched-metadata invoice:** read in 5.2 seconds; all 7 lines; Northwind Pharma, VERITAS and
  Prairie Field Research Group all suggested as likely, with the name, year and site reasons, on a
  confirmation screen checked in a browser with no console errors.
- **Simple invoice:** read correctly in 8.4 seconds (checked directly, outside the app).

Along the way the API key was briefly pasted into `.env.example` (tracked by Git). It was moved to
`.env` before any commit; Git's history contains no key.
