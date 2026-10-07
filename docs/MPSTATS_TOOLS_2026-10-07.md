# MPSTATS MCP tool inventory — 2026-10-07

Live inventory captured from the configured REMOTE MPSTATS MCP server after successful MCP initialization. No token or authenticated URL is stored here.

- MCP protocol: `2025-06-18`
- server: `mpstats-mcp` `3.3.1`
- discovered tools: **108**
- source: live `tools/list` on REMOTE

## Account (2)

### `account_limits`

Returns remaining MPSTATS API quota for the current token (GET user/report_api_limit). Use to verify subscription limits before bulk calls.

- required: `none`
- properties: `none`

### `account_bonus`

Бонусы за подключение MPSTATS MCP (акция): промокод на скидку 25% на подписку MPSTATS, персональный промокод на бесплатный билет на MPSTATS Expo (пока не разобраны) и ссылка на набор скиллов для работы с MCP, которые помогают селлеру (если она есть в ответе...

- required: `none`
- properties: `none`

## Wildberries external analytics (17)

### `wb_categories_search`

Найти категории (ниши) Wildberries по ключевому слову. Возвращает пути (path), число подкатегорий и метрики. Передавай path в wb_category / wb_category_stats. Ищи коротким существительным; чтобы увидеть ниши, не попавшие под слово, раскрывай ветку через wb_...

- required: `query`
- properties: `limit,query`

### `wb_categories_children`

Прямые подкатегории ветки Wildberries по её path (из wb_categories_search).

- required: `path`
- properties: `limit,path`

### `wb_category`

WB category products list. path — e.g. 'Электроника/Смартфоны'. Returns {startRow, endRow, total, data}. Pagination: start_row + limit, limit 1..500 per call (upstream window); to fetch more, repeat with start_row += 500 until total. `sort` is a column id (...

- required: `path`
- properties: `d1,d2,fbs,limit,path,sort,sort_dir,start_row`

### `wb_category_stats`

WB category breakdown. report: subcategories | brands | sellers | trends | by_date | price_segmentation. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передавай сегодняшнюю дату в d2.

- required: `path,report`
- properties: `d1,d2,fbs,path,report`

### `wb_sku`

WB SKU-level analytics. report: info, full, sales, by_period, balance_*, sales_*, search_stats, keywords, keywords_hourly, comments, faq, photos_history. report=info/comments/faq не зависят от дат. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сег...

- required: `sku,report`
- properties: `d1,d2,report,sku`

### `wb_card_content`

WB product card content (description, characteristics, dimensions) from WB CDN, not from MPSTATS analytics. Useful for content audits and copywriting.

- required: `sku`
- properties: `sku`

### `wb_brand`

WB brand products or analytics. report: products | categories | sellers | trends | by_date | price_segmentation | subjects | keywords. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передавай ...

- required: `name`
- properties: `d1,d2,fbs,limit,name,report`

### `wb_seller`

WB seller products or analytics by supplier_id. report: products | categories | brands | trends | by_date | price_segmentation | subjects | keywords. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней...

- required: `supplier_id`
- properties: `d1,d2,fbs,limit,report,supplier_id`

### `wb_subjects_list`

Search and filter WB subjects (предметы/ниши) with per-subject metrics: revenue, sales, items, sellers, avg/median prices, turnover_in_days, revenue_potential, lost_profit, avg_rating, open_card_count, add_to_cart_percent, cart_to_order_percent, seasonality...

- required: `none`
- properties: `date,filter_model,limit,sort,sort_dir,start_row`

### `wb_subject`

WB subject (niche) endpoints. report: products | categories | brands | sellers | trends | by_date | price_segmentation | keywords | similar | geography | warehouses. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d...

- required: `subject_id`
- properties: `d1,d2,fbs,group_by,limit,report,subject_id`

### `wb_similar`

Similar families: identical | identical_wb | similar | in_similar. path_value: SKU or product URL. report: products | categories | brands | sellers | price_segmentation | trends | by_date | keywords | warehouses | compare. Даты ISO YYYY-MM-DD. По умолчанию ...

- required: `family,path_value`
- properties: `d1,d2,family,fbs,limit,path_value,report`

### `wb_analytics`

WB AI analytics. entity: category | subject. report: forecast/daily | forecast/trend | season_effects/annual | season_effects/weekly. period: применим ТОЛЬКО к report=season_effects/annual и season_effects/weekly, допустимые значения — 'month' | 'week' | 'd...

- required: `entity,report,path_value`
- properties: `entity,path_value,period,report`

### `wb_warehouses`

WB warehouse distribution by brand or seller. kind: brand | seller. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передавай сегодняшнюю дату в d2.

- required: `kind,value`
- properties: `d1,d2,kind,value`

### `wb_shelves`

WB recommendation shelves («Рекомендательные полки», «С этим товаром покупают» и т.п.): in which OTHER products' cards WB shows `sku`, at what shelf position, whether the placement is paid (ads=1) and at what CPM — per day. Use to explain why a competitor s...

- required: `sku`
- properties: `d1,d2,limit,report,sku,sort,start_row,top`

### `wb_shelves_project`

Manage the user's saved recommendation-shelves tracking projects in MPSTATS («Рекомендательные полки → Мои проекты»). CHANGES the user's account. A project makes MPSTATS check the SKU in shelves every hour, unlocks wb_shelves report=graph (daily dynamics) a...

- required: `action,sku`
- properties: `action,name,sku`

### `wb_check_rates`

Live WB search results for a query in a region (up to 5 pages × 100): where each product ranks right now. Use to compare positions of your SKU and competitors across regions (e.g. FBS vs FBO, delivery time impact). Snapshot at call time, no history — for dy...

- required: `query`
- properties: `limit,query,region,skus`

### `wb_compare`

WB period-over-period compare. scope: category | brand | seller | subject. d11/d12 = period 1; d21/d22 = period 2. Даты периодов ISO YYYY-MM-DD; концы периодов (d12, d22) не позже вчера — данные за сегодня недоступны.

- required: `scope,value,d11,d12,d21,d22`
- properties: `d11,d12,d21,d22,fbs,limit,scope,value`

## Repricer (9)

### `repricer_tokens`

List user marketplace tokens; each id is a user_token_id used by repricer_list / mine_products_*. Several tokens may share the same name (duplicate cabinet connections). cards_total is the WB cabinet card count, NOT the number of products in the repricer (a...

- required: `none`
- properties: `none`

### `repricer_limits`

Account-wide repricer quota. total_repricer_products counts PRODUCTS under repricers across every token/region (verified: equals the sum of the per-token total_repricer_products). It is NOT a repricer count — do not compare it with the length of repricer_li...

- required: `none`
- properties: `none`

### `repricer_list`

List repricers (overview). tokens = user_token_id list from repricer_tokens (required; API returns 422 if empty). IMPORTANT: repricers are spread across tokens and some tokens hold 0 — always pass ALL ids from repricer_tokens, never a guessed subset. A shor...

- required: `tokens`
- properties: `active_only,deleted,search,tokens`

### `repricer_get`

Full repricer config: products, competitors, schedule, region, flags. Read-only.

- required: `repricer_id`
- properties: `marketplace,repricer_id`

### `repricer_history`

Price change history for one card in a repricer. Dates ISO YYYY-MM-DD, default last 30 days. Read-only.

- required: `repricer_id,nmid`
- properties: `d1,d2,limit,nmid,repricer_id`

### `repricer_products`

Cards in a repricer. preview=false → draft list, preview=true → preview/actual list. Read-only.

- required: `repricer_id`
- properties: `limit,preview,repricer_id`

### `repricer_competitors`

Competitor cards attached to a repricer. Read-only.

- required: `repricer_id`
- properties: `repricer_id`

### `repricer_search_competitors`

Search competitor cards by article numbers (nmid). Read-only.

- required: `nmids`
- properties: `marketplace,nmids`

### `repricer_regions`

Available regions for price/stock calculation. Read-only.

- required: `none`
- properties: `marketplace`

## Own products / marketplace tokens (3)

### `mine_products_list`

My products with current prices for a token. Read-only.

- required: `user_token_id`
- properties: `limit,marketplace,user_token_id`

### `mine_products_status`

Status of the price-load queue for a token. Read-only.

- required: `user_token_id`
- properties: `marketplace,user_token_id`

### `mine_products_history`

Price history for one card under a token. Dates ISO YYYY-MM-DD, default last 30 days. Read-only.

- required: `user_token_id,nmid`
- properties: `d1,d2,nmid,user_token_id`

## Wildberries advertising / bidder (8)

### `wbbidder_cabinets`

Рекламные кабинеты Wildberries, подключённые к MPSTATS. Вызови первым, если кабинетов несколько или нужно понять, где есть реклама: id — это значение для параметра tokens в остальных wbbidder_* инструментах. Поля: ads_campaigns_active / ads_campaigns_pause ...

- required: `none`
- properties: `none`

### `wbbidder_overview`

Сводка «как дела с рекламой на Wildberries» одним вызовом. Начинай с него любой общий вопрос про СВОЮ рекламу: «сколько потратили на рекламу», «какой ДРР», «стало лучше или хуже», «сколько кампаний ведёт биддер», «упёрлись ли в лимит». Возвращает четыре бло...

- required: `none`
- properties: `bidder_only,d1,d2,tokens,zone`

### `wbbidder_campaigns`

Список своих рекламных кампаний Wildberries. Отсюда берётся campaign_id (поле id) для wbbidder_campaign, wbbidder_campaign_stats, wbbidder_events и wbbidder_clusters. В каждой строке два идентификатора: id — внутренний id MPSTATS (он и есть campaign_id), wb...

- required: `none`
- properties: `bidder_only,d1,d2,limit,nm_id,report,search,sort,sort_dir,start_row,status,tokens,zone`

### `wbbidder_campaign`

Полная карточка одной рекламной кампании Wildberries: настройки, бюджет, баланс кабинета и минимальные ставки одним вызовом. Для вопросов «как настроена кампания», «сколько осталось бюджета», «почему кампания не крутится», «какая минимальная ставка», «включ...

- required: `campaign_id`
- properties: `campaign_id`

### `wbbidder_campaign_stats`

Статистика одной рекламной кампании Wildberries за период. campaign_id — внутренний `id` кампании из wbbidder_campaigns, НЕ wb_id (ID кампании на Wildberries; он приходит в ответах отдельным полем wb_id и как параметр не подходит). report: - days (по умолча...

- required: `campaign_id`
- properties: `campaign_id,d1,d2,nm_id,query,report,zone`

### `wbbidder_events`

Журнал событий рекламной кампании Wildberries — «что делал биддер»: когда и почему менялась ставка, какие кластеры получили ставку или ушли в минус, когда кончились остатки, что менял человек вручную. campaign_id — внутренний `id` кампании из wbbidder_campa...

- required: `campaign_id`
- properties: `campaign_id,category,d1,d2,limit,manual_only,start_row`

### `wbbidder_clusters`

Поисковые кластеры (группы запросов), по которым товар показывается в рекламной кампании Wildberries. Для вопросов «по каким запросам уходит бюджет», «какие кластеры не конвертят», «что заминусовано и почему», «как настроено автоминусование». campaign_id — ...

- required: `campaign_id,nm_id`
- properties: `campaign_id,d1,d2,limit,nm_id,norm_query,report,sort`

### `wbbidder_products`

Реклама Wildberries в разрезе товаров, а не кампаний: один артикул может участвовать в нескольких кампаниях, и здесь его расход сведён вместе. Для вопросов «на какие товары уходит рекламный бюджет», «у какого товара худший ДРР», «окупается ли реклама артику...

- required: `none`
- properties: `d1,d2,limit,nm_id,report,sort,sort_dir,start_row,tokens`

## Ozon external analytics (7)

### `ozon_categories_search`

Найти категории (ниши) Ozon по ключевому слову. Возвращает пути (path), число подкатегорий и метрики. Передавай path в ozon_category. Ищи коротким существительным; чтобы увидеть ниши, не попавшие под слово, раскрывай ветку через ozon_categories_children.

- required: `query`
- properties: `limit,query`

### `ozon_categories_children`

Прямые подкатегории ветки Ozon по её path (из ozon_categories_search).

- required: `path`
- properties: `limit,path`

### `ozon_category`

Ozon category. report: products (default) | subcategories | brands | sellers | by_date | price_segmentation | trends | keywords | niches. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передав...

- required: `path`
- properties: `d1,d2,fbs,limit,path,report`

### `ozon_sku`

Ozon SKU report. report: sales (default) | by_day | balance | categories | keywords | full | by_period | search_stats | stores | comments. by_day/balance need 'point_date' (YYYY-MM-DD); остальные — диапазон d1/d2. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчер...

- required: `sku`
- properties: `d1,d2,fbs,point_date,report,sku`

### `ozon_brand`

Ozon brand. report: products | categories | sellers | by_date | price_segmentation | trends | keywords | niches | geography. newsmode: 7|14|30 for new-products mode. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d...

- required: `name`
- properties: `d1,d2,fbs,limit,name,newsmode,report`

### `ozon_seller`

Ozon seller. seller_id_or_name accepts numeric id or seller name. report values same as ozon_brand. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передавай сегодняшнюю дату в d2.

- required: `seller_id_or_name`
- properties: `d1,d2,fbs,limit,newsmode,report,seller_id_or_name`

### `ozon_compare`

Ozon period-over-period compare. scope: category | brand | seller. d11/d12 = period 1; d21/d22 = period 2. Даты периодов ISO YYYY-MM-DD; концы периодов (d12, d22) не позже вчера — данные за сегодня недоступны.

- required: `scope,value,d11,d12,d21,d22`
- properties: `d11,d12,d21,d22,fbs,limit,scope,value`

## Yandex Market external analytics (5)

### `ym_category`

Yandex Market category. YM has no rubricator endpoint — use known paths. report: products | subcategories | brands | sellers | by_date | price_segmentation. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − ...

- required: `path`
- properties: `d1,d2,fbs,limit,path,report`

### `ym_brand`

YM brand. report: products | categories | sellers | by_date | price_segmentation. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передавай сегодняшнюю дату в d2.

- required: `name`
- properties: `d1,d2,limit,name,report`

### `ym_seller`

YM seller by name. report: products | categories | brands | by_date | price_segmentation. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передавай сегодняшнюю дату в d2.

- required: `name`
- properties: `d1,d2,limit,name,report`

### `ym_sku`

YM item sales/stock history by numeric id. Даты ISO YYYY-MM-DD. По умолчанию d2 = вчера (данные за сегодня у MPSTATS ещё не готовы), d1 = d2 − 30 дней. Не передавай сегодняшнюю дату в d2.

- required: `item_id`
- properties: `d1,d2,item_id`

### `ym_compare`

YM period-over-period compare. scope: category | brand | seller. d11/d12 = period 1; d21/d22 = period 2. Даты периодов ISO YYYY-MM-DD; концы периодов (d12, d22) не позже вчера — данные за сегодня недоступны.

- required: `scope,value,d11,d12,d21,d22`
- properties: `d11,d12,d21,d22,fbs,limit,scope,value`

## Photo editor (18)

### `pe_health`

Photo editor service health check.

- required: `none`
- properties: `none`

### `pe_remove_background`

Remove background. Image input accepts: URL, base64, data:image/...;base64,..., or 'wb:<sku>' / 'wb:<wb-url>'.

- required: `image`
- properties: `image,timeout_s`

### `pe_upscale`

Upscale image. Image input accepts: URL, base64, data:image/...;base64,..., or 'wb:<sku>' / 'wb:<wb-url>'.

- required: `image`
- properties: `image,timeout_s`

### `pe_replace_background`

Replace product background using a server-side template. Image input accepts: URL, base64, data:image/...;base64,..., or 'wb:<sku>' / 'wb:<wb-url>'. Get template_key from pe_templates_backgrounds. model: model_1..5 | auto. aspect: 1:1 3:4 4:3 2:3 3:2.

- required: `image,template_key`
- properties: `aspect_ratio,image,model,template_key,timeout_s,user_prompt`

### `pe_in_action`

Place product into a use-case scene from a template. Image input accepts: URL, base64, data:image/...;base64,..., or 'wb:<sku>' / 'wb:<wb-url>'. Get template_key from pe_templates_in_action.

- required: `image,template_key`
- properties: `aspect_ratio,image,model,template_key,timeout_s,user_prompt`

### `pe_recolor`

Recolor product to a target hex color (#RRGGBB). Image input accepts: URL, base64, data:image/...;base64,..., or 'wb:<sku>' / 'wb:<wb-url>'.

- required: `image,color`
- properties: `aspect_ratio,color,image,model,timeout_s`

### `pe_freeform`

Free-form prompt-based edit. Image input accepts: URL, base64, data:image/...;base64,..., or 'wb:<sku>' / 'wb:<wb-url>'. References (max 5) also accept any image format.

- required: `image,prompt`
- properties: `aspect_ratio,image,model,prompt,references,timeout_s`

### `pe_photoshoot_test`

Photoshoot pipeline: one test frame.

- required: `image,prompt`
- properties: `aspect_ratio,image,model,prompt,references,timeout_s`

### `pe_photoshoot_generate`

Photoshoot pipeline: generate N frames from an approved test shot. count 1..6.

- required: `approved_image,prompt,image_count`
- properties: `approved_image,aspect_ratio,image_count,model,prompt,timeout_s`

### `pe_photoshoot_auto`

Photoshoot pipeline: test → generate in one call. count 1..6.

- required: `image,prompt,image_count`
- properties: `aspect_ratio,image,image_count,model,prompt,references,timeout_s`

### `pe_infographics_test`

Infographics pipeline: one test slide.

- required: `image,prompt`
- properties: `aspect_ratio,image,model,prompt,references,timeout_s`

### `pe_infographics_generate`

Infographics: generate N slides from an approved test. count 1..6. Endpoint returns max(4, count) frames.

- required: `approved_image,prompt,image_count`
- properties: `approved_image,aspect_ratio,image_count,model,prompt,timeout_s`

### `pe_infographics_auto`

Infographics: test → generate in one call. count 1..6.

- required: `image,prompt,image_count`
- properties: `aspect_ratio,image,image_count,model,prompt,references,timeout_s`

### `pe_templates_backgrounds`

List server-side background templates, or one template by key.

- required: `none`
- properties: `key`

### `pe_templates_in_action`

List server-side 'in action' templates, or one template by key.

- required: `none`
- properties: `key`

### `pe_wb_fetch_photos`

Fetch WB CDN photo URLs for an SKU (or 'wb:<sku>' / WB URL). Returns up to max_count public URLs.

- required: `sku_or_url`
- properties: `max_count,sku_or_url`

### `pe_run`

Submit a raw Photo Editor body to any endpoint and poll until completion. Escape hatch when typed tools don't fit.

- required: `endpoint,body`
- properties: `body,endpoint,timeout_s`

### `pe_poll`

Poll an existing Photo Editor event_id until completion.

- required: `event_id`
- properties: `event_id,timeout_s`

## Own Wildberries cabinet (33)

### `lk_wb_cabinets`

Выбор WB-кабинета для последующих lk_wb-запросов текущего токена. По умолчанию (без выбора) данные агрегируются по всем кабинетам. action='list' — показать кабинеты (id, name, valid, selected); action='select' c id=<id> — скоупить данные на один кабинет; ac...

- required: `none`
- properties: `action,id`

### `lk_wb_request`

Universal LK WB API caller (read-only). path относительно LK_WB_BASE_URL.

- required: `method,path`
- properties: `body,method,path,query`

### `lk_wb_dashboard_business_economics`

Экономика бизнеса. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_order_analytics`

Аналитика по заказам. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_widget`

Виджет сводки. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_sales_funnel`

Воронка продаж. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_table`

Таблица сводки по дням. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_table_aggregated`

Агрегированная таблица сводки. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_chart`

График сводки. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_chart_aggregated`

Агрегированный график сводки. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_expenses`

Детализация расходов. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_dashboard_widget30days`

Виджет за 30 дней (lost_sales, localization_index, stock_count и т.д.). Параметров не требует.

- required: `none`
- properties: `turnover_days,urgently_days`

### `lk_wb_orders_region_statistics`

География заказов. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_products_stocks`

Раскладка остатков по складам. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True. start_row/end_row пагинация (default 0/50).

- required: `none`
- properties: `date_from,date_to,end_row,period_type,self_redemption,start_row`

### `lk_wb_reports_weekly`

Еженедельный отчёт. period_type='30days' (или 7days/90days/year), либо date_from+date_to (YYYY-MM-DD). Опционально self_redemption=True.

- required: `none`
- properties: `date_from,date_to,period_type,self_redemption`

### `lk_wb_reports_compare`

Сравнение двух периодов. Даты в формате ДД.ММ.ГГГГ (как в UI кабинета). start_row/end_row пагинация (default 0/50).

- required: `d11,d12,d21,d22`
- properties: `d11,d12,d21,d22,end_row,show_all,size_group,start_row,tags`

### `lk_wb_products`

Отчёт по товарам (async, polling до готовности). date_from/date_to в YYYY-MM-DD. start_row/end_row пагинация.

- required: `date_from,date_to`
- properties: `date_from,date_to,end_row,start_row`

### `lk_wb_sales_tape`

Лента продаж и заказов. date_from/date_to YYYY-MM-DD. start_row/end_row пагинация.

- required: `date_from,date_to`
- properties: `date_from,date_to,end_row,start_row`

### `lk_wb_sales_chart`

График заказов по часам. date_from/date_to YYYY-MM-DD.

- required: `date_from,date_to`
- properties: `date_from,date_to`

### `lk_wb_tags_search`

Поиск тегов по подстроке.

- required: `search`
- properties: `search`

### `lk_wb_tags_count`

Список тегов с количеством SKU.

- required: `none`
- properties: `none`

### `lk_wb_cabinet_notifications`

Уведомления кабинета (товары с нулевой себестоимостью и т.п.).

- required: `none`
- properties: `none`

### `lk_wb_brands_actual`

Словарь актуальных брендов кабинета.

- required: `none`
- properties: `none`

### `lk_wb_brands_actual_count`

Бренды с количеством товаров.

- required: `none`
- properties: `none`

### `lk_wb_reference_all_stores`

Расширенный словарь складов.

- required: `none`
- properties: `none`

### `lk_wb_taxes`

Список налогов и НДС кабинета.

- required: `none`
- properties: `none`

### `lk_wb_pulse_summary`

Pulse: сводная таблица за период (date_from..date_to).

- required: `date_from,date_to`
- properties: `date_from,date_to,refresh`

### `lk_wb_pulse_products`

Pulse: таблица товаров за период.

- required: `date_from,date_to`
- properties: `date_from,date_to,end_row,refresh,start_row`

### `lk_wb_card_info`

Карточка → основная информация. type — brands | tags | articles. value — название/id сущности.

- required: `type,value`
- properties: `type,value`

### `lk_wb_card_orders`

Карточка → продажи/заказы за период (AgGrid). type — brands | tags | articles. value — название/id сущности.

- required: `type,value,date_from,date_to`
- properties: `date_from,date_to,end_row,start_row,type,value`

### `lk_wb_card_table`

Карточка → таблица/график по дням. type — brands | tags | articles. value — название/id сущности.

- required: `type,value`
- properties: `period_type,self_redemption,type,value`

### `lk_wb_card_widget`

Карточка → виджет показателей. type — brands | tags | articles. value — название/id сущности.

- required: `type,value`
- properties: `period_type,self_redemption,type,value`

### `lk_wb_card_region`

Карточка → география заказов. type — brands | tags | articles. value — название/id сущности.

- required: `type,value`
- properties: `period_type,self_redemption,type,value`

## Own Ozon cabinet (6)

### `lk_ozon_cabinets`

Список подключённых кабинетов Ozon текущего токена (id, name, status, is_ozon_valid, client_id_seller). Вызови первым, чтобы узнать id/имена кабинетов. У других lk_ozon_* инструментов скоуп задаётся параметром cabinet=<id или имя из этого списка>; без cabin...

- required: `none`
- properties: `none`

### `lk_ozon_fields`

Каталог полей отчёта lk_ozon_products: 109 колонок (имя, описание, группа, тип, фильтруется/сортируется ли, допустимые операторы). Статика в коде — к API не ходит. Когда применять: когда 4 готовых preset'а lk_ozon_products (economics/stocks/prices/expenses)...

- required: `none`
- properties: `group,search`

### `lk_ozon_products`

Экономика по товарам своего кабинета Ozon: заказы, продажи, остатки, расходы, прибыль, маржа. Поверх POST api/products/report — асинхронного отчёта upstream; инструмент сам ждёт готовности (поллинг), агенту почти всегда прилетает готовый результат за один в...

- required: `none`
- properties: `cabinet,date_from,date_to,end_row,fields,group_by,include_facets,preset,refresh,search,sort,start_row,status,where,widget,widget_threshold`

### `lk_ozon_overview`

Состояние кабинета Ozon одним вызовом: сколько заработал, куда ушли деньги, есть ли проблемы, растёт или падает. Это ПЕРВЫЙ инструмент на любой вопрос про свой кабинет Ozon целиком ('как дела с моим Ozon', 'сколько заработал', 'что с прибылью за месяц') — в...

- required: `none`
- properties: `cabinet,compare_date_from,compare_date_to,date_from,date_to`

### `lk_ozon_pulse`

Воронка продаж товаров своего кабинета Ozon из раздела «Рука на пульсе» (RNP): показы, CTR, переходы в карточку, добавления в корзину, конверсия в заказ — то, чего НЕТ в lk_ozon_products (тот про деньги/остатки/цены по ВСЕМУ каталогу, этот — про воронку у т...

- required: `none`
- properties: `cabinet,date_from,date_to,end_row,refresh,segment,sort,start_row`

### `lk_ozon_product_daily`

Динамика воронки продаж ОДНОГО товара по дням (раздел «Рука на пульсе» RNP): как показы/CTR/переходы в карточку/корзина/заказы менялись день за днём за период — детализация к lk_ozon_pulse на уровне одного sku. Когда применять: после lk_ozon_pulse нашёл тов...

- required: `sku`
- properties: `cabinet,date_from,date_to,groups,sku`

## Acceptance note

This inventory proves that the tools are advertised by the live MPSTATS MCP endpoint. Individual tools still need business-semantic classification and, where relevant, harmless read-only validation before being treated as trusted sources for automated decisions.
