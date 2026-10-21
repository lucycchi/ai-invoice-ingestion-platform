# Decisions

Every material decision for this project, in the order it was made. A model
can only propose a decision; only the author settles one.

## D1: How should the provided reference API be fixed so it starts? As shipped, it crashed with "No module named 'psycopg'".

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Keep SQLAlchemy on the 2.0 series: change requirements.txt to sqlalchemy>=2.0.36,<2.1 (one line, one file)
  - Change the database address to name the psycopg2 driver (postgresql+psycopg2://) in docker-compose.yml, app/database.py and docker-entrypoint.sh (three files)
  - Switch the driver to psycopg version 3 (psycopg[binary]), which the starter code was never tested with
- **Research:**
  - [services/api/requirements.txt](services/api/requirements.txt): Only a lower bound on SQLAlchemy, so a fresh build installed SQLAlchemy 2.1.5.
  - [https://docs.sqlalchemy.org/en/21/changelog/migration_21.html](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html): SQLAlchemy 2.1 makes a plain postgresql:// address load the psycopg version 3 driver by default instead of psycopg2.
- **Choice:** Keep SQLAlchemy on the 2.0 series (sqlalchemy>=2.0.36,<2.1)
- **Reason:** It is the smallest change to code we were given, it keeps the starter code running the way it was written and tested, and it touches one file. Already applied and committed; the API starts and its seed data matches the take-home instructions.

## D2: Which AI model provider should the app use to read invoices and match line items? The author has keys for both Anthropic (Claude) and OpenAI.

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Claude only, model claude-opus-5-5, with the model name set in an environment variable
  - OpenAI only
  - Both, behind a setting that picks the provider: about 150 to 250 more lines, two sets of prompts to tune and test, and twice the paid test runs
- **Research:**
  - [https://platform.claude.com/docs/en/build-with-claude/pdf-support.md](https://platform.claude.com/docs/en/build-with-claude/pdf-support.md): Claude's Messages API accepts a PDF directly as a document block, reading both its text and its page images, so scanned PDFs work too.
  - [https://platform.claude.com/docs/en/build-with-claude/vision.md](https://platform.claude.com/docs/en/build-with-claude/vision.md): The same API accepts PNG, JPEG, GIF and WebP images, which covers the 'PDF or image' upload requirement with one code path per file type.
  - [https://platform.claude.com/docs/en/build-with-claude/structured-outputs.md](https://platform.claude.com/docs/en/build-with-claude/structured-outputs.md): Structured outputs (output_config.format, or messages.parse in the Python SDK) make the model return JSON that matches a schema we give it, so extraction and matching results can be checked automatically.
  - [https://platform.claude.com/docs/en/about-claude/models/overview.md](https://platform.claude.com/docs/en/about-claude/models/overview.md): claude-opus-5-5 is the current default Claude model: 1M-token context, $4 per million input tokens and $20 per million output tokens.
- **Choice:** Claude only, model claude-opus-5-5, with the model name set in an environment variable
- **Reason:** One provider keeps the five-day scope small and lets us tune one set of prompts well. Claude reads PDFs and images natively and returns schema-checked JSON, which covers both the image-upload requirement and reliable parsing. Meets the 'Real AI' requirement (a real LLM API for extraction and matching) word for word. Risk: a reviewer with only an OpenAI key could not run the app; adding OpenAI is listed as an option for later rather than built now.

## D3: In the review stage (the take-home's Stage 4), can the user change what the AI suggested?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Read-only review: the user can only look, then finalize
  - Override matches only: for any line, the user can pick a different catalog item from a searchable list or mark the line unmatched; extracted descriptions, quantities and prices stay read-only (about half a day to a day)
  - Full editing: overrides plus editing the extracted values, with totals recalculated (about one more day on top of overrides)
- **Research:**
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): Stage 4 says 'let them review before finalizing' and 'Provide a way to finalize/submit the invoice once the user is satisfied', without saying whether review can change anything.
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): The large invoice has several ambiguous lines (for example 'ECG' could be three catalog items), so the AI will sometimes be wrong; a read-only review would leave the user no way to fix it before finalizing.
- **Choice:** Override matches only
- **Reason:** It makes the review step and finalizing meaningful, since a person can correct a wrong or ambiguous match, at a cost that fits the five-day deadline. The AI's original suggestion is stored next to the override, so it is visible which lines a person changed. This goes beyond the requirement to show each line's suggested match, and leaves no required item unmet. Editing extracted values is left out to save about a day.

## D4: What happens if the user changes the confirmed metadata after line items have been matched?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Allow going back until the invoice is finalized: any metadata change clears that invoice's line matches and overrides (after a warning) and matching runs again against the newly confirmed catalog; finalized invoices are locked (about two hours)
  - Block going back once line matching has started
  - Allow going back but keep the old matches
- **Research:**
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): The instructions make metadata confirmation a hard gate before line matching, but never say what happens if the user changes the metadata afterwards.
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): Keeping old matches after the sponsor or study changes would show matches made against the wrong catalog; the review lists this as a second-order effect of enforcing the gate.
- **Choice:** Allow going back until the invoice is finalized, clearing matches and re-running matching
- **Reason:** A wrongly confirmed invoice should not be stuck with no fix but re-uploading, and matches from the wrong catalog must never be shown. Treating every metadata change the same way, including a site-only change that does not affect the catalog, keeps the rule simple. The invoice's status already controls what can run, so this is one more allowed status change. It keeps the hard gate intact: matching still runs only after metadata is confirmed. No required item is left unmet.

## D5: Should price differences between an invoice line and its matched catalog item be flagged, and with what tolerance?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Flag any difference, to the cent, on every matched line; use price as a tie-breaker in matching; treat a catalog price of zero or blank as 'no fixed price' and do not flag it (about an hour)
  - Flag only differences above a tolerance, such as 5%
  - Do not compare prices; match on descriptions only, as the instructions literally say
- **Research:**
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): The sample invoice notes call out a price mismatch on the medium invoice (IRB at $550 against $500) and on the large invoice (CT scan), 'so human review is needed', while the matching step only mentions comparing descriptions.
  - [services/api/seed/data/catalog_items.json](services/api/seed/data/catalog_items.json): The LUMIN-2024 catalog has items at $0.00 (Study Device, Rescue Medication) that are billed at cost, several near-twin items that differ mainly by price (Cold Chain Shipping $125 against Study Drug Shipping $75), and four visit weeks that share $525.
- **Choice:** Flag any difference, to the cent, with price as a tie-breaker and zero or blank catalog prices treated as no fixed price
- **Reason:** Catalog prices are agreed rates, so any difference deserves a person's look; a tolerance would not change the samples (both mismatches are about 5% to 10%) but would hide small overcharges. Price helps choose between near-twin items but never decides a match alone. A price flag is a warning, not a block on finalizing. This adds to the requirement to compare descriptions without removing it, so no required item is left unmet.

## D6: What does finalizing an invoice do, and can an invoice be finalized while lines are unmatched or price-flagged?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Lock and record, with acknowledgment: finalizing sets the status to finalized, locks the invoice and stores the final result per line; open problems are allowed but the user confirms a summary such as '3 lines unmatched, 2 price differences', which is saved; plus a 'Download JSON' button on finalized invoices (about three hours in all)
  - The same, without the JSON download (about two hours)
  - Block finalizing until every line is matched and no price flags remain
- **Research:**
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): Stage 4 asks only for 'a way to finalize/submit the invoice once the user is satisfied'; there is no downstream payment system to send it to.
  - [scripts/generate_sample_invoices.py](scripts/generate_sample_invoices.py): The large invoice deliberately has three lines with no catalog item (parking reimbursement, patient stipend, translator services), so blocking on unmatched lines would make it impossible to finalize.
- **Choice:** Lock and record, with acknowledgment, plus a 'Download JSON' button on finalized invoices
- **Reason:** Blocking would leave the large invoice impossible to finish, while acknowledging open problems puts the decision on record as a person would in practice. The JSON download gives reviewers something concrete to inspect for about one extra hour. The author answered 'go with your recommendation', and the recommendation leaned toward including the download, so it is included. This meets the requirement to provide a way to finalize, and leaves no required item unmet.

## D7: Which upload types must work, and how are they read?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - PDFs (digital or scanned) and PNG, JPEG or WebP images, all sent as files straight to Claude (PDFs as documents, images as images), one file per upload, with a size limit set in the spec; plus our own image test files (about half a day)
  - Text PDFs only, reading their text with a PDF library
  - Read PDF text with a library and send only images to Claude (two extraction paths)
- **Research:**
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): Stage 1 says 'Accept an invoice file (PDF or image)', but the four sample invoices are all PDFs with a text layer and no image samples are provided.
  - [https://platform.claude.com/docs/en/build-with-claude/pdf-support.md](https://platform.claude.com/docs/en/build-with-claude/pdf-support.md): Claude reads both the text and the page images of a PDF sent as a document block, so scanned PDFs need no separate handling.
  - [https://platform.claude.com/docs/en/build-with-claude/vision.md](https://platform.claude.com/docs/en/build-with-claude/vision.md): Claude accepts PNG, JPEG, GIF and WebP images; the per-image size and resolution limits are to be confirmed when writing the spec.
- **Choice:** PDFs and images, all sent as files straight to Claude, with our own image test files
- **Reason:** A text-only reader passes every provided sample and fails on the first screenshot or scan a reviewer uploads. Sending every file to Claude keeps one extraction path for all types. Test files we will make: a PNG of the simple invoice, a PNG of the mismatched-metadata invoice, and a slightly rotated and blurred photo-like copy. This meets the 'PDF or image' requirement word for word, reading 'or' as both.

## D8: When extracted metadata is close to a reference record but not exact, does the app suggest its best guess or show the field as not found?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Suggest the best guess per field with a confidence level (exact, likely, uncertain, not found) and plain reasons for any doubt; never confirm automatically; check the fields against each other (study belongs to sponsor, site takes part in study) and use a matched study's sponsor when the sponsor is not found
  - Show any field without an exact match as not found and make the user pick
  - Pick the best match silently and show it as matched
- **Research:**
  - [scripts/generate_sample_invoices.py](scripts/generate_sample_invoices.py): The mismatched-metadata invoice targets Northwind Pharma, VERITAS and Prairie Field Research Group, but prints 'Northwind Pharmaceuticals Inc.', 'VERITAS Phase 2 Study', protocol 'NWD-VER-2024-002' (real: NWD-VER-2023-002) and 'Prairie Clinical Research', with the same city, state and principal investigator surname as the real site.
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): The write-up must explain 'How you handled the case where metadata matching partially fails (e.g. sponsor not found but study matched)'; each study belongs to exactly one sponsor, so a matched study implies its sponsor.
- **Choice:** Suggest the best guess per field with confidence and reasons, never auto-confirm, and cross-check the fields
- **Reason:** Showing 'not found' when an obvious candidate exists makes the user redo work; a silent confident match hides problems such as the wrong protocol year. Spelling out the differences makes the user's confirmation meaningful, and requiring a click every time keeps the hard gate real. Fields with nothing close enough start empty with a manual picker, which meets the requirement that the user can select the correct entity when a field cannot be matched. How closeness is scored is left to the approach choice in the ideas stage. No required item is left unmet.

## D9: How should the app handle latency, and how is it measured?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Run extraction and matching in the background with visible progress (for example 'Matching line items: 12 of 27 done', each line filling in as its match arrives); measure from the Confirm click until every line has a result on screen; log every run and report first and repeat runs per sample invoice in the README; aim for under 30 seconds on the large invoice, measured rather than promised (about half a day)
  - Run matching inside the request and show a spinner until it finishes
  - Set no target and do not measure
- **Research:**
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): 'One sponsor+study combination (Northwind Pharma / LUMIN-2024) has a large catalog (~100 items) so you can test how your pipeline handles latency when matching against many options' gives no target and no definition.
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): The success-metrics pass notes that the clock must start at the Confirm click, because starting matching early would make the number small while breaking the gate, and that cached runs should be reported separately from first runs.
- **Choice:** Background work with visible progress, a fixed measurement from the Confirm click to the last line on screen, and a measured target under 30 seconds for the large invoice
- **Reason:** Progress the user can see is most of what handling latency means for a person waiting, and a fixed measurement makes the claim checkable. Fixing the start at the Confirm click stops the measurement from rewarding a broken gate. How the target is reached (running groups of lines at the same time, reusing the catalog part of the prompt between calls) is left to the approach choice in the ideas stage. No required item is left unmet.

## D10: May automated tests use a stand-in for Claude, given the instruction 'Real AI — No mock AI'?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - The running app always calls real Claude and refuses to start without an API key; most automated tests use a stand-in that returns saved answers; a small marked set of tests calls real Claude on the four sample invoices and checks results against the expected results, run only on request
  - Every test calls real Claude
  - Tests use stand-ins only, with no real-model tests
- **Research:**
  - [TAKEHOME_INSTRUCTIONS.md](TAKEHOME_INSTRUCTIONS.md): 'Real AI — Use a real LLM API for extraction and for line-item matching. No mock AI.' is stated as a requirement on the product.
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): The review's answer key gives the expected metadata, matches, price flags and unmatched lines for each sample invoice, which the real-model tests can check against.
- **Choice:** Real Claude in the app always; stand-ins in most tests; a marked set of real-Claude tests on the four samples, run on request
- **Reason:** 'No mock AI' is about what reviewers see the product do, which this keeps fully real: there is no fake mode in the app. Calling a paid model on every test run would make tests slow, costly and randomly failing. The real-model tests double as the accuracy measurement against the answer key. Meets the 'Real AI' requirement word for word.

## D11: What overall approach should the app be built with?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - One Python app: FastAPI serving server-rendered pages with htmx, SQLite for app data, background work in the app process; metadata matching in ordinary code (fuzzy comparison plus cross-checks); Claude for extraction and for line-item matching in concurrent groups of about five or six lines with the catalog cached at the start of each prompt
  - Split front end and worker: FastAPI JSON API, React and TypeScript front end, Redis job queue with a worker per stage; fuzzy candidates then Claude for metadata; text-similarity shortlist then Claude for line matching
  - Claude as an agent with tools that search the reference API and explain its own metadata and line matches
- **Research:**
  - [services/api/](services/api/): The reference API is Python with FastAPI, SQLAlchemy and Pydantic in Docker, so a Python app reuses the same patterns and the pytest test command already set for this project.
  - [docs/PRD_REVIEW.md](docs/PRD_REVIEW.md): The review's success measure is accuracy against the expected results for the four sample invoices, which favours deterministic, testable steps where Claude is not needed.
- **Choice:** One Python app (FastAPI, server-rendered pages with htmx, SQLite), code-based metadata matching, Claude for extraction and grouped, cached line matching
- **Reason:** It meets every settled decision inside five days with the fewest moving parts for a reviewer to install and run, and keeps Claude where it adds the most: reading invoices and judging ambiguous line matches. Metadata matching in code is free, instant and unit-testable, and still produces the plain reasons the near-miss metadata decision (D8) requires. Accepted costs: plainer screens than a React app, and a restart during matching needs a Retry click. Keeps extraction, metadata matching and line-item matching as distinct modules, meeting the separation requirement. No required item is left unmet.

## D12: How should line matching keep hostile text in one invoice line from affecting the matches for other lines?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Keep groups of up to six lines per Claude request, send each line as a separate data field with a reminder that descriptions are untrusted data, and test that every other line on a hostile-text invoice still gets its expected catalog item (about an hour; latency unchanged)
  - Send one line per Claude request for true isolation (27 requests for the large invoice, roughly 45 to 60 seconds at five at a time, likely missing the 30-second target)
- **Research:**
  - [docs/ARCHITECTURE_REVIEW.md](docs/ARCHITECTURE_REVIEW.md): Codex found that lines sent together could let a hostile description pull its neighbours toward a wrong but valid catalog item, which ID checks cannot catch.
  - [docs/SPEC.md](docs/SPEC.md): The invoice-text safety rule (R54) originally said no other line could be affected; it now says other lines are tested to still get their expected items.
- **Choice:** Keep groups, separate data fields, and a test that other lines are unaffected
- **Reason:** No prompt design can guarantee isolation, and one request per line would likely break the latency target (D9) for little practical gain on a single-user demo. Separate fields plus an explicit test give checkable evidence. This changes the wording of the invoice-text safety rule (R54) in the approved spec from a guarantee to a tested property; no required item from the brief is left unmet.

## D13: Should the matching prompt's worked examples come from the sample invoices, including the tie-break example the spec gives for price breaking a tie (R39)?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - Use examples that appear in no sample invoice, keeping the tie-break rule but with a new example
  - Keep the sample-derived examples and disclose them in the README
- **Research:**
  - [app/prompts/matching_instructions.md](app/prompts/matching_instructions.md): The earlier prompt named the samples' abbreviations, their three no-match lines and their price mismatch.
  - [tests/live/test_samples_live.py](tests/live/test_samples_live.py): Rerun with the neutral prompt on 2026-10-20: 47 of 47 lines matched, both price flags and all three no-match lines found.
- **Choice:** Use examples that appear in no sample invoice, keeping the tie-break rule but with a new example
- **Reason:** Examples taken from the samples made the live score partly a test of memory; the author chose neutral examples and a rerun. The rule the spec requires (price may break a tie but never decides a match) is unchanged, but its example is now a frozen-sample courier line rather than the spec's cold-chain shipping line, which is itself a sample line. The score stayed 47 of 47. No required item from the PRD review's table is affected.

## D14: How should the status guard take SQLite's write lock before reading an invoice it will change (status guard task, Task 3)?

- **Status:** settled
- **Proposed by:** Claude (claude-opus-5-5) on 2026-10-20
- **Options:**
  - A conditional update that changes nothing, which takes the write lock inside the normal transaction
  - BEGIN IMMEDIATE, as the plan says
- **Research:**
  - [app/status.py](app/status.py): locked_invoice runs a no-change UPDATE on the invoice row, then re-reads it.
  - [tests/test_status.py](tests/test_status.py): Concurrency tests check that two writers can't both pass the guard.
- **Choice:** A conditional update that changes nothing, which takes the write lock inside the normal transaction
- **Reason:** SQLAlchemy has already begun its own transaction by the time the guard runs, so a second BEGIN IMMEDIATE can't be issued without changing how every session starts. A no-change UPDATE takes the same write lock at the same moment and is covered by the concurrency tests. It was built this way but not recorded; the final review by a fresh agent and Codex pointed out the gap.

## Glossary

- **Acknowledgment:** The user's explicit confirmation that they have seen the open problems, saved with the invoice.
- **Answer key:** The expected result for each sample invoice, worked out from the generator script and the seed data.
- **Background work:** Work the server keeps doing after it has answered the browser, so the page stays responsive.
- **BEGIN IMMEDIATE:** a SQLite command that starts a transaction and takes the write lock straight away.
- **Confidence level:** A label saying how sure the app is about a match: exact, likely, uncertain or not found.
- **Cross-check:** Checking that the chosen sponsor, study and site fit together, using the reference API's records.
- **Document block:** The way a PDF is attached to a request to Claude so the model can read it.
- **Driver:** The small library that actually connects Python to a particular database, here Postgres.
- **Extraction path:** The code route a file takes to be turned into structured invoice data.
- **FastAPI:** A Python library for building web servers and APIs; the reference API uses it too.
- **Final result:** The stored outcome for each line: the chosen catalog item or 'unmatched', whether a person overrode it, and any price flag.
- **Finalize:** The last step, where the user marks the invoice as reviewed and done.
- **First run and repeat run:** A run with nothing reused from before, and a run that can reuse saved work such as a cached prompt; repeat runs are usually faster.
- **htmx:** A small JavaScript library that lets a server-rendered page update one part of itself, such as a progress bar, without a full front-end framework.
- **Isolation:** Making sure one piece of input cannot influence how another is handled.
- **JSON:** A plain-text format for structured data that both people and programs can read.
- **Latency:** How long the user waits for a result.
- **Locked:** Finalized invoices can no longer be changed.
- **Marked tests:** Tests tagged so they are skipped by default and run only when asked for, such as tests that cost money.
- **Metadata:** The invoice's header facts: sponsor, study and protocol, site, invoice number and date.
- **Model provider:** The company whose AI model the app calls over the internet, such as Anthropic or OpenAI.
- **Overfitting:** tuning something so closely to its test cases that the test score no longer shows how it does on new cases.
- **Override:** A choice by the user that replaces the AI's suggestion, saved alongside the original suggestion.
- **Pass-through item:** A cost the site passes on at whatever it actually cost, such as shipping or a device, rather than at a fixed rate.
- **Picker:** A control that lets the user choose a sponsor, study or site from the reference data.
- **Price flag:** A warning on a matched line whose invoice price differs from the catalog price.
- **Prompt caching:** Claude reusing the unchanged start of a prompt between calls, which makes repeat calls faster and cheaper.
- **Prompt injection:** Text inside the input that tries to give the AI new instructions.
- **Rate limit:** A cap on how many requests an API accepts in a period of time.
- **Scanned PDF:** A PDF made from a picture of paper, which has no selectable text inside it.
- **Searchable list:** A drop-down the user can type into to filter the catalog items by name or code.
- **SQLAlchemy:** A Python library that lets code talk to a database without writing raw SQL for every query.
- **SQLite:** A database stored in a single file, needing no separate server.
- **Stand-in (mock):** A fake version of Claude used only in tests, returning saved answers so tests are fast, free and repeatable.
- **Status:** A stored label on each invoice, such as 'awaiting confirmation' or 'finalized', that decides which steps may run next.
- **Structured outputs:** A feature that forces the model's answer to be JSON in a shape we define, so code can read it without guessing.
- **Text layer:** The selectable text inside a digital PDF.
- **Tie-breaker:** Extra information used to choose between two otherwise equally good matches.
- **Token:** A small chunk of text, roughly three-quarters of a word, used to measure and bill model input and output.
- **Tolerance:** An allowed amount of difference below which no flag is raised.
- **Version pin:** A rule in requirements.txt that limits which versions of a library may be installed.
- **Worked example:** a sample case written into a prompt to show the model how to apply a rule.
- **Write lock:** SQLite's guarantee that only one connection can change the database at a time.
