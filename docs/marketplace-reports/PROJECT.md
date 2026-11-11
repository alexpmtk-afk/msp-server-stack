# МСП — отчёты из кабинетов WB/Ozon — рабочая карта

Дата начала: 28.10.2026. Статус: **разработка в отдельной ветке; не развёрнуто на VPS**.

## Задача
Сформировать локальный долгосрочный архив официальных финансовых данных за 2026 год по трём кабинетам WB и трём Ozon. Сначала историческая загрузка, затем дозагрузка по запросу и, возможно, расписанию. Google Drive **не** используется как каноническое рабочее хранилище новой системы.

## Единая точка совместной работы
Репозиторий `alexpmtk-afk/msp-server-stack`, директории `apps/msp_marketplace_reports/` (код), `tests/test_msp_marketplace_reports.py` (проверки) и `docs/marketplace-reports/` (контракт, решения, передача). Работа по `docs/MSP_GITHUB_VPS_WORKFLOW.md`: ChatGPT и Hermes читают main + соответствующие PR и ветки, каждый пишет в собственную ветку, без прямой записи main, автоматического слияния или установки.

Перед работой читать эту карту, `DECISIONS.md`, `HANDOFF.md` и действующий `AGENTS.md`. После работы обновлять журнал передачи с точными ссылками на коммиты/PR и PASS/FAIL.

## Кабинеты (стабильные непубличные секреты НЕ указаны)
WB: `wb_laser_master`, `wb_novokshenov`, `wb_dmitrieva`.
Ozon: `ozon_laser_master`, `ozon_novokshenov`, `ozon_dmitrieva`.
ID сохраняются при ротации ключа.

## Источники по первой очереди
- WB `wb_weekly_finance_main`: основной финансовый `reportType=1`, ключ `reportId + rrdId`. Все физические фрагменты одной недели обязательны.
- WB `wb_weekly_finance_buyout`: отдельный финансовый отчёт по выкупам `reportType=2`, тот же уникальный ключ, другой каталог/CSV. В документации WB это продажи в ЕАЭС и выкупы WB. Не смешивать документы без специальной сверки.
- Ozon `ozon_final_realization`: закрытые месяцы `/v1/finance/realization/posting`, месячные источники + годовой файл, ключ `report_year + report_month + row_number`.
- Ozon `ozon_current_orders_fbo`, `ozon_current_orders_fbs`, `ozon_current_accruals`: открытый месяц пересчитывается целиком, ключи `posting_number` или `accrual_id`.
- Не подменять продажу заказом или начислением; не включать рекламные отчёты в финансовые без явного контракта.

## План размещения (не создан на сервере)
- `/opt/mcp/data/msp-marketplace-reports/` — CSV, реестры и резервные версии.
- `/etc/msp-marketplace-reports/` — отдельные учётные данные, исключительно на VPS (root:root 0700; cabinets.json 0600). Не использовать общий каталог `/opt/mcp/secrets`: он принадлежит `hermes`.
- Код через утверждённую версию из GitHub; система МСП/SQLite и существующий Marketplaces MCP не изменяются.

## Этапы
0. [код готов, проверка CI] Локальное хранилище, проверка формата, контрольных сумм, резервные версии, тесты; ручные HTTP-адаптеры WB/Ozon без установки.
1. [частично] VPS и диск проверены штатным read-only каналом; ключи на локальном ПК владельца. Подготовлены Windows-отправитель и root-приёмник, но установка, безопасная передача и последующая проверка доступа на VPS не выполнены.
2. [частично] Исторические контракты и текущие публичные сведения сверены; код чтения WB/Ozon и моделируемые тесты подготовлены. Реальный тест по одному WB reportId и месяцу Ozon ожидает доступа к ключам на VPS.
3. [ожидает] Однажды импортировать существующие проверенные исторические CSV (если доступны) или восстановить из API. Никаких данных не считать полными без проверки реестра провайдера.
4. [ожидает] Массовое заполнение шести кабинетов, проверка покрытия 01.01.2026–последний доступный закрытый период, нулевых/пустых/исправленных отчётов и пропусков.
5. [ожидает] Команды обновления и проверки для всех клиентов/Hermes, затем по отдельному решению — расписание.
6. [ожидает] Восстановление после сбоев, тестирование с лимитами API, резервные копии вне основного диска.

## Условия принятия
Состояние `COMPLETE` только после сверки провайдера, реестра покрытия, ключей строк, SHA256 и независимого `verify`. Подготовленный PR не означает, что код установлен; нет доказательства прав к API, пока не выполнен безопасный запрос с сервера.

## Источники
Предоставленная владельцем передача «ТЕХНИЧЕСКАЯ ПЕРЕДАЧА — АРХИВ ПРОДАЖ И ФИНАНСОВЫХ ОТЧЁТОВ WILDBERRIES / OZON» (13–26.09.2026). Исторический код: `alexpmtk-afk/marketplaces-mcp-ru`. Этот проект не вносит в него изменения.

## Испытание WB 28.10.2026 — подтверждено на VPS
- После исправления ввода секретов все 9 реквизитов успешно прошли локальную проверку формата и прав.
- `wb_laser_master`: `GET /api/v1/account/balance` → HTTP 200 JSON; `POST /api/finance/v1/sales-reports/list` за 01–27.10.2026 → HTTP 200 JSON, 8 документов: четыре `reportType=1`, четыре `reportType=2` на отчётные периоды 01–04, 05–11, 12–18 и 19–25 октября.
- Данные отчётов пока **не загружались и не сохранялись**. Проверка списка — не подтверждение корректной детализации. Новая ветка научилась раздельно архивировать оба типа, запуск на VPS только по отдельной команде.


## Ozon closed months — 2026-11-10

Owner requested January–October 2026 for all three legal entities; WB current month paused. Fixed one-month Dmitrieva January Ozon FINAL pilot prepared, 12 network-denied tests PASS. No authenticated Ozon request/activation has occurred. Root execution remains the technical prerequisite, not missing authorization/keys. Reuses accepted executor and shared Redis; no broad four-method gate or new scheduler. Exact artifacts and acceptance: `ops/ozon-final-pilot-20261110/STATUS.md`. Pilot is not annual publication or complete Ozon expense coverage.


## Preflight correction — 11 November 2026

Owner ran the pinned launcher: snapshot `/var/lib/msp-ozon-final._6rkj4nr`, preflight line111 HOLD before any executor start/state/admission. Root console frames establish erroneous whole-receipt SHA comparison. The accepted supervisor compares receipt.probe_sha256 (probe program origin), then exact typed acceptance fields. Fixed Ozon verifier to reproduce that contract, reject duplicate keys/wrong origin/failed results/type-confused values, and require active existing Redis. No new synthetic writes or backend/credential permission changes. 13 network-denied tests PASS. Revised bundle/launcher prepared, NOT root-executed; old preflight failure is not a provider error or consumed send entry. Preserve old snapshot; same January cabinet/plan and max1 budget.
