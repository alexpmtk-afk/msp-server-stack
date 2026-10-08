# MPSTATS REMOTE audit protocol

## Purpose

Verify deployed MPSTATS MCP and Hermes skill **without calling MPSTATS API**, altering production services, or touching parallel DevExec work.

The canonical read-only checker is `scripts/remote/audit_mpstats_runtime.py`. It is invoked by a fixed-title private `msp-server-bridge` workflow with a **pinned canonical checkout**.

## Checks

1. Runner is user `hermes`; protected `/opt/mcp/secrets/mpstats.env` is a regular file owned by `hermes` with mode `0600`. Its **contents, size and token are never read or printed**.
2. The two Codex TOML configurations can be parsed and each contains both `hermes-tools` and enabled `mpstats`; MPSTATS uses the expected HTTPS host/path and an opaque token query. The two full URL values are compared **in memory only**.
3. Both configs are owned by `hermes` with mode `0600`; only the *number* of pre-MPSTATS local backups is reported.
4. The installed Hermes MPSTATS skill matches the **exact previously approved canonical source commit** byte-for-byte by SHA-256 for all known skill and reference files.
5. No unexpected files inside the installed skill and no stale `.mpstats.install.*` or `mpstats.prev` sibling directories; names of any unexpected files or secret values are not printed.
6. The deployed marker references the approved commit and `contains_secrets=false`.
7. The two Hermes services are active. `codex mcp list --json` and `hermes skills list` are run with stdout/stderr captured; only whitelisted PASS/FAIL properties are reported, **never raw configuration or CLI output**.

## Audit does not do

- No `tools/call`, `initialize`, `tools/list` or other remote MPSTATS calls.
- No Telegram messages, new Hermes agent task, service restart, package installation, systemwide cleanup or credentials rotation.
- No removal of local backups or temporary directories. Unexpected files must be separately diagnosed and approved for cleanup before any change.

## Interpret results

- **PASS**: every integrity and service check passed; no suspicious scoped leftovers.
- **WARN**: no hard failure but extra MPSTATS-related temporary/previous directories were found; diagnose before deleting.
- **FAIL**: one or more configuration, permission, source-integrity, CLI discovery or service checks failed; report exact check name without revealing content.

Do **not** update the deployed commit or replace an installation merely to make a failed audit pass. Investigate first, especially when another ChatGPT chat may be working on the same REMOTE stack.

## GitHub synchronization

Store the sanitized audit findings and conclusions in the public `msp-server-stack` documentation, but retain secret-bearing TOML, URLs, token files, CLI raw outputs and full business data exclusively on REMOTE. Private bridge issue comments contain only the safe, reduced audit result.

When auditing bridge hygiene, classify obsolete fixed-title workflows as candidates only. Deletion of another chat's active workflows or DevExec files is out of scope.
