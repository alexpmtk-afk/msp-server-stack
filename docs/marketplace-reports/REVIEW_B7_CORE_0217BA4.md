# B7 — независимая ревизия первого generation core

Hermes, 29.10.2026. Точный PR №95 commit `0217ba4edd2503a0998d7bae531873e4bb1a6f9c`, baseline R3 `2f1c9427e4245e9af452bcce063c85215016cbbf`. PR открыт, не слит, head подтверждён. Чужая ветка/код не менялись.

## Заключение: первый программный блок — FAIL

Основа перспективна: полный payload, проверенный descriptor и атомарный pointer дают согласованное opt-in чтение; lock/CAS действительно предотвращают проверенную конкурирующую запись. Но публичное чтение старых поколений и классификация commit evidence пока не удовлетворяют заявленному контракту. G1–G4 ниже требуют доработки/явного ограничения до принятия core. Это **не отказ из-за ещё не написанной legacy integration или automatic recovery**: они честно обозначены как будущая работа. Полная B7 остаётся OPEN.

## Реальные испытания

| Проверка | Результат |
|---|---|
| Штатные tests в отдельном checkout, module origins внутри него, сеть запрещена | 82 PASS |
| Exception на каждом предусмотренном checkpoint: WB и Ozon (2 месяца+annual), первый импорт и обновление | 32 случая PASS: active old до commit, new после; старые generation bytes неизменны |
| Тот же набор в отдельных дочерних процессах с настоящим SIGKILL | 32 случая PASS, fresh parent reads/reconcile, не monkeypatch exception |
| OSError на каждом os.replace в нормальном WB update | 4 точки: отказ/uncertain, активный набор целиком old или new; старый pinned snapshot сохранён |
| OSError на каждом os.fsync в том же WB update | 10 точек: то же; это syscall fault injection, не power-loss |
| Два отдельных процесса-писателя с одним expected parent | Один успешно публикует, другой stale отклонён; lost update в этом тесте нет |
| Reader при удержанном writer и переключении CURRENT, Ozon | 40 reads: только целые old/new payloads, смесь не обнаружена |
| Неверные имена/paths и schema/JSON corruption в CURRENT, descriptor, payload manifest | 21 отрицательный сценарий fail-closed; reconciliation не меняет bytes архива |
| GitHub check-runs точного SHA | Прочитаны success offline-tests/windows-ps51-parse/gitleaks; сами Actions не запускались |

[Harness](evidence/b7_independent_review.py), [результаты](evidence/b7_0217ba4_results.jsonl), [stock runner](evidence/b7_run_stock.py), [stock stdout](evidence/b7_0217ba4_stock_tests.txt). Временные fixtures — scratch; исходные кабинеты/финансовые отчёты/credentials не используются. Harness `--checkout /path/to/pinned-checkout`, импортирует fixture builders tests именно этой копии; собственные проверки независимы от штатных assertions. Connect и DNS запрещены audit hook также в дочерних процессах.

## G1 — публичное чтение неопубликованного поколения (HIGH)

**Файл:** `apps/msp_marketplace_reports/generation_store.py:235`, `read_generation` → `_read_generation` без проверки committed evidence.

Воспроизведение:

1. Опубликовать A (amount=10).
2. Готовить B (amount=20), аварийно завершить на `before_commit`.
3. `reconcile` вернёт B в `uncommitted_generations`; CURRENT продолжает выбирать A.
4. Передать B в публичный `read_generation`: он успешно отдаёт B без признака «не подтверждено».

Реальный результат: `candidate_accepted=true`, `current_still_old=true`. Неполные staged-папки обычно отказывают, но полностью сформированная до commit — проходит. Это противоречит публичному сценарию «чтение конкретного подтверждённого поколения». Проверка целостности не является подтверждением публикации.

**Исправление:** разделить private candidate-validation и public committed-snapshot read. Последний требует доверенный commit/pin token (ID+descriptor digest и provenance) либо проверенное членство в подтверждённой истории. Нельзя объявлять наличие generation.json достаточным commit receipt. Если нужен forensic API для candidates, назвать/пометить его отдельно и не выдавать как обычный финансовый снимок. До изменения интеграции нужны тесты candidate до commit, после lost response и после pointer loss.

## G2 — потеря CURRENT превращает подтверждённую историю в «uncommitted» (MEDIUM, обязательно до recovery)

**Файл:** `generation_store.py:217`, `_read_active_at`; `:367`, reconcile.

Воспроизведение: успешно опубликовать A, затем B; удалить только CURRENT.json. `read_active` возвращает None. `reconcile` выдаёт PENDING и оба достоверно ранее опубликованных A/B в `uncommitted_generations`.

Сейчас это не удаляет данные и publish fail-closed из-за orphan; автоматического destructive recovery ещё нет. Но классификация неверна и опасна как вход будущей cleanup/recovery. При утере единственного commit receipt состояние полного staged B и потерявшего receipt committed B может быть неразличимо. Нельзя утверждать «не было commit» только по отсутствию CURRENT.

**Исправление:** RECOVERY_REQUIRED/UNKNOWN_COMMIT_STATE, candidates неизвестного статуса вместо доказанно uncommitted; read_active должен различать действительно пустую область и потерю pointer при существующих поколениях. Для надёжного выбора последнего committed нужны дополнительно защищённые commit receipts/previous pointer/журнал с определённым durable порядком. Пока такого evidence нет — ручное рассмотрение, не выбор по UUID/mtime и не автоудаление.

## G3 — старое поколение и parent chain не привязаны к доверенному digest (HIGH для pinned/recovery contract)

**Файл:** `generation_store.py:235`, read_generation; `:267`, `_lineage` читает parent только по ID; `_descriptor` хранит parent UUID без хеша.

Воспроизведение: A успешно опубликовано, затем B (CURRENT и B не трогать). В папке A согласованно заменить CSV amount 10→99, его metadata и generation.json, пересчитав внутренние checksum. Повторное чтение A по прежнему UUID отдаёт amount99; reconciliation B всё ещё ACTIVE_VERIFIED.

Это **не одиночный bit flip**: он корректно обнаруживается. Это искусственный контрпример согласованной перепаковки истории, например неправильным будущим repair. Не заявляется защита от владельца, способного переписать весь store и доверенные anchors. Существенно то, что CURRENT и B с их хешем оставались неизменны: проверка подтверждённой цепочки не связывает с ними прежние bytes A. UUID не является content digest, «immutable» сейчас лишь соглашение приложения, не запрет файловой системы.

**Исправление:** хранить и проверять parent descriptor digest в дочернем descriptor; public pinned token содержит ожидаемый digest и полную identity. Можно выбрать content-addressed IDs вместо UUID, но нужен явный контракт доверенного anchor. Не восстанавливать A, доверяя только checksum, пересчитанным в A. Не исправлять это только chmod: он не создаёт криптографическую связь поколений. Тест с перепаковкой parent при неизменном trusted child должен отказывать.

## G4 — новые предки scope не синхронизируются до COMMITTED (durability gap)

**Файл:** `generation_store.py:246` mkdir(parents=True); `:322–341` stage sync/commit; `archive.py:45` single-file fsync.

На первом импорте трассировка реальных вызовов os.fsync показала синхронизацию файлов, generation directory, generations и конечного scope, но не parent directories для новых root/.b7-generations/dataset/cabinet/scope entries. fsync конечного scope не заменяет fsync его родителя, где создано имя scope. Эта часть протокола durable first commit не обеспечена самим кодом.

**Исправление:** явная безопасная и durable инициализация цепочки каталогов, синхронизация содержащих новые entries родителей до подтверждения commit; инъекция ошибки на каждом таком fsync. Либо жёсткий проверяемый precondition предварительно durable созданной области и отдельный initializer, а не скрытый mkdir в publish. Проверять также создание нового cabinet/year в существующем store. **Потеря данных при отключении питания не воспроизведена** — это не отчёт о фактическом crash FS. Power-loss остаётся NOT VERIFIED даже после исправления и syscall tests.

## S1 — политика root symlink нуждается в уточнении (не отдельный blocker)

`_scope` вызывает root.resolve(), поэтому symlink самого переданного root разрешается до `_require_plain`; опытный publish через root-symlink записал store в target. Промежуточные symlink внутри уже вычисленного store отклоняются штатными проверками. Если configured resolved root допустим — документировать именно это. Если обещан запрет ВСЕХ symlink, проверять lexical root/ancestors до resolve. TOCTOU-защита от конкурентного злоумышленника с правом записи в каталоги не доказана; path checks до open не равны dirfd/O_NOFOLLOW confinement.

## Покрытие F01–F24: не подменять частичную приёмку полным PASS

- Частично реально испытаны F01/F02/F04/F06/F07/F08/F09/F10/F11/F16/F18/F19/F21/F24: данные обоих форматов, checkpoint failures, kill, IO, concurrency, paths и network denial. Это не все комбинации ошибок каждого FS-вызова.
- F03/F12/F13/F14/F23 — отрицательные проверки частично есть в stock и нашем harness, но G1–G4 показывают незавершённый trust/classification/durability contract.
- F05/F15/F17/F20/F22 — полноценная приёмка backup/recovery/recovery concurrency/retention/миграции и разных scope ещё NOT VERIFIED или не реализована. Старое поколение сохраняется, но это не уже готовый backup/recovery API.
- Многочасовой stress, ограничения памяти/истории и аппаратная power-loss durability не проверены. read_active валидирует выбранный snapshot, reconcile дополнительно читает всю lineage; повреждённый давний parent блокирует новые записи. До retention нужно определить политику anchors/истории, иначе удаление любого ancestor ломает chain.

## Архитектура следующего блока: до подключения архиватора

1. Исправить G1/G2/G3, определить форматы full identity, commit/pin receipt, parent digest, checkpoint states и политику неизвестного commit. Устранить G4, сохранить строгие JSON/R3/B9 проверки. Не объявлять staged/valid равным committed.
2. Адаптер импорта должен под тем же scope lock читать pin A, строить полный новый набор по A+incoming и CAS-публиковать B. При конфликте перечитать и заново применить изменение, не бесконечно слать прежний полный набор. При Ozon нельзя потерять ранее сохранённые месяцы; семантика исправлений и удаления строк — отдельный контракт.
3. Проверенная legacy migration: все старые CSV/manifest и Ozon group проверяются ДО записи; источник не меняется; первый generation копирует подлинные bytes. API/CLI/verify/ingest и внешние читатели переводятся на один snapshot reader. Экспорт старых CSV — проекция, не второй независимый источник истины; не обещать глобальную атомарность раздельной публикации экспортов.
4. Recovery — явная локальная операция с тем же lock, expected active token и планом: сохранить evidence; проверить действующий pointer/receipt; при неопределённости не повторять импорт; проверить целиком кандидата из доверенной committed history; stage recovery transaction; durable переключить CURRENT; независимо перечитать; записать результат. Не перекодировать повреждённые CSV и не считать новые checksum «ремонтом».
5. Не определять «последний» по mtime/порядку UUID. С rollback на предыдущее поколение сохранять факт утраты более новых данных; не объявлять его полным свежим архивом. Старая receipt A не может откатить уже подтверждённый C: CAS/fencing на recovery обязателен.
6. Crash during recovery, повтор recovery, cleanup/retention, совместимость readers и freeze миграции — отдельные F01–F24 тесты конкретного следующего SHA. verify/status только читают. При активном writer readers пинят один committed snapshot. Не подменять проверку происхождения/полноты B8 локальной checksum verification.

Без изменения API block. P01 NOT VERIFIED. Ни merge, deployment, Actions execution, Redis, provider/API запросов, ни изменения working services. Публикуется только собственная документация/доказательства, разработчик исправляет свой код самостоятельно.
