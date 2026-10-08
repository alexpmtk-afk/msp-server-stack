# Official MPSTATS knowledge sources for MCP analytics — 2026-10-08

## Source ranking

1. The **live, authenticated MPSTATS MCP `tools/list` schema and `tools/call` output** is authoritative for which MCP tools exist, their current input contract, returned field paths and account-specific errors.
2. The **official MPSTATS REST API documentation and official `mpstats-io/claude-code-skills`** are authoritative reference material for documented REST fields/units and API request contracts. This is a separate **API skill, not another MCP server**. Reconcile endpoint/version/field against the live MCP tool before transferring a REST definition.
3. The **official MPSTATS knowledge base** is authoritative for provider-described user-facing metrics, collection methods, formulas, calculation scope and freshness. UI report semantics may differ from specific raw REST/MCP fields.
4. The internal MSP semantic dictionaries are authoritative for **company-specific identity**, self-purchase classifications, company price-change reasons and source-routing precedence. They do not override MPSTATS on MPSTATS's own definitions.

## Official MCP and API sources

- Official MCP connector and capability page: https://mpstats.io/instruments/ai/mcp
  - remote Streamable HTTP endpoint: `https://mcp.mpstats.io/mcp` (a personal token is appended only in protected runtime settings);
  - the official page advertises read-only access to reports and specifies that access is scoped to the holder's MPSTATS account;
  - do not infer all 108 tool contracts from marketing copy; use authenticated `tools/list`.
- REST API developer documentation: https://mpstats.io/integrations/docs/description/
  - token normally passed as `X-Mpstats-TOKEN` HTTP header;
  - optional REST query `auth-token` is **not** the same as the official remote MCP `?token=` convention;
  - HTTP 401 = auth error, 429 = rate limit, `Retry-After` indicates when to retry.
- Official maintainer repository: https://github.com/mpstats-io/claude-code-skills
  - skill source: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/SKILL.md
  - API authentication: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/auth.md
  - pagination/filter/sort: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/pagination-filter-sort.md
  - Wildberries categories/fields: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/wb-categories.md
  - Wildberries SKU: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/wb-similar-sku.md
  - Ozon categories/fields: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/ozon-categories.md
  - Ozon SKU: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/ozon-brands-sellers-sku.md
  - API quota: https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/account.md

### REST-specific facts

- REST product list POST contracts use `startRow`, `endRow`, `filterModel`, `sortModel`. Max 5000 rows per REST request according to the official skill.
- The official REST `category/items` references explicitly describe `revenue` as RUB and `final_price` as RUB for WB. Ozon category revenue is also described in RUB in its subcategory documentation.
- A field definition in the REST skill is evidence for *that REST endpoint*; it should not be silently assigned to all analogous `lk_*`, `wbbidder_*` or other MCP outputs.
- No second REST API skill or competing MCP server is installed. Only documentation is incorporated; current REMOTE `mpstats` MCP and its protected token remain unchanged.
- The official upstream skill includes an option to send a token in chat; **do not use that option**. MSP never asks for tokens in chat or puts them in public repositories; our existing protected REMOTE config remains the credential source.

## Official metric knowledge base

- Collection methods and source differences:
  https://wiki.mpstats.io/FAQ/Аналитика_данных/Как_MPSTATS_собирает_данные
- WB SKU report and the distinction between externally estimated orders and Insight buyouts:
  https://wiki.mpstats.io/Wildberries/Поиск_по_SKU
- WB report: product-level own-cabinet sales, prices, stock and economics:
  https://wiki.mpstats.io/Личный_кабинет/Товары
- WB own-cabinet order/sale/returns:
  https://wiki.mpstats.io/Личный_кабинет/Продажи_и_заказы
- Ozon own-cabinet products:
  https://wiki.mpstats.io/ru/Кабинет_Ozon/Товары
- WB price/SPP explanation:
  https://wiki.mpstats.io/ru/FAQ/Продажи_и_заказы/Почему_цена_СПП_отличается_от_финальной_цены
- WB advertising campaign CTR/DRR:
  https://wiki.mpstats.io/ru/Продвижение/Журнал_продвижения

## Important provider-defined rules

1. **External vs internal:** MPSTATS external market research is based on public page parsing and estimated stock changes. Internal WB/Ozon cabinet reporting uses the seller's marketplace API. These datasets can disagree; do not silently reconcile them.
2. **WB FBO/FBS:** external product/order analysis defaults to FBO; opt-in FBS stock/order analysis is less reliable because seller-managed stock changes for reasons besides customer orders. Insight buyouts may cover both FBO and FBS regardless of FBS switch.
3. **Freshness:** the knowledge base says parsing cadence depends on product activity; internal seller cabinet order/sale/stock data is normally fetched on a multi-hour cadence and WB weekly reports may retrospectively adjust business data. Check exact timestamps, report periods and current documentation before claiming live operational accuracy.
4. **Prices:** base price, seller-discounted price, price after SPP and WB Wallet price are different. A Moscow card price and an individual buyer's actual paid amount can differ because SPP and regional/personal conditions vary.
5. **Orders vs buyouts vs sales:** the external SKU page presents estimated orders and Insight actual buyouts as different measures; a raw field called `sales` or `purchase` must be matched to its specific endpoint/report version before interpretation.
6. **Dollars/currency:** the official *specific* WB external category product REST contract identifies certain prices/revenue in RUB. Do not generalize unknown currency/scale/tax basis for other MCP families.
7. **Ads:** CTR means clicks/impressions; DRR means advertising spend relative to a specifically defined sales/orders denominator. WB report variants use different denominators. Document denominator and scale before comparing ratios.

## Conflict or ambiguity requiring validation

The official `wb-categories.md` API reference labels `purchase` as **"Add-to-cart count"**, while the user-facing WB SKU knowledge article describes **buyouts** separately and raw MCP `period_stats.purchase` has no fully confirmed one-to-one field mapping in these references. Do not label `purchase` or `purchase_after_return` as company self-purchases, and do not treat them as automatically comparable to externally estimated `sales`. This discrepancy requires tool-version-specific confirmation.

## First read-only business acceptance

Private bridge issue https://github.com/alexpmtk-afk/msp-server-bridge/issues/150

- Tool: `wb_sku`, report `full`, public marketplace SKU `218395039`.
- Period requested: 2026-09-08 through 2026-10-07.
- Result PASS, HTTP 200, user-visible short diagnostic available in issue #150.
- The result includes distinct `sales`, `revenue`, `purchase`, `purchase_after_return`, `price`, `final_price`, `wallet_price`, `stock.fbo` and `stock.fbs` fields.
- These values must not be aggregated into an own-cabinet financial report or read as confirmed live company stock.
- This example does **not** establish that the SKU belongs to the MSP company; ownership must be checked against the internal product catalog.

## Maintenance

Before applying new provider metric definitions:
- find an official cited source describing the exact metric/scope;
- reconcile the source's API and report version with live MCP schema and response;
- store source URL, evidence scope and unresolved assumptions;
- run semantic CI and secret scanning;
- deploy to only the MPSTATS Hermes skill after checking the existing files for drift. Do not touch any other skill, DevExec workspace, Codex MCP config or service.
