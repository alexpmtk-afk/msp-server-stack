# Andrey / QRsite integration

## Purpose

Read-only integration from the MSP REMOTE server to Andrey's QRsite API and MCP.

Public documentation sources:

- API docs: `https://qrbott.ru/api/v1/docs/`
- MCP docs: `https://qrbott.ru/api/v1/mcp/docs/`

No live token values belong in this repository.

## Authentication

Two independent tokens are used.

### REST API

- token prefix: `qra_`
- header: `Authorization: Token qra_...`
- protected variable name: `ANDREY_API_TOKEN`

### MCP

- token prefix: `qr_`
- server: `https://qrbott.ru/mcp`
- transport: Streamable HTTP
- header: `Authorization: Bearer qr_...`
- protocol verified: `2025-06-18`
- protected variable name: `ANDREY_MCP_TOKEN`

The real values are stored as protected GitHub Actions Repository Secrets in the private repository `msp-server-bridge`. They must never be committed to the public stack.

## Verified REST API methods

Marketplace group `marketplaces`:

- `GET /api/v1/stocks/1c/` — current or dated 1C stock.
- `GET /api/v1/marketplaces/blocks/` — company/block lookup.
- `GET /api/v1/wb/orders/` — saved WB order feed.

Plansite group `plansite`:

- `GET /api/v1/plansite/orders/` — active production orders.
- `POST /api/v1/plansite/estimate/` — non-persistent estimate for a new batch. This is documented by QRsite as a virtual calculation; the default MSP bridge client does not expose it in the read-only allowlist.

Important stock block IDs:

- `13` — novok + ultra.
- `2` — lm.

## Verified MCP connection

On 2026-10-04 the REMOTE runner successfully initialized:

- server: `QRsite`
- version: `2.0`
- protocol: `2025-06-18`
- tools capability: enabled

The current MCP token exposes four marketplace tools:

1. `marketplaces_blocks`
2. `stock_1c_history`
3. `stocks_1c`
4. `wb_orders`

The QRsite documentation also describes groups for ГЗП лазер, YouGile and 24LMS, but those tools are not currently exposed by this token. Token groups determine the visible tool set.

## Current live verification

Verified from the self-hosted runner `msp-remote-01` on 2026-10-04:

- REST stock request returned HTTP 200.
- latest stock date was `2026-10-04`.
- stock result count was `816`.
- MCP initialize returned HTTP 200.
- MCP `tools/list` returned HTTP 200.
- MCP `stocks_1c` returned HTTP 200 and the same stock dataset as REST.

This proves both access paths are operational from REMOTE.

## Persistent private execution path

Private repository: `alexpmtk-afk/msp-server-bridge`.

Files:

- `.github/workflows/andrey-qrsite-request.yml`
- `scripts/andrey_qrsite_readonly.py`
- `requests/andrey-readonly.json`

The request file contains only a non-secret operation and parameters. A push that changes the request file automatically runs the read-only workflow on `msp-remote-01`. This lets an authorized chat/agent change the request in GitHub, wait for the workflow, and read the result without asking the user to handle tokens again.

Supported request operations:

- `api_stocks_1c`
- `api_marketplaces_blocks`
- `api_wb_orders`
- `api_plansite_orders`
- `mcp_tools_list`
- `mcp_tool_call`

MCP calls are allowlisted to the four currently verified read-only tools. Page size is capped at 50 by the bridge client.

Example request:

```json
{
  "operation": "api_stocks_1c",
  "params": {
    "page_size": 5
  }
}
```

## Rate limits

Observed from QRsite documentation:

- stocks / stock history: up to 5 requests per second and 30 per 60 seconds per API token.
- WB orders: up to 5 requests per second and 30 per 60 seconds.
- company search: up to 5 requests per second and 60 per 60 seconds.
- ГЗП: up to 2 requests per second and 10 per 60 seconds.

On HTTP 429, honor `retry_after` or the `Retry-After` header.

## Data semantics

- `quantity: 0` is a recorded zero stock.
- `quantity: null` means quantity is unknown.
- absence of a row does not mean zero.
- WB `count` is the number of matching saved order records, not the number of bought items.
- WB `orderStatus` is the current status, not status history.
- WB `vendorCode` and `title` come from the current WB card, not a historical snapshot.

## Security rule

Never copy real `qra_` or `qr_` values into Git, issue bodies, logs, documentation, chat messages, or public configuration. Only protected secret stores may contain live values.
