# Remote operations

This directory is the canonical place for safe, reusable REMOTE-operation helpers.

Main documentation:

- [REMOTE interaction](../../docs/REMOTE_INTERACTION.md)
- [REMOTE bridge](../../docs/REMOTE_BRIDGE.md)

The standard transport is the private `msp-server-bridge` GitHub Actions repository with a self-hosted Linux runner on REMOTE.

## Logical commands

```text
status        show service/component state
healthcheck   run health verification
logs          return bounded diagnostic logs without secrets
test          run functional tests
deploy        deploy repository-controlled changes
restart       restart an explicitly selected service
```

## Design rules

- No passwords, tokens or private keys are embedded in scripts.
- Authentication belongs to the authorized execution environment.
- Service targets use names from `inventory/services.yaml`.
- Read-only operations should be safe to repeat.
- State-changing operations must be followed by verification.
- Scripts must not echo secret environment variables.
