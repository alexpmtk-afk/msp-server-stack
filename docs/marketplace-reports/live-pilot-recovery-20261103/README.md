# PR115: isolated approval permission recovery

The root writer created approval.json root:root0600 while the accepted reader runs as msp-reports995:985. This is a reproducible pre-sender PermissionError. Only the nonsecret approval capability becomes root:msp-reports0640. Root ownership, parent directories, credential/Redis files and their0600 modes remain unchanged. No A/B/C installation or token updates.

## Evidence and limits

The public receipt confirms PermissionError/worker_exit1/API closed, but records no exception filename. Hermes cannot access the historical root-only logs; sudo requires a password. Do not claim historical HTTP=0 or a confirmed historical stack trace. Recovery reads the exact old private result/stdout/stderr, compares the public receipt and pinned failed runner source, then reconciles the original budget, events and staged pages without modifying them. Stderr is never printed. Unknown evidence, orphan pages or missing counters with HTTP history stop before provider execution.

## Execute once after independent review

Use ROOT_ONE_LINE.txt in the existing root console. The local source is /home/hermes/workspace/msp-wb-E-recovery.py; its content must match MANIFEST.json/launcher_sha256 and the reviewed Git commit. The command snapshots it into a fresh root-only directory and verifies SHA256 before execution. Do not use the old PR115 command.

Before starting the existing finance unit, the package runs two no-network transient read-only processes as actual msp-reports995:985: an old0600 fixture must fail with PermissionError, the fixed approval0640 must validate. Existing report state hashes must remain unchanged. These checks do not load tokens, reserve Redis quota or enter the sender. Only after both pass may the same installed finance service run, using the original plan/digest and cumulative maximum3 entries (including previous entries). Existing quota delays remain effective. AWAIT/PAUSED is not a completed report.

Only new recovery evidence is written to /var/lib/msp-wb-E-883801632-recovery1. Old /var/lib/msp-wb-E-883801632 and all archive files are retained. New public result: /opt/mcp/report-run-results/wb-883801632-E-recovery1.json. It includes the reconciled prior entries/observed dispatch attempts, cursor/pages and this-run HTTP evidence. Terminal204 plus validated archive is required for PASS.

## Stop / rollback

ROOT_HOLD_ONE_LINE.txt closes only this package's hash-matching temporary controls and stops only its known pilot service; approval is removed and the original PrivateNetwork=yes unit restored. No pages, cursors, budgets, tokens or logs are removed. On uncertain/crashed preparation use hold and inspect the new private state; never delete the state to retry. No timers enabled, no independent financial sender, no Redis reinstallation.

## Tests

Network-denied local suite:252 tests, one real-root fixture skipped locally. Eight recovery evidence tests cover preserved nonzero budget, missing budget with HTTP evidence, bad seals, orphan pages, altered old runner, differing failure and symlink rejection. GitHub hosted CI additionally must execute the actual unprivileged-reader test: root0600 denied, root:reader_group0640 accepted by the original authorization reader. Production performs the same negative/positive check with UID995/GID985 before HTTP.
