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

### Deployment acceptance — 2026-10-08

Deployment to REMOTE completed with `PASS`.

- target: `/home/hermes/.hermes/skills/productivity/mpstats/`;
- owner: `hermes:hermes`;
- `SKILL.md`: mode `0644`;
- all semantic references installed with mode `0644`;
- deployed canonical commit: `64e0d20c4e48c269a5545acb4956e3106dab5714`;
- semantic JSON validation: `PASS`;
- installed skill contract validation: `PASS`;
- Hermes Gateway remained `active`;
- Hermes Dashboard remained `active`.

The location and structure match the already working custom QRsite skill convention: `/home/hermes/.hermes/skills/productivity/<skill>/SKILL.md`.

This proves that the semantic contract is physically installed in the standard Hermes skill tree. A future live agent task should still be used as behavioral acceptance: verify that the agent actually chooses MPSTATS and source precedence correctly in a real query, not merely that the files exist.


## Behavioral acceptance — 2026-10-08

The deployed skill was verified in the live Hermes skill registry:

- `hermes skills list` reports `mpstats` as a local enabled productivity skill;
- the skill remains at `/home/hermes/.hermes/skills/productivity/mpstats/SKILL.md`;
- no gateway restart was needed.

A controlled one-shot Hermes model turn then preloaded `--skills mpstats`, explicitly prohibited all tool/MCP/network/shell calls, and tested four routing/safety decisions. The workflow returned only boolean acceptance checks; the model response itself was not persisted.

Results:

- company self-purchase canonical source → `v_self_purchase`: **PASS**;
- company price-action history canonical source → `v_price_history`: **PASS**;
- external Wildberries niche/competitor analytics → MPSTATS: **PASS**;
- `wb_shelves_project` must require confirmation, not automatic execution: **PASS**.

Overall behavioral acceptance: **PASS**.

This closes the core semantic-foundation loop: the MPSTATS MCP is installed, its tools are inventoried, semantic routing/safety rules exist, those rules are deployed as a Hermes skill, Hermes recognizes the skill, and a fresh model turn applies the key rules correctly without external tool use.

## Live business-field audit, batch 2 — 2026-10-08

The first attempt (bridge issue #144) did not run because of escaped GitHub Actions expressions. The workflow was corrected in PR #145. The replacement read-only run, issue #146, completed.

- 13 tool/variant probes; 10 returned usable structural responses; 3 returned tool-level errors;
- successful product/detail responses: `wb_subjects_list`, `wb_category`, `wb_sku(report=full)`, `ozon_category(report=products)`, `ozon_sku(report=full)`, category searches, `repricer_tokens`, `lk_ozon_fields`, and the `wbbidder_products` envelope;
- errors: `mine_products_list`, `lk_wb_products_stocks`, `lk_wb_dashboard_business_economics`. Do not treat these as proven data sources until access/scope is diagnosed;
- `wbbidder_products` returned an envelope but **no product row**, so per-product advertising columns remain unverified;
- all actual token IDs, SKUs, cabinet identifiers, business values and authenticated URLs were excluded from the recorded audit.

Combined with the first audit, 19 distinct tool names have been probed, 14 with successful response-shape evidence and five with tool-level errors; all 108 remain covered by tool-routing/access policy, but this is **not** 108/108 verified response fields.

Key fields observed:

- WB subject: `revenue`, `sales`, `purchase`, `purchase_after_return`, `revenue_estimated`, `lost_profit`, `avg_price_final`, `median_price_final`, `turnover_in_days`;
- WB SKU full: `period_stats.revenue`, `period_stats.sales`, `price.price`, `price.final_price`, `price.wallet_price`, `stock.fbo`, `stock.fbs`;
- Ozon SKU full: `period_stats.revenue`, `period_stats.sales`, `price.price`, `price.final_price`, `price.ozon_card_price`;
- `lk_ozon_fields`: a schema catalog with field names, descriptions, groups, declared types, filtering and sorting capabilities; its actual business values were not retrieved.

These observations verify **field paths and JSON types only**, not formula, currency, tax basis, price applicability, metric scale or snapshot freshness. The catalog in `config/mpstats/semantics/metric_semantics.json` explicitly records these unknowns.

In particular, MPSTATS `purchase` / `purchase_after_return` **must not be interpreted as our internal self-purchase records**. Internal self-purchases remain defined by `msp_data.v_self_purchase`.

For current stock and execution, prefer the verified direct marketplace source. Price fields such as WB `wallet_price` and Ozon `ozon_card_price` are not interchangeable without validation.

## Metric semantics skill deployment v2 — 2026-10-08

The updated metric semantics from batch 2 have been installed into the live REMOTE Hermes `mpstats` skill, without restarting services.

Acceptance by guarded private-bridge workflow (issue #148):

- previous deployed skill compared byte-for-byte with the previously approved canonical commit before any write; unexpected external changes would have stopped deployment;
- new source commit: `f1a538ded81b840d2df79b9034dd2724965d0ee6`;
- target: `/home/hermes/.hermes/skills/productivity/mpstats/` (no other skill targets);
- `semantic_json=PASS`, `mpstats_skill_contract=PASS`, `metric_semantics_installed=yes`;
- `hermes-gateway.service` and `hermes-dashboard.service`: active;
- no Codex MCP configuration, DevExec service or account tokens were changed.

The new skill now includes `references/metric_semantics.json`. This adds explicit evidence/uncertainty rules for monetary, conversion, pricing, stock, purchase and estimated metrics. **It does not magically validate the monetary units, formulas or freshness**; those remain open until separately verified.
