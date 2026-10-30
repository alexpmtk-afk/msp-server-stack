# PR №98 — комплексная повторная проверка e6dd960

30.10.2026, Hermes. Точный SHA `e6dd9608eeb13ff6b1ec268aff86df8d6865ee82`.

## Вердикт: FAIL

**Прежние исправления приняты:** R98-1 PASS, WB canonical key PASS по исходникам, pacing 66/65 PASS, ранний отказ при известном B7 scope PASS. Новые R98-2/R98-3/R98-4 ниже требуют доработки. Код/ветка автора не менялись. Не предлагать новый большой этап B7 вместо этих ограниченных исправлений.

**161 штатный тест — локально PASS. 213 дополнительных независимых сценариев**, включая воспроизведённые дефекты, поэтому это НЕ «213 PASS». Network/DNS denied; project module origins закреплены на checkout. CI именно этого SHA независимо прочитан success: offline-tests, windows-ps51-parse, gitleaks. PowerShell локально не запускался, Actions вручную не запускались. VPS, Redis, секреты и реальные API не использовались.

| Группа | Сценариев | Наблюдение |
|---|---:|---|
| Повтор комплексной матрицы готовности | 27 | Прежние R98-1/keys/pacing устранены; старая ingest WB функция всё ещё без checkpoint, как и заявлено |
| Новые WB resume/Ozon cooldown пробы | 25 | 18 позитивных, 7 воспроизведений дефектов |
| Реальные ошибки fsync и preflight | 18 | 12 IO failure→retry + 6 ingestion families, PASS |
| Admission/path предыдущего B7 блока | 71 | PASS |
| Adapter/quarantine/concurrency предыдущего B7 блока | 68 | PASS |
| Первоначальные G1–G4 контроли | 4 | PASS |
| **Всего дополнительных** | **213** | Не число штатных unittest |

## Что подтверждено исправленным

1. **R98-1 PASS.** При новом исправном Ozon поколении dangling annual CSV и manifest дают MIXED_UNSAFE, штатный importer отказывает. Пустой старый monthly_source directory даёт LOCAL_VERIFIED, importer разрешает. Проверяются одним helper.
2. **WB shared keys — OFFLINE PASS.** Старый canonical runtime_overrides scope finance, host finance-api.wildberries.ru и rate 1 req/min теперь дают тот же catalog key, что новый request_rules. Owner SHA совпадает. Для синтетического owner suffix обеих систем catalog:8e3edef7324d018a05b2. Extra safety65 сохранён. Это не подтверждение фактической DB/installed client, P01 runtime NOT VERIFIED.
3. **66/65 PASS.** Реальный ReadOnlyHTTP с fake clock/quota/opener отправил page200 и terminal204 через 66 секунд. Ранее после 63 секунд safety65 останавливал второй запрос. Реальные sleep/network не использовались.
4. **WB нормальное продолжение PASS в выполненных случаях.** Main/buyout, две страницы, busy/429/transport, повтор без запроса на завершённом stage, проверка уже индексированных страниц. 8 настоящих SIGKILL: после page rename, после page fsync до state, после state cursor rename, после STAGED_COMPLETE rename, для обоих типов. Сохранённые страницы не скачивались повторно; при отсутствии ещё сохранённого terminal результата 204 повторяется допустимо.
5. **12 реальных fsync EIO/retry PASS.** Page temp file, page directory после rename, cursor state temp file/directory, complete state temp file/directory × два типа. После file fsync failure до rename исходная страница ещё не была сохранена, её повторный fetch допустим; после durable page повтор принимает файл без refetch.
6. **Preflight известных B7 scope PASS для 6 ingestion families.** WB main/buyout, Ozon FINAL, CURRENT FBO/FBS/accruals — fake sender не вызван. Это не полная проверка всех прав, повреждённых legacy данных или no-op coverage до HTTP.
7. **Регрессий прежних принятых B7 гарантий в выполненных контролях не обнаружено.** Полная B7 остаётся OPEN.

## R98-2 — pending page принимается с новой суммой и новым SHA

**Файл:** `apps/msp_marketplace_reports/wb_page_resume.py:107–119`, `_replay_or_advance`; запись страницы :200–213.

**Приоритет высокий, до подключения WB resume.** Нужна целостность именно в обещанном crash window, не внешний криптографический witness и не новый B7 framework.

Воспроизведение только на искусственных данных:

1. Первая страница содержит reportId555, rrdId10, reportType1, amount="10".
2. Прервать после записи page-0.json, до изменения state. State cursor остаётся0; независимый сохранённый digest этой страницы отсутствует.
3. Изменить только amount "10"→"99", сохранив валидные идентификаторы и canonical JSON. Не пересчитывать никакой существующий checksum.
4. Повтор с sender, запрещающим HTTP: модуль вычисляет SHA уже изменённого файла, принимает его и продвигает cursor10.
5. После искусственного 204 read_completed_wb_pages возвращает сумму99. State SHA совпадает с повреждёнными байтами. То есть checksum впервые создаётся после повреждения и не выявляет его.

Второй вариант той же ошибки: добавить только пробел к pending page. Replay хеширует `_canonical(payload)`, а не реальные bytes; фиксирует cursor10, затем следующая `_verify_pages` сравнивает с raw bytes и блокирует собственный результат.

**Минимальная правка:** сохранять проверяемый checksum payload вместе со страницей до ack cursor (например целостный envelope с digest). При replay проверять сохранённый digest, а не создавать доказательство из прочитанных неизвестных bytes; state raw SHA должен описывать именно реальные сохранённые bytes. Недопустимый pending file — отказ до изменения state и без refetch/blessing. Проверки amount corruption и raw/canonical mismatch добавить в тот же пакет, сохранив работающий SIGKILL replay.

## R98-3 — writer создаёт страницу, которую reader не принимает по размеру

**Файл:** `wb_page_resume.py:19, 35–43, 200–213`.

MAX_STAGE_BYTES=64MiB проверяется при чтении, но перед `_safe_write(stage_path, _canonical(page))` размер не проверяется. HTTP runtime допускает до128MiB ответа. Поэтому принятый sender payload может быть больше staging read cap; модуль запишет файл, затем сам же откажет на replay. Повтор упирается в тот же файл, cursor не продвинут, адаптивного уменьшения limit нет.

**Воспроизведено со scaled cap4096**, без реальной большой финансовой нагрузки: допустимая synthetic row даёт page5162 bytes; файл записан, parser отказывает, повтор блокируется. Это проверка того же алгоритма с уменьшенной константой; фактическую страницу64MiB/реальный VPS не испытывал.

**Минимальная правка перед большим backfill:** единый допустимый размер serialized stage, проверка до записи и возможность безопасно выбирать меньший provider page limit, не застревая на собственном файле. Ошибка не должна менять уже проверенные страницы/cursor. Для небольшого пилота bounded pages можно ограничить явно; масштабирование не требует полной переработки B7.

## R98-4 — дополнительный Ozon safety скрывает общий cooldown от старых клиентов

**Файлы:** `quota.py:101–107`, `quota.py:180–185`, `shared_rate_limit.py::GlobalRateController.defer` около :297–306.

request_rules добавляет global Client-Id key и новый msp-finance-safety. Наследованный defer выбирает `specific or normalized`, то есть при наличии safety вообще не откладывает global. Получив 429 общей квоты Client-Id, новый клиент пишет паузу только в свой safety key, неизвестный старому MCP.

**Воспроизведено на всех четырёх путях**, Retry-After120: captured deferred keys содержат только msp-finance-safety, global_key_deferred=false. Fake Redis write function, без соединения/изменения очереди. Для построения будущего разрешённого набора заменялся только локальный namespace q.os на synthetic mapping; реальный os.environ до/после совпадает, approval flags не включались.

Это новый adapter-дефект после добавления safety поверх существующего defer, а не требование менять общую WB политику. Текущие барьеры Ozon остаются выключены, поэтому live риска в этой задаче не создавалось.

**Минимальная правка до Ozon approval:** явно выбирать scope cooldown. Для общего Client-Id429 должны откладываться и общий bucket, и дополнительный safety. Например отдельные defer calls для global-only и specific-only: передать оба вместе в нынешний defer недостаточно. Пер-методный подтверждённый429 можно обрабатывать по доказанному scope; неизвестный scope не должен позволять другим интеграциям обходить общую паузу. Проверить fake backend trace, не включать флаги для испытания.

## Достаточен ли WB модуль для подключения старого исполнителя?

**Как заготовка — да; как готовый drop-in — нет.** Базовая state machine и one-page step работают, но сначала устранить R98-2 и размерный тупик. Затем нужна короткая явная интеграция, не новый scheduler:

- старый worker асинхронно вызывает call_spec и получает envelope; новый step принимает synchronous send и tuple(status,payload). Адаптер должен сохранить ошибки quota/transport, cancel/retry semantics и не блокировать async loop через вложенный asyncio.run;
- старый `_download_step` использует собственные staging/current_rrd_id. Выбрать один источник state, не два расходящихся cursor. Не запускать новый контроллер Redis jobs;
- передать известный reportId/type из discovery, поддержать main и buyout; годовая принадлежность — пересечение недели, не только год dateTo;
- передать структурированный retry delay/not-before: сейчас busy/429 дают WAITING_RATE_LIMIT без времени следующего допуска. Не делать tight loop и не угадывать delay из строки;
- после STAGED_COMPLETE преобразовать проверенные страницы в локальный staging CSV и вызвать выбранный writer. Reader generator удерживает общий lock, поэтому не захватывать тот же lock повторно из publisher при незавершённом чтении; полностью закончить CSV staging до writer lock;
- подтвердить запись поколения/CSV и manifest, только затем coverage/COMMITTED registry. STAGED_COMPLETE не опубликованный официальный архив. Уточнить повтор после потери ответа при финальном commit;
- сам `ingest.py wb-one` всё ещё вызывает старый wb_detail, а не новый page step: наблюдаемый `[0,1,0,1]` у прежней функции сохраняется. Это заявленная незавершённая интеграция, не регрессия автономного модуля.

Для автоматической истории2026 дополнительно нужен обход трёх WB inventories и reportId/type, трёх Ozon кабинетов/закрытых месяцев, реестр пропусков/исправлений/подтверждённой пустоты, сохранённый retry и stop/resume. Готовые старые координаторы использовать повторно. Не требовать full auto-repair, всех legacy readers, retention или physical power-loss до чистого fail-stop pilot.

## Четыре Ozon метода: что подтверждено официально

| Метод | Подтверждённая часть | Полная актуальная schema / special limit |
|---|---|---|
| /v3/posting/fbo/list | Официальная новость01.06.2026 перечисляет текущую версию | NOT VERIFIED / NOT VERIFIED |
| /v4/posting/fbs/list | Та же новость подтверждает текущую версию | NOT VERIFIED / NOT VERIFIED |
| /v1/finance/accrual/by-day | Официальная новость06.05.2026 указывает как новый финансовый метод | NOT VERIFIED / NOT VERIFIED |
| /v1/finance/realization/posting | Ответ официального модератора01.12.2025 подтверждает назначение для реализации предыдущего месяца; это не новая полная spec | NOT VERIFIED / NOT VERIFIED |

[Официальные версии FBO/FBS](https://dev.ozon.ru/news/734-Otkliuchenie-starykh-metodov-Seller-API-dlia-raboty-s-postingami/), [официальный переход к accrual](https://dev.ozon.ru/news/699-Novye-metody-dlia-finansovykh-otchetov-v-Seller-API/), [ответ о реализации](https://dev.ozon.ru/community/1809-API-metod-dlia-fakticheskikh-vykupov/).

Ни для одного из четырёх **отдельный специальный лимит не подтверждён**; это не утверждение, что лимит существует или что его нужно придумать. [Официальный общий предел50RPS на Client-Id](https://dev.ozon.ru/news/584-Vnedriaem-novye-limity-v-Seller-API-s-19-maia/) и [правило для методов без персонального лимита](https://dev.ozon.ru/community/2373-HTTP-429-na-finansovykh-metodakh-Seller-API-pri-redkikh-zaprosakh/) подтверждены. 5sec — дополнительный собственный pacing, не Ozon special limit. Имеющийся old catalog — источник проверенного code contract, не текущая официальная спецификация.

docs.ozon.ru/api/seller снова не вернул читаемых строк этому reader. Минимально нужно получить публичный snapshot каждой нужной method schema через доступный коллеге штатный канал: inputs, limits, items/cursor/terminator, доступный historical range и отсутствие/наличие специальной квоты. Не нужны токены или кабинет, для пилота одного OzonFINAL не обязательно ждать готовности всех CURRENT feeds: можно отдельно согласовать его узкий допуск, но нынешний общий flag не считать per-method proof.

## Что осталось по реальному P01 до разрешённого пилота

1. Через отдельно разрешённый исполнитель подтвердить конечный сервер и точные действующие client/catalog versions. Старый GitHub source не доказывает installed version.
2. На двух системах локально сравнить endpoint/TLS/CA/DB/namespace, effective RPS overrides и mandatory fail-closed. Выдать match/mismatch без реквизитов.
3. По каждому участвующему продавцу сравнить owner/key scopes и подключённые интеграции; local hostnames/display cabinet не заменяют sid/Client-Id. Перепроверить общую отсрочку429 после R98-4.
4. Проверить доступность/авторизацию и контролируемую конкуренцию admission двух клиентов в отдельно разрешённой тестовой области без HTTP, не чистя рабочие buckets; Redis outage запрещает запросы. TCP/PONG недостаточно.
5. Подтвердить права разрешённого процесса к root-protected credentials и staging/disk/backup без ослабления0600; утвердить точный SHA и один ограниченный pilot. Здесь всё перечисленное **NOT VERIFIED**, не выполнялось.

**Короткий следующий шаг:** автор исправляет R98-2/3/4 одним целевым пакетом, параллельно готовит thin worker/writer adapter и публичные Ozon specs. Hermes проверяет новый SHA. Никакой новой очереди, установки или расширения B7 ради этих ошибок. Блокеры остаются кодовыми и внешними, не разрешительными предположениями.

## Артефакты

[evidence/pr98_recheck_e6dd960](evidence/pr98_recheck_e6dd960): исходники независимых scripts, captured JSONL, штатный лог, summary. Scripts принимают --checkout; readiness_regressions.py также --legacy старого0510a409; run_stock.py принимает checkout позиционно. Только искусственные суммы/ID/файлы. Вызовы настоящего Redis/HTTP исключены audit hook и fake backends. Чужая ветка clean, изменения reviewer — только docs/evidence/HANDOFF/PROJECT/Skill.
