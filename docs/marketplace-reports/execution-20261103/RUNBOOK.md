# Один staged runbook: synthetic → cutover → E → 2026 → daily → Ozon

**A/B/C CLOSED.** Это подготовка кода и команд, НЕ установка/запуск API.
Исторические HTTP200 и100 строк переданы владельцем/ChatGPT из архивов; здесь
они не переисполнялись и не выдаются за проверку сегодняшнего токена.
Google Drive для этой работы не нужен. Старый REMOTE не опрашивается.

## Текущий исполнимый шаг: только synthetic, после отдельного разрешения writes

Одна физическая строка — ROOT_SYNTHETIC_ONE_LINE.txt, существующая root-консоль
VM-817589, не `hermes`/sudoers. Файл `/home/hermes/workspace/msp-run-synthetic.py`
уже подготовлен; его exact bytes также run-synthetic.py в этом PR.
Команда копирует launcher в fresh root0700 entry stage, проверяет literal SHA,
потом выполняет root snapshot. Launcher содержит reviewed probe bytes+SHA.

Launcher создаёт отдельный root-owned readable nonsecret stage под /var/lib,
не меняет accepted release или installer inventory. Файл probe0644/dir0755
доступен msp-reports при ProtectHome=yes. Запускает только transient unit как
UID995/GID985, existing venv -I -B, root0600 Redis EnvFile читает PID1, не Hermes.
NoNewPrivileges/ProtectSystem=strict/ProtectHome/PrivateTmp; egress только127/32;
20sec Python /30sec unit /45sec parent bounds. Не открывает/копирует WB token.
Результат root0600 `<probe-stage>/result.json` содержит SHA/result, без URL/password.
Никакого approval.json/gate YES, restart Redis или включения таймеров.

Scope:4 уникальных synthetic keys с TTL<=715s,2 клиента/1 owner, another owner,
defer90sec. Нет SCAN/DEL/FLUSH/CONFIG/реальных seller keys. Не повторять uncertain
запуск автоматически; сохранить stage/receipt. PASS не доказывает старый cutover.
На production Redis выполнение пока NOT_EXECUTED. Offline exact probe PASS в PR113;
дополнительные тесты launcher доказывают payload hash/nonroot refusal, не real root unit.

## Cutover: остаётся отдельным внешним условием

Заполнить CUTOVER_EVIDENCE.template.json по live WB Partners «Интеграции по API»
и, если нужно, support: все finance-capable personal/service/OAuth integrations
пилотного seller, название/тип/категории/status/expiry/владелец/effective time.
Не сохранять token values. Отсутствие REMOTE не означает отсутствие HTTP.
Подтверждать impact для цен/остатков/Telegram/1C. Общий токен не отзывать.
После отдельного D допуска — только согласованный finance cutover с evidence.
Если безопасный selective access cutoff не подтверждается WB, NO-GO, не
придумывать редактирование scope или безопасность «редкого клиента».
Новый токен/local Redis/тихая65sec пауза не исключают прежний доступ.

## E packet: один fixed report и максимум3 учитываемых входа

pilot-plan.json — byte-identical approved plan: wb_laser_master/year2026/
report883801632/type1/max_send_entries3. authorization.BLOCKED.json — исходный
неразрешающий шаблон: false gates/expiry0. Не копировать его как действующее
разрешение; не подставлять true без synthetic PASS, cutover evidence и отдельного E.
MANIFEST.json фиксирует hashes. Эти файлы не устанавливаются builder-ом.

После E текущему принятому msp-wb-pilot.service нужны reviewed scoped drop-in
с protected runtime EnvFile/REQUIRE_REDIS=1 и shared gate, плюс снятие сетевого
deny ТОЛЬКО для этого fixed-host, read-only transport. Existing LoadCredential
pilot-only, protected dirs, local budget/locks сохранить. Сначала check exact
installed plan/code digests и срок/finance eligibility без вывода claims/token;
генерировать root-controlled approval с коротким expiry и реальной evidence link.
Candidate helpers этого PR не подмешивать в immutable installed release: first E
использует accepted PR104 release; digest шаблона относится к нему, не новому
кандидату. Новые backfill/revision helpers требуют отдельной reviewed поставки.

Не повторять balance/list «на пробу» перед fixed-report E — это лишние запросы.
Исторически подтверждён ID/type/период19–25.10; отдельно type2/883801636 не входит
в этот E. Current API contract/eligibility подтвердить по доступной официальной
документации перед E. При401/403 STOP, не менять tokens;429 durable wait/cooldown;
Redis failure запрещает новый HTTP. До factory/reservation увеличивается и fsync
budget. После200 page+hash → cursor, следующаястраница saved rrdId, только204
даёт terminal.100 строк не COMPLETE. Existing batch1000 не менялся на исторический
100: это меньшая проба, а не доказательство обязательного batch100.

При3 nonterminal entries PAUSED_BUDGET; четвёртого HTTP нет. Completion не
гарантируется при неизвестном размере. Продолжение требует отдельно reviewed
budget-extension, НЕ изменения plan hash/удаления журнала ради нового бюджета.
До этого сохраняются cursor/pages/errors/delay. Последующая local reconciliation
готового отчёта не вызывает API. DONE подтверждает терминальную выгрузку и
проверенные local pages/CSV, не финансовую сверку всех сумм/документов за год.

## 2026: исполняемые offline helpers, не вторая очередь

`wb_discovery_resume.step`: отдельный явно утверждённый список/диапазон, existing
standalone executor lock, injected existing sender. <=1 HTTP зашаг, cumulative
budget до factory, page checksum до offset.200 короткаястраница/204 заканчивают
list, two report types сохраняются; crash page-before-offset replay без refetch.
429/QuotaBusy сохраняют not-before, backend error fail-closed, unknown state
не reseal/recreate. Дозагрузка list не ест/не сбрасывает fixed pilot budget.

`finance_refresh_plan`: bounded offline plan по3 WB+3 Ozon. WB сначала verified
provider discovery от01.01.2026 до as-of (month windows, overlap report IDs
нужно объединять), затем reportId/type/period. Missing inventory UNKNOWN, не0.
`finance_receipts` читает реальные page hashes/cursor, checksum-verified бюджет,
not-before/errors и pinned business values, без mkdir/repair/HTTP.
CLI --archive-root получает фактические receipts вместо доверия флагу JSON.
Invalid local integrity формирует HOLD/REVIEW, не повторную загрузку с нуля.
Это **manifest**, не jobqueue и не автосенд. root-approved existing supervisor
должен передавать actions тому же sender. Unit ID deterministic; counters/cursor
живут в существующих executor/page journals, не в плане. Unchanged terminal
receipts исключают повторный backfill. File/count alone не достаточны.

Демонстрация без сети:
`python3 -B -m apps.msp_marketplace_reports.finance_refresh_plan --as-of 2026-11-03 --mode backfill --max-actions 12`
Для online batching нужны отдельные разрешения кабинетов/бюджетов и ресурсная
приёмка. Не выдавать new helper library за уже установленный annual executor.

## Late corrections и ежедневная подготовка

Daily план заново запрашивает metadata inventories и назначает revalidation
последних35дней ежедневно, старых документов каждые30дней. Это conservative
локальная policy, не WB guarantee. Same-ID/same-metadata corrections тоже
попадают в recheck. Bound oldest checked first; completed list-window receipts
checked_on=as_of подавляют повторные list actions в пределахдня. Нужен актуальный
receipt catalog от sole supervisor; planner не считает непроверенный JSON истиной.

`wb_report_revision.publish_revision` принимает только complete+hash-verified
pages новой изолированной revision_root. Same approved sender/budget должен
собирать revision; publisher НЕ отправляет HTTP. Под existing admission lock/CAS
он заменяет строки ровно одного reportId/type (включая исчезнувшие строки),
сохраняет остальные reports и immutable old generations. В том же CSV manifest
атомарно фиксирует last-check/revision/terminal/page hashes. Stale parent STOP.
No-op повтор не создаёт дублей. Старый PR104 importer остаётся strict и не меняется.
Исторические coverage.json остаются historical pins, latest revision смотреть
в latest generation data.csv.meta.json/wb_report_checks, не в старой receipt.

msp-finance-daily-plan.service.in/.timer.in — INERT plan-only templates без
calendar/Install/gate/credentials, не запускают HTTP и не установлены.08:00
Europe/Moscow относится к Sheets. Перед ежедневными загрузками остаётся принять
bounded dispatch/fresh receipt-catalog integration с sole executor и дать
отдельный schedule допуск после E/backfill. Planner template не называется
готовой ежедневной загрузкой. Автоматического enable/start здесь нет.

## Отдельный Ozon (не блокирует первый WB E)

`ozon_connection_plan` использует existing source contracts:
FINAL `/v1/finance/realization/posting` year/month для закрытых месяцев;
CURRENT `/v3/posting/fbo/list`, `/v4/posting/fbs/list` cursor/has_next и
`/v1/finance/accrual/by-day` date/last_id. Каждому cabinet свой Client-Id scope;
тот же existing Redis controller, global+method/safety,429 headers, fail-closed.
Все gates по-прежнему OFF. Orders не заменяют FINAL.
Закрытый month revalidate в bounded rotation и replace monthly source+rebuild
annual; CURRENT replace full open-month snapshots. Не складывать их как один
официальный финансовый отчёт.

Provenance — existing legacy core/ozon_final_archive.py,
core/ozon_current_archive.py, core/archive_refresh.py, ozon_mcp/endpoints.yaml;
локальный snapshot marketplace-review-20261028/legacy. Его source logic
переиспользована, успешные live methods Ozon не выдуманы.
Текущие official notices подтверждают актуальные версии posting/accrual methods:
https://dev.ozon.ru/news/734-Otkliuchenie-starykh-metodov-Seller-API-dlia-raboty-s-postingami/
https://dev.ozon.ru/news/699-Novye-metody-dlia-finansovykh-otchetov-v-Seller-API/
Full official schemas https://docs.ozon.ru/api/seller/ возвращают redirect-loop/
нечитаемую страницу; WB official finance docs/swagger вернули498. Поэтому
exact current method limits/schemas/eligibility НЕ объявлены VERIFIED и
MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED не включён. Копии сторонних блогов
не используются как доказательство контракта. До API требуется читаемая
официальная схема либо подтверждение WB/Ozon; исторический60s+65s сохраняется
как прежний проверенный контракт, не как новая live verification.

## Execution matrix

| Stage | Artifacts | Status now |
|---|---|---|
| synthetic | pinned root launcher + one line + result receipt | PREPARED, live NOT_EXECUTED |
| cutover | redacted evidence matrix | UNKNOWN, old accesses unchanged |
| E | exact plan3 + blocked authorization + existing loader | PREPARED, API NO-GO |
| WB2026 | durable list step + bounded manifest + revision publisher | OFFLINE TESTED, NOT DEPLOYED |
| daily | revalidation policy+planner+inert systemd templates | PREPARED, dispatch acceptance pending |
| Ozon | source-derived separate connection plan + closed method gate | PREPARED, current schemas pending |
