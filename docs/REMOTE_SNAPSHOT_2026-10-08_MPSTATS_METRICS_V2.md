# REMOTE MPSTATS metric semantics v2 acceptance — 2026-10-08

## Source and targets

- canonical public repo: `alexpmtk-afk/msp-server-stack`
- deployed commit: `f1a538ded81b840d2df79b9034dd2724965d0ee6`
- private bridge issue: [#148](https://github.com/alexpmtk-afk/msp-server-bridge/issues/148)
- target: `/home/hermes/.hermes/skills/productivity/mpstats/`

## Verified result

```text
runner_user=hermes
canonical_commit=f1a538ded81b840d2df79b9034dd2724965d0ee6
semantic_json=PASS
installed=/home/hermes/.hermes/skills/productivity/mpstats
result=PASS
mpstats_skill_contract=PASS
metric_semantics_installed=yes
gateway_active=active
dashboard_active=active
result=PASS
```

## Safety

Before installation the workflow compared every installed MPSTATS skill/reference file with the previous approved canonical source and checked the prior deployment marker. The workflow would fail without changing the skill if any file had drifted.

This update only replaced the MPSTATS skill tree; no change to DevExec, other Hermes skills, Codex MCP configuration, protected credentials or server services was requested. No service restart was required.

## Data semantics

Source: privacy-preserving response-shape audit [#146](https://github.com/alexpmtk-afk/msp-server-bridge/issues/146).

- 13 batch-2 probes: 10 successful shape captures, three tool errors.
- 19 distinct tools probed across two shape-audit batches: 14 with usable structural evidence, five tool errors.
- Currency, percentage scaling, discount formula, revenue/purchase accounting basis and live-stock freshness remain unverified unless separately documented.
- `MPSTATS.purchase_after_return` is **not** company self-purchase classification.

Next step: provider field definitions and controlled unit validation; never infer undocumented formulas solely from path names.
