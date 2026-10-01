# REMOTE INTERACTION

Canonical instruction for chats and agents that need to work with the MSP remote server.

## Purpose

This document defines **how a chat or agent interacts with REMOTE**. It is not a credential store and it does not contain server passwords, private keys, tokens, private addresses or tunnel secrets.

The standard chain is:

```text
Chat / Agent
    |
    v
Read repository instructions and inventory
    |
    v
Use an authorized REMOTE execution channel
    |
    v
Execute read / test / change task
    |
    v
Verify independently
    |
    v
Return evidence and result
```

## Important distinction

Access to this GitHub repository provides the **instructions and code**, not access to the server.

A chat or agent may execute REMOTE tasks only when its current environment exposes an authorized server-access tool or runner. The concrete access credential remains outside GitHub.

## Standard workflow

### 1. Understand the target

Before execution, identify:

- target service or application;
- requested action;
- whether the action is read-only or changes server state;
- expected result;
- verification method.

Use [inventory/services.yaml](../inventory/services.yaml) as the component map.

### 2. Confirm execution capability

The agent must determine whether an authorized REMOTE execution channel is actually available in the current session.

Examples may include an approved SSH executor, MCP bridge, runner or another explicitly authorized remote-execution tool.

Do not invent a connection method and do not infer credentials from repository content.

### 3. Prefer read-only diagnostics first

For investigation, first collect only the information needed to understand the current state:

- service status;
- relevant configuration names and paths;
- health endpoints;
- recent non-secret logs;
- repository / deployed version;
- dependency state.

Do not print secret values.

### 4. Execute the requested task

Use the smallest safe operation that satisfies the task.

State-changing work should be reproducible: if a manual server change is required permanently, its script, service definition or documented procedure should be added to this repository.

### 5. Verify independently

A command returning exit code 0 is not enough.

After a change, verify the expected result using a separate check such as:

- service status;
- health check;
- functional test;
- expected file/version;
- expected API response;
- restart persistence when relevant.

### 6. Report

Return a short result containing:

- what was checked or changed;
- actual result;
- verification result;
- any remaining problem;
- whether GitHub was updated to match the server.

## Standard remote-operation interface

Repository-managed remote helpers belong under:

`scripts/remote/`

The intended logical operations are:

- `status` — show current component/service status;
- `healthcheck` — verify expected functionality;
- `logs` — retrieve bounded non-secret diagnostic logs;
- `test` — run functional checks;
- `deploy` — apply repository-controlled deployment;
- `restart` — controlled restart of an approved service.

The transport underneath these operations may change. Chats should rely on the logical operation and documented service name rather than hard-coded addresses or credentials.

See [../scripts/remote/README.md](../scripts/remote/README.md).

## Security rules

Never store in this file or elsewhere in the public repository:

- server passwords;
- private SSH keys;
- access tokens;
- Telegram sessions;
- proxy/VPN/tunnel credentials;
- credential-bearing URLs;
- private certificates;
- production `.env` contents.

Use symbolic service names and safe paths instead.

## Current implementation status

The interaction contract is defined.

The concrete authorized REMOTE transport/executor will be recorded here only in a **non-secret form** after it is finalized. Until then, an agent must use only a server-access tool that is explicitly available and authorized in its current environment.
