# Bounded finance diagnostics upgrade — 2026-11-05

## Actual incident (not a reproduced provider failure)

Attempt nonce `41a54780de264dbca38b0ddbf9be7907` failed in the root
administrative controller at 12:38:47–48 MSK. No public job/summary receipt
was produced. The financial unit's last start remained 12:29:10 MSK (the
previous successful report865431404). No second API invocation is authorized
by this diagnostic upgrade. Three accepted report receipts total1658 rows.
The archive itself is not readable by hermes; unchanged receipts are not an
independent verification of current protected page contents.

Installed controller immutable-payload verification was separately executed
read-only as hermes: PASS. Root journal and claims are not readable by hermes.
The devexec maintenance broker's fixed contract covers only devexec; it is not
an authorized finance installation or journal-read route. Do not abuse it.
Installed diagnostic readback now confirms HOLD in SELECT_REPORT_READ_ONLY,
control.choose line58 (completed archive receipt rejected). Source inspection
and an isolated failing regression reproduce the cause: report_receipt called
read_completed_wb_pages, whose archive._lock opens O_CREAT|O_RDWR. Under the
administrative/diagnostic unit's ProtectSystem=strict, the archive is read-only.
The first missing report skips completed-page reads; the next wake visits the
completed report and fails at that hidden write. This is not a WB rate error.

The updated finance_receipts overlay reads terminal pages without writer locks,
validates captured state/cursor chain, checks every page's SHA256 again on its
actual read, and retains publication/business-row verification. Controller/
diagnostic admission already serializes against the sole financial executor.
No writable archive permission is added to either root unit. The isolated test
first reproduced HOLD on a denied write to the archive lock; with the fix it
verifies the completed receipt with zero writable opens and byte-identical
archive evidence. Live protected-page verification remains pending update.

## Installed capabilities after the one-time upgrade

`msp-finance-diagnose` (hermes UID1001, no arguments) starts ONLY
`msp-finance-diagnostics.service` using an exact start-only Polkit rule.
No sudo, arbitrary command/path, user-editable root executable, journal-reader
membership, secret-read capability, budget reset or financial start is granted.
The root diagnostic service is PrivateNetwork=yes / ProtectSystem=strict,
with write access ONLY to the existing public results directory. Credential
and Redis configuration directories are inaccessible to it.

It verifies immutable code, reads the accepted request, checks old activation
ownership, repeats selection READ_ONLY and reconciles selected budget/HTTP/
staging. It does not consume the request nonce, create a claim, acquire Redis
quota, start/stop finance, clean up activation or alter source evidence. A
shared nonblocking lock refuses diagnostics while control is executing.
A HOLD is a successful diagnostic run, not permission to retry a download.

Receipt: `/var/lib/msp-finance-control/results/diagnostics-latest.json`.
Root-owned0644, atomic replacement and parent fsync, no exception text,
locals, credential values or raw HTTP. Includes phase, exception class/errno,
module basename/function/line, selected plan if known and safe unit status.
Future ordinary control failures additionally publish `<nonce>-failure.json`
and `controller-latest-failure.json`, including failures before job creation.
Killed-before-handler cases remain distinguishable from reported exceptions.

## One-time installation / rollback

Existing A/B/C and finance worker, archive, Redis, token files and schedules
are unchanged. This is a different immutable controller release, never edits
inside the installed PR120 release. Use **UPGRADE_ONE_LINE.txt**, not the old
fresh-install command. The update now pins the already-installed diagnostic release e418e253, not
the superseded initial PR120 release. Pinned old release/hashes and all old wiring must
match. Refuse concurrent financial execution, unknown targets and partial
installation. Back up only changed wiring and INSTALL.json to root0700
`/var/lib/msp-finance-control/upgrades/diagnostics-<payload-prefix>`.

After replacement, verify units, reload systemd and start ONLY the read-only
diagnostic unit. No financial/control/recover start or daily timer activation.
Existing recovery-at-boot stays as configured; no new scheduler or executor.
Repeated install verifies hashes/wiring and performs no download.

Rollback: execute the SAME reviewed root snapshot with `--rollback`.
It restores only exact backed-up old wiring/INSTALL.json, refuses changed
wiring or active execution, removes only its own new diagnostic entry/rule/unit,
reloads systemd and starts nothing. New/old immutable releases, all receipts,
claims, pages, counters, generations and credentials are retained. Partial
upgrade is HOLD; do not rerun a financial wake to test it.

## Boundaries and tests

Tested offline: failure location without message/local leaks; first-failure
stop; old-receipt preservation and symlink rejection; full temporary-directory
upgrade/idempotence/rollback transaction; live drift stops before writes/start.
The temporary transaction tests inject current-UID trust and mock systemctl;
they are not root/VPS acceptance. Hosted CI separately exercises real systemd,
root-owned0644 diagnostic publication and UID1001 Polkit/client read without
incrementing the financial fixture counter. No provider calls in these tests.

The next operation after installation is read-only diagnostics and repair of
the revealed defect, NOT an automatic retry of report865431405. Source edits,
tests and PR publication are available to hermes; protected root-code replacement
still requires the exact reviewed administrative package. No unlimited-root
or unrestricted auto-updater is introduced under the guise of diagnostics.
