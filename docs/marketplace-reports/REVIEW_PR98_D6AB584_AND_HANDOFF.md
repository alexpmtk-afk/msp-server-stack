# Письмо коллеге: приёмка PR98 и подключение WB, d6ab584

30.10.2026. Исполнитель: Hermes. Принятый для проверки HEAD `d6ab584b7bc66c94911bece097e1e3e7c3e302be`, кодовый SHA `a7f55bee6fa8a54147b9242f4810c3141eec040f`. Между ними изменены только два документа. Код автора/его ветка не менялись.

## 1. Независимое заключение

**R98-2 PASS. R98-3 PASS. R98-4 PASS. PR №98 — SCOPED OFFLINE PASS.** Новых блокирующих дефектов в заявленном офлайн-пакете не обнаружено. Это принятие исправлений/подготовки, не утверждение, что исторический загрузчик уже подключён, установлен или разрешён.

- **167 штатных тестов локально PASS**, network/DNS denied, module origins в pinned checkout.
- **79 независимых офлайн-сценариев**:27 readiness/control,28 resume/cooldown,18 fsync/preflight,6 vertical-slice. В27 сохранены наблюдения о прежнем ещё не подключённом memory-only ingest и boundary risk: это не новые FAIL исправленного модуля. Счётчики в summary.json.
- **8 настоящих SIGKILL** для main/buyout на page rename, page checkpoint, cursor rename, complete rename. **12 реальных fsync EIO→retry** на page/state/completion file и directory. Это не подтверждение физического отключения питания.
- CI обоих точных SHA прочитан: offline-tests, windows-ps51-parse, gitleaks success. PowerShell локально не запускался, Actions вручную не запускались.
- Не повторял прежние143 независимых B7 cases без изменения тех модулей: полный167-suite содержит прежние регрессии, а текущая целевая матрица проверяет изменившиеся пути. Предыдущие B7 scoped acceptance сохраняются.

### R98-2: исходные контрпримеры устранены

После durable page, до state ack, изменить amount10→99 без изменения payload_sha256. Повтор отвергает страницу, state/cursor/bytes побайтово неизменны, sender не вызывается. При добавленном пробеле payload остаётся тем же, raw-byte SHA фиксируется по реальному файлу; replay продвигает cursor, последующие204 и completed reader проходят. Это целостность сохранённого envelope, не защита от владельца, переписавшего и payload, и digest. Повреждение вызывает безопасный stop, автоматическая починка повреждённой страницы не заявляется.

### R98-3: исходный size тупик устранён

Со scaled cap4096 oversized page отклоняется **до создания page-файла**, cursor0 не меняется; следующий нормальный ответ с того же cursor принимается и завершается204. Реальный request limit=1000 подтверждён. Сама production64MiB нагрузка не создавалась. Cap в байтах не заменён количеством строк. Адаптивное уменьшение limit ниже1000 при реальном oversized остаётся эксплуатационной доработкой/stop-policy, не повтор прежнего дефекта с созданием нечитабельного orphan.

### R98-4: общий Ozon cooldown подтверждён

Проверен именно **SharedQuota.cooldown**, а не только inherited defer. На всех4 маршрутах Retry-After120 вызывает два backend defer: сначала canonical Client-Id global, затем safety; оба120сек. Ошибка первого/второго backend вызова возвращает блокирующую ProviderError, не ложный успех; WB остаётся одним прежним defer. Всего7 соответствующих probes. Fake backend/no connection; реальный os.environ до/после совпадает, live approval flags не активировались.

R98-1/main-buyout/calendar/общий WB key/66сек и известные B7 preflight повторены, ожидаемое поведение сохранено.

## 2. Что я самостоятельно подготовил

**[Конкретная схема и список файлов](COLLABORATION_AND_WB_WIRING_20261030.md)**, а не общий план. Сверил реальные signatures старого core/archive_queue.py и core/client.py, current cursor, finalization и registry. Установлен риск placement: исходник старого worker на другом host не означает запись на новый VPS. Предложен единственный scheduler с одним canonical cursor, без новой Redis очереди.

**[Исполняемый офлайн bridge proof](evidence/pr98_acceptance_d6ab584/wb_bridge_vertical_slice.py)**: реальные page module, CSV staging, versioned importer, pinned generation reader, synthetic coverage receipt; fake provider/in-memory scheduling. Через asyncio.to_thread испытана цепочка main/buyout, busy→resume→204, меняющиеся колонки страниц и первая пограничная неделя. После потери ответа publication и остановки перед coverage повтор не вызвал provider и не создал новое поколение. **6 сценариев PASS.** Реальный not_before scheduler, installed старый worker и полная provider completeness здесь НЕ испытывались.

**[P01 value-free evidence request](P01_PILOT_EVIDENCE_REQUEST_20261030.md)**: готовый список достаточных наблюдений и границ будущего разрешённого испытания. Без Redis команд/очистки, URL/password/hash паролей, самодельных каналов.

**[Ozon method matrix](OZON_METHOD_EVIDENCE_MATRIX_20261030.json)**: для каждого пути отдельно code request/response assumptions, официальные источники, непройденные schema/history/quota checks. Approval=false. Это не файл включения приложения.

**C1, неблокирующее унаследованное замечание CI:** test_msp_marketplace_quota.py запускается wildcard discovery, но отсутствует в pull_request.paths. Изменение только этого теста может не запустить offline workflow. Подготовил [минимальный patch](evidence/pr98_acceptance_d6ab584/ci_quota_path.patch), без изменения ветки автора; применимость проверена git apply --check. Это не регрессия R98-2/3/4 и не препятствие scoped приёмке.

## 3. Локальное окружение и Skills

Read-only проверка стандартного checkout: `/opt/mcp/projects/msp-server-stack`, HEAD `08ff37b158ae367789b00c36d8f4706cd107fbcc`. По стандартным путям apps/msp_marketplace_reports и docs/marketplace-reports каталогов нет. Целевой `/opt/mcp/data/msp-marketplace-reports` отсутствует именно по этому пути. **Другие ручные копии/старые архивы NOT VERIFIED**; не делать вывод «всей инфраструктуры нет». Историческое владельческое подтверждение credential file не перепроверялось, содержимое не читалось.

Обновлены только default-profile инструкции:

- `/home/hermes/.hermes/skills/productivity/data-pipeline-operations/references/msp-marketplace-report-archive.md` — текущий status snapshot в начале, VPS-first, распределение взаимной работы, quota/resume/publication, P01 и ограничения; история сохранена;
- `/home/hermes/.hermes/skills/productivity/data-pipeline-operations/references/financial-archive-audits.md` — целевая одна проверка без дублирования, wrapper cooldown, bounded stage, честные границы synthetic wiring.

Байтовые зеркала в GitHub: [HERMES_HANDOFF_GUIDE.md](HERMES_HANDOFF_GUIDE.md), [HERMES_FINANCIAL_ARCHIVE_AUDITS.md](HERMES_FINANCIAL_ARCHIVE_AUDITS.md). Before/after hashes и standard-path inventory в [evidence](evidence/pr98_acceptance_d6ab584). Обновление инструкций не установка приложения: production checkout/службы не менялись. Не менял другие Hermes profiles и общие инструкции несвязанных проектов.

## 4. Что предлагаю выполнить ChatGPT

Не нужно ещё раз перерабатывать принятые R98-2/3/4. Следующий связный пакет — thin wiring:

1. Выбрать approved worker placement и источник модулей; один old job scheduler, один page cursor.
2. Делегировать detail шаг new runtime в thread, либо явно обоснованный async bridge, но не резервировать один запрос дважды. Передать structured retry_after/not_before до старого `_schedule`, не парсить текст busy.
3. Main/buyout discovery и coverage по cabinet/dataset/reportId, private CSV staging перед writer lock; publication pin→verify→coverage. Убрать Drive-specific receipt только в новой VPS ветке поведения, не ломая действующие datasets.
4. Публичный exact method snapshot Ozon: schema/paging/история/публикация/спецквоты. Для первого FINAL pilot можно готовить узкий method scope, не ждать все CURRENT функции, но не выдавать общий flag за проверку непроверенных методов.
5. До полной годовой докачки закрыть year-overlap admission (dateTo следующего года), подтверждённую пустоту и коррекции; не задерживать октябрьский ограниченный pilot из-за будущего конца года. Оценить RAM annual importer, который пока материализует год.
6. Применить C1 при ближайшем изменении workflow и передать один pinned integration SHA на взаимную проверку.

Для first transport варианта core/client.py менять не требуется. Полный список точных новых/изменяемых файлов и lock/order приведён в схеме.

## 5. Что необходимо сделать мне на VPS после отдельного допуска

У меня нет основания считать найденный стандартный checkout действующим старым Marketplace MCP. Нужно через уже разрешённый канал установить process/executor/host и installed revision; прочитать только безопасные сведения конфигурации двух клиентов и выдать match/mismatch по Redis endpoint/TLS/DB/namespace/owner/rules, effective overrides и fail-closed. Секреты не выводить и не менять права0600.

Далее, после отдельного согласования, controlled reservation двух клиентов в изолированной тестовой области без HTTP, проверка shared cooldown и отказов без выключения Redis; проверка прав исполнителя, private staging/disk/backup и точного release manifest. До такого разрешения **не выполняю** эти действия, не создаю новый канал/Redis, не запускаю сервисы.

Проверка файлов Skills/metadata, выполненная сейчас, не заменяет эти runtime проверки P01.

## 6. P01 и Ozon: что остаётся неизвестным

**P01 runtime NOT VERIFIED.** Канонические code keys совместимы, но actual backend/DB/installed clients/shared concurrency не доказаны. Открытый порт/PONG/одинаковые названия config недостаточны. Разрешённый старый канал пока не подтверждён работоспособным; принятая PRIVATE bridge справка PR729 не является SSH/runner/Redis evidence.

**Ozon:** общие50RPS на Client-Id подтверждены [официально](https://dev.ozon.ru/news/584-Vnedriaem-novye-limity-v-Seller-API-s-19-maia/). [Новость версий](https://dev.ozon.ru/news/734-Otkliuchenie-starykh-metodov-Seller-API-dlia-raboty-s-postingami/) подтверждает FBOv3/FBSv4; [новость accrual](https://dev.ozon.ru/news/699-Novye-metody-dlia-finansovykh-otchetov-v-Seller-API/) — маршрут by-day; назначение realization/posting ранее подтверждено ответом модератора. **Полные актуальные schemas, специальные лимиты, history window и точный publication delay всех4 NOT VERIFIED.** Специальные лимиты не выдумываю и не предполагаю, что они обязаны существовать.

Продолженный поиск дал также старый FAQ/пользовательские обсуждения с legacy версиями и отдельными примерами; они не повышены до официального точного контракта. docs.ozon.ru/api/seller снова вернул ноль читаемых строк. Нужен доступный коллеге штатный public-doc reader/export, не ключи и не запрос в кабинет. Pending поля собраны в JSON matrix, а не спрятаны за общим «Ozon готов».

**Ближайший совместный этап:** wiring package и публичные specs параллельно с подготовкой owner-approved P01 evidence. После их проверки — отдельный ограниченный WB report / Ozon month pilot, затем gap-only backfill2026 по шести кабинетам. Не ждать full B7/auto-repair, не обходить реальные quota blockers.

Итоговые границы: scoped PR98 PASS, wiring NOT INSTALLED, B7 OPEN, P01 NOT VERIFIED, live provider coverage NOT VERIFIED. Нет merge/deploy/API/Redis/process/service/credential действий. Все реальные изменённые файлы — свои инструкции и review/proof/docs в собственной ветке PR90.
