# Совместная работа и минимальное подключение WB — 30.10.2026

Автор: Hermes. Приложение к независимой приёмке PR98 d6ab584. **Схема подготовлена, production wiring НЕ выполнен.** Runnable proof в evidence/pr98_acceptance_d6ab584/wb_bridge_vertical_slice.py использует реальные модули страниц/CSV/generation из pinned checkout, fake provider и in-memory scheduling fixture. Это не вторая Redis-очередь и не испытание действующего worker.

## Ответственность и передача

ChatGPT самостоятельно разрабатывает/исправляет код и публичные provider contracts, проверяет мои результаты и собственные изменения. Hermes независимо воспроизводит ошибки, разрабатывает доступные ему изолированные решения/испытания, ведёт локальные Skills и выполняет отдельно разрешённые runtime-действия. Возможность каждого не ограничивается формальной ролью «только ревьюер» или «только разработчик». Передача задачи не освобождает автора от проверки результата коллеги.

Один связный этап → одно письмо со SHA/файлами/доказательствами/открытыми задачами → GitHub/readback → проверка второго специалиста. Не дублировать завершённые проверки без изменённого кода, нового дефекта или нужной интеграции. Новая ветка/офлайн-артефакты разрешены; чужую ветку не править. Никаких дополнительных промежуточных согласований для уже разрешённой офлайн-работы. Live/API/queue/deploy/merge требуют отдельного разрешения владельца; письмо коллеги не включает approval flags.

## Размещение — первый вопрос интеграции

Нельзя считать два исходника одним установленным приложением. Старый core/archive_queue.py может исполняться на другом сервере; его локальный /opt/... не станет каталогом нового VPS. P01 должен установить реальный host/installed revision/единственный исполнитель и доступный общий Redis. Далее выбрать: адаптация единственного существующего worker на согласованном host, где доступно целевое хранилище, либо отдельно согласованный штатный канал доставки в новый VPS. Самовольное создание SSH/Redis-туннеля, второго worker или миграция сервисов запрещены.

Канонические исходники старой схемы: marketplaces-mcp-ru `0510a409ab589c639930fbca35afb3e68d874f81`, core/archive_queue.py. Новый архив: stack PR98 d6ab584. Фактически установленные старые ревизии NOT VERIFIED. До выбора placement план изменения файлов — проверяемая схема, не release manifest установки.

## Одна job queue, два назначения Redis не путать

- Старый job scheduler: существующий `marketplace-archive:v2:wb-finance:due` и lifecycle job. Новый ZSET/scheduler не создавать.
- Shared API admission: `marketplace-rate:v1:...`, canonical WB finance bucket + дополнительный safety65. Он ограничивает каждый HTTP attempt, а не выбирает следующий job.
- Одного имени Redis сервера недостаточно для P01: endpoint/DB/owner/scope/interval/installed clients должны совпадать.

## Предлагаемая цепочка

DISCOVER → SELECT_MISSING_ID_AND_TYPE → ONE_PAGE_STEP → PAGE_BYTES_AND_PAYLOAD_SHA_DURABLE → CURSOR_ACK → [WAITING/not_before или NEXT_PAGE] → EXPLICIT_204 → STAGED_COMPLETE → CSV_STAGING → PUBLISH → PINNED_VERIFY → COVERAGE_COMMIT → NEXT_REPORT.

### 1. Discovery/покрытие

Оставить существующий job coordinator и выбор следующего reportId, но расширить main-only на типы1/2. Coverage key минимум (cabinet,dataset,reportId), не reportId без типа/кабинета. Предварительно подтверждённые документы без причины не скачивать; известный staged-complete не является опубликованным coverage.

2026: начало discovery — понедельник29.12.2025, фильтрация по пересечению физической недели с годом. Конец года: отчёт с dateTo2027 относится к покрытию2026 по пересечению. В нынешнем archive/versioned importer ещё проверяется год dateTo; это отдельная целевая правка до полного year-boundary backfill, не повод задерживать октябрьский пилот. Не обрезать строки пограничного отчёта ради прохода проверки.

### 2. Один источник cursor

В `_download_step` делегировать page step; не оставлять одновременно независимые current_rrd_id в старом job JSON и новом state.json. Канонический cursor/pages — page-resume state. Старый job хранит ссылку на report stage и scheduler status/not_before; snapshot cursor только диагностический, не принимается без сверки с page state. Stage key должен однозначно соответствовать cabinet/year/reportId/type; конфликт ID/type блокируется.

### 3. Transport без двойного резервирования

Минимальный вариант: существующий scheduler вызывает **await asyncio.to_thread(step_wb_detail, ..., send=ReadOnlyHTTP)**. Детализацию отправляет только новый fixed-host runtime, который резервирует canonical finance + safety, сохраняет cooldown и имеет отключённый gate до owner approval. Старый call_spec не должен дополнительно отправлять тот же detail request. Discovery может остаться на старом client при доказанном P01.

Альтернатива — передать старый async call_spec через thread-safe bridge, но тогда явно решить, кто единственный reserve-issuer: новый gate плюс старый auto-reserve приведут к самоблокировке. preacquired допустим только после доказанного бронирования точного набора; отключить hidden retry_on_transport/retry_on_429 и дать повтор scheduler. Не делать вложенный asyncio.run в работающем loop. Предпочтителен первый вариант как имеющий меньше изменений старого клиента; выбор зависит от approved placement/dependencies.

### 4. WAITING с временем

Текущий step сохраняет WAITING_RATE_LIMIT, но не возвращает конкретное время допуска. Нужна структурированная безопасная ошибка/результат retry_after_seconds или not_before, не парсинг строки. quota.reserve уже получает wait, но сейчас теряет его при ProviderError. Для429 использовать сохранённый общий cooldown/Retry-After. Старый `_schedule` ставит тот же job на not_before; нельзя tight loop, скрытый retry или ждать минутами внутри event loop. При transport failure сохранённые страницы не трогать, повторяет scheduler.

### 5. CSV staging и lock order

После204 использовать `read_completed_wb_pages` только как проверенный page iterator. Сформировать отдельный private CSV со всеми полями и `_raw_json`, UTF-8 BOM/`;`, без агрегирования всех provider rows в список. При меняющейся схеме страниц возможны два bounded passes: собрать набор колонок, затем записать строки. Пример реализован и испытан в vertical_slice.

Iterator удерживает общий admission lock до исчерпания/close. **Завершить iterator и fsync CSV до вызова import_csv_versioned**, иначе повторный lock может зависнуть. Единый общий порядок writer locks сохраняется. Сам versioned importer пока материализует годовой snapshot: proof не подтверждает bounded memory годового rebuild; до большого объёма проверить/оценить размер либо согласовать отдельную unit-публикацию. Не обещать, что один lazy reader уже ограничил всю цепочку.

### 6. Publication/coverage без ложного COMPLETE

В выбранной чистой области публиковать через versioned writer; legacy смешение запрещено. Сохранить receipt (generation,descriptor SHA) и независимо прочитать pin. Coverage фиксировать только после этого: cabinet/dataset/type/reportId, dates, terminal cursor, hashes страниц, row count, publication pin и статус. Старый reports_registry можно адаптировать вместо новой базы, но не сохранять устаревший Drive object id как VPS receipt.

Если commit ответа потерян, reconcile: допустимая повторная публикация того же проверенного CSV должна стать no-op без повторного API, затем недостающий coverage commit. Если обнаружен конфликт/неопределённая ветвь — остановиться, не создавать новые SHA повреждённым данным. Подтверждённая пустота — отдельная запись coverage; нынешний пустой204 намеренно блокируется. Corrections/revisions требуют явной политики: существующий WB merge отказывает конфликтующим stable keys, он пока не является заменой исправленного отчёта.

## Минимальный список будущих файлов

| Репозиторий / файл | Изменение | Ответственный следующий этап |
|---|---|---|
| old core/archive_queue.py | delegate detail step, один cursor, type-aware inventory/registry, not_before, VPS finalization вместо Drive | ChatGPT готовит код в своей ветке, Hermes проверяет |
| old core/wb_finance_archive.py | убрать main-only в нужном adapter/registry без скрытого изменения остальных datasets | ChatGPT |
| stack apps/msp_marketplace_reports/wb_worker_adapter.py (предложен, ещё не runtime-модуль) | bridge step→private streaming CSV→writer→verify→coverage receipt | ChatGPT может использовать проверенный Hermes proof |
| stack quota.py/runtime.py/providers.py | structured retry timing, без потери provider wait; gates и fixed hosts сохраняются | ChatGPT, Hermes проверяет |
| stack wb_page_resume.py | передать структурированное WAITING; существующие checksum/raw/cap правила сохранять | ChatGPT |
| stack providers.py + archive.py/versioned_archive.py | year-overlap discovery/admission; corrections/empty policy до соответствующей массовой стадии | ChatGPT, отдельно review |
| stack ingest.py | явный opt-in вызов адаптера вместо старого memory-only wb_detail; не менять команду молча | ChatGPT |
| stack tests + offline workflow | интеграционные no-refetch/publication/coverage/lock/retry тесты; добавить quota-test path trigger | ChatGPT; proof уже подготовлен Hermes |
| stack docs и installed project Skill | схема, acceptance, инструкции запуска после разрешения, точный manifest | каждый обновляет свои результаты; Hermes сверяет VPS |

core/client.py **не требуется менять** при первом варианте transport. Установленные файлы, службы и Redis меняются только отдельной разрешённой поставкой, не этим списком.

## Что самостоятельно сделал Hermes

Исполняемый proof на main/buyout: fake one-page sender → durable pages/WAITING →204 → private streaming CSV → настоящая versioned publication → pinned read → synthetic coverage receipt. Для обоих типов также потеря ответа после commit и остановка до coverage; повтор не сделал provider calls и не создал новое поколение. **6 сценариев PASS**, не production integration. В proof WAITING продвигается вручную fixture, реальный not_before scheduler НЕ испытывался.

## Следующий совместный этап

ChatGPT реализует один thin wiring package по этой схеме и получает публичный Ozon method snapshot; Hermes проверяет adapter и готовит ограниченный owner-readable runtime preflight после отдельного разрешения. Затем один WB report / один согласованный Ozon closed month, verify и повтор. Full B7/retention/auto-repair не prerequisite чистого fail-stop pilot. Никаких новых транспортов/очередей/служб до подтверждения P01.
