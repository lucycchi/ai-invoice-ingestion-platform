## Top five issues, ranked by impact

- **Confirmed metadata can bypass the catalog scope (F1).** “The study picker lists only the chosen sponsor's studies.” ([the metadata confirmation screen (R24)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:130)) The picker constrains the screen, but the spec never requires the server to validate submitted sponsor, study and site IDs. A direct Confirm request could store a study under the wrong sponsor, fetch an empty catalog, and produce plausible “no match” results. **ADDITION.** Ask: *Must Confirm validate the submitted entities and the study’s sponsor against the reference API?*

- **An unusable AI answer becomes a finalizable “no match” (F2).** “Any line still without a valid result is stored as no match with the reason ‘The AI's answer for this line could not be used.’” ([the group answer rule (R40)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:198)) This treats a failed answer as a finding about the catalog. Retry only runs lines with **no result**, so the user cannot recover these lines through Retry; the invoice can reach review and finalization. **DEFINITELY WRONG.** Ask: *Should unusable answers leave the group failed and retryable, or should the user be asked to resolve them in review?*

- **An exact protocol can hide a conflicting study name (F3).** “The study suggestion first looks for an exact protocol number. If none exists, it compares the extracted protocol number and study name with every study…” ([the study suggestion (R20)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:111)) As written, the study name is compared only when no protocol matches. A correct protocol beside a wrong study name could therefore receive an exact suggestion without a warning, contrary to the spec’s stated anti-goal. **DEFINITELY WRONG.** Ask: *Should a name conflict always be shown, even when the protocol identifies a study exactly?*

- **The planned cache warm-up does not enable caching (F4).** “Every request to Claude starts with the same text… so that Claude's prompt caching can reuse it when it is long enough.” ([the shared matching prompt (R38)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:191)) Identical text and sufficient length are not enough: Claude requires a `cache_control` setting. To reuse this particular prefix, its breakpoint must be on the shared instructions/catalog block. Otherwise the first-group delay buys no cache hit. [Claude’s prompt-caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) confirms the requirement. **DEFINITELY WRONG.** Ask: *Will the matching request explicitly mark the shared catalog prefix for caching?*

- **The latency metric stops before the user sees the result (F5).** “For line matching, the time runs from when the server receives the Confirm request until the last line's result is stored.” ([run timing (R51)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:248)) The settled latency decision measures until every result is **on screen** ([the latency decision (D9)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/DECISIONS.md:121)). Polling delay or a stalled page can make the reported number look good while the reviewer is still waiting. **DEFINITELY WRONG.** Ask: *Which endpoint is authoritative for the 30-second report: stored or visible?*

## Full findings by pass

### Contradictions

- **Unusable answer has two incompatible completion rules (F2).** “Any line still without a valid result is stored as no match…” ([the group answer rule (R40)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:198)); “Each line's result is stored as soon as its group's answer is accepted… When every line has a result, the invoice moves to in review.” ([the result transition (R42)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:205)) One rule stores a result when the answer is *not* accepted; the other ties storage to acceptance. **DEFINITELY WRONG.** It also creates the false “no match” and blocked Retry path described above.

- **Exact protocol suppresses conflicting evidence (F3).** “If none exists, it compares the extracted protocol number and study name…” ([the study suggestion (R20)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:111)) Conflicts with “A confident match shown with no warning when the invoice's facts do not match exactly” being a failure ([the confidence anti-goal](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:34)). **DEFINITELY WRONG.**

- **Recorded time differs from the settled measure (F5).** “...until the last line's result is stored.” ([run timing (R51)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:248)) The approved measure ends when the result is on screen. **DEFINITELY WRONG.**

### Ambiguity

- **Sponsor–study conflict handoff (F6).** “If they disagree, the reason says so and the study's own sponsor is offered.” ([the cross-check (R22)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:122)); “The study picker lists only the chosen sponsor's studies.” ([the metadata picker (R24)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:130)) Two readings: selecting the offered sponsor changes the sponsor picker and then exposes that study; or the study remains offered while excluded from the picker. The first is probably intended. **UNCLEAR.** Ask: *What exactly changes on screen when the suggested study belongs to another sponsor?*

- **“Empty” numeric extraction fields (F7).** “A field not printed on the invoice comes back empty, never guessed.” ([the extraction shape (R12)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:80)); “Money values are stored as exact decimal amounts… Quantities are stored as numbers.” ([numeric storage (R15)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:92)) Two readings: missing numeric values are `null`; or they are empty strings that later need conversion. `null` is probably intended. **UNCLEAR.** Ask: *What JSON value represents an unprinted quantity, price or amount?*

- **Duplicate identity changes at confirmation (F8).** “If an invoice with the same invoice number and the same suggested site already exists…” ([the duplicate warning (R25)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:134)) Two readings: compare the current suggestion with the earlier invoice’s suggestion, or compare with its confirmed site. The latter probably reflects the intended duplicate identity. A missing or corrected suggestion otherwise misses a duplicate. **UNCLEAR.** Ask: *Which site identity is compared, and is the warning recalculated after a manual choice?*

### Untestable requirements

- **Absolute invoice-text safety claim (F9).** “Text inside an invoice can never change how the app behaves beyond the matches it suggests…” ([the invoice-text safety rule (R54)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:259)) Invoice text necessarily affects extraction, metadata suggestions, arithmetic warnings and the “is this an invoice?” decision. The universal “never” also has no finite test. **UNCLEAR.** Missing: the observable behaviors that must remain under server control and examples of malicious invoice text to test. Ask: *Which outcomes must invoice instructions be unable to change?*

### Gaps in the flow

- **Confirmed IDs are trusted at the server boundary (F1).** “The study picker lists only the chosen sponsor's studies.” ([the metadata confirmation screen (R24)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:130)) The earlier cross-check covers *suggestions*, while the spec gives no server rule for submitted choices. **ADDITION.** Cost: roughly 50–100 lines for validation and focused tests; about half a day in the confirmation milestone plus a quarter day for tests; it adds reference-API validation to Confirm. Left out, a direct request can silently scope matching to the wrong catalog.

- **Extraction failure has no immediate transition (F10).** “Extraction failed and matching failed each show the reason for the failure and a Retry button.” ([the failure screens (R30)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:152)); “When the app starts, any invoice still in the extracting status is moved to extraction failed…” ([restart recovery (R31)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:156)) The spec does not say what an extraction API error, timeout, refusal or unreadable response does *without* an app restart. Two reasonable builds either mark extraction failed immediately or leave it extracting until restart; the first is probably intended. **UNCLEAR.** Ask: *Which extraction failures transition immediately, and is a model timeout defined?*

### Hidden assumptions

- **Cache activation and breakpoint (F4).** “...the first group is sent alone so it can write the cache…” ([the cache plan (R37)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:183)) This assumes the request enables caching and marks a prefix shared by later groups. Neither is specified; Claude’s documented behavior does not supply them merely because text repeats. **DEFINITELY WRONG.**

### Traceability

- **Public repository delivery drops out of the spec (F11).** “`README.md` explains, for someone new to the project…” ([the deliverables section (R58)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:282)) The spec’s deliverables cover documentation but omit the PRD’s instruction to push code to GitHub ([the code deliverable](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/PRD.md:149)) and the approved design’s public GitHub and GitLab distribution ([the distribution plan](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/DESIGN.md:246)). **ADDITION.** Cost: no application code; roughly 30–60 minutes in the delivery milestone; it adds remote and access verification. Left out, reviewers may not receive the required repository.

- **Latency decision is changed without acknowledgment (F5).** “...until the last line's result is stored.” ([run timing (R51)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:248)) The settled latency decision (D9) says on screen. **DEFINITELY WRONG.**

### Risk

- **Failure masquerades as an unmatched billable item (F2).** “Any line still without a valid result is stored as no match…” ([the group answer rule (R40)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:198)) The reason is visible on the line, but the review count, finalize summary and JSON final item still treat it as “no match.” **DEFINITELY WRONG.**

- **Wrong catalog can look like a legitimate all-unmatched result (F1).** “The study picker lists only the chosen sponsor's studies.” ([the metadata picker (R24)](/home/lucyc/gauntlet/AI_Invoice_Ingestion_Platform_LedgerRun/docs/SPEC.md:130)) A browser constraint is insufficient for direct Confirm requests. **ADDITION**, with the cost stated above.

No further findings warranted new scope.

## Clarifying questions, ordered by build impact

1. Must the server validate chosen sponsor, study and site IDs, including study ownership, before accepting Confirm?
2. Should an unusable Claude group answer remain failed and retryable, rather than become “no match”?
3. Must a conflicting study name be warned about even when its protocol number matches exactly?
4. Where will the matching request place Claude’s explicit cache breakpoint?
5. Should the reported matching time end when results are stored or when they appear on screen, as the latency decision (D9) says?
6. What happens immediately when extraction errors, times out, is refused or returns unreadable data?
7. When a suggested study belongs to another sponsor, how does selecting its offered sponsor update the pickers?
8. What represents absent numeric fields in extraction JSON?
9. Is duplicate detection based on suggested or confirmed site, and does it update after a manual change?
10. Which specific outcomes must hostile text inside an invoice be unable to alter?
11. Should public GitHub and GitLab delivery be an explicit spec deliverable?
## Rulings

Reviewed by Codex (model `gpt-6-sol`) on 2026-10-20. The author accepted all eleven findings on
2026-10-20, and each has been applied to `docs/SPEC.md`:

| Finding | Kind | Ruling and change |
|---|---|---|
| Confirmed metadata can bypass the catalog scope (F1) | Real problem (Codex called it an addition) | Accepted. New rule that the server checks Confirm's choices against the reference API (R61). |
| An unusable AI answer becomes a finalizable "no match" (F2) | Real problem | Accepted. Such lines stay without a result, and the invoice goes to matching failed so Retry reruns them (the group answer rule, R40). |
| An exact protocol can hide a conflicting study name (F3) | Real problem | Accepted. The study name is always compared, and a conflict lowers the suggestion to likely (the study suggestion, R20). |
| The planned cache warm-up does not enable caching (F4) | Real problem | Accepted. The request explicitly marks the cache point after the shared text (the shared matching prompt, R38). |
| The latency metric stops before the user sees the result (F5) | Real problem | Accepted. Both a stored time and an on-screen time are recorded, and the on-screen time is the headline, as the latency decision (D9) defines it (run timing R51, the timing display R52, the README timing report R60). |
| Extraction failure has no immediate transition (F10) | Real problem | Accepted. New rule for extraction errors: retried twice, then straight to extraction failed (R62). |
| Sponsor–study conflict handoff (F6) | Wording | Accepted. Choosing the offered sponsor switches the picker and selects the study (the cross-check, R22). |
| "Empty" numeric extraction fields (F7) | Wording | Accepted. Missing values are null (the extraction shape, R12). |
| Duplicate identity changes at confirmation (F8) | Wording | Accepted. The warning compares against earlier invoices' confirmed site and is rechecked when the site changes (the duplicate warning, R25). |
| Absolute invoice-text safety claim (F9) | Wording | Accepted. The rule now names the outcomes code controls and adds a hostile-text test invoice (the invoice-text safety rule R54, the automated tests R55). |
| Public repository delivery drops out of the spec (F11) | Addition, about 30 minutes, no app code | Accepted. New deliverable for GitHub and GitLab delivery with a fresh-clone check (R63). |

Before this review, a builder check (a fresh Claude reviewer reading the spec as its builder) raised
two points, settled as Claude's own calls and listed in the spec's "Calls I made": when
the first group is sent alone (the batching rule, R37), and what a repeat run means (the README
timing report, R60).
