# MPSTATS semantic layer — v1.1

## Goal

The live MPSTATS MCP schema tells Codex how to invoke 108 tools. This semantic layer adds the missing business contract: what each family means, which source should win when data overlap, which identifiers are safe to join, what freshness assumptions are allowed, and which tools have side effects.

Machine-readable files:

- `config/mpstats/semantics/catalog.json`
- `config/mpstats/semantics/routing.json`
- `config/mpstats/semantics/tool_policy.json`
- `config/mpstats/semantics/response_shapes.json`

Raw live tool inventory:

- `docs/MPSTATS_TOOLS_2026-10-07.md`

## Source families

The 108 live tools are grouped into ten semantic families:

| Family | Role |
| --- | --- |
| Account | MPSTATS quota/account metadata |
| WB external analytics | competitor, niche, seller, brand, SKU, search and market analytics |
| Ozon external analytics | competitor, category, seller, brand and SKU analytics |
| Yandex Market external analytics | category, brand, seller and item analytics |
| WB cabinet | analytical read model of connected own Wildberries cabinet(s) |
| Ozon cabinet | analytical read model of connected own Ozon cabinet(s) |
| WB advertising | read-only bidder/campaign/ad-performance analysis |
| Repricer | MPSTATS repricer configuration and price history |
| Own products | prices/status/history under connected marketplace tokens |
| Photo Editor | creative compute service; not a business-data source |

## Source precedence

### Internal identity

The canonical identity of a company listing is:

```text
marketplace + store + marketplace_sku
```

Resolve internal article and internal product name through the MSP product catalog. Never derive `internal_article` from an MPSTATS label, seller article, brand text or product title.

For Wildberries, MPSTATS `sku` / `nmid` may be treated as a candidate `marketplace_sku` only with `marketplace=wb` and after resolving the correct store context.

For Ozon, `sku` is marketplace-scoped and must never be treated as an internal article.

### Self-purchases

The internal `v_self_purchase` dataset is canonical for the company's definition of self-purchases. MPSTATS `self_redemption` switches are provider-side analytical filters, not a replacement for the internal registry.

### Price history

For company-recorded price changes and their business reasons, `v_price_history` is canonical. MPSTATS `mine_products_history` and `repricer_history` are useful independent/observed histories and cross-checks.

### Current operational state

For current order, stock, price and execution state, prefer a verified direct marketplace API/MCP when one is available. MPSTATS own-cabinet tools are excellent analytical read models, but their exact cache/freshness semantics have not yet been benchmarked against direct APIs.

### External market analytics

For competitor, category, niche, seller, brand and external-market analysis, MPSTATS external WB/Ozon/Yandex Market tools are the primary analytical source.

Most dated external analytics explicitly state that today's data are not ready and the default end date is yesterday. Do not silently substitute today. `wb_check_rates` is a specific exception: it is a live search-ranking snapshot and contains no history.

## Safety and side effects

Most MPSTATS tools discovered on 2026-10-07 are read-only. The following need special treatment:

- `wb_shelves_project` changes saved MPSTATS tracking projects. It is not allowed in automatic passive analytics and requires explicit user confirmation.
- `lk_wb_cabinets` is mixed: `action=list` is a read; `select/reset` changes the active MPSTATS cabinet scope. A scope change must be intentional and its effect recorded/restored when appropriate.
- Photo Editor generation/edit tools perform external compute and can consume service quota. Use them only for an explicit creative task, never as an automatic analytical step.
- `pe_run` is a raw Photo Editor escape hatch. Prefer typed `pe_*` tools; require explicit confirmation before using it.
- `lk_wb_request` is a universal read-only LK escape hatch. Prefer typed `lk_wb_*` tools and use it only for a known read-only path that is not otherwise covered.
- `account_bonus` is promotional/account metadata, not a business source, and its returned content should not be logged because it may contain personal promo codes.

No currently discovered MPSTATS tool is approved as a marketplace execution tool for price changes, stock zeroing, advertising pause, or similar operational actions.

## Identifier traps

Do not interchange these identifiers:

- company listing key: `marketplace + store + marketplace_sku`;
- MPSTATS `user_token_id`: connected-token id;
- MPSTATS `repricer_id`: repricer id;
- MPSTATS bidder `campaign_id`: internal MPSTATS campaign id, explicitly not the WB `wb_id`;
- MPSTATS Ozon/WB cabinet id/name: connected-cabinet scope;
- category `path`, `subject_id`, seller/supplier ids: provider taxonomy/entity ids.

Resolve identities before combining MPSTATS results with internal MSP datasets.

## Query discipline

Before a broad paginated collection, call `account_limits` and minimize requests.

When two sources disagree:

1. keep the values separate;
2. show the source and date/period;
3. consider freshness/cache differences;
4. use the source-precedence rules above;
5. never silently average or merge conflicting operational values.

For action verification, analytical evidence is not enough. A reply, report, or analytical metric does not prove that a marketplace action completed; use direct post-action evidence.

## Semantic coverage status

Version 1 covers all 108 tools at the level of:

- family;
- business description from the live MCP schema;
- required parameters and accepted input properties;
- source role;
- access/side-effect class;
- automatic-use policy;
- confirmation policy;
- freshness class;
- tool-specific warnings where needed.

Representative response semantics have now started. A privacy-preserving live audit on 2026-10-08 stored only field paths/types for eight representative tools; no values were retained.

Observed successful shapes:

- `account_limits`: quota counters `available/use` plus WB/Ozon external counters;
- `wb_categories_search` and `ozon_categories_search`: rows with `path`, `children`, `revenue`, `sales`;
- `repricer_limits`: repricer product/quota count fields;
- `wbbidder_overview`: period, campaign counts, limits, product summary and current/previous/diff/status metric groups for clicks, CTR, DRR, orders, order sum, spending and views;
- `pe_health`: Photo Editor service-health fields.

Two own-cabinet probes — `lk_wb_dashboard_widget30days` and `lk_ozon_overview` — reached the MCP server but returned `isError=true` in the current environment. This is recorded as **not yet validated**, not as proof that those capabilities are globally unavailable.

Important: observed integer/string types do not establish business units. In particular, currency for category `revenue` and numeric scales/units for bidder CTR/DRR/spending/order sums remain unverified and must not be invented.

Next refinement: expand response-shape/field semantics for the highest-value analytical tools and diagnose the two LK tool errors without exposing private account values.


## Live own-cabinet access diagnostic — 2026-10-08

A privacy-preserving read-only diagnostic was performed after the first response-shape audit.

- Wildberries cabinet listing is reachable with the current MPSTATS token.
- The tested `lk_wb_dashboard_widget30days` call returned a permission-class HTTP 403 tool error in the current environment.
- Ozon cabinet listing did not return a usable cabinet list in the current environment, and `lk_ozon_overview` returned a cabinet-related tool error.
- No cabinet ids, names or business values are stored in this public repository.

These are **runtime access observations**, not permanent tool semantics. The agent must not conclude that all LK functionality is absent, and must not arbitrarily change WB cabinet selection to bypass access errors.

## Agent exposure

Semantic files in GitHub are not sufficient by themselves: the Hermes agent needs an installed skill that tells it to load and apply them.

Canonical skill source:

```text
apps/hermes/mpstats_skill/SKILL.md
```

Canonical deployer:

```text
scripts/deploy/install-mpstats-skill.sh
```

Target on REMOTE:

```text
/home/hermes/.hermes/skills/productivity/mpstats/
```

The deployed skill is self-contained: it receives copies of the semantic JSON files, live tool inventory and this semantic-layer document under its `references/` directory. No secret values are copied into the skill.
