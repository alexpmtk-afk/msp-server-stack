# MPSTATS MCP — SKU reviews, star-only ratings and text evidence (13 November 2026)

## Conclusion

**Verified on live REMOTE official MPSTATS MCP:** both `wb_sku(report="comments")` and `ozon_sku(report="comments")` return individual dated entries, numeric 1–5 star valuations, and either nonempty or empty text. `report="full"` separately returns a rating and review counter. The two counts **must not** be assumed identical or exhaustive.

Evidence is in private bridge issues:
- [#963 — actual read-only API probe](https://github.com/alexpmtk-afk/msp-server-bridge/issues/963)
- [#965 — live tool catalog audit](https://github.com/alexpmtk-afk/msp-server-bridge/issues/965)

All calls used the existing protected MCP URL only in REMOTE memory. No token, authenticated URL, or raw customer-review text was exported/stored in GitHub. No WB/Ozon cabinet changes or local service restarts.

## Official MPSTATS documentation

- [MPSTATS official MCP product](https://mpstats.io/instruments/ai/mcp)
- [Official WB SKU reviews API reference](https://github.com/mpstats-io/claude-code-skills/blob/main/mpstats/references/wb-similar-sku.md): `GET items/{id}/comments`, declared `date`, `text`, `rating`, `valuation`. On the actual live sample, the fields returned were `date`, `text`, `valuation`; no `rating` key was observed in those rows.
- [Official Ozon REST API](https://mpstats.io/integrations/analytics-oz/): `GET analytics/v1/oz/items/{id}/comments`, including examples with `date`, `valuation`, `likes`, and `text`, including empty-text valuations.
- [Official WB Search-by-SKU guide](https://wiki.mpstats.io/Wildberries/Поиск_по_SKU): review-text history and daily graph of total ratings, negative ratings, ratings with text; negative ratings defined as 1–3 stars.
- [Official WB AI review-analysis module](https://wiki.mpstats.io/Wildberries/Анализ_отзывов): separate provider UI operation, not proved as a distinct tool on the present MCP.
- [Official seller-WB review management module](https://wiki.mpstats.io/ru/Студия/Автоответы/Новые_отзывы): separate UI use case, **not** proof its moderation or all-account review methods are exposed through MCP.

Keep the installed MCP, official REST API, and web-interface capabilities distinct.

## Live samples

Two previously examined public marketplace SKU IDs were deliberately fixed for a bounded test. **Neither SKU was revalidated as owned by the MSP company**; the demonstrated feature is SKU-scoped retrieval, not company-ownership linkage.

| Field | WB SKU `218395039` | Ozon SKU `5287344329` |
| --- | ---: | ---: |
| MCP `comments` call | HTTP 200; JSON parse OK | HTTP 200; JSON parse OK |
| Individual entries returned | 95 | 363 |
| Rows with nonempty `text` | 51 | 133 |
| Rows without text | 44 | 230 |
| `valuation=1` | 5 | 2 |
| `valuation=2` | 0 | 0 |
| `valuation=3` | 6 | 3 |
| `valuation=4` | 12 | 16 |
| `valuation=5` | 72 | 342 |
| Rows with valid 1–5 valuation | 95 | 363 |
| Rows with date | 95 | 363 |
| Earliest returned date | 2024-03-29 | 2026-08-14 |
| Latest returned date | 2026-10-15 | 2026-11-12 |
| Current `full.rating` | 5 | 4.9 |
| Current `full.comments` | 254 | 362 |
| `full.updated` date | 2026-11-13 | 2026-11-13 |

Actual individual row key sets:
- WB: `date`, `text`, `valuation`.
- Ozon: `date`, `likes`, `text`, `valuation`.

The test analyzed star distributions in memory and retained only aggregate counts, field names, dates and the two public SKU IDs in its private GitHub issue.

## Critical validity findings

1. **List completeness cannot be assumed.** WB has 95 returned entries but `full.comments=254`. Ozon has 363 entries but `full.comments=362`. This may reflect differences in coverage, definitions, or non-public/unfiltered rows; the test did not resolve the reason.
2. **Separate two concepts:** a 1–5 `valuation` with empty `text` is not a textual review. A row with `text` is not necessarily proven to belong to an exact Ozon variant or be a currently published product review.
3. No publication/status or unique review identifier was observed in the **returned live key sets**, so we have no verified way with these two reports alone to exclude delivery-only feedback, deduplicate reliably across sources, or prove published-only coverage.
4. The `comments` report has `sku` and a `report` option; in the known MCP descriptions `d1/d2` are not applied to `comments` (WB and Ozon). Historical windows of individual review records must be filtered *after retrieving* with awareness of partial coverage, or validated against a different provider report.
5. Do not recompute the platform's aggregate card rating from the returned review subset and label it authoritative.
6. WB's most recent returned review is almost a month before the audit, despite the `full` card update on 13 Nov. Do not confuse up-to-date card snapshots with up-to-date comments.
7. An Ozon discrepancy of 1 row is not proof of a particular cause. Delivery-review contamination or other statuses need *independent* verification in the relevant official source before interpreting that difference.
8. A count of positive rows in the available `comments` response is **not** a validated count of all new positive ratings on the platform.

## Current live MCP catalog differs from archived October catalog

On 13 Nov 2026, official authenticated `tools/list` returned **115** tools (HTTP 200). The archived 7 Oct 2026 inventory has 108. This is not simply 7 additions: **12 WB bidder tools were added and five `ym_*` tools were absent**.

Added tools:
`wbbidder_cabinet_details`, `wbbidder_campaign_capabilities`, `wbbidder_campaign_history`,
`wbbidder_campaign_sku_config`, `wbbidder_cluster_lookup`, `wbbidder_journal_metrics`,
`wbbidder_journal_tables`, `wbbidder_last_bid`, `wbbidder_nms_distribution`,
`wbbidder_phrase_reports`, `wbbidder_recommended_bid`, `wbbidder_regions`.

No longer advertised on this token/date:
`ym_brand`, `ym_category`, `ym_compare`, `ym_seller`, `ym_sku`.

The two original `wb_sku` and `ozon_sku` tools are present. Their live `report` enums include `comments`. No additional specialist review-text tool was discovered. Some other tool descriptions mention ratings/reviews (for example `lk_ozon_product_daily` and `lk_wb_pulse_products`), but this does not establish they return individual textual reviews.

**Do not silently overwrite the old 108-tool semantic coverage marker with 115/115.** The 12 new tools require semantic policy review, and the missing 5 tools require explicit status handling. The old inventory is historical evidence, not a live list.

## Recommendation for own-product monitoring

- Resolve ownership from the canonical internal product/listing catalog: marketplace, store/account, marketplace-specific SKU and exact product variant. A public SKU value alone is insufficient.
- Obtain per-item public `full.rating` and `full.comments` as provider aggregate measurements, with `source`, `retrieved_at`, `report`, and the provider's `updated` timestamp.
- Obtain `comments` for dated `valuation` and text analysis; separately count text-bearing rows vs star-only rows. Record response-row count, coverage dates and incomplete/unverified coverage.
- When a task requires *all* new positive ratings or the exact rating for an Ozon variant, **do not use the filtered comment subset as proof**. Cross-check a validated official marketplace per-variant rating source and published-status semantics.
- Avoid transferring raw review texts to public GitHub. Use a controlled private data store only if the user explicitly needs ongoing full-text analysis. Do not quote users' full reviews unnecessarily.
- Keep every read-only review probe bounded by account permissions and limits; do not call writing/auto-reply methods without explicit authorization.

**Scope:** verification and documentation only. No ongoing review collector installed, no product list altered, no cabinet actions performed.
