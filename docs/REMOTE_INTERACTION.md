# REMOTE INTERACTION

Canonical instruction for chats and agents that need to work with the MSP remote server.

## Standard transport

The active standard transport is:

```text
Chat / Agent
    |
    v
private GitHub repository: msp-server-bridge
    |
    v
GitHub Actions
    |
    v
self-hosted Linux runner on REMOTE
    |
    v
version-controlled operation / verification
    |
    v
result
```

See [REMOTE_BRIDGE.md](REMOTE_BRIDGE.md) for the bridge contract.

Current transport status: **OPERATIONAL / PASS**.

## Chat-triggered command channel

The private bridge supports a whitelisted GitHub issue command:

`[REMOTE] status`

`[REMOTE] agent-status`

Additional read-only maintenance probes currently available through the private bridge include:

- `[REMOTE] telegram-status`
- `[REMOTE] codex-rate-limits`
- `[REMOTE] canonical-snapshot-audit`

These probes do not grant arbitrary shell access; each workflow has a fixed, reviewed diagnostic scope.

The workflow accepts only this exact command from the repository owner, runs a safe read-only status check on REMOTE, posts the result back to the issue and closes the request automatically.

Arbitrary shell commands from issue text are not allowed.

The current `status` command reports only basic host health: uptime, load, memory, root disk usage, architecture and whether `/opt/mcp` exists.

The `agent-status` command checks Hermes/Codex installation, services, processes and local listener state without changing the server.

Current agent state: Hermes services are active and Codex is installed. Hermes exposes a local API on `127.0.0.1:9119`, including task creation and dispatch endpoints. Direct task dispatch from the GitHub bridge is not yet enabled because the runtime currently returns `401 Unauthorized` for dispatch without an approved authentication handoff.

GitHub stores the procedure and reproducible code. GitHub access by itself does **not** grant server access.

## Standard workflow

1. Read this document and [../inventory/services.yaml](../inventory/services.yaml).
2. Identify the target service/project and whether the task is read-only or state-changing.
3. Use the authorized `msp-server-bridge` workflow.
4. Prefer read-only diagnostics first.
5. Execute the smallest required operation.
6. Verify the result independently.
7. Report what changed, what was verified and whether GitHub matches the live server.

## Read-only diagnostics

Typical safe checks include service status, bounded recent logs without secrets, deployed version/commit, expected directory presence, health endpoints and dependency state.

## State-changing work

Permanent server changes should be reproducible. If a manual change is required, add its script, unit or documented procedure to `msp-server-stack`.

For one production repository or service, use one writer at a time.

After any uncertain write result, inspect actual state before retrying.

## Standard logical operations

Repository-managed helpers belong under `scripts/remote/`:

- `status`
- `healthcheck`
- `logs`
- `test`
- `deploy`
- `restart`

The transport must not hard-code production credentials.

## Acceptance distinction

A successful bridge run proves REMOTE command transport.

Application readiness, `/opt/mcp` layout, individual services and business functionality require their own acceptance checks.

## If the bridge is unavailable

Do not pretend the task ran. Report that REMOTE execution is unavailable until the runner/bridge is restored.
