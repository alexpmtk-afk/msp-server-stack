# Remote operations

This directory is the canonical place for safe, reusable REMOTE-operation helpers.

The user-facing and agent-facing contract is described in [../../docs/REMOTE_INTERACTION.md](../../docs/REMOTE_INTERACTION.md).

## Planned logical commands

```text
status        show service/component state
healthcheck   run health verification
logs          return bounded diagnostic logs without secrets
test          run functional tests
deploy        deploy repository-controlled changes
restart       restart an explicitly selected service
```

## Design rules

- No IP addresses, passwords, tokens or private keys are embedded in scripts.
- Authentication is supplied by the authorized execution environment.
- Service targets use names from `inventory/services.yaml`.
- Read-only operations should be safe to repeat.
- State-changing operations should fail clearly and be followed by verification.
- Scripts must not echo secret environment variables.

Executable implementations will be added once the actual REMOTE execution transport is finalized.
