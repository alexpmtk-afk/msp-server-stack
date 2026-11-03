# E: первый настоящий WB report883801632 — пакет для независимой проверки

**API-пилот уже разрешён владельцем. НЕ требуется новое E/D разрешение.**
Старый REMOTE: OWNER_ATTESTED_OLD_REMOTE_RETIRED, не новый сетевой аудит.
Installed synthetic PASS принят из /var/lib/msp-quota-probe-i8kqe69o/result.json,
повторной synthetic/Redis protocol проверки НЕТ. A/B/C не переустанавливаются.
Этот пакет до выполнения root-команды: PREPARED_NOT_EXECUTED.

## Один шаг после независимой проверки ChatGPT

В существующей root-консоли WinSCP выполнить ROOT_ONE_LINE.txt одной физической
строкой. Launcher уже подготовлен /home/hermes/workspace/msp-wb-E.py. Команда
копирует его в fresh root0700 snapshot /var/lib, выставляет root0600, проверяет
literal SHA256 и только затем выполняет /usr/bin/python3 -I -B.
Self-contained script содержит exact nonsecret runner+hash и expected inventory;
никаких root imports из user-writable checkout. Две сборки byte-identical;
Bash one-line syntax проверен. Саму команду Hermes НЕ выполнял.

Код HTTP/archive остаётся строго accepted PR104:
`c1fee070e9efa0c925a78f266fdf03cb12a173cf` в текущем immutable release.
Принятый код, venv, base unit, секреты/права/пользователи, Redis не меняются.
Новые backfill/daily модули PR114 не подмешиваются в этот release.

## Preflight ДО activation

- Root-only snapshot/path ownership; existing UID995/GID985.
-17 accepted app modules: exact hashes/inventory, no unknown Python module.
-130 regular venv files: wheel8.1.0 bytes + accepted generated cfg/activation hashes;
  ordinary python/lib64 links exact allowlist; pinned host Python SHA.
- Base unit exact accepted root0600 SHA (не chmod), no foreign drop-in anywhere,
  inactive/failed state, PrivateNetwork=yes, Restart=no.
- Exact accepted pilot plan: wb_laser_master/2026/report883801632/type1/max3.
- Existing archive995:985/0700. Existing cursor/budget не удаляется и не обнуляется.
- Root0600 pilot credential compares ONLY selected token with master alias;
  no token copy/rotation/printing. sid presence+expiry checked locally; JWT
  signature/finance authorization не выдумываются. First bounded detail response
  verifies effective access;401/403 produce STOP via original executor.
- Root0600 Redis EnvFile requires exact approved127.0.0.1:16379/DB0/runtime principal
  and REQUIRE_REDIS=1. Reject extra env keys/PYTHONPATH/gates/proxies. URL/password
  никогда не печатаются и не копируются в report/command.
- Read-only verification of EXISTING synthetic receipt; no test rerun or keys.
  is-active of Redis only; no restart/protocol/SET.
- Refuse existing approval, root E state, foreign metrics/result/control files.
  Completed E repeat returns saved result, never new HTTP. Partial state STOP.

## Temporary activation only this existing service

Root controller creates private state /var/lib/msp-wb-E-883801632 (0700/0600)
and a separate root0755/nonsecret program directory under /var/lib, runner0644.
It durably stores ownership hashes BEFORE writing controls.

Only /run/systemd/system/msp-wb-pilot.service.d/90-msp-E-883801632.conf is created;
base /etc unit unchanged. PrivateNetwork=no for this run; IPAddressDeny=any stays.
Allowlist fixed for run: root-resolved public finance-api.wildberries.ru IPs,
local127.0.0.1 Redis and existing DNS resolver IPs. No global firewall/DNS edits.
DNS resolution is not a provider API call; address drift fails closed. L3 filter
allows those resolver addresses, while accepted HTTP transport additionally fixes
HTTPS host/path and blocks redirects. Existing TLS verification retained.

PID1 passes original Redis EnvironmentFile and original pilot-only LoadCredential.
Shared gate enabled only for this owner-approved E after accepted live synthetic.
Root-controlled approval expires600s and pins exact plan/code/archive/evidence.
No timer/[Install]/enable, Restart=no, existing TimeoutStartSec420 retained.
Existing unit ExecStart is temporarily wrapped to call the SAME run_bounded,
ReadOnlyHTTP and archive/controller implementation, not another HTTP sender.
Effective service identity/drop-in/network namespace/envfile read back before start.
One `systemctl start msp-wb-pilot.service`, parent bound480s; no retry loop around
systemctl. WinSCP command may wait several minutes for allowed quota intervals.

## HTTP, pages, budget and completeness

Only POST `/api/finance/v1/sales-reports/detailed/883801632` with original batch1000
and saved integer rrdId. No preliminary balance/list requests. Historical limit
is unchanged existing seller60s catalog+65s safety, local66s pacing. Official
current WB docs/swagger returned498; owner explicitly permits the first detail
request as bounded live verification rather than indefinite contract blockade.
No provider request happens before original synced sender budget and Redis admission.

Scoped wrapper additionally requires explicit integer reportId883801632/reportType1/
rrdId>0 on every200 row; original staged chain enforces ordered cursor/no duplicates.
200 is never terminal. Original pages+SHA before cursor; only204 and independently
verified local coverage/pinned CSV yield report_detail_complete=true.

Redacted events .wb-executor/E-883801632-events.jsonl record dispatch before opener,
HTTP status or UNKNOWN transport outcome, never headers/body/token. Metrics distinguish
sender entries from HTTP dispatch attempts and known responses. A recorded dispatch
attempt is not claimed as a proven server-received call when network outcome unknown.

After3 nonterminal entries PAUSED_BUDGET, progress retained; fourth call blocked.
No new approval/plan identity to reset budget.429 carries original headers delay
into existing shared Redis cooldown; errors retain state. Local reconciliation of
terminal data does not call API. Original run_bounded remains8 local steps/300sec
start-wait bound, with existing outer systemd420sec bound. Source report size unknown:
three entries may not reach204, so full report is not promised before execution.

## Closure and hold (not data rollback)

After service returns, controller removes ONLY matching-hash approval/runtime
fragment and empty owned drop-in directory, daemon-reload; readback requires
PrivateNetwork=yes, no drop-ins and no approval. Credentials/modes checked unchanged.
There is no report budget/cursor/Redis quota rollback. Pages and all immutable
archive generations survive. No other service stop/restart/edit occurs.

If root process dies, original worker bound and approval expiry still limit it;
unknown state NEVER automatically reruns. ROOT_HOLD_ONE_LINE.txt runs the same
verified payload --hold: verifies own active control hashes before stopping only
msp-wb-pilot, removes only known controls, preserves program/evidence/data.
Changed/unknown control file => no deletion/foreign stop. Cleanup uncertainty
reported as api_enabled_after_run=null, not false. Preserve private state; do not
rerun bootstrap or delete worker journals to make the command pass.

## Readback after operator execution

Public redacted result:
`/opt/mcp/report-run-results/wb-883801632-E.json`.
Private detailed root state/result/stderr:
`/var/lib/msp-wb-E-883801632/`.
Wrapper summary includes sender entries, HTTP attempts/statuses/unknowns, page
hashes, last cursor, staged rows and terminal verified rows, generation/manifest
and real archive paths. No financial amounts/raw rows/tokens in public result.

PASS only when DONE + terminal204 + verified saved report. PARTIAL for paused/waiting;
FAIL/HOLD for wrong IDs/auth/storage errors. A generic systemctl exit0 is not
completion proof. Historical28.10 100 rows are not relabelled as this pilot result.

## Independent tests and next gates

Local tests exercise unchanged PR104 through exact wrapper with mocked HTTP:
100rows → cursor100 → row101 →204,3dispatches/3entries, CSV verified; three200 pages
→ PAUSED_BUDGET/no4th; wrong report→HOLD after1 entry. Also scope/header secrecy,
exclusive modes under077, symlink rejection, credential binding/expiry, env
injection refusal, one-start closure/repeated-run no new API, foreign active controls
not stopped. These do NOT prove actual root/systemd/BPF/TLS runtime on VPS.

After actual pilot result, install reviewed PR114 helpers only as a new separately
pinned release, then admit bounded WB2026 batches. No mass job starts with this E
command. Ozon separate method acceptance/pilot follows; no Ozon calls in this E.
Daily schedule remains disabled until historical/dispatch acceptance. Owner API
permission persists; old REMOTE/Google Drive/token screenshots not requested.
