# WB 2026 thin wiring — opt-in offline integration, 30.10.2026

Upstream Hermes scoped acceptance: PR #98 / HEAD d6ab584b7bc66c94911bece097e1e3e7c3e302be, 167 PASS + 79 additional scenarios. Current task: one minimal follow-on code package in PR #99. **This document does not authorize VPS installation, Redis/API calls, enabled flags, merge or live pilot.**

## Реально реализовано в PR #99

- `wb_page_resume.step_wb_detail` остаётся единственным source of truth для page/cursor. Staging идентифицируется `cabinet/year/reportId/type` (добавлен `type` чтобы не пересекать main и buyout). Без новой Redis job-очереди.
- `quota.QuotaBusy` возвращает структурированный `retry_after_seconds`; HTTP 429 записывает upstream cooldown через утверждённый shared controller до отказа. `wb_page_resume` отдаёт `not_before_utc` и `retry_after_seconds` в результате WAITING_RATE_LIMIT для **сохранения существующим scheduler**. Старый worker не подключён; пока нет production not-before persistence. Попытки с gate=NO блокируются.
- `wb_worker_adapter.run_one_step` — **один вызов, не цикл/планировщик**. Предварительно проверяет отсутствие смешанного legacy и целостность CURRENT до HTTP. При STAGED_COMPLETE без новых сетевых запросов:
  1. делает два bounded прохода проверенных WB page files (полный union полей, _raw_json);
  2. пишет CSV в закрытый временный каталог (0700) с файлом 0600, fsync;
  3. закрывает генератор и освобождает page lock до versioned publish;
  4. вызывает `import_csv_versioned` с CAS/no-op, проверяет CURRENT-anchored pinned read и строки собственного reportId/type;
  5. только после проверки записывает `coverage.json` локального статуса `LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE`, без заявления полного provider coverage.
- При потере ответа после CURRENT или после commit до coverage следующий вызов финализирует уже сохранённый stage, не скачивая страницы снова. Обнаруженное повреждение/конфликт — блокировка, без автоматической починки.
- Явная CLI команда `wb-versioned-step` добавлена рядом с прежним `wb-one` **без тихого переключения старой команды**. Каждый вызов максимум одна попытка запросить страницу (и при 204 финализация). Для async планировщика требуется `asyncio.to_thread` с единственным approved sender; второй call_spec/reserve запрещён.
- CI `pull_request.paths` дополнен обоими WB worker и quota тестами (C1 Hermes). Прототип/модули в GitHub — не installed worker и не доказательство P01.

## Границы, которые ещё блокируют live

- Существующий worker `core/archive_queue.py` в `marketplaces-mcp-ru` не изменён. Нужен подтверждённый installed revision/host, то, как именно worker достигает data root нового VPS, и разрешённая схема развёртывания. Не создавать второй scheduler, сетевой tunnel или новый Redis.
- Реальные `P01` endpoint/TLS/DB/namespace/installed rules/owner/shared-admission/fail-closed и права к 0600 secret/staging **NOT VERIFIED**. Hermes готовил read-only evidence request; выполнять runtime tests только по отдельному разрешению владельца.
- Общие 50 RPS Ozon подтверждены официально, но схемы четырёх методов, их special limits/history/задержки публикации **NOT VERIFIED**. Ozon approval остаётся NO.
- Первая календарная неделя 2026 начинается 29.12.2025, конец может пересекать январь 2027. Текущий WB year/dateTo admission versioned writer проверяет год dateTo и не готов к обоим boundary без отдельного review. Для пилота выбрать внутреннюю неделю 2026, границу не скрывать, не обрезать строки.
- Publisher всё ещё материализует полный годовой WB snapshot и требует отдельной проверки RAM для массового backfill. Empty coverage и исправленные provider rows/corrections требуют явной политики. Обработка реальных payloads пока не проводилась; page staged hard cap 64MiB.
- Нельзя объявлять archived report «provider complete» лишь по HTTP204: отдельный источник discovery/reconciliation подтверждает наличие всех reportId, даты и типы; локальный pin доказывает только целостность опубликованных данных.

## Для Гермеса

Независимо проверить pinned HEAD PR #99; повторить main/buyout, type collision, quota busy/HTTP429, no double reservation, failure before request, 2-pass CSV + late field, lock-release, crash before coverage, lost publication response, pin+coverage tamper rejection. Особое внимание на безопасный `not_before` и реальные ограничения `ingest` / `versioned_archive`. После review вернуть единое PASS/FAIL и фактический placement/P01 evidence gate, без live действий.

**Не смешивать**: принятое offline PR98 ≠ новый PR99 ≠ установленный worker ≠ разрешённый пилот.
