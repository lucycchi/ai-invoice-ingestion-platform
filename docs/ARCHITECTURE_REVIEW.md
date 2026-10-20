## Top five issues, ranked by impact

1. **One invoice line can influence other matches (F1).** “The user message: this group's lines, each with its position, description, quantity and unit price.” [Architecture, line 515](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:515) The instruction-isolation requirement (R54) says hostile text in one line must not affect another. The design sends up to six lines to Claude together; checking that returned IDs belong to the catalog cannot detect a valid but influenced choice for another line. **DEFINITELY WRONG.** This can produce a wrong match that looks valid. **Question:** Is line isolation mandatory, even if separate calls put pressure on the timing target?

2. **Retry can mix two catalog versions (F2).** “They are saved as the invoice's catalog snapshot” followed by “on Retry it is only the missing ones.” [Architecture, lines 371–373](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:371) The flow fetches and saves a catalog on every matching run while keeping successful matches from the previous run. If reference prices or items change before Retry, retained matches and new matches can refer to different catalogs under one snapshot. **DEFINITELY WRONG.** Price flags, overrides, and the download can then misrepresent what was matched. **Question:** Should Retry reuse the original snapshot for remaining lines, or clear all results and match again against the new catalog?

3. **An override can be saved after finalization (F3).** “`G-->>P: 6. allowed, or refused if finalized`” precedes “`F->>S: 8. saves override and flag`.” [Architecture, lines 401–403](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:401) A Finalize request can change the status between that check and the override write. The finalized-invoice lock (R33) is therefore not enforced by this flow. **DEFINITELY WRONG.** The saved final result could change after the user acknowledged it. **Question:** Will the override write and its status condition occur in one database transaction?

4. **Four proposed tables have no primary key (F4).** The diagram gives `EXTRACTIONS` only “`INTEGER invoice_id FK`”; the same omission affects metadata suggestions, catalog snapshots, and line matches. [Architecture, lines 156–157](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:156) Yet the design says these are SQLAlchemy tables. [Architecture, line 705](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:705) **DEFINITELY WRONG.** SQLAlchemy cannot map those tables as drawn, and the stated “at most one” relationships have no database enforcement. **Question:** Which single or composite primary keys and uniqueness constraints are intended?

5. **A reference API outage during Confirm has no defined state (F5).** “The handler asks the reference API client for each record.” [Architecture, line 326](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:326) Reference API failure handling (R35) requires a failure status and Retry, but Confirm begins in awaiting confirmation, which has no corresponding failure status or Retry path; its route lists only invalid choices and wrong status. [Architecture, line 650](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:650) **DEFINITELY WRONG.** Builders could variously return an error, mark extraction failed, or start matching without a completed check. **Question:** Should an API outage leave the invoice awaiting confirmation with a retryable Confirm error, or is another status intended?

## Full findings by pass

### Requirements coverage

- **Duplicate warning is absent (F6).** The confirmation flow says, “The form sends the chosen sponsor, study and site IDs,” but specifies no lookup or recheck when the site picker changes. [Architecture, line 325](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:325) The earlier-upload warning (R25) requires both. **DEFINITELY WRONG.** A reviewer could confirm an apparent duplicate without seeing the required warning.

- **Chosen-site cross-check is unspecified (F7).** “Cross-checks then run” in metadata matching, which occurs before the confirmation picker is used. [Architecture, lines 545–546](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:545) The site-link warning (R22) also applies to a *chosen* site. **UNCLEAR:** either changing a picker reruns this check, or only the initial suggestion is checked. The latter leaves a newly chosen unlinked site without its warning.

### Contradictions

- **Sponsor exact-match rules conflict (F8).** “Company endings are not removed for this test.” [Architecture, lines 530–532](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:530) The sponsor matching rule (R19) says names matching after cleanup that ignores company endings are exact, but its Northwind example says likely. **UNCLEAR:** endings are ignored for exact matches, as the rule says, or only for fuzzy scoring, as the example and architecture say. This changes confidence labels and reasons.

- **A failed Confirm has no compatible status (F5).** Quoted and explained in the top five. The API-failure rule (R35) and seven-status rule (R27) need one agreed outcome for this call.

### Failure paths

- **Uncaught background failures can leave an invoice stuck (F9).** The retry loop tests “`Answer usable?`” after “`Call Claude`,” while restart recovery handles only work interrupted by a restart. [Architecture, lines 585–599](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:585) A missing stored file, failed database write, or other exception outside a handled Claude/API response has no stated transition to a failure screen. **ADDITION:** a top-level job failure handler and file-read handling, roughly 40–80 lines and half a day, with no new service. Without them, the invoice can remain extracting or matching until the app restarts; a missing file also makes Retry repeatedly fail.

- **Null numeric fields have no arithmetic rule (F10).** “Every field allows null for ‘not printed’” while “the reading is stored, then the arithmetic checks run.” [Architecture, lines 504–507](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:504) **UNCLEAR:** should a line with missing quantity, price, or amount produce an “unable to check” warning, or fail extraction? Unqualified multiplication will error; silently skipping it can make an unchecked line look sound. The exact-money and arithmetic rules (R15, R16) need that behavior specified.

- **Catalog Retry changes the basis of retained results (F2).** Quoted and explained in the top five.

### Data model

- **Required numeric quantity is stored as text (F11).** “`TEXT quantity "number as printed"`.” [Architecture, line 170](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:170) The quantity-storage rule (R15) says quantities are stored as numbers. **DEFINITELY WRONG.** The builder must choose a numeric SQLite representation and define how fractional quantities are handled.

- **Keys and uniqueness are missing (F4).** Quoted and explained in the top five. The missing constraints also affect line order: “`INTEGER position "order on the invoice, from 1"`” has no uniqueness rule per invoice. [Architecture, line 168](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:168) Two rows could occupy one position despite the ordered-lines rule (R14).

I found no app-field type name to compare against implemented app models: the document says that application code does not exist yet. The reference API’s `Numeric` catalog price is deliberately copied into SQLite as exact decimal text, so that difference is not a type error.

### Boundaries and risk

- **Valid-looking prompt-influenced matches pass validation (F1).** Quoted and explained in the top five. The relevant boundary is invoice text entering Claude’s shared group prompt; membership checks protect catalog IDs but do not enforce the instruction-isolation rule (R54).

- **The on-screen timing report can be accepted early (F12).** “`POST /invoices/{id}/shown` | The page reports that every result is on screen” has no stated status, run, or completion check. [Architecture, line 656](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:656) **UNCLEAR:** the server either verifies that the current run is complete before recording `shown_at`, or trusts any post. Trusting it can make the headline timing measure (R51) look faster than what the user saw.

### Fit for size

**None found.** The chosen single app, SQLite file, and in-process work fit the approved one-user laptop scope. The failures above concern rules within that scope.

### Diagram quality

- **The Confirm sequence sends rejected choices onward (F13).** “`A-->>P: 3. returns the records, or not found`” is followed unconditionally by “`P->>G: 5. asks to move to matching`” and “`G->>R: 9. starts line matching`.” [Architecture, lines 314–320](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/ARCHITECTURE.md:314) The text correctly says a missing record refuses Confirm. **UNCLEAR:** the diagram is meant to show only the successful branch, or its arrows describe all outcomes. A junior engineer following the latter would breach the Confirm validation rule (R61).

## Clarifying questions, in build-impact order

1. Must the instruction-isolation rule (R54) hold across invoice lines, and may matching therefore send only one line per Claude request?
2. On matching Retry (R30), is the original catalog snapshot retained, or are all previous matches cleared before a fresh catalog is used?
3. Must override, metadata-change, and Finalize writes check status atomically with the write to enforce the finalized lock (R33)?
4. What primary keys and uniqueness constraints should the extraction, suggestion, snapshot, match, and line-position tables enforce?
5. What should Confirm do when the reference API is unavailable, given the API-failure rule (R35) and the seven-status rule (R27)?
6. When a person changes the site picker, should the site-link warning (R22) and duplicate warning (R25) be recomputed immediately?
7. For sponsor names, do company endings count in exact matching, or only in fuzzy matching under the sponsor matching rule (R19)?
8. How should extraction treat missing numeric operands under the null-field rule (R12): a warning that arithmetic could not be checked, or extraction failure?
9. What server-side conditions must hold before a `/shown` post records the on-screen time (R51)?
## Rulings

Reviewed by Codex (model `gpt-6-sol`) on 2026-10-20. The author ruled on 2026-10-20: option A for the
line-isolation finding, and every other finding accepted. All changes are applied to
`docs/ARCHITECTURE.md`; three also corrected wording in the approved `docs/SPEC.md`, noted below.

| Finding | Kind | Ruling and change |
|---|---|---|
| One invoice line can influence other matches (F1) | Real problem, author's choice | Option A, recorded as the decision on line isolation (D12): groups stay; each line is a separate data field with an untrusted-data reminder; the hostile-text test checks every other line still gets its expected item. Spec change: the invoice-text safety rule (R54) now says isolation is tested, not guaranteed. |
| Retry can mix two catalog versions (F2) | Real problem | Accepted. Retry reuses the saved catalog snapshot; changing metadata deletes it. |
| An override can be saved after finalization (F3) | Real problem | Accepted. Every status-dependent write checks the status inside the same transaction. |
| Four proposed tables have no primary key (F4) | Real problem | Accepted. Every table has an `id`, plus uniqueness rules for the "at most one" links and line positions. |
| A reference API outage during Confirm has no defined state (F5) | Real problem | Accepted. Confirm answers 503, the status stays awaiting confirmation, and pressing Confirm again retries. Spec change: the reference API failure rule (R35) now says it covers background steps and describes Confirm's behaviour. |
| Duplicate warning is absent (F6) | Real problem | Accepted. A warnings route redraws the duplicate and site-link warnings when a picker changes. |
| Chosen-site cross-check is unspecified (F7) | Real problem | Accepted, same change as the duplicate warning. |
| Sponsor exact-match rules conflict (F8) | Wording | Accepted. Spec change: the sponsor rule (R19) now ignores company endings only for similarity scores, never for exact. |
| Uncaught background failures can leave an invoice stuck (F9) | Addition, about an hour, no new parts | Accepted. A catch-all around every background job sets the failure status with the reason. |
| Null numeric fields have no arithmetic rule (F10) | Real problem | Accepted. A line with a missing number gets a "couldn't be checked" warning. |
| Required numeric quantity is stored as text (F11) | Real problem | Accepted. Quantity is stored as a number. |
| The on-screen timing report can be accepted early (F12) | Real problem | Accepted. Recorded only once the run has stored every result, and only the first time. |
| The Confirm sequence sends rejected choices onward (F13) | Wording | Accepted. The diagram now shows the refusal branch. |
