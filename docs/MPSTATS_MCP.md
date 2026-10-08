# MPSTATS MCP integration

## Purpose

Connect the official MPSTATS remote MCP service to the MSP REMOTE agent stack and then describe its real tools in the shared semantic layer.

The work is intentionally split into two stages:

1. technical connection and acceptance;
2. inventory and semantic description of the tools and data actually exposed by MPSTATS.

Do not design the final semantic model before live tool discovery.

## Official remote MCP endpoint

MPSTATS documents the remote MCP endpoint in this form:

```text
https://mcp.mpstats.io/mcp?token=<MPSTATS_API_TOKEN>
```

The real token is a production secret and must never be committed to GitHub or printed in diagnostics.

## Verified REMOTE configuration — 2026-10-06

A read-only audit through the private `msp-server-bridge` confirmed:

- Codex CLI: `0.159.3`;
- the Hermes gateway runs as user `hermes`;
- gateway Codex configuration: `/home/hermes/.codex/config.toml`;
- dashboard Codex configuration: `/home/hermes/.codex-dashboard/config.toml`;
- both config files are mode `0600`;
- both currently contain one MCP server, `hermes-tools`;
- `codex mcp add` supports streamable HTTP servers through `--url`;
- `codex mcp add` also supports bearer-token environment variables, but MPSTATS currently documents MCP authentication through the URL query parameter;
- `/opt/mcp/secrets` is owned by the `hermes` service user, mode `0700`, and is readable/writable by that user;
- individual existing secret files are mode `0600`;
- non-interactive sudo is not available to the bridge runner.

The first MPSTATS integration therefore does not require sudo: protected secret storage and both active Codex configs are writable by the `hermes` user.

A state-changing but credential-safe bridge operation then created `/opt/mcp/secrets/mpstats.env` with mode `0600`, owner `hermes:hermes`, and an empty `MPSTATS_API_TOKEN=` placeholder. No credential value has been supplied yet.

## Secret handling

Canonical protected location on REMOTE:

```text
/opt/mcp/secrets/mpstats.env
```

Variable name:

```text
MPSTATS_API_TOKEN=<real value only on REMOTE>
```

Required permissions:

```text
directory: /opt/mcp/secrets 0700
file:      /opt/mcp/secrets/mpstats.env 0600
owner:     hermes
```

Repository content contains only the variable name, placeholder examples and deployment logic.

### Runtime copy in Codex config

MPSTATS currently documents MCP authentication by embedding the token in the remote MCP URL. Codex does not document environment-variable expansion inside the `url` field itself.

For that reason, the current deployment procedure reads the token from the protected secret file and writes the authenticated URL into the two private Codex runtime configs. Those files remain mode `0600` and are not stored in GitHub.

Diagnostics must never print the expanded MPSTATS URL. The reproducible installer accepts no token CLI argument, preventing accidental exposure in command history or process arguments.

If MPSTATS later documents a supported header-based MCP authentication mechanism, prefer `env_http_headers` or another environment-backed credential method and remove the duplicated runtime secret from Codex config.

## Active Codex targets

MPSTATS is installed into both:

```text
/home/hermes/.codex/config.toml
/home/hermes/.codex-dashboard/config.toml
```

The first target is used by the Hermes gateway/current default Codex runtime. The second is used by the Hermes dashboard through its separate `CODEX_HOME`.

## Reproducible installer

Tracked installer:

```text
scripts/remote/install_mpstats_mcp.py
```

It:

1. reads the token only from `/opt/mcp/secrets/mpstats.env`;
2. refuses an empty token or secret-file permissions broader than `0600`;
3. backs up both current Codex config files locally;
4. adds/replaces only the `[mcp_servers.mpstats]` table;
5. keeps both active config files at mode `0600`;
6. verifies only the non-secret URL shape and never prints the token.

## Installation sequence

1. Capture a read-only pre-change REMOTE snapshot — **PASS**.
2. Audit actual Codex/Hermes MCP configuration and permissions — **PASS**.
3. Create protected empty MPSTATS secret file — **PASS** (2026-10-06; mode `0600`, owner `hermes:hermes`, value empty).
4. Populate the token directly on REMOTE — **PASS** (performed locally on REMOTE; value never entered into chat or GitHub).
5. Run the tracked installer — **PASS** on 2026-10-07. Backups created for both Codex configs.
6. Verify `codex mcp list` with sanitization — **PASS**. `mpstats` is enabled as `streamable_http` in both Codex configs; endpoint verified as `https://mcp.mpstats.io/mcp` with query redacted.
7. Perform a real MCP `initialize` + `tools/list` call without exposing the token — **PASS**. Protocol `2025-06-18`, server `mpstats-mcp` `3.3.1`, 108 tools discovered.
8. Record the post-change state and configuration delta — **PASS**.
9. Choose one harmless read-only MPSTATS tool from the discovered schema and run it — **PASS** using `account_limits` (`HTTP 200`, `is_error=false`).
10. Build the semantic catalog — **PASS (v1, 2026-10-08)**. All 108 tools have machine-readable family/routing/access policies; response-field semantics remain the next refinement.

## Post-install verification — 2026-10-07

A read-only bridge audit after installation confirmed:

- `/home/hermes/.codex/config.toml`: 2 MCP servers (`hermes-tools`, `mpstats`), mode `0600`;
- `/home/hermes/.codex-dashboard/config.toml`: 2 MCP servers (`hermes-tools`, `mpstats`), mode `0600`;
- `mpstats.enabled = true`;
- transport: `streamable_http`;
- safe endpoint: `https://mcp.mpstats.io/mcp` (query/token redacted in audit output);
- `/opt/mcp/secrets/mpstats.env`: mode `0600`, owner `hermes:hermes`;
- `hermes-gateway.service`: active/running after the configuration change;
- `hermes-dashboard.service`: active/running after the configuration change.

The installer created local pre-change backups:

- `/home/hermes/.codex/config.toml.pre-mpstats.20261007T134519Z.bak`;
- `/home/hermes/.codex-dashboard/config.toml.pre-mpstats.20261007T134519Z.bak`.

This post-install checkpoint proved configuration registration and service health. Subsequent live acceptance also proved credential acceptance, MCP initialization, `tools/list` (108 tools), and a harmless read-only tool call.

## Restart policy

Do not restart Hermes merely to edit Codex MCP configuration.

Existing Codex sessions may keep their already-loaded tool catalog. New Codex sessions should be used for acceptance after the configuration change. Restart the gateway only if a later live test demonstrates that the gateway cannot pick up the MCP configuration in a new session.

## Acceptance criteria

Technical connection is now **PASS**. Acceptance evidence:

- MPSTATS appears in both target Codex MCP configurations;
- no token appears in GitHub, issue output or chat;
- MCP initialization succeeded with protocol `2025-06-18`;
- `tools/list` succeeded and returned 108 tools;
- harmless read-only `account_limits` call succeeded (`HTTP 200`, `is_error=false`);
- Hermes Gateway and Dashboard remained active after installation;
- the change is reproducible from this repository plus protected secrets.

Live tool inventory: [MPSTATS_TOOLS_2026-10-07.md](MPSTATS_TOOLS_2026-10-07.md).

## Semantic layer — v1

Machine-readable semantics are now stored under `config/mpstats/semantics/` and documented in [MPSTATS_SEMANTIC_LAYER.md](MPSTATS_SEMANTIC_LAYER.md).

Version 1 records for every exposed capability:

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

The semantic layer describes meaning and source-selection rules, not merely MCP tool names. Current coverage includes all 108 tools. The next refinement is representative live-response shape/field semantics and freshness validation without storing private account values.


## Agent semantic exposure — 2026-10-08

The MPSTATS semantic layer is now installed as a Hermes custom skill:

```text
/home/hermes/.hermes/skills/productivity/mpstats/
```

Deployment from canonical `msp-server-stack` commit `64e0d20c4e48c269a5545acb4956e3106dab5714` passed semantic validation and installed-file contract checks. Gateway and Dashboard remained active; no restart was required.

The skill instructs the agent to apply internal source precedence, identifier rules, freshness caveats and side-effect policies before using the 108 MPSTATS tools. The next acceptance level is behavioral: observe a real new agent task and verify that it applies these rules correctly.


## Behavioral acceptance — 2026-10-08

Hermes skill discovery reports the local `mpstats` skill as enabled. A fixed one-shot acceptance with `--skills mpstats` then passed all four core semantic checks: internal self-purchase routing, internal price-history routing, MPSTATS external-WB analytics routing, and confirmation requirement for the stateful `wb_shelves_project` tool.

The MPSTATS foundation can therefore be treated as **installed + live-accepted + semantically deployed + behaviorally accepted**. Further work is enrichment of response/metric semantics, not basic connectivity or agent awareness.


## Metric layer deployed — 2026-10-08

Live MPSTATS skill was safely updated from the previously accepted commit to `f1a538ded81b840d2df79b9034dd2724965d0ee6` after a fail-closed baseline comparison. Includes `references/metric_semantics.json` and the second privacy-preserving response-shape audit. Both Hermes services remained active. Verified field paths: 19 distinct tools probed, 14 with successful structural response evidence, five with tool-level access/execution errors. Business units/formulas are not yet fully validated.

## Official knowledge and first business read — 2026-10-08

Official provider knowledge is indexed in [MPSTATS_OFFICIAL_KNOWLEDGE.md](MPSTATS_OFFICIAL_KNOWLEDGE.md) and included in the deployed Hermes MPSTATS skill at commit `503262060d7d818a6e2ed6fd5dead5dd41aab157`.

First actual business read: private bridge issue [#150](https://github.com/alexpmtk-afk/msp-server-bridge/issues/150) succeeded with `wb_sku(report=full)` for WB SKU `218395039`. The result verified external product/price/sales/stock fields and exposed potential differences between FBO/FBS and estimated orders vs Insight-style purchase fields. The fact that a SKU can be queried does not mean it belongs to MSP; compare it with the canonical internal catalog before treating it as an own SKU.
