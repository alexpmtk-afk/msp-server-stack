# REMOTE INTERACTION

Canonical instruction for chats and agents that need to work with the MSP remote server.

## Standard transport

The preferred standard transport is:

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

GitHub stores the procedure and reproducible code. GitHub access by itself does **not** grant server access.

## Standard workflow

1. Read this document and [../inventory/services.yaml](../inventory/services.yaml).
2. Identify the target service/project and whether the task is read-only or state-changing.
3. Use only the authorized `msp-server-bridge` workflow or another explicitly approved REMOTE execution tool.
4. Prefer read-only diagnostics first.
5. Execute the smallest required operation.
6. Verify the result independently.
7. Report what changed, what was verified and whether GitHub matches the live server.

## Read-only diagnostics

Typical safe checks:

- service status;
- bounded recent logs without secrets;
- deployed version / commit;
- expected directory presence;
- health endpoint or functional test;
- process and dependency state.

Do not print secret values.

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

The transport should not hard-code production credentials.

## If the bridge is unavailable

Do not pretend the task ran. Prepare the exact safe action and report that REMOTE execution is unavailable until the runner/bridge is restored.
