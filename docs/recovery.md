# Recovery

This document defines the target recovery contract. Commands will be filled in as deployment automation is implemented.

## Recovery target

Starting point: a clean supported Ubuntu server.

Expected result: the same application stack is installed, configured, started and validated without relying on undocumented manual changes from the previous server.

## Required inputs

- this repository
- protected secret backup
- protected persistent-data backup, where required
- access to external providers and source repositories used by the stack

## High-level sequence

1. Prepare the operating system and required service account(s).
2. Create the canonical `/opt/mcp` directory structure.
3. Clone the required repositories.
4. Install pinned system and application dependencies.
5. Restore secrets from protected storage.
6. Restore persistent data where required.
7. Install systemd units and timers.
8. Start services in dependency order.
9. Run health checks and functional tests.
10. Verify backup and restart behavior.

## Acceptance rule

Recovery is complete only when automated checks confirm that required services are running and their expected interfaces respond correctly.

Any manual recovery step discovered during a real deployment must be documented or automated here before the deployment is considered reproducible.
