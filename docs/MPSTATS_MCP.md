# MPSTATS MCP integration

## Purpose

Connect the official MPSTATS remote MCP service to the MSP REMOTE agent stack and then describe its real tools in the shared semantic layer.

This integration is intentionally split into two stages:

1. technical connection and acceptance;
2. inventory and semantic description of the tools and data actually exposed by MPSTATS.

Do not design the final semantic model before live tool discovery.

## Official remote MCP endpoint

Use the official MPSTATS remote MCP endpoint pattern:

```text
https://mcp.mpstats.io/mcp?token=<MPSTATS_API_TOKEN>
```

The real token is a production secret and must never be committed.

## Secret handling

Preferred protected location on REMOTE:

```text
/opt/mcp/secrets/mpstats.env
```

Suggested variable name:

```text
MPSTATS_API_TOKEN=<real value only on REMOTE>
```

Repository content may contain only the variable name, placeholder examples and deployment logic.

Because MPSTATS authentication is carried in the remote URL, configuration and diagnostics must be reviewed so that the fully expanded URL is not printed to logs, GitHub Actions output, issue comments or process listings.

## Installation sequence

1. Capture a read-only pre-change REMOTE snapshot.
2. Verify the actual MCP configuration mechanism used by the live Hermes/Codex runtime.
3. Create protected token storage on REMOTE with restrictive permissions.
4. Add the MPSTATS MCP definition using the smallest supported configuration change.
5. Reload/restart only the component that actually requires it.
6. Verify service health.
7. Discover the MPSTATS MCP tool list.
8. Execute one harmless read-only request.
9. Record the post-change state and any configuration delta.
10. Only then build the semantic catalog.

## Acceptance criteria

PASS requires all of the following:

- the MPSTATS MCP server is visible to the target agent/runtime;
- no token is present in GitHub or diagnostic output;
- tool discovery succeeds;
- at least one read-only MPSTATS call succeeds;
- existing services remain healthy;
- the change is reproducible from this repository plus protected secrets.

## Semantic-layer follow-up

After acceptance, record for every exposed capability:

- source: MPSTATS;
- marketplace/domain;
- entity being described;
- business meaning;
- required identifiers;
- available time range and freshness;
- important returned fields and units;
- known limitations;
- when the agent should choose MPSTATS;
- when another internal source has priority;
- relationships to internal product/card identifiers.

The semantic layer must describe meaning and source-selection rules, not merely copy MCP tool names.
