# WB optional buyout publication policy —13.11.2026

Status: PREPARED_NOT_INSTALLED. Existing Root934_py03 continues collecting.
Owner explicitly approved this business correction in the current conversation.
Scope: all three WB cabinets, daily/weekly/bootstrap, saved-queue reassessment,
current-source reuse and Remote Server notices. Ozon semantics/wiring unchanged.

## One common policy

reportType1 main is required; reportType2 WB buyouts is conditional and may not
be published at all. Absence is NOT evidence of financial zero, zero sales or
absence of foreign orders. No empty report, source row or amount is fabricated.

Verified main weekly coverage closes its exact historical daily dates. Thus a
main period through8November does not require daily optional reports for1–8Nov.
The next daily planning watermark is the primary weekly report, NOT the minimum
of primary and optional publication dates. Exact fragments and year tails stay
intact. Existing positive daily type2 rows are retained in the active catalog
until equivalent real type2 weekly coverage replaces them; primary reports do
not erase buyout financial rows. No source/history/ledger deletion.

For an open daily period, optional absence may wait three total20min checks;
Monday weekly may wait ten. After the last check, absent optional publication
is OPTIONAL_NOT_LISTED, normal completion, no missing-report alert. Earlier
normal closure is allowed when verified main weekly covers the day, or a later
verified main document exists. For weekly main already ready after Monday,
optional nonpublication is normal. Main absence retains its3daily/10Monday
retry/notification rules. A positively listed buyout report without usable
terminal detail is a real incomplete download: retries/notice remain. HTTP
errors, partial/unknown sends, corrupt source, HOLD are never called absence.

## Existing queue and evidence

Central policy.py is used by worker and controller. Settled, source-verified
optional-only waits are reassessed against a freshly verified current view,
without new HTTP or rewritten worker results. Attempts/nonces/budgets do not
reset. IN_FLIGHT and HOLD are never silently settled. Retained request triples
are all checked before any no-HTTP early weekly closure. Original source rows
and report IDs remain exact. Worker/root receipts record optional absence and
its evidence, explicitly financial_zero_inferred=false.

The actual read-only policy preview resolved nine old Dmitrieva waits without
new requests:1–8Nov by verified weekly coverage,9Nov by a later verified main.
This preview did NOT change the installed protected controller.

## Narrow protected upgrade

Use ROOT_WB_OPTIONAL.txt, one physical Bash line from Linux root console.
The hash-pinned launcher extracts and verifies an immutable75-file snapshot
and nested manifest before upgrade_root.py. It verifies the exact installed
934_py03 source and wiring, pauses ONLY the WB coordinator, and lets any owned
shared worker finish. No kill/restart of a live shared sender. Only exact owned
inactive controls are reconciled with the original trusted cleanup helper.
Unexpected/foreign controls or partial evidence are retained and block upgrade.

It backs up and replaces ONLY WB service ExecStart and root_release/policy in
WB schedule/installation metadata. Same cycles, private job map, source paths,
nonces, original attempts, all retained responses and budget entries survive.
The coordinator then resumes, not a new backfill. Existing08:45 timer, Ozon08:40,
canonical financial data, accepted runtime/Redis/credentials and Gateway stay
unchanged. No new background model calls or Telegram test messages.

Tests:3 central-policy,12 edge/reassessment,6 handoff/transaction and39 existing
WB regressions, on3.14/3.12 from the actual extracted release, network denied,
project imports checked. Real root upgrade/handoff is NOT executed by tests.
Full archive and baseline document identities remain local; public handoff is
delta source + safe hashes/evidence, not the complete local activation bundle.

After owner execution: read installation.optional_buyout_policy and root_release,
optional-policy-upgrade.json and actual live public cycle. Verify old1–8Nov
waits disappear without new HTTP/attempt resets, current days continue, primary
missing/listed incomplete optional remain actionable, both times unchanged.
Never rerun the original full installer or reset the source request ledger.
