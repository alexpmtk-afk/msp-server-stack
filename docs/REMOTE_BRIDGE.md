# REMOTE BRIDGE

## Purpose

The standard ChatGPT-to-REMOTE execution transport is a dedicated private GitHub bridge:

```text
ChatGPT
  |
  v
private repository: msp-server-bridge
  |
  v
GitHub Actions
  |
  v
self-hosted Linux runner on REMOTE
  |
  v
approved local scripts / services
  |
  v
REMOTE verification result
```

The bridge is transport only. Application logic and reproducible server configuration stay in the public `msp-server-stack` repository.

## Current status

**Operational / acceptance PASS.**

The read-only `REMOTE Smoke Test` completed successfully through the self-hosted Linux runner on REMOTE.

This confirms the transport chain:

`GitHub Actions -> REMOTE runner -> command execution -> returned result`

Server-layout checks such as the presence of `/opt/mcp` are tracked separately from bridge transport health.

## Repository split

### Public: `msp-server-stack`

Contains architecture, recovery documentation, safe configuration templates, service inventory, versioned server-side scripts, health checks and deployment logic.

### Private: `msp-server-bridge`

Contains GitHub Actions workflows used to request REMOTE operations, runner routing and minimal execution wrappers.

The private repository is not a secret store. Runner registration tokens, application credentials, SSH keys and service secrets remain outside Git.

## Runner

The self-hosted Linux runner is registered to `msp-server-bridge` and uses the logical label:

`msp-remote`

Jobs should target the generic label rather than depend on one machine-specific runner identity.

## Acceptance model

### Bridge transport PASS

PASS requires:

1. GitHub schedules the job to the REMOTE runner.
2. The runner executes on the intended Linux server.
3. The command result is returned to GitHub Actions.
4. No secret value is printed.

### Server layout readiness

Checks such as `/opt/mcp`, required projects, services and health endpoints are separate acceptance layers.

A missing application path may make the server layout NOT READY without making the transport itself fail.

## Safety model

Read-only diagnostics are the default.

State-changing actions must:

1. name the target service/project explicitly;
2. use version-controlled scripts from `msp-server-stack` where practical;
3. avoid arbitrary secret output;
4. serialize writes to the same production target;
5. run an independent acceptance check after the change.

## Secret handling

Never commit or print runner registration tokens, API keys, application `.env` contents, private keys, Telegram sessions, proxy/VPN/tunnel credentials or credential-bearing URLs.

## Recovery

If REMOTE is replaced:

1. prepare the new Linux server;
2. restore the required server layout and protected data;
3. install a fresh self-hosted runner;
4. register it to private `msp-server-bridge` with label `msp-remote`;
5. run the read-only bridge acceptance test;
6. only then enable state-changing workflows.
