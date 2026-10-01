# Architecture

## Purpose

`msp-server-stack` is the canonical public description of the reproducible MSP remote server stack.

The repository describes how the remote system is assembled, not the live secret state of the server.

## Logical layers

1. **Operating system** — Ubuntu server baseline and required system packages.
2. **Runtime** — language runtimes, service users and process supervision.
3. **Agent / orchestration layer** — server-side automation and agent components.
4. **MCP services** — MCP servers and adapters added to the stack.
5. **Application services** — Telegram integration, marketplace tools and other project applications.
6. **Data layer** — databases and runtime state stored outside Git.
7. **External dependencies** — model providers and third-party APIs.
8. **Observability and recovery** — health checks, logs, backups and restore procedures.

## Security boundary

Code and safe configuration are public. Production secrets and mutable runtime data are external to GitHub.

No component should require a secret to be hard-coded into source, systemd units or scripts.
