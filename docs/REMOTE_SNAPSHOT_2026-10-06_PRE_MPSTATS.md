# REMOTE pre-MPSTATS snapshot — 2026-10-06

Purpose: reproducible pre-change checkpoint before integrating the official MPSTATS remote MCP server.

Source of live verification: private `msp-server-bridge` read-only command `[REMOTE] canonical-snapshot-audit`, issue #93. Result: PASS.

## Host and runtime

- OS: Ubuntu 24.04.5 LTS, x86_64.
- Logical host: VM-817589.
- Uptime at audit: about 3 days 18 hours.
- Hermes Agent: v0.21.5+5295.g234badf.
- Codex CLI: 0.159.3.
- Tailscale: 1.102.4.
- nginx: 1.24.0.
- Hermes reports an upstream update available; no update is part of the MPSTATS integration task.

## Verified active services

- `hermes-dashboard.service`
- `hermes-gateway.service`
- `nginx.service`
- `tailscaled.service`
- self-hosted GitHub Actions runner for `msp-server-bridge`

Verified local listeners include Hermes on `127.0.0.1:9119`, nginx proxy on `127.0.0.1:9120`, and SSH on port 22.

## Hermes execution policy

- Hermes dashboard and gateway run as the unprivileged `hermes` user.
- `HERMES_YOLO_MODE=1` is present in the current Hermes service policy.
- Existing Telegram allowlists and service-user permissions remain the external safety boundary.
- MPSTATS integration must not change this policy unless separately approved.

## Current application layout

Canonical target root:

```text
/opt/mcp/
├── projects/
├── data/
├── secrets/
├── runtime/
├── logs/
└── backups/
```

At the audit, only the protected `/opt/mcp/secrets` portion was populated. Hermes runtime remains under `/home/hermes/.hermes`.

This layout gap must be respected during MPSTATS integration: the MPSTATS credential belongs in protected server-side secret storage, while reproducible templates and documentation belong in GitHub.

## Existing integrations

- Telegram gateway and channel archive are operational.
- QRsite/Andrey marketplace integration remains present.
- Existing integrations must not be modified as part of the first MPSTATS connection test.

## MPSTATS integration boundary

The first stage is read-only integration of the official MPSTATS remote MCP endpoint.

No real token may be committed to GitHub, written into public documentation, printed in logs, issue comments, process listings, or chat messages.

Initial acceptance requires:

1. protected token storage on REMOTE;
2. a reproducible non-secret configuration shape in GitHub;
3. successful MCP connection from the intended agent/runtime;
4. successful tool discovery without exposing the token;
5. one harmless read-only call;
6. confirmation that existing Hermes, Telegram, nginx, Tailscale and QRsite functions remain healthy.

Semantic cataloging of MPSTATS tools follows only after live tool discovery.
