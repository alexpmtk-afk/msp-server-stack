# Server layout

The canonical root for the remote stack is:

```text
/opt/mcp/
├── projects/   checked-out application repositories and source
├── data/       persistent application data
├── secrets/    production credentials; never committed
├── runtime/    sockets, transient state and generated runtime files
├── logs/       service and application logs
├── backups/    protected recovery copies
```

## Rules

- Source and reproducible configuration belong in Git.
- Persistent data does not belong in Git.
- Secrets never belong in Git.
- Generated runtime files do not belong in Git.
- Services should reference secrets by environment variable or protected file path.
- File permissions for `/opt/mcp/secrets` must be restrictive and reviewed during deployment.

Exact public hosts, private endpoints and credentials are intentionally not documented in this repository.
