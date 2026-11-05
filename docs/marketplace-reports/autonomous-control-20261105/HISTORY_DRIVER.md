# Unprivileged sequential WB backfill admission

This is NOT a financial HTTP sender, scheduler timer or Redis queue. It invokes
only installed `msp-finance-diagnose` and `msp-finance-wake --jobs 1`, serially.
The only provider sender remains msp-wb-pilot.service under msp-reports. No
credential/Redis/archive reads or direct provider HTTP occur in this driver.

The hermes user systemd service is msp-wb-history-driver.service, Restart=no,
NoNewPrivileges=yes, RestrictAddressFamilies=AF_UNIX. The already enabled user
linger keeps it independent of the chat/login. No daily timer is installed or
enabled. Transient service is not auto-resumed after reboot: durable DISPATCHING
requires reconciliation, never blindly resends on relaunch.

Code: ~/.local/share/msp/finance-history-driver/history_driver.py
State: ~/.local/state/msp-finance-history/state.json (hermes0700/0600)
Wrapper-only diagnostics: last-client-output.txt (0600).

It waits without waking finance until the exact approved read-only-receipt fix
release is installed. Each wake is preceded by root diagnostic PASS and a
closed financial unit. Completed-report exclusions and real IDs come from the
existing protected discovery/archive verifier, not a separate user-side queue.
It snapshots admission-in-progress before invoking the fixed client and saves
the exact root receipt before continuing. Per-wake budget remains3, cumulative
budgets/cursors remain in existing journals. Global bounded limit512 wakes.

Owner continuation approval: after PASS, wait at least70 seconds. A normal
PARTIAL is auto-continuable ONLY when root attests one PAUSED_BUDGET job,
exactly3 consumed wake entries/HTTP attempts, HTTP200/200/200, zero unknowns,
not complete, sealed cumulative count below the existing approved ceiling,
API closed and scheduling off. Wait max(now+70, saved not_before_epoch), then
recheck root diagnostic PASS, SAME selected plan hash and network closure.
Cumulative counters must increase exactly3 across successive budget pauses.
No initial/root budget/plan/cursor is changed. Root Redis limits still govern
every individual HTTP request inside each portion.

All other PARTIAL/HOLD/UNCERTAIN/nonzero/foreign activation stops without retry
or state reset. HTTP429 is not mistaken for a normal200-only budget pause. A previous DISPATCHING on process recovery is
HOLD, even if the process died before the child reached HTTP. Receipts and child
output are retained for reconciliation. The driver does not overwrite root
inbox, budgets, credentials or archive itself; only the reviewed installed
client allocates requests.

Cabinets: wb_laser_master -> wb_novokshenov -> wb_dmitrieva. Before switching,
read-only diagnostic must explicitly show selected_plan=null for the SAME
last request cabinet after all available closed reports/inventories verify.
Discovery is not downloaded coverage. Completion is only the closed reports
available at the root policy as_of (currently2026-11-05), not future periods.

This is initial backfill, NOT daily finance automation. Daily dynamic-date,
late-correction execution and Ozon method acceptance remain separate gates.
No unconfirmed Ozon method is enabled by this driver.

Local tests cover no wake before approved release, partial/no automatic retry,
crash/unknown-dispatch refusal and durable PASS. Initial live service acceptance
must be recorded from actual protected root receipts, separately from tests.


## Reconcile the existing safe pause

The first deployed driver had stopped on root nonce
9c79ca70e5f44a3a8f762083730077cc (report594988667/type1) after3 successful
HTTP200 entries. The new driver may migrate this HOLD only when its complete
saved receipt exactly equals the original root-owned public receipt, the normal
pause predicate passes, and read-only diagnostics reverify original budget,
HTTP history, page chain and matching plan. It preserves the last receipt,
all11 previous wakes, cabinet index and spent count3, records COOLDOWN, and
waits70 seconds before continuing. No blanket HOLD reset or automatic retry
of unknown/crashed dispatch is introduced.
