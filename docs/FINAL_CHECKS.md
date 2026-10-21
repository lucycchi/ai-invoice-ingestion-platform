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

At the end, all 285 offline tests pass (`.venv/bin/pytest`). The live tests against the real Claude
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

- **Offline tests:** all 279 pass.
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

## Review against the PRD, the PRD review and the plan

At the author's request, a fresh Claude agent and a fresh Codex run read the PRD, the PRD review's
literal requirements table and the plan, then checked the code, tests and README against them. Neither
had seen the project before. Both found every required item built. They also found the following.

- **The matching prompt contained the samples' answers.** This was the serious one. Its examples named
  the samples' own abbreviations ("Wk 4", "UA") and the large invoice's three expected no-match lines
  (parking, patient stipend, translation), and its price example was the medium invoice's IRB line. That
  made the 47-of-47 score partly a test of memory. **Fixed, as the author chose:** every example is now
  one that appears in no sample, and the tie-break rule is kept with a new example. This replaces the
  example the spec's tie-break rule gives (R39), so it is recorded as a proposed decision for the author
  to settle (D13). The live tests were rerun with the new prompt: 47 of 47, with both price flags and all
  three no-match lines. The browser tests were rerun too: all 8 pass.
- **Opening "change the sponsor, study or site" for an invoice that doesn't exist gave a server
  error.** Fixed: it now gives the not-found page.
- **Pressing Change after a catalog search without choosing an item showed raw JSON.** Fixed: it now
  shows the normal refusal page, which says to choose an item or No match.
- **The timing table's request count left out the token-counting request.** Each matching run makes
  one, before deciding whether to warm the cache. Fixed: it is now counted. The README's table was
  measured before the fix, so it now says it shows one fewer request per matching run.
- **README wording.** Three passages were corrected:
  - it said a possible duplicate lowers confidence, but it only adds a warning;
  - it said "nothing written to disk" for oversized uploads, which is now "at most about 10 MB";
  - it did not say that the compose file needs Docker Compose 2.24 or later.
- **Records.** The SQLAlchemy pin decision (D1) pointed to a root `DECISIONS.md` that doesn't exist;
  the pointer is removed. The plan said the status guard takes its lock with `BEGIN IMMEDIATE`, but the
  code uses an update that changes nothing, which takes the same lock. That change had no recorded
  decision, and it is now recorded as proposed (D14).
- **Delivery.** GitHub was 7 commits behind, and the GitLab project is still private. The push and a
  fresh-clone check follow the author's approval of these final checks.

Codex could not run the offline tests in its read-only sandbox. The Claude agent ran them: all 278
passed then, and all 279 pass after these fixes.

## Visual review of every screen

After the project was approved, the author asked whether the UI also makes sense and looks good, which
the functional browser tests can't judge. Playwright took screenshots of every screen at desktop width
(1,280 pixels) and phone width (375 pixels). Claude then looked at each one. The screens covered were:

- the invoice list, reading, confirm (including the mismatched invoice) and matching;
- review, an overridden line, finalize and the finalized invoice;
- change metadata, the refusal page, not-found and the conflict page.

The wording, the self-explaining suggestions, the summaries and the shading of no-match lines worked
well. Ten problems were found, and the author chose to fix all of them:

1. **The confirmed sponsor, study and site never appeared after confirming.** The review and finalized
   pages now show them under the invoice heading.
2. **The duplicate warning repeated once for every earlier copy.** The mismatched invoice showed five
   identical boxes. Earlier copies now give one warning that says how many there are.
3. **An overridden line kept the AI's confidence and reason beside the person's choice**, which read as
   a contradiction. Those columns are now headed "AI confidence" and "AI reason", and they fade once a
   person changes the line.
4. **The price-flagged line was easy to miss.** Flagged rows are now shaded with an orange edge.
5. **On a phone, the important columns were off-screen to the right.** The confirm and review tables now
   become stacked, labelled cards on narrow screens. The browser test checks that the pickers, the
   Change button and the price flag are all on screen at phone width.
6. **The refusal page for a line change was titled "Confirm wasn't accepted".** It now says "That change
   wasn't made".
7. **27 large blue Change buttons dominated the review page.** Change and Undo are now smaller outlined
   buttons. Confirm and Finalize stay as the main actions.
8. **Timestamps were raw**, such as "2026-10-21T03:26:40.796Z". They now read "2026-10-21 03:26 UTC".
9. **A finalized invoice put its status and Download JSON at the very bottom.** Both are now at the
   top.
10. **Buttons and links touched with no gap.** They are now spaced apart.

The fixes that change what a page says were made test-first, in `tests/test_ui_polish.py`. The visual
ones were checked by retaking the screenshots. All 285 offline tests and all 8 browser tests pass.

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
