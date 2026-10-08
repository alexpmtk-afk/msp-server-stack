# MPSTATS REMOTE complete scoped integrity audit — 2026-10-08

## Verdict

**PASS — zero hard failures, zero warnings** for the installed MPSTATS MCP/Codex and Hermes skill contour.

This is a **deployment, configuration, permissions, inventory, and runtime-discovery audit**, not an MPSTATS business metric/API acceptance test. The user requested to postpone business-tool testing; no MPSTATS network/API calls were made during this audit.

Evidence: [private bridge issue #154](https://github.com/alexpmtk-afk/msp-server-bridge/issues/154), executed by the REMOTE self-hosted runner as `hermes`.

Auditor:
- public source: `scripts/remote/audit_mpstats_runtime.py`
- canonical audit code: `ad72b5704c33233189cbe9ed89597fd13feb1f77`
- expected **deployed** semantic source: `503262060d7d818a6e2ed6fd5dead5dd41aab157`
- bridge workflow: `.github/workflows/remote-mpstats-runtime-integrity-audit.yml`
- communication: issue-triggered fixed-title read-only audit with strict, redacted output.

## Actual REMOTE observations

| What was checked | Observed result |
| --- | --- |
| Runner account | `hermes`, PASS |
| Protected MPSTATS secret | regular file, mode `0600`, owned by `hermes`, PASS; **no content read** |
| `/home/hermes/.codex/config.toml` | mode `0600`, correct owner, PASS |
| `/home/hermes/.codex-dashboard/config.toml` | mode `0600`, correct owner, PASS |
| MPSTATS MCP registration | enabled in both TOML configs, expected HTTPS host/path and private token query, PASS |
| Original `hermes-tools` | remains in both configs, PASS |
| MCP entries in each config | **2** |
| Full configured MPSTATS endpoint comparison | same in both configs (value compared **in memory only**), PASS |
| Native Codex MCP list command | both `mpstats` and `hermes-tools` visible, PASS |
| Hermes skills CLI | `mpstats` visible and enabled, PASS |
| MPSTATS skill installed file set | matches expected set, PASS |
| Source integrity | **all 9 source mappings match canonical by SHA-256**, PASS |
| MPSTATS skill file ownership/modes | `hermes`, `0644`, PASS |
| Deployment marker | approved source commit and no-secrets flag, PASS |
| Hermes Gateway | active, PASS |
| Hermes Dashboard | active, PASS |
| MPSTATS temporary sibling entries | **0** |
| Codex config pre-MPSTATS backup count | **1 in each config directory** |
| Issues / warnings | **0 / 0** |

The audit did not print any authenticated URLs, token values, TOML contents, business values, raw CLI output, or credentials. The entire official documentation/semantic reference set is present at the deployed location.

### Scope and limits

- The protected secret's existence/permissions are verified, **not its current content/value**. Earlier authenticated MPSTATS MCP acceptance proved the token worked at that point in time, but token validity was not retested in this file audit.
- Checks confirm integrity against the **approved deployment commit**, not against all later `main` documentation snapshots. The latter must not be mistaken for file drift.
- Files in unrelated VPS projects, DevExec workspaces, Telegram applications, other agent skills, service logs and secret directories were not enumerated, modified, or cleaned.
- This report is a snapshot in time; no claim is made that another chat cannot modify files in the future.

## What counts as clutter?

### REMOTE: none found within the MPSTATS integration

The only additional copies observed are two legitimate `config.toml.pre-mpstats.*.bak` pre-install safety backups (one per Codex profile). They are not stray deployments and should be retained for controlled rollback. They must not be copied to public GitHub because config backups may contain credentials.

The temporary `.mpstats.install.*` / `mpstats.prev` entries searched within the Hermes productivity skills directory are absent.

Do **not** remove backups or alter another agent's workspace as part of MPSTATS housekeeping.

### GitHub: historical workflow clutter, not REMOTE runtime debris

Seventeen previously known MPSTATS-related/skill-discovery workflow files were independently fetched from the private `msp-server-bridge` default branch. All inspected workflow GitHub Actions expressions are unescaped; no known broken expression remains in these files.

Four checked workflows can perform file mutations:

- `remote-mpstats-secret-init.yml` — legacy protected secret-template initializer, unnecessary for day-to-day usage;
- `remote-mpstats-skill-deploy.yml` — historical initial skill deployer pinned to old commit `64e0d20c...`;
- `remote-mpstats-metrics-skill-deploy-v2.yml` — historical update pinned to `f1a538de...`;
- `remote-mpstats-official-knowledge-skill-deploy-v3.yml` — already-consumed update pinned to `50326206...`.

The remaining 13 checked workflows are fixed-purpose diagnostics or controlled read-only acceptance calls.

**Hygiene recommendation:** retire or disable historical one-time state-changing deployment triggers in a separate, reviewed bridge-only change. Do not delete them during this read-only audit: Git history preserves provenance, and parallel DevExec development may be using the bridge. Most critically, do not launch the unguarded original v1 deploy workflow against the accepted current skill.

The current `remote-mpstats-runtime-integrity-audit.yml` is read-only and should remain available.

## Reproducibility and GitHub sync

- Canonical source files: `apps/hermes/mpstats_skill/SKILL.md`, `config/mpstats/semantics/*.json`, `docs/MPSTATS_TOOLS_2026-10-07.md`, `docs/MPSTATS_SEMANTIC_LAYER.md`, `docs/MPSTATS_OFFICIAL_KNOWLEDGE.md`.
- Installer: `scripts/deploy/install-mpstats-skill.sh`; original Codex registration installer: `scripts/remote/install_mpstats_mcp.py`.
- Read-only auditor: `scripts/remote/audit_mpstats_runtime.py`; audit protocol: `docs/MPSTATS_AUDIT_PROTOCOL.md`.
- Installed target: `/home/hermes/.hermes/skills/productivity/mpstats/`.
- All active semantic skill files are already identical to their canonical pinned source; **no deployment or forced resync is necessary**.
- This sanitized report and audit status are the only new items requiring a public GitHub commit.

## Readiness decision

**Ready for later MPSTATS MCP analytical testing.** No runtime remediation needed.

Outstanding unrelated concerns:
1. The five historical MPSTATS business-tool access errors (own-cabinet and own-product families) remain unresolved; no business API calls were made in this audit.
2. The 108 MCP tools are registered, but only earlier samples of response shapes have been validated. Do not mislabel this file audit as 108/108 successful business-tool tests.
3. Historical one-shot write workflows are review-only cleanup candidates; not touched.
