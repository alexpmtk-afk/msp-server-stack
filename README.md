# msp-server-stack

Public, reproducible description of the MSP remote server stack.

The goal of this repository is simple: if the remote server is lost, the software stack should be rebuildable on a clean server from this repository plus a separate protected backup of secrets and runtime data.

## What belongs here

- MCP services and supporting applications
- installation and deployment scripts
- systemd units and timers
- safe configuration templates
- dependency definitions
- server layout and service inventory
- health checks and tests
- backup and recovery procedures
- standard interaction procedure for chats and agents working with the remote server

## Remote server interaction

For any task that requires reading, testing or changing the remote server, start with:

**[docs/REMOTE_INTERACTION.md](docs/REMOTE_INTERACTION.md)**

It defines the standard chain:

`chat/agent -> authorized execution channel -> REMOTE server -> verification -> result`

GitHub stores the procedure and reproducible code. GitHub access by itself does **not** grant access to the remote server.

## What must never be committed

Real passwords, API tokens, SSH private keys, Telegram sessions, cookies, OAuth credentials, proxy/VPN/tunnel credentials, private certificates, production `.env` files, database dumps, backups, or any other live access material.

See [SECURITY.md](SECURITY.md) and [docs/secrets.md](docs/secrets.md).

## Repository layout

```text
apps/        application and MCP service source code
config/      safe configuration templates and schemas
docs/        architecture, deployment, remote interaction and recovery documentation
inventory/   machine-readable service inventory
scripts/     bootstrap, deploy, update, backup, remote-operation and health-check scripts
systemd/     service and timer units
tests/       automated validation
```

## Server layout

The canonical application root is `/opt/mcp`. See [docs/server-layout.md](docs/server-layout.md).

## Recovery principle

A rebuild uses two independent sources:

1. this public repository for reproducible code and configuration;
2. a protected, non-GitHub backup for secrets and required runtime data.

The repository intentionally contains no production credentials.

## Current status

Bootstrap stage. The secure repository structure, remote interaction contract and recovery contract are established first. Components will be added incrementally as the remote server is built.
