# Решения и открытые вопросы — 28.10.2026

## Зафиксировано владельцем
- Новая система работает на VPS МСП, хранит архив локально, без обязательной авторизации Google Drive.
- Первоначально собрать 2026 год по каждому зарегистрированному WB/Ozon кабинету.
- Дальнейшее обновление по запросу; расписание решается позднее.
- ChatGPT и Hermes работают с общим GitHub-источником по существующему согласованному регламенту.
- Пока Hermes недоступен по лимитам, ChatGPT выполняет доступные ему задачи.

## Инженерные решения для подготовительного PR
- Независимое приложение, а не замена действующего Marketplaces MCP.
- CSV UTF-8 BOM и `;`, без изменения бизнес-смысла.
- Шесть стабильных идентификаторов.
- Подозрительные ключи строк/конфликты блокируют импорт, не стирая существующий CSV.
- Каждая версия имеет SHA256, число строк, старые версии резервируются.
- `LOCAL_VERIFIED` означает локальную целостность, а не историческую полноту поставщика.
- Токены не попадают ни в этот проект, ни в лог, ни в чат.

## Открыто до боевой загрузки
- Реальное место на диске и права на папки VPS.
- Действительность текущих WB/Ozon токенов по каждому кабинету, на сервере без вывода значений.
- Итоговые контракты API и квоты на конец октября 2026.
- Принцип закрытых месяцев Ozon: перепроверять старые отчёты по окну корректировок или целиком по регламенту — согласовать по API после испытаний.
- Источник первичного переноса: проверенные старые файлы Drive или исключительно API.
- Глубина резервирования и отдельный носитель.
- Автоматическое расписание: не включено.

## Неприкосновенность
Без отдельного согласования не сливать PR, не разворачивать на VPS, не перезапускать сервисы и не затрагивать текущие отчёты, 1С, Битрикс, Гермес, сигналы или базы МСП.

## Подтверждение владельца 28.10
Токены всех шести кабинетов **имеются**. Их нахождение непосредственно на новом VPS и фактический доступ ещё НЕ подтверждены. Создавать новые ключи без необходимости не нужно. Нельзя утверждать, что пробные запросы выполнены до реального серверного испытания.

## Где находятся ключи — уточнение владельца
Все токены находятся **локально на компьютере владельца**, на новом VPS их нет. Это значит: `credential-status` на VPS пока не может подтвердить наличие, а API-загрузки запускать рано. Для передачи подготовлен отдельный безопасный протокол `CREDENTIAL_TRANSFER.md`, без помещения секретов в чат/GitHub и без записи открытого промежуточного файла на Windows. Передача не выполнялась.

## Обособленное защищённое хранилище для ключей (28.10.2026)
- Диагностика VPS: `/opt/mcp/secrets` — `hermes:hermes 0700`, а рабочий каталог будущего архива внутри него — `root:root 0700`. Приёмник отказал с `ERROR=secrets parent directory unsafe` (это штатная защита).
- Не менять владельца/права `/opt/mcp/secrets`, чтобы не ломать Hermes. Новый корневой защищённый каталог выбрали в `/etc/msp-marketplace-reports/` (root:root 0700), файл `cabinets.json` (root:root 0600). Выбор касается только новой системы.
- Перед вводом секретов перенести обновлённую программу приёмника, проверить её контрольную сумму и выполнить `--check`. Для последующего чтения из непривилегированного процесса требуется отдельно согласовать ограниченную сервисную учётную запись/группу или изолированный секретный процесс.

## Решение после живой проверки WB 28.10.2026
- Фактически подтверждено: четыре отчёта типа 1 и четыре типа 2 за 01–25.10.2026 кабинета WB Лазер-Мастер. Типы относятся к разным финансовым документам, не дубликаты.
- Новый архив содержит оба вида WB: `wb_weekly_finance_main` и `wb_weekly_finance_buyout` в разных каталогах, без автоматического сложения денежных показателей. Реестр `reportId` — источник контроля полноты за период, детализация — по каждому номеру до завершения постраничного обхода.
- Ни один тест API из этого цикла не изменял данные в кабинетах. Автоматическая загрузка на VPS не включена.

## Критический допуск по лимитам — 28.10.2026
- До массовой и даже пробной автоматической загрузки отчётов восстановить строгий регламент общей очереди WB/Ozon из старого сервиса `alexpmtk-afk/marketplaces-mcp-ru`: пер-методные лимиты WB на продавца, общий и пер-методные лимиты Ozon на Client-Id, атомарная очередь всех вызовов (включая повтор и каждую страницу), паузы 429 из заголовков, отсутствие запросов при сбое очереди, безопасность параллельного запуска, контроль и сохранение прогресса.
- Текущие локальные интервалы 63 секунд для WB и 5 секунд для Ozon сами по себе недостаточны и **не допускают запуск**. До проверки контроллера сетевой транспорт временно заблокирован (fail closed) в ветке PR #89. Сама загрузка файлов кода и офлайн-тесты допустимы и не обращаются к площадкам.

## Решение по повреждённым локальным документам — 29.10.2026 (проект PR #91)
- Нельзя ни объединять, ни заменять, ни повторно удостоверять старый CSV без подтверждения исходного SHA256, числа строк, размера, идентичности, версии схемы и статуса в manifest. Проверка распространяется на **все зависимости** Ozon FINAL (месячные источники и годовой снимок), до первого изменения файла/резервной версии.
- Сиротский CSV или manifest, несогласованность месячных исходников и годового снимка блокируют новую запись, не замещаются молчаливой пересборкой.
- Статус только `OFFLINE_PASS` до независимого подтверждения Hermes; код в открытом PR №91, не в main и не на VPS. Даже при успешной проверке R1/R2 многофайловая атомарная публикация/восстановление после аварии B7 **не реализованы** и требуют отдельного проекта; отложенный доступ API не меняется.

## 29.10.2026 — строгая числовая типизация manifest (R3, PR #91)

- `schema`, `rows`, `bytes` всегда JSON **integer** (не boolean `true/false`, не floating-point `1.0`, не строка). Даже если значение численно равно ожидаемому, другой тип отклоняется до публикации, чтобы не скрывать повреждение контрольного документа. `bool` в Python требует явного исключения, поскольку `True == 1`.
- Решение реализовано и протестировано офлайн в PR №91; независимое заключение Hermes по R3 **ещё ожидается**. Ранее подтверждённые R1/R2 — отдельный PASS. Слияние, установка и реальные API-вызовы не разрешены.
- B7 — отдельное обязательное условие эксплуатации: сохранять согласованность нескольких файлов/поколений и доказуемое восстановление после аварии. Строгая отказная проверка R3 **не заменяет** многофайловое восстановление; ни при каких обстоятельствах не «чинить» старые данные слепым пересчётом SHA.

## ACTIVE — автономный VPS, решение владельца 02.11.2026

Доступ к старому REMOTE потерян; поиск и просьбы старой консоли прекращены. Исторические operator инструкции ниже superseded, если нет нового подтверждённого доступа. Это не доказательство old shutdown. Новый этап AUTONOMOUS_VPS_20261102.md, branch feat/hermes-autonomous-wb-pilot-20261102, reuse PR98/99/102/103. standalone_wb one-shot под существующим systemd, без второго scheduler/daemon/Redis job queue; future existing cron no_agent только по отдельному решению. Новый root-wide local flock, checksum ledger с monotonic max3 send entries (не proven HTTP count), persisted not-before, typed transport retry, page replay и B7 coverage. 195 tests PASS на3.14.9 и3.12.3, включая2 SIGKILL и2 concurrent processes; не Redis/API/systemd runtime acceptance. Redis8.1.0 wheel — hash-pinned dependency candidate, zip-import smoke без установки, compatibility с actual backend NOT VERIFIED.

Реальный pilot NO-GO до owner/shared-quota/conflict-exclusion evidence. Root-controlled authorization bound to plan/code/root/expiry — operator attestation, не independent proof old server stopped. Оригинальные gates не включаются кодом. Не создавать Redis автоматически; потеря доступа/новый token не отзывают старые. Proposed dedicated user/private target0700/LoadCredential/immutable release/oneshot template — только owner-approved provisioning plan, не installed. Старые службы/secret permissions не менять. Все существенные результаты/манфесты в GitHub, строгий review коллегой прежде runtime.


## Ozon closed months — 2026-11-10

Owner requested January–October 2026 for all three legal entities; WB current month paused. Fixed one-month Dmitrieva January Ozon FINAL pilot prepared, 12 network-denied tests PASS. No authenticated Ozon request/activation has occurred. Root execution remains the technical prerequisite, not missing authorization/keys. Reuses accepted executor and shared Redis; no broad four-method gate or new scheduler. Exact artifacts and acceptance: `ops/ozon-final-pilot-20261110/STATUS.md`. Pilot is not annual publication or complete Ozon expense coverage.


## Preflight correction — 11 November 2026

Owner ran the pinned launcher: snapshot `/var/lib/msp-ozon-final._6rkj4nr`, preflight line111 HOLD before any executor start/state/admission. Root console frames establish erroneous whole-receipt SHA comparison. The accepted supervisor compares receipt.probe_sha256 (probe program origin), then exact typed acceptance fields. Fixed Ozon verifier to reproduce that contract, reject duplicate keys/wrong origin/failed results/type-confused values, and require active existing Redis. No new synthetic writes or backend/credential permission changes. 13 network-denied tests PASS. Revised bundle/launcher prepared, NOT root-executed; old preflight failure is not a provider error or consumed send entry. Preserve old snapshot; same January cabinet/plan and max1 budget.
