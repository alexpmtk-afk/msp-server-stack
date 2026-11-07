# Local error detection and remediation — owner authorization 2026-11-07

Owner request: detect errors without a chat query, identify their cause, fix and
resume already-authorized work. Applies to default profile and this local host.
Monitoring covers local user service failures, visible system service failure
metadata, user priority-error journal, enabled cron failures and NEW Hermes
errors.log entries. Remote hosts, unlogged failures and protected root journals
are not automatically visible. Root writes still need an actual authorized
administrator execution route, not merely a request to repair.

Collection: hermes-error-watch.timer every30 seconds, no LLM/network actions.
Agent: existing Hermes cron monitor mode every1 minute, unchanged-output silence.
Incident catalog: /home/hermes/.local/state/hermes-error-watch/incidents.json.
Script: /home/hermes/.hermes/scripts/msp_error_watch.py.
Incident fields contain class/location/IDs, not exception text, tokens or values.
Same unresolved fault has at most4 automatic investigation rounds (initial plus
three10-minute follow-ups); a different error class or recovered-then-new failure
opens another incident. blocked_external is retained visibly without futile retries.

For each actionable incident: inspect exact receipts/metadata, establish a
reproduction, fix reversible local code/config in scope and run affected tests.
Resume only from the last verified checkpoint, with original nonce/budget and
protected admission. Mark resolved only after independent observed recovery;
a live failed service cannot be silenced by a false resolved claim.

Do not replay external business writes, resend messages or alter price/dimensions
as incident recovery. Unknown delivery/dispatch stays blocked until reconciled.
Do not change permissions, root brokers, tokens, quotas or another profile.
No external messages are authorized by this policy; keep cron output local.

Finance current scope: WB Laser Master ONLY, historical closed reports under
installed root policy; no other cabinet, Ozon or daily schedule activation.
The corrected user driver delegates full archive/budget verification to the
EXACT pinned root controller, which checks choose/report_receipt/reconcile under
an exclusive lock BEFORE sender activation. Do not run the redundant standalone
msp-finance-diagnose during normal admission: its root service currently has a
60-second timeout and is a known separate administrator-only maintenance item.
Never remove actual pre-HTTP integrity/admission checks or reset any ledger.
Root immutable controller pin is recorded in history_driver. Failed preflight
before new nonce may be recovered only after previous root receipt, request,
network closure and installed version reconcile; DISPATCH_UNCERTAIN is not that.

Use --mark ID resolved|blocked_external|investigating --evidence 'sanitized verified evidence'
on the monitor script. Explicit evidence is mandatory. For root-only repair,
save a concrete reviewed package/command and mark blocked_external; do not claim
it installed. A missing root service must not be invented/recreated from a name.
If repair exceeds one cron run, retain evidence/progress locally and finish the
next bounded step at a later investigation. No blind infinite retry loops.
