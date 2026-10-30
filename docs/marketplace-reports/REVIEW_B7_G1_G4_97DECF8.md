# B7 — повторная независимая проверка G1–G4, 97decf8

Hermes, 29.10.2026. Точный PR №95 commit `97decf831a2499d1dc0d4d93395a46a1626cbaaa`, старый baseline `0217ba4edd2503a0998d7bae531873e4bb1a6f9c`. Открытый head совпадает; merge/deploy отсутствуют. Код и ветка коллеги не менялись.

## Заключение

| Замечание | Статус | Что реально подтверждено |
|---|---|---|
| G1 | **PASS** | Полный staged candidate до commit не читается публично даже с его настоящим SHA; active остаётся прежним |
| G2 | **PASS** | Потеря CURRENT после двух commits — UNKNOWN_COMMIT_STATE; нет ложного списка uncommitted; новые записи блокируются |
| G3 | **PASS** | Перепаковка старого parent при неизменном trusted CURRENT/child обнаружена; прежний и заново вычисленный подложный pin отвергаются |
| G4 | **FAIL** | Нормальная первая публикация теперь синхронизирует предков, но успешный повтор после отказа/SIGKILL инициализации пропускает ранее не завершённый parent fsync |

Общий первый блок остаётся **FAIL** до исправления G4-R1 ниже; полная B7 **OPEN**. Физическое отключение питания **NOT VERIFIED**, его последствия не симулируются как установленный факт. Три закрытых замечания не переоткрываются из-за оставшегося G4.

## Испытания и доказательства

- **89 stock tests PASS** в отдельном точном checkout; все импортированные apps.msp_marketplace_reports.* разрешились внутри него. Network/DNS запрещены audit hook. GitHub check-runs точного коммита прочитаны completed/success offline-tests, windows-ps51-parse и gitleaks; локальный PS5.1 и ручные Actions не запускались.
- Все **4 исходных контрпримера before/after** повторены на старой и новой реализации (8 сравнительных records). Первоначальный G4 normal-parent trace теперь исправлен: было 5 пропущенных parent-sync, стало 0.
- **24 отрицательных варианта pin**: для current и committed ancestor — отсутствие аргумента, None/bool/int/float/bytes, пустой/неверной длины/не-hex/uppercase и неправильный SHA. Корректные pinned reads обоих поколений также прошли.
- **8 вариантов CURRENT**: отсутствие, оборванный JSON, null, дубли ключей, schema bool, неверный формат digest, неизвестный generation ID, неправильный digest. Public read и публикация отказывают, reconcile возвращает UNKNOWN/RECOVERY_REQUIRED; bytes всех файлов после отказа неизменны. Неизвестный ID может дать FileNotFoundError на direct read — это fail-closed, не новый успех и не обход.
- **13 отказов os.fsync** — каждый вызов в update после трёх успешных публикаций; старые generation bytes сохранены, active всегда целиком старый/новый. Это не тест всех IO errno и не всех форматов.
- **32 реальных SIGKILL checkpoint случая**: WB/Ozon (два месяца+annual), первый импорт/обновление, каждый declared checkpoint до/после commit. До commit старое активное поколение сохраняется; для первой попытки с оставшейся generation evidence корректно UNKNOWN_COMMIT_STATE. После commit новое поколение ACTIVE_VERIFIED. Это не power-loss тест.
- **5 parent-sync failure→retry контрпримеров**, **1 новый год после трёх commits**, **1 дополнительный настоящий SIGKILL во время инициализации→retry** — все выявили G4-R1. Инициализационный kill отдельно от 32 checkpoint kills.

Не суммировать регрессионные before/after records и counterexamples в «всё PASS». Числа каждого набора отражены в [результатах](evidence/b7_97decf8_results.jsonl). [Harness](evidence/b7_g1g4_review.py), [stock runner](evidence/b7_97decf8_run_stock.py), [stock stdout](evidence/b7_97decf8_stock_tests.txt).

## G4-R1 — незавершённая синхронизация не возобновляется после ошибки/смерти процесса

**Файл:** `apps/msp_marketplace_reports/generation_store.py:284`, `_ensure_scope_durable`, особенно строки 289–298. `while not current.exists()` считает оставшийся каталог достаточным основанием прекратить обход; publish после повторного запуска может вернуть COMMITTED без ранее проваленного fsync родителя.

### Минимальный воспроизводимый сценарий

1. В scratch выбрать ещё не существующий `root = test_directory / "archive"`.
2. При первой публикации перехватить `_sync_dir(root.parent)` и выбросить OSError. К этому моменту `root.mkdir()` уже завершился; каталог остаётся. CURRENT ещё нет.
3. Снять инъекцию, записывать все дальнейшие `_sync_dir` и повторить публикацию.
4. Реальный результат: `status=COMMITTED`, но `root.parent` больше не синхронизировался. Первоначально не закреплённое имя root оставлено без успешного повторного parent-sync.

В harness это сделано для пяти уровней: root, .b7-generations, dataset, cabinet, year/scope. Во всех пяти `previously_failed_parent_retried=false`, `retry_status=COMMITTED`.

Отдельно: после трёх успешных commits 2026 создать scope 2027; отказать на sync его содержащего cabinet directory после mkdir(2027); повтор получает COMMITTED без повторного sync cabinet directory. Старый 2026 остаётся неизменным. Значит проблема не ограничена совсем пустым хранилищем.

Отдельный дочерний процесс действительно убит SIGKILL **после mkdir(root), до parent sync**, затем выполнен повтор в другом процессе (родительском harness). Результат тот же: COMMITTED и пропущенный parent sync. Это не только exception/finally артефакт.

### Почему это ошибка

Наличие имени в page cache после mkdir/отказа/смерти процесса не является доказательством его durability. Повторный запуск не знает, был ли sync этого имени успешен. Нормальный first-run trace исправлен, но протокол не идемпотентен на стадии инициализации. Аналогичное окно есть при смерти между mkdir и fsync без зарегистрированного исключения.

Мы доказали пропуск требуемого шага после сбоя, **не фактическую потерю файлов при отключении питания**. Даже если FS incidental journaling случайно сохранит эти каталоги, код не обеспечивает заявленный порядок фиксации.

### Способ исправления

Сделать durable initialization возобновляемой: синхронизировать требуемые parent/name связи от явно заданного доверенного existing anchor до scope/generations и при наличии каталогов, если нет durable доказательства завершённой инициализации. Простое `exists()` не такое доказательство. Альтернатива — явный durable initializer/state protocol, но маркер также требует корректного порядка sync; нельзя записать «готово» раньше закрепления предков.

Добавить regressions failure→retry и SIGKILL→retry на каждом уровне инициализации, а не только «первая попытка не вернула commit». Проверять успешную повторную синхронизацию ранее проваленного содержащего каталога ДО нового COMMITTED. Новый cabinet/year после успешной истории обязателен. Исправление остаётся за разработчиком; своей версии generation_store.py не создавал.

## Граница функций чтения и гарантий

Публичные read_active/read_generation проверены как committed readers. Private `_read_generation` по-прежнему может валидировать и вернуть staged bytes: это нужно самому publish до commit и **не считается обходом публичного контракта**, пока функция остаётся private и не подключена как финансовый reader/restore source. В harness это явно показано, чтобы не смешивать integrity validation и commit proof.

При намеренной ручной перезаписи доверенного CURRENT возникает другой threat model: новый CURRENT сам является точкой публикации, SHA не является подписью/секретной capability. Не утверждаем защиту от владельца, способного переписать весь store и trust anchors. Проверенный G3 контрпример оставляет trusted child/CURRENT неизменными и теперь блокируется.

Новый read_generation зависит от действующего CURRENT и проверяемой цепочки; при потере CURRENT даже известный старый pin не является отдельной автоматической restore-командой. Это ожидаемый fail-closed до будущего явного recovery, не новая регрессия G1.

## Рекомендации к следующему блоку

1. Сначала исправить G4-R1 и передать точный новый SHA на review. Текущий узкий FAIL не разрешает интеграцию на VPS.
2. Сохранить разделение candidate/committed APIs, UNKNOWN состояния и hash-bound parent links. Не ослаблять их для обхода ошибок legacy/recovery.
3. Для миграции/обычного импорта читать единый committed snapshot, собирать полный scope и публиковать с CAS; после конфликта перечитывать, не терять старые Ozon месяцы. Все внешние readers и verify должны получить единый snapshot-контракт.
4. Recovery явное и crash-idempotent под lock/CAS; не выбирает по mtime/UUID, не пересчитывает hash повреждённого CSV и не удаляет unknown evidence. Retention предков требует отдельного anchor/checkpoint дизайна: удаление ancestor сейчас закономерно ломает проверку всей lineage.
5. Power-loss, FS-specific durability, полная F01–F24, migration/restore/retention остаются NOT VERIFIED/OPEN. Старые тесты 0217ba4 — исторические, их успешные counts не выдавать за повторённые на этом SHA.

Реальные API, Redis, credentials и работающие службы не затрагивались. Нет merge/deploy/Actions execution/нового канала. P01 NOT VERIFIED, download block сохранён. Только собственный review/evidence/Skill и ответ разработчику в GitHub.
