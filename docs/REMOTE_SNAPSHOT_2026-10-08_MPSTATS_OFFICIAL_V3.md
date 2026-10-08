# REMOTE MPSTATS official knowledge and business read — 2026-10-08

## Official source adoption

- official MCP documentation: https://mpstats.io/instruments/ai/mcp
- official API documentation: https://mpstats.io/integrations/docs/description/
- official MPSTATS maintainer API skill reference: https://github.com/mpstats-io/claude-code-skills
- official knowledge base: https://wiki.mpstats.io/
- internal consolidated index: `docs/MPSTATS_OFFICIAL_KNOWLEDGE.md`

These sources are complementary. The API skill is not a second MCP and was not installed. Existing MPSTATS remote MCP remains the only configured server.

## Safe v3 deployment

- source commit: `503262060d7d818a6e2ed6fd5dead5dd41aab157`
- deployment: https://github.com/alexpmtk-afk/msp-server-bridge/issues/152
- `semantic_json=PASS`, `mpstats_skill_contract=PASS`, `metric_semantics_installed=yes`, final `result=PASS`.
- Gateway and Dashboard both active.
- MPSTATS skill only; no DevExec, other skills, protected auth or MCP config modifications.

## First actual business data

- private evidence: https://github.com/alexpmtk-afk/msp-server-bridge/issues/150
- tool: `wb_sku`, report `full`, SKU `218395039`;
- query date window: `2026-09-08` through `2026-10-07`;
- HTTP 200 and `result=PASS`;
- returned price variants, two warehouse modes, period sales/revenue and distinct purchase fields;
- official MPSTATS source rules require caution about product ownership, FBO/FBS methodology and stock-change order estimates versus buyouts.

Private product/account values are not duplicated into this public source repository.

## Next

Actual marketplace analysis via the installed MCP, scoped by product/category/period and using only verified source semantics. Validate unfamiliar provider fields against the official references before presenting derived business conclusions.
