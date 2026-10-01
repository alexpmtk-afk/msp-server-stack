# Scripts

Planned groups:

- `bootstrap/` — prepare a clean server
- `deploy/` — deploy services
- `update/` — controlled updates
- `backup/` — create protected backups
- `recovery/` — restore the stack
- `healthcheck/` — validate service health

Scripts must be safe to rerun where practical and must never print secrets to logs.
