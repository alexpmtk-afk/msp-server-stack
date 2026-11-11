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


## Strict-umask partial recovery — 11 November 2026

Second owner invocation reached activation preparation but failed at trust(DROP.parent,0755). Launcher uses umask077, so mkdir(...,0755) created0700. No executor start/API entry: unit still last started9Nov, no drop-in, network denied; exact partial snapshot `/var/lib/msp-ozon-final.esz6i2qs` and empty executor state retained. Fix finalizes new directory mode explicitly; recovery accepts ONLY this pinned old payload (manifest1f40f499ed24c79771a63fb5e0a3f6e1fda02307a08c6ff55722ea5a10d925dd), matching minimal credential/plan, exact empty0711 state and empty root0700 drop directory. It changes only that literal directory mode, preserves prior snapshot/secrets and never deletes/resets any journal or consumed entry. Any state file/changed payload/foreign control HOLD. 16 network-denied tests PASS, including actual umask077 regression and exact empty-state recovery/tamper refusal. Revised artifact is PREPARED, not installed or provider-verified.


## Existing unit approval condition — 11 November 2026

Third owner invocation produced public HOLD_NO_WORKER_RECEIPT, entry_consumed=false, cleanup=true. Live systemd DBus Conditions showed WB approval.json requirement remained unmet; ConditionTimestamp11Nov09:11, no new ExecMainStartTimestamp. No provider dispatch. Exact skipped receipt SHA229e8b8ae9a631b92e91ba9a158b2dc363a2ef73307b9e7e37fc6e23e06ce87c and snapshot `_impcshq` manifestf4cf55dcf1064c37a20e0fa4de679f83b94525a3fe6732858b6a17eca158b604 pinned. New override resets condition list, explicitly reinstates archive-directory guard and points approval condition to this Ozon attempt. Does not create WB API approval.

Real unprivileged systemd fixture reproduced skipped base condition, then ran a harmless marker worker with identical replacement condition; PASS, zero provider calls, no root executor changes. RemainAfterExit=yes is used ONLY by fixture to retain properties for observation (inactive oneshots can be garbage-collected and show reset properties); actual executor remains oneshot/no restart. 17 network-denied tests PASS. Startup stderr retained privately with sanitized error class/executor fields exported when worker result missing. Recovery accepts only pinned skipped receipt + verified payload + empty state + absence of cleaned credential + no foreign controls; atomically archives original receipt under condition-skipped suffix, preserving it and all prior evidence. Any prior state file or altered receipt HOLD. Revised root artifact PREPARED_NOT_EXECUTED.


## Ozon pilot VERIFIED; closed-month history PREPARED —11.11.2026

Actual January2026 Dmitrieva realization:151unique rows,200,raw/CSV hash/date/value checks, read access and restored inactive isolated unit confirmed. Originalpilot collected, not allOzon finances. Fixed30JanOct report campaign prepared in `ops/ozon-history-20261111/STATUS.md`, verifiedpilot reused withoutHTTP, max29newsendentries, same executor/sharedRedis/controllerlock; one deterministic nonblocking root supervisor, noLLM/timer/newqueue. Nine network-denied tests PASS on3.14/3.12 and actual151-row offlinepublication roundtrip PASS (zero productionwrites/API). Package reproducible and one-line launcher ready; NEW ROOT LAUNCH NOT EXECUTED. After operator launch read exact public ozon-history-2026 receipt and reconcile all3 canonicalannualscopes before complete. Shareddefault-profile instruction installed: docs/data-sources/OZON_FINANCIAL_REPORTS.md. Daily/currentWB andNovember excluded.


## Actual six-cabinet reading VERIFIED; Ozon collection COMPLETE —11.11.2026

Independent read audit source/result: `ops/marketplace-access-audit-20261111/`. Consumed all6WBmain/buyout archives fully with raw-value/hash checks, selectedOctober380/5276/2569rows(Dmitrieva/Laser/Novokshenov). Verified all30Ozonraw/staged/published monthly snapshots and pinned receipts against three annual business-value unions;1724/9167/3313annualrows,150/878/476Octoberrows. Realreceiver identities matched. No newAPIrequests or sourcewrites. Backgroundhistory rootunit successful/inactive; workerinactive/privateNetworkyes/noDropIns. CollectionJanOctrealization complete, readingwithoutroot proved. Canonicalsource updated. This doesnot prove unrestrictedwebcabinet/allAPI/allperiod access or allOzonexpense coverage; WBdaily/current and OzonNovember excluded.


## Ozon semantics sources —11.11.2026 PARTIAL

Official SellerEducation source located but actual browser403/redirect challenge prevents currentarticletext; not read. Historic primarymoderator evidence + attributedschemamirror + real30reports establish46 observedfieldbindings,14204rows,14525populated-block observedidentity checks. Practical guide and sourceflags installed, but currentnormativeformulas/fullXLSX mapping remainpending. Importantcorrection: monthlyOzon reportdoesnot give arbitrarydailysales; orderdate isnotrealizationdate. No money/source/API/scheduler changes. Canonical: docs/data-sources/ozon-financial-reports/; evidenceacceptance: ops/ozon-report-semantics-20261111/PROVENANCE.md.


## Ozon official PDF reconciled —11.11.2026

Owner-provided official six-page realization article read including illustrations; linked official XLSX confirms closing totals C28=F24-J24 and C29=G24-K24. Canonical guide and46-field map updated, source-reconciliation.json records SHA256/scope. Full source copies retained only on server. Closing document is distinct from downloaded posting API; API total remains empirical, not normative. Daily endpoint subscription/32-day limitation documented, not enabled or called. No source-report/API/root changes. Shared default-profile read entrypoints updated.
