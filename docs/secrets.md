# Secret handling

## Principle

The public repository contains the **shape** of configuration, never production values.

| Information | GitHub | Protected server / backup |
|---|---|---|
| environment variable names | yes | yes |
| example values that are non-sensitive | yes | optional |
| API tokens | no | yes |
| passwords | no | yes |
| SSH private keys | no | yes |
| Telegram sessions | no | yes |
| tunnel / proxy credentials | no | yes |
| database files and dumps | no | yes |
| public application code | yes | deployed copy |

## Server-side storage

Production secrets should be stored under a protected location such as `/opt/mcp/secrets/` or supplied by an approved secret manager.

Tracked configuration should point to secret names or paths, not embed values.

## Recovery

A server cannot be fully restored from this public repository alone. Recovery also requires the separate protected secret backup and any persistent data that cannot be reconstructed.
