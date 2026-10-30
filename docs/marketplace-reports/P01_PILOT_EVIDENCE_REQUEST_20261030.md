# P01 — запрос доказательств перед разрешённым пилотом

Статус: PREPARED, NOT EXECUTED. Это контракт read-only сведений и будущего отдельно разрешённого admission test, НЕ команда запуска и НЕ разрешение Redis/API/deploy.

Проверить через уже разрешённый канал, без расширения PAT/новых туннелей:

1. Конечный host identity совпадает с владельческим ожиданием (PASS/FAIL без публичного адреса); действующий executor/process/version установлен, не взят только из GitHub.
2. Для старого Marketplace MCP и кандидата нового archive указаны точные installed source/catalog revisions; знать, где физически выполняется worker и где будет VPS staging.
3. Redis endpoint/TLS/CA/DB match; оба клиента имеют права на одинаковый namespace. URL, пароли, environment dump не передаются. Пароль не хешировать как «доказательство». Достаточны локальные match/mismatch и источник проверки.
4. Prefix/schema совпадают: rate marketplace-rate:v1, WB finance host/scope/rate, Ozon Client-Id global; дополнительный safety не заменяет canonical key. Job ZSET marketplace-archive:v2:wb-finance:due — другая роль, не доказательство общей API-квоты.
5. Identity match по каждому участвующему кабинету: sid/Client-Id сравниваются в защищённой сессии; публично только cabinet label + PASS/FAIL, без реальных owner hash/токенов.
6. Effective overrides не ослабляют provider contracts: Ozon aggregate<=50RPS, WB canonical1req/min + safety65, дополнительные special rules только из подтверждённой spec.
7. Все попытки/страницы проходят admission, Redis outage fail-closed; WB429 откладывает canonical finance, Ozon общий429 — canonical global и safety. Не проверять падение выключением рабочего Redis.
8. После отдельного согласования — controlled two-client reservation в изолированной тестовой области того же backend, без HTTP, flush/reset/restart рабочих buckets. До такого разрешения только чтение конфигурации/источников. TCP/PONG не доказывают atomic/shared behavior.
9. Чтение root-protected cabinets.json разрешённому process и private staging/disk/backup подтверждено без вывода содержимого и без ослабления0700/0600. Проверка прав отдельно от действительности API keys.
10. Owner разрешает конкретные версии/метод/кабинет/период pilot и активацию только нужного gate. Принятие offline PR не включает flag.

Формат ответа для каждого пункта: check_id, PASS/FAIL/NOT_VERIFIED, installed revision/source, обезличенное наблюдение, remaining_action. Реальные сетевые локаторы/ключи/финансовые rows в публичный stack не помещать. Если канала нет, точно назвать требуемый существующий SSH/консольный read-only доступ, не создавать обходной.

**В этом этапе не читались процессы, Redis-конфигурации, credential file или API keys.** Стандартный локальный checkout/Skills проверены отдельно; это не результат P01.
