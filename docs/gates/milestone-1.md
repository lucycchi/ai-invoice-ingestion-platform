# Milestone 1 gate

Reviews of this milestone compare against `tortoise/plan`, the last approval.

## Tests

**Passed:** `.venv/bin/pytest` finished with exit code 0.

```
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun
configfile: pytest.ini
testpaths: tests
plugins: anyio-4.15.1
collected 50 items

tests/test_models.py ......                                              [ 12%]
tests/test_reference_api.py ............                                 [ 36%]
tests/test_startup.py ........                                           [ 52%]
tests/test_status.py ...........                                         [ 74%]
tests/test_upload.py .............                                       [100%]

============================== 50 passed in 4.13s ==============================
```

## Requirement coverage

Every requirement in SPEC.md is named by a task in PLAN.md.

## Tasks

Every task in milestone 1 is ticked (4 of 4).

## Architecture check

Codex (`gpt-6-sol`) and a fresh Claude agent each compared the code with `docs/ARCHITECTURE.md`.

**Both found:** no milestone 1 work missing; the "no application code exists yet" line out of date; the
upload flow showing the status guard creating the invoice (the route does) and leaving out the 422
answer for an unreadable PDF and the 7 MB image limit; column types in the database diagram differing
from what the code creates; and the invoice list reading an invoice number no table holds.

**Only Claude found:** the missing-key refusal lives in `app/__main__.py`, not `app/main.py`; section 12
leaves out `app/uploads.py`, `app/clock.py` and `app/__main__.py`; a fourth setting (`DATA_DIR`); time
and ID fields lacking plain meanings; the running app never building the real reference API client.

**Only Codex found:** the reference API client's 10-second timeout and error handling aren't described.

**Disagreement:** for the column types, Claude proposed changing the code (TEXT, INTEGER, REAL), Codex
the document (VARCHAR, BOOLEAN, FLOAT). The author chose the document (below).

**Document changes applied:** status line, upload flow and its text, route table, database diagram types
and meanings with a note on how SQLite stores them, the reference API client's errors and timeout, and
section 12's file list and settings. All 14 diagrams were checked in a browser and draw.

## Reviews

| Finding | Codex | Claude | Outcome |
|---|---|---|---|
| Reference API error answers in the 400s, and non-JSON answers, slip through the client | Yes | Yes | Fixed, with tests |
| `locked_invoice` can return a stale copy of the invoice | | Yes | Fixed (explicit re-read); its new test passed before the fix, so it does not reproduce the reviewer's case |
| The whole upload is read into memory before the size check | Yes | Yes | Fixed: reads at most 10 MB plus one byte |
| Several files in one request are silently accepted | Yes | Yes | Fixed: refused with 422, with a test |
| The invoice number can never appear in the list | Yes | Yes | Moved to the extraction task (Task 6), with a test added to the plan |
| The running app never builds a real reference API client | | Yes | Fixed, with a test |
| The API key prints with the settings | | Yes | Fixed: held as a secret value, with a test |
| Money is rounded when saved, and floats are accepted | | Yes | Fixed: never rounded, floats refused, with tests |
| PDFs that only restrict printing are refused | | Yes | Fixed: accepted if they open without a password, with a test |
| Screens show labels rather than the status names | | Yes | Kept as is; the README will list both |
| Claims are tested only one after another; the lock is never tested | | Yes | Tests added: two claims racing in threads, a second writer waiting |
| The key-never-logged test checks almost nothing | | Yes | Tests added: printed settings and error pages |

After the fixes the suite has 50 tests, all passing.

## Author's choices

On 2026-10-20 the author accepted every recommendation: fix the code findings test-first, refuse
several files, hide the key as a secret value, never round money and refuse floats, accept PDFs that open
without a password, keep the friendly status labels, fix the invoice number in the extraction task, add
the missing tests, and change the architecture document (not the code) for the column types.
