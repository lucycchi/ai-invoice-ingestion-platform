# Final checks

This is the record of the last stage of the project. Three independent checks looked at the finished
app: a hands-on test in a real browser, a security audit, and a whole-project review by a second AI
company's model. It lists what each one found, what was fixed and how, and what the author chose to
leave. Every fix was made test-first: a test showing the problem was written and seen to fail before the
code changed.

## Summary

| Check | Found | Fixed | Left, by the author's choice |
|---|---|---|---|
| Browser test (gstack `/qa`) | 4 problems | 4 (three during the test, the fourth in the final fixes) | none |
| Security audit (gstack `/cso`, static mode) | 1 problem | 1 | none |
| Whole-project review (Codex, `gpt-6-sol`) | 8 problems, one of them the audit's | 7 | the overall cap on paid Claude calls |

At the end, all 278 offline tests pass (`.venv/bin/pytest`). The live tests against the real Claude
scored 47 of 47 lines earlier in this stage. After the final fixes, the rebuilt app was checked by hand
against the running stack.

## 1. Browser test

The gstack `/qa` skill drove a headless browser through the whole flow on http://localhost:8080:
uploading each sample, confirming the sponsor, study and site, reviewing and overriding matches, then
finalizing and downloading. It also checked phone-width layouts and the error paths. Its report is in
`.gstack/qa-reports/run-20261021T023335Z/`, and its health score went from 92 to 99. That score is
provisional, because performance and accessibility were not scored separately.

- **The study picker disappeared after the sponsor was changed (ISSUE-001, high).** When the user picked
  a different sponsor, the study picker vanished, so the invoice couldn't be confirmed. The page library
  (htmx) was replacing the whole form instead of only the list inside the picker. Fixed in `9038511`.
- **Wide tables made the whole page scroll sideways on a phone (ISSUE-002, medium).** Each table now
  scrolls inside its own box. Fixed in `af6fbff`.
- **Retry timings were measured from the upload (ISSUE-003, medium).** A Retry after a restart reported
  "Reading took 9669.5 seconds", because the time ran from the original upload. A timing record is now
  opened when the upload or the Retry starts. Fixed in `c3a4658`.
- **An unknown invoice address showed raw JSON (ISSUE-004, low).** The browser test left this for later
  because it was below its severity bar. The author chose to fix it in the final fixes, and the address
  now shows a normal page with a link back to the invoice list.

## 2. Security audit

The gstack `/cso` audit ran in its static mode, which reads the source and runs no code, with its
ten-minute budget. Its runtime scanners were not used. Its coverage is **partial**:

- it reviewed the Docker Compose file closely;
- it relied on the reviews at each milestone and on the whole-project review below for the app's code;
- it could not read the git history.

Its run record is under `~/.gstack/security/cso/` (run `1792550500864-7556fb6d75471e64`).

- **The reference database was reachable from the network with a known password (medium).** The
  provided Postgres database and reference API were published on every network interface. The
  database's password (`ctref`) is in the public repository. On shared Wi-Fi, someone could log in and
  change catalog prices, and the app would then show false price differences or match lines to the
  wrong item. **Fixed:** both ports are now published on 127.0.0.1 only, as the app's own port already
  was. A test checks that every published port in `docker-compose.yml` is localhost-only.

## 3. Whole-project review by Codex

Codex reviewed the whole repository for security and for how the parts work together, which the
per-milestone reviews could not see. It used the prompt `prompts/final-review.md` from Tortoise Lite,
and its findings are in [`FINAL_REVIEW.md`](FINAL_REVIEW.md).

- **Reference database exposed beyond localhost (F1).** This is the same problem the security audit
  found; it is fixed as described above.
- **The upload size limit applied only after the whole upload was stored (F2).** The web framework
  writes an uploaded file to temporary storage before the app sees it. So a file far over the 10 MB
  limit could fill the disk before it was refused. **Fixed:** a guard placed in front of the app now
  counts the bytes as they arrive and refuses an upload over the limit straight away, whether or not the
  browser declared its size. The app's own 10 MB check on the file is unchanged.
- **Error text was written to the log (F3).** The page already showed only the error's type, but the
  log still received the full error. A failed save can include values read from the invoice. **Fixed:**
  the log now records the error's type and where in the code it happened, never its text. The tests
  feed in an error containing "secret invoice text" and check that the phrase is not in the log.
- **No overall cap on paid Claude calls (F4).** Each call is tried at most three times, but nothing
  limits how many uploads or Retries run in total. **Left, by the author's choice.** Adding a spending
  limit would take about 150 lines and a new stored budget record. The app is for one person on their
  own machine, where each upload costs about 5 cents. The README states this as a known limit and says a
  shared deployment would need a spending limit first.
- **Prices with fractions of a cent gave a "+$0.00" price flag (F5).** An invoice price of $1.001
  against a catalog price of $1.00 was flagged as "+$0.00". **Fixed:** both prices are rounded to the
  cent (halves round up) before they are compared. So $1.001 against $1.00 is not flagged, and $1.006
  against $1.00 is flagged as "+$0.01".
- **The cache threshold was fixed for one model (F6).** The app sends the first group of lines alone to
  write Claude's prompt cache, but only when the shared catalog is long enough to cache. That minimum
  length was fixed at 512 tokens, the minimum for the default model, even though the model is a setting.
  **Fixed:** the minimum is now looked up for the configured model, using the values in Claude's
  prompt-caching documentation. A model that isn't in the list gets the largest minimum, 4,096 tokens,
  because setting it too high only skips the warm-up.
- **The settings example was missing two settings (F7).** `.env.example` now also lists the data folder
  (`DATA_DIR`) and the allowed host names (`ALLOWED_HOSTS`). A test checks that every setting the app
  accepts is listed.
- **An uploaded file was left behind when saving the invoice failed (F8).** The file is written to disk
  before the invoice record is saved. If the save failed, no record pointed at the file, so nothing
  would ever delete it. **Fixed:** a failed save now deletes the file.

## Checks run again after the fixes

- **Offline tests:** all 278 pass.
- **The rebuilt app, by hand:**
  - all three ports show as published on 127.0.0.1;
  - an unknown invoice shows an HTML page with status 404;
  - a 12 MB upload is refused with status 413;
  - a normal sample upload still goes through;
  - the reference API still answers on localhost.
- **Codex review of the fix commit `04fc7d7`.** Codex judged four fixes correct and complete: the
  localhost-only ports, the error logs, the settings example and the upload-file cleanup. It found three
  new bugs, which were fixed test-first in the commit that follows:
  - **A catalog price under half a cent crashed the price check.** Such a price rounded to $0.00, and
    the percentage then divided by zero. It is now treated like a zero price, which means no fixed price
    and no flag.
  - **Some older models were missing from the cache table.** These include Claude Sonnet 4.5 and Claude
    Opus 4.1, so they fell back to 4,096 tokens instead of their documented 1,024. They are now listed.
  - **The JSON export answered "not found" in HTML.** The new not-found page also caught the JSON
    download. Addresses ending in `.json` now get the error in JSON again.

  Codex also pointed out that the upload guard allows 10 MB plus 64 KB for the form around the file. A
  file just over 10 MB is therefore still received before the app's own check refuses it. That amount
  is small and fixed, so it was kept. A real upload adds far less than 64 KB, because that space only
  holds the file name and the form's separators.

## Browser tests with Playwright

The author asked for the finished UI to be checked in a real browser after the final fixes. A
repeatable Playwright test, `tests/browser/test_ui_browser.py`, now drives Chromium through the
running app and the real Claude. It is skipped by default, like the live tests; run it with
`.venv/bin/pytest -m browser`. It covers:

- **All four samples:** each is uploaded and read. The test checks the suggested sponsor, study and
  site, confirms them, and checks the review summary and every line's catalog item against the answer
  key.
- **The study picker:** it changes the sponsor and back, and checks that the study picker stays and
  refills. This was the high-severity browser-test problem (ISSUE-001).
- **Reviewing and finalizing:** it searches the catalog and overrides a line, then undoes it. It
  finalizes with the open problems stated, downloads the JSON and checks it, and checks that a
  finalized invoice can't be changed.
- **The not-found page:** an unknown invoice shows a page with a link back.
- **Phone width:** at 375 pixels, no page scrolls sideways.
- **Console errors:** any error on a page fails the test.

**Result:** all 8 pass, in about two minutes, costing about 20 cents. The first run failed one check.
The cause was the test, not the app. Opening the finalize page of a finalized invoice correctly
returns the "can't be changed" page with status 409, and Chrome logs every 409 as a console error. The
test now checks for console errors before that deliberate visit, and checks the 409 itself.

## Glossary

- **Playwright:** a library that drives a real browser from a test, clicking and typing as a person
  would.
- **Console error:** an error a web page reports in the browser's developer console, such as a failed
  request or a script crash.

- **Static mode:** a security check that reads the code without running it.
- **Published port:** a port Docker makes reachable from outside a container. Binding it to `127.0.0.1`
  makes it reachable from this computer only.
- **Network interface:** a connection the computer has to a network, such as Wi-Fi. Publishing a port on
  every interface makes it reachable from other devices on those networks.
- **Temporary storage:** files the web framework writes while it is still receiving an upload.
- **Prompt cache:** Claude can store the start of a prompt it has already seen, so later requests that
  begin the same way are faster and cheaper. It only works when that start is at least a model-specific
  minimum length.
- **Token:** the unit Claude measures text in; roughly three quarters of a word.
- **htmx:** a small JavaScript library that lets a page swap in a part of the page from the server.
- **Health score:** the browser test's overall rating of the app, out of 100.
- **Test-first:** writing a test that fails because of the problem, then changing the code until it
  passes.
- **Codex:** OpenAI's coding model, used here as an independent reviewer from another company.
