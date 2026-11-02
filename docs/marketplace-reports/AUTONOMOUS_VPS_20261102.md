# Автономный WB на действующем VPS — результат реализации 02.11.2026

## Решение и готовность

**Поиск старого REMOTE прекращён по новому решению владельца.** Предыдущие operator-console инструкции PR103 — история, больше не следующий шаг. Недоступность старого сервера не означает, что он выключен.

**Офлайн-кандидат WB: PASS. Установка: NOT DONE. Реальный pilot: NO-GO.** В собственной ветке подготовлен bounded deterministic executor `standalone_wb.py`, поверх принятых PR98/99/102. Использует прежние page cursor/checksums, SharedQuota, CSV conversion, B7 pinned publication и coverage. Прежние разработки и cloud-worker bridge не удалялись; старый backend/queue не копируется и не создаётся заново.

Функциональный объём нового кандидата — один явно выбранный финансовый отчёт, ограниченное продолжение в одном запуске (до8 локальных шагов, до300 секунд start/wait budget; max3 durable sender entries); не готовая автоматическая загрузка всех кабинетов/всего2026. Это минимальная вертикаль до первого проверенного отчёта, после которой существующий backfill planner даёт gap inventory для расширения.

## Что действительно есть на VPS

[Наблюдения](evidence/autonomous-20261102/vps_components.json):

- systemd; active/running gateway, msp-devexec и maintenance службы;
- active/running user Hermes durable-worker и Telegram-long-tasks worker;
- установленный код Hermes cron с script/no_agent механизмом; пользовательские MSP services/timers присутствуют. Не создавались и не запускались новые jobs;
- системный Python3.12.3 и Hermes-shell Python3.14.9. Ни в одном не найден установленный redis Python distribution;
- предыдущий подтверждённый snapshot target root/credential permissions из PR103 остаётся исходным состоянием: archive-root отсутствует, исходный secret directory закрыт root0700; повторно сканировать их без причины не требовалось.

Роли не подменяются: Telegram-worker запускает модельные задачи и доставку сообщений, не deterministic финансовый pipeline. Devexec — отдельный protected executor; возможность финансового HTTP/credential workflow через его sandbox НЕ проверена и не означает права менять capabilities. Actions runner не даёт root/admin права. Модификация этих работающих процессов для пилота не нужна.

**Повторно используем systemd как supervisor**, без нового scheduler/демона: один ручной oneshot: сам продолжает небольшой пилот между durable steps, затем exit/DONE либо paused. Long quota wait возвращает checkpoint сразу, watchdog420 секунд; `--one-step` сохранён для будущего scheduler-вызова. [Подготовлен inert unit template](deployment/autonomous-wb/msp-wb-pilot.service.in). Позже тот же CLI допускает запуск через уже существующий no_agent cron, но создание задания/расписания и runtime acceptance требуют отдельного решения. Никаких cron entries сейчас нет. [Официальная модель no-agent cron](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron).

## Реализованная цепочка

`approved exact plan → root-controlled owner authorization → existing systemd oneshot → local root-wide flock → durable attempt ledger → original WB page module → SharedQuota sender → durable page+cursor → CSV → verified B7 generation → verified coverage → DONE`

- Один root-wide lock для standalone процессов всех WB кабинетов/типов. Проверено двумя настоящими forked processes. Это не cross-host lock и не защита от произвольного стороннего/legacy writer: до API owner должен исключить такие входы.
- Единственный rrdId — существующий durable page state, не новый journal. Новое `.wb-executor/<plan-hash>.json` хранит только статус/бюджет/ожидание/pin; **не Redis job queue** и не второй отчётный реестр.
- Монотонный бюджет max3 sender entries сохраняется и fsync до factory/admission/HTTP. Запуск повторно не сбрасывает бюджет. Quota denial или crash до HTTP могут консервативно потратить entry; это не счётчик доказанных HTTP. Нельзя увеличить бюджет новым планом без нового root-controlled разрешения.
- PAGE_STAGED и typed transport failure требуют минимум66 секунд; длительный quota not-before сохраняется. Ранний повтор ничего не отправляет. Один bounded запуск не спит бесконечно: ожидание за пределами300 секунд возвращает состояние супервизору; при допустимом ожидании sleep до not-before без API polling. Один in-flight step может превысить start deadline — outer watchdog отдельный.
- Новый `TransportUnavailable` в runtime — подкласс прежнего ProviderError, без изменения endpoint/квот. Он разрешает ограниченный retry с прежнего cursor. Integrity/прочие provider errors удерживают HOLD_ERROR; автоматического снятия hold нет.
- Ledger имеет checksum и strict JSON/int validation. Повреждение блокирует, не пересоздаёт counter. При повторе существующий journal fsync повторяется, чтобы visible rename не означал преждевременную durability.
- Авария после durable page до cursor подтверждения: page replay без provider и без нового budget entry. Crash после budget до dispatch: conservatively consumed, не обещание exactly-once HTTP. Ответ, не успевший попасть в durable page, может потребовать повтор того же read; это не повтор уже сохранённой страницы.
- Terminal204 → прежние CSV/manifest/generation/coverage проверки. DONE повторно сверяет receipt/archive и не имеет права снова скачивать при утере stage. Это local verification, provider_coverage_proven=false; DONE одного документа не означает полноту2026.

## Допуск и независимость от старого сервера

CLI отказывает без root-controlled approval, совпадающего с exact plan digest, package code digest, archive root и сроком. Требуются явные owner pilot/shared-quota/conflict-exclusion attestations и reference на внешние доказательства. [Шаблон](deployment/autonomous-wb/authorization.BLOCKED.template.json) намеренно истёк и все три bool=false; не является разрешением. Expiry проверяется при начале invocation; это не аппаратный сетевой deadline уже выполняющегося шага.

Эти attestations — заявления уполномоченного оператора, не самостоятельное обнаружение выключенного REMOTE и не криптографическое доказательство. Root-controlled path/file проверяется CLI; dependency-injected Python API — тестовый/доверенный integration seam, не непреодолимая граница для администратора/произвольного Python caller.

Ни этот код, ни unit не включают `MSP_REPORTS_SHARED_QUEUE_VERIFIED`, Ozon gate или Redis configuration. ReadOnlyHTTP сохраняет прежний fail-closed. Canonical finance1req/min+safety65 и общий Client-Id cooldown не менялись.

**Разрешённые варианты следующего решения владельца:**

1. Подтвердить реально общий backend/DB/namespace и участие всех клиентов, способных обращаться от этих продавцов; либо
2. Отдельно согласовать контролируемое переключение API-доступа: через кабинет/поддержку/администратора подтвердить отзыв прежних действующих доступов и учёт всех остальных интеграций, затем утвердить единую квоту для разрешённых клиентов. Сам факт выпуска нового токена не отключает старые токены; квота WB остаётся seller-scoped.

Без одного из этих оснований API остаётся заблокированным, несмотря на работоспособный новый модуль. Нет бесконечного требования найти старый хост, но и нет ложного вывода, что новая независимая Redis-квота автоматически общая. Новый Redis server/queue/namespace не создавались; если действующий подходящий backend не найден, его выбор/подготовка — отдельное архитектурное и admin approval, не скрытая часть установки.

## Точный состав будущей установки, без выполнения

[INSTALL_MANIFEST.json](deployment/autonomous-wb/INSTALL_MANIFEST.json) фиксирует17 module files и SHA256, общий code digest, target release/root и dependency candidate. [Pinned dependency candidate](deployment/autonomous-wb/requirements.candidate.lock) — redis8.1.0 wheel с PyPI SHA256; скачан только в scratch, hash проверен, zip-import и unconnected async-client close на системном Python3.12 PASS с socket-deny. **Не установлен. Реальная совместимость backend/protocol/TLS/EVAL NOT VERIFIED**; redis8 меняет default wire protocol на RESP3 — нельзя считать source tests достаточным runtime admission. Перед owner install необходимо проверить backend compatibility; не менять controller/driver наугад. [Первичный источник redis-py](https://pypi.org/project/redis/).

Администратору после отдельного согласования:

1. Принять точный SHA, создать root-owned staging из проверенного release artifact; сверить manifest до исполнения любого installer. Не запускать root installer из hermes-writable checkout и не делать git pull в production.
2. Предлагаемая отдельная OS identity `msp-reports` (system account без shell; пока НЕ создана), без sudo/доступа к Hermes secrets. Numeric UID назначается только при approved provisioning. Существующие gateway/worker/1C/сигналы не менять.
3. Создать только `/opt/mcp/data/msp-marketplace-reports`, owner=msp-reports, mode0700, umask0077; не менять `/opt/mcp/data` целиком. Immutable release root-owned0755, приложение/venv недоступны для записи исполнителю. Установить17 модулей + pilot-plan + approved candidate dependency/venv + отрендеренный oneshot unit. Нет timer и Restart=no.
4. Сохранить `/etc/msp-marketplace-reports` root0700 и cabinets.json root0600. Proposed systemd LoadCredential предоставляет private runtime копию непривилегированному unit; это отдельное разрешение на чтение/копирование, не chmod исходного файла. Проверить metadata/runtime path совместимость loader. Для пилота отдельно согласовать минимальный набор кабинетов, если весь JSON не должен передаваться unit. Никаких credentials в argv/env/log/GitHub. [Официальный LoadCredential](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#LoadCredential=).
5. Root-controlled nonsecret approval `/etc/msp-marketplace-reports-executor/approval.json` (root-owned parent0755/file0644 без writable groups) выписывается только после квоты/conflict evidence и на точный plan/code/root/expiry. Одно локальное разрешение не заменяет vendor/Redis evidence. Нельзя копировать истёкший template как активное разрешение.
6. Проверить free-space и owner-approved capacity headroom, реальный private write/rename/fsync, page/CSV/archive verification и readback под executor identity. Проверка `--help`/fixtures не заменяет runtime/systemd/LoadCredential acceptance. Текущая выбранная unit/network configuration ещё NOT VERIFIED.
7. Резервная копия до первой смены версии и далее после подтверждённых поколений: согласованный private/encrypted backend, coherent snapshot при остановленных writers, CSV/manifests/CURRENT+цепочки+staging+execution ledger вместе, backup SHA и отдельная offline restore-проверка без API. Secret-source не добавлять в архив. Не восстанавливать старый budget journal поверх более новых attempts: restored execution держать остановленным до reconciliation/нового точного допуска. Backup target/retention/offhost copy пока не утверждены и не создавались.

## Pilot и минимальный следующий этап

План: wb_laser_master, main883801632, период19–25.10.2026 (из передачи владельца), limit1000 у прежнего модуля, **полный размер NOT VERIFIED**, max3 durable sender entries. Не выбирать buyout/другие кабинеты автоматически. Default CLI сам продолжает малый пилот с соблюдением not-before; `--one-step` оставлен для будущего существующего scheduler. Если204 не достигнут — PAUSED_BUDGET, не «отчёт загружен», бюджет без нового разрешения не увеличивать.

Проверка результата: число строк/CSV BOM и delimiter, page hashes/cursor terminal204, manifest SHA/bytes/rows, pinned generation, проверенная coverage, повтор без HTTP. Обязателен readback из реального установленного каталога.

Порядок до реального отчёта: review нового PR → owner-approved quota/conflict cutover evidence → admin provisioning/dependency+unit+credential-reader acceptance → отдельный bounded API pilot approval → explicit root-controlled authorization и approved original gate/config → один bounded pilot invocation и readback. Создание Redis/установка/flags/API сейчас НЕ разрешены и НЕ выполнены. Versioned importer всё ещё материализует годовой набор; bounded pages не доказывают bounded RAM всей годовой публикации — проверить ресурсы до массового backfill. Для следующих кабинетов/всего2026 переиспользовать backfill planner с подтверждённым discovery main+buyout, gaps/corrections и boundary weeks; перед автоматизацией расширить bounded explicit-unit admission и согласовать существующий cron/no_agent. Полной B7/Ozon ждать не требуется.

## Ozon параллельно

| Компонент | Подтверждено публично | Остаётся NOT VERIFIED |
|---|---|---|
| Общая квота | [50RPS на Client-Id по всем методам](https://dev.ozon.ru/news/584-Vnedriaem-novye-limity-v-Seller-API-s-19-maia/) | actual shared backend/owner/overrides/cooldown |
| FBO/FBS | [пути v3/fbo/list и v4/fbs/list](https://dev.ozon.ru/news/734-Otkliuchenie-starykh-metodov-Seller-API-dlia-raboty-s-postingami/) | полные актуальные schemas/pagination/периоды/глубина/спецлимиты |
| Accrual | [by-day — рекомендованная замена transaction](https://dev.ozon.ru/news/699-Novye-metody-dlia-finansovykh-otchetov-v-Seller-API/) | точный date/last_id/result контракт и ограничения |
| Realization posting | локальный реализованный year/month контракт сохранён | свежая полная официальная спецификация, глубина, лимиты/полнота финансовых видов |

Методные gates не включены. Safety5 — наша защита, не официальный per-method limit. Новый standalone относится только к WB, Ozon provider/archive modules сохранены, готовность Ozon не условие запуска WB.

## Испытания и передача коллеге

195 tests PASS =181 прежних +14 новых методов; одна и та же suite прошла на Python3.14.9 и целевом системном3.12.3, это не390 независимых тестов. Network-deny и pinned imports на собственной ветке, реальные forked writer competition и два SIGKILL checkpoint; не физическое отключение питания. [Результаты](evidence/autonomous-20261102/test_summary.json). Redis driver zip-import отдельно без сетевых команд. Runtime API/Redis/systemd-unit acceptance NOT VERIFIED.

Коллеге ChatGPT: независимо проверить новый standalone/root-controlled admission/monotonic budget и transport exception на exact SHA, совместимость17-file release, шаблон unit/LoadCredential и cutover условия. Не переоткрывать уже принятые R99-1/2 и не отправлять владельца искать старую консоль. Результаты собственного source/CI review не выдавать за runtime VPS/Redis PASS. Код находится в собственной ветке feat/hermes-autonomous-wb-pilot-20261102, не в ветке коллеги.
