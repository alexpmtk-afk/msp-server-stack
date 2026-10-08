# MPSTATS semantic layer

Load these files together with `docs/MPSTATS_TOOLS_2026-10-07.md`.

- `catalog.json` — what MPSTATS is, family meanings, identifiers, freshness and global guardrails.
- `routing.json` — source-selection and conflict-resolution rules across MPSTATS, internal MSP data and direct marketplace sources.
- `tool_policy.json` — one policy record for every live MPSTATS MCP tool discovered on 2026-10-07.
- `response_shapes.json` — privacy-preserving observed response field paths/types for representative live tools; no values are stored.

The raw MCP schema tells the agent **how to call** a tool. This semantic layer tells it **why/when to call it, what kind of truth it represents and what it must not assume**.

## Hard rules

1. Internal product identity uses `marketplace + store + marketplace_sku`.
2. Internal self-purchase classification comes from `v_self_purchase`.
3. Company-recorded price history comes from `v_price_history`.
4. MPSTATS external analytics is primary for competitor/niche/market research.
5. MPSTATS LK tools are analytical read models for own cabinets, not automatic proof that an operational action completed.
6. Write/stateful tools are never treated like ordinary analytical reads.
7. Photo Editor tools are not data sources and require explicit creative intent.
