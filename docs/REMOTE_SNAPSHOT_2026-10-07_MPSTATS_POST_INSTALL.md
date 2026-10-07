# REMOTE MPSTATS post-install snapshot — 2026-10-07

## Scope

Post-install checkpoint after adding the official MPSTATS remote MCP definition to both active Codex configurations.

No production credential values are recorded here.

## Installation result

Tracked installer:

`scripts/remote/install_mpstats_mcp.py`

Installer result supplied from REMOTE console:

```text
configured=/home/hermes/.codex/config.toml mode=0600 backup=config.toml.pre-mpstats.20261007T134519Z.bak
configured=/home/hermes/.codex-dashboard/config.toml mode=0600 backup=config.toml.pre-mpstats.20261007T134519Z.bak
result=PASS
```

## Independent sanitized verification

Private bridge issue #110 executed the read-only `[REMOTE] mcp-config-audit` probe.

Verified:

- Codex CLI: 0.159.3.
- Main Codex config exists, mode 0600, 2 MCP servers.
- Dashboard Codex config exists, mode 0600, 2 MCP servers.
- Existing `hermes-tools` entry remains present.
- New `mpstats` entry is enabled.
- MPSTATS transport: `streamable_http`.
- Safe endpoint: `https://mcp.mpstats.io/mcp`; query/token redacted by the audit.
- MPSTATS startup timeout: 30s.
- MPSTATS tool timeout: 600s.
- Protected `/opt/mcp/secrets/mpstats.env` exists, mode 0600, owner hermes:hermes.

## Service health

Private bridge issue #111 executed the read-only `[REMOTE] agent-status` probe after installation.

Verified active/running:

- `hermes-dashboard.service`
- `hermes-gateway.service`

Hermes listener remains on `127.0.0.1:9119`.

## Acceptance state

Configuration installation: **PASS**.

Post-install service health: **PASS**.

Live MPSTATS MCP protocol acceptance: **PENDING**.

Next acceptance step:

1. establish MCP `initialize`;
2. run `tools/list`;
3. select and execute one harmless read-only tool;
4. only then start the semantic inventory.
