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

PASS continues; PARTIAL/HOLD/UNCERTAIN/nonzero/foreign activation stops with no
automatic retry or state reset. A previous DISPATCHING on process recovery is
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
