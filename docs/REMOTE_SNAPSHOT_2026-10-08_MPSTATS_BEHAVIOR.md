# REMOTE MPSTATS behavioral acceptance — 2026-10-08

## Skill discovery

Live Hermes command:

`hermes skills list`

reported the custom skill:

```text
mpstats | productivity | local | local | enabled
```

The installed source remained:

```text
/home/hermes/.hermes/skills/productivity/mpstats/SKILL.md
```

## One-shot semantic acceptance

A fixed private bridge workflow ran a new Hermes one-shot turn with:

- the `mpstats` skill explicitly preloaded;
- no tool/MCP/network/shell use allowed by the prompt;
- one turn maximum;
- only PASS/FAIL evaluation persisted.

Acceptance checks:

```text
self_purchase=PASS
price_history=PASS
external_wb=PASS
wb_shelves_project=PASS
result=PASS
```

## Meaning

The check verifies that a fresh Hermes model turn can apply the core MPSTATS semantic contract:

1. `v_self_purchase` is canonical for company self-purchases;
2. `v_price_history` is canonical for company-recorded price actions/reasons;
3. MPSTATS is the analytical source for external WB niche/competitor research;
4. state-changing `wb_shelves_project` is not automatic and requires confirmation.

No production business values or credentials were persisted by this acceptance.
