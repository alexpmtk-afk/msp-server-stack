# Ozon method acceptance: progress and remaining exact-schema gate

Only public official documentation fetched; no provider API or token reads.

Official notices substantiate candidate versions:
- https://dev.ozon.ru/news/734-Otkliuchenie-starykh-metodov-Seller-API-dlia-raboty-s-postingami/ (2026-06-01): current FBO /v3/posting/fbo/list and FBS /v4/posting/fbs/list; previous versions retired2026-08-01.
- https://dev.ozon.ru/community/2062-Nekorrektnyi-primer-otveta-dlia-v4-posting-fbs-list/ (moderator,2026-05-07): FBSv4 response has no result envelope; the historical adapter's top-level postings parser is consistent with that statement.
- https://t.me/s/OzonSellerAPI/682 (2026-07-28/30): /v1/finance/realization/posting and /v1/finance/accrual/by-day updated; the latter's date,last_id,accruals and response last_id are explicitly mentioned. This confirms names/fields exist, NOT full formats/pagination/rates/permissions.

Direct https://docs.ozon.ru/api/seller/ gives307 (__rr redirect); cookie-enabled retrieval returns403. No complete current official schemas/rate-limit tables obtained. Do not promote release notices or old fixtures into current schema acceptance.

FIRST PILOT CANDIDATE, NOT EXECUTABLE YET:
- cabinet ozon_laser_master; FINAL closed October2026; candidate POST /v1/finance/realization/posting; candidate body {year:2026,month:10}; at most1 durable sender entry through existing controller and Client-Id quota. This body/response/terminal contract must be confirmed before admission, not guessed in a live test.
- Validate immutable official schema evidence for exactly that method, pagination/terminal indication, requested period bounds, provider-owned row identity, method quota and429 headers. Keep raw JSON and page hash before ingest. A first page must not be marked full without method-specific terminal evidence.
- CURRENT is separate: FBO/FBS postings and accruals, no substitution for realization. No CURRENT call in the FINAL pilot.
- Existing global MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED remains unset. Never use a successful FINAL call to enable all four methods. The exact candidate allowlist must reject other methods even if the underlying shared quota approval flag is present.

Schema acceptance, current-body compatibility and Ozon live pilot remain NOT VERIFIED. Existing old successful/offline fixtures are not re-labelled as current real results.
