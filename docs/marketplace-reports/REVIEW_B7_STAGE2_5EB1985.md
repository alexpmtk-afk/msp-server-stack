# B7 stage 2 — независимая ревизия 5eb1985, PR №96

Hermes, 29.10.2026. Проверен точный `5eb19855b1aa9bc48eb6c3157987a557a411aee6`. PR №96 открыт и не слит; head совпадал с проверенным SHA. База принятого core — `407d144...`; generation_store.py в этом diff не изменён. Работа только в отдельном checkout и собственной review-ветке, код разработчика не изменён.

## Итог: второй программный блок — FAIL

108 stock tests PASS, но независимые контрпримеры R96-1/R96-2/R96-3 требуют исправления. Прежняя scoped приёмка G1–G4 не отменяется: проблемы в новых adapter/recovery. Полная B7 OPEN, P01 NOT VERIFIED, power-loss NOT VERIFIED. Отсутствие полной миграции/восстановления повреждённого CURRENT не само по себе причина FAIL — эти ограничения честно указаны.

## Реально выполненные проверки

**108 локальных stock tests PASS**, все apps.msp_marketplace_reports.* импортированы из точного checkout; audit hook запрещает connect/DNS, в том числе дочерним процессам. GitHub check-runs точного SHA прочитаны completed/success offline-tests, windows-ps51-parse, gitleaks; локальный PS5.1 не запускался, ручного Actions execution нет.

Дополнительно **32 независимых сценария**, включая положительные, отрицательные и воспроизводители дефектов — НЕ «32 PASS»:

| Группа | Количество | Результат |
|---|---:|---|
| Нормальный импорт/no-op/изменение/pinned read для всех datasets | 6 | PASS, без появления legacy layout |
| Статический legacy guard: CSV, meta, CSV symlink, dangling meta symlink | 4 | Первые 3 блокируются; dangling meta symlink пропускается |
| Последовательное coexistence и legacy commit после второго guard | 2 | Оба воспроизводят R96-2 |
| Два реальных процесса versioned importer, WB и Ozon FINAL | 2 | Один commit, один stale; после явного повторного импорта 3 строки сохранены, Ozon месяцы и annual в одном поколении |
| Source-directory fsync failure после evidence rename и retry | 1 | Воспроизводит R96-1 |
| Настоящий SIGKILL в quarantine до rename/после rename/до source sync/после обоих sync | 4 | Наблюдаемые bytes сохранены; два middle windows воспроизводят пропуск source sync при retry |
| Позднее обнаружение конфликтующего второго candidate | 1 | Воспроизводит R96-3 |
| Ранее committed B после внешнего rollback CURRENT на A | 1 | Подтверждено известное ограничение: B может быть перемещено как внелинейное, bytes сохранены |
| Quarantine preconditions: ack/pin/ID/committed/unlisted/duplicate/missing&corrupt CURRENT/symlink/target-file | 11 | PASS: отказ, побайтовое состояние архива неизменно |

Артефакты: [независимый harness](evidence/b7_stage2_review.py), [JSONL результаты](evidence/b7_stage2_5eb1985_results.jsonl), [stock runner](evidence/b7_stage2_run_stock.py), [stock stdout](evidence/b7_stage2_5eb1985_stock_tests.txt). Harness: `python3 -B b7_stage2_review.py --checkout /path/to/5eb1985`. Fixtures только scratch, файлы после проверки удалены; исходные кабинеты/credentials/финансовые отчёты не использовались. Ручное acknowledgment дано только синтетическим quarantine calls.

## R96-1 — retry карантина пропускает незавершённый source-directory fsync (HIGH)

**Файл:** `apps/msp_marketplace_reports/generation_recovery.py:88–99`.

Воспроизводимые шаги:

1. Успешно опубликовать A. Сформировать B и прервать его на before_commit.
2. Выполнить quarantine(B), инъецировать OSError в `_sync_dir(scope / "generations")` сразу после успешного `os.replace(source,target)`.
3. Получить RecoveryUncertainError; B уже находится в evidence, source отсутствует.
4. Снять инъекцию и повторить с теми же pin/candidates. Код видит `already`, выполняет continue и возвращает EVIDENCE_RETAINED.
5. Трасса реальных os.fsync показывает: source parent `generations` повторно НЕ синхронизирован.

Настоящие SIGKILL сразу после rename и непосредственно перед source sync дали тот же результат после повторного запуска. Observed bytes каталога B и активный A сохранились; это НЕ доказательство durable relocation после power-loss. `ensure_scope_durable(evidence)` синхронизирует evidence и предков, но не sibling `generations`, где удалена исходная запись.

Это та же категория idempotency gap, что исправленный G4-R1, но теперь при переносе доказательств. После kill ПОСЛЕ обоих успешных sync повтор также пропускает source sync, однако само такое окно не доказывает незавершённой синхронизации — его не считаем отдельным ошибочным отказом.

**Исправление:** before EVIDENCE_RETAINED повторять обе обязательные sync операции source-parent и evidence даже для already-moved кандидатов, либо иметь durable phase journal, подтверждающий их завершение. После неопределённого исхода нельзя считать наличие target достаточным evidence завершённого переноса. Нужны failure→retry и SIGKILL→retry tests на rename/обоих sync, включая несколько кандидатов. Изменение не должно переключать CURRENT или переудостоверять payload.

## R96-2 — guard не обеспечивает взаимного исключения старого и нового layout (HIGH)

**Файл:** `versioned_archive.py:26`, `_assert_no_legacy`; `:114–150`, проверки вне publish lock. Связанный старый путь — `archive.py::import_csv/_lock`.

### A. Последовательный случай — без вмешательства в код

Первым вызвать `import_csv_versioned` amount10; затем обычный публичный `archive.import_csv` того же cabinet/dataset/year с amount99. Оба вызова успешны. Обычный verify=True и verify_versioned_scope=True, но CSV bytes различаются. Новый reader не смешивает rows одного снимка, однако для одного логического отчёта возникают две расходящиеся «исправные» истории. Следующий versioned import уже блокируется, но coexistence к тому моменту создано.

### B. Окно после второго guard

В harness на границе вызова `va.publish_batch` (после двух проверок) синхронно выполнен legacy import, затем настоящий publish_batch. Оба успешны, новый receipt COMMITTED. Это воспроизводимая допустимая interleaving; не утверждение о выполненном live race. Старый и новый writer берут разные lock, поэтому повторение guard дважды окно не закрывает.

**Исправление:** единый контракт режима/владения scope и общая admission lock для обоих entrypoints, с проверкой запретов под ней; legacy writer обязан отказывать при наличии versioned scope/evidence. Альтернатива — принудительно раздельные корни с проверяемым запретом использования чужого режима. Не нужна автоматическая миграция ради исправления guard. Простого переноса guard под только новый lock недостаточно, если legacy writer этот lock не соблюдает. Перед будущей migration отдельно остановить/переключить всех старых писателей.

### C. Статический symlink bypass

Создать только dangling symlink `<legacy.csv>.meta.json` при отсутствующем CSV. Новый WB import допускается и возвращает COMMITTED: для meta вызывается только exists(), которое false у dangling symlink; is_symlink() есть только у CSV. Та же ветвь используется CURRENT. Добавить проверку is_symlink для metadata и тесты orphan/dangling на всех ветвях. Link в harness сохранён, за его пределами ничего не записывалось. FINAL имеет отдельный inventory и не является этим конкретным bypass.

## R96-3 — проверка всего списка candidates завершается после первой мутации (MEDIUM)

**Файл:** `generation_recovery.py:69–95`, особенно source/target проверки внутри цикла перемещения.

Fixture: исправный A, два orphan directories X и Y (синтетически подготовлены копированием кандидатного дерева, ID X лексически раньше Y); заранее существует также `evidence/Y`. Полные candidates=[X,Y] проходят inventory-set проверки. Операция перемещает X, затем для Y обнаруживает source И target и бросает обычный GenerationError `candidate present in both stage and evidence`.

Результат: `earlier_candidate_already_moved=true`, файловое состояние по именам изменено. Это не потеря содержимого и не переключение активного A, но ошибка preflight обнаружена уже после мутации, без partial/uncertain result. Similar gap: fault("before_evidence_rename") второго элемента находится вне try, хотя первый элемент уже мог быть перемещён.

**Исправление:** проверить состояния всех source/target и коллизии до первой перемены/создания evidence; построить план. После начала перемещения ошибки последующих шагов должны сохранять progress/receipts и давать явный partial/uncertain результат с возможностью проверяемого продолжения. Не обещать атомарный много-каталожный rename: обеспечить журналируемую повторяемость. Тест отклонённого плана — unchanged snapshot; тест mid-operation IO failure — retained bytes и явное неопределённое/частичное состояние.

## Можно ли переместить ранее подтверждённое поколение?

**Да, если внешний процесс откатил CURRENT назад, и оператор подтвердил выбранный план.** Успешно создать A, затем B; вернуть старые подлинные bytes CURRENT(A); вызвать quarantine(B) с корректным pin A и acknowledged=True. B перемещается, хотя harness знает, что оно прежде было committed. Код не может восстановить этот факт из текущей цепочки A. Данные B не удаляются.

Это ограничение прямо описано автором, поэтому не выдаётся за вновь обнаруженную недокументированную регрессию. Но `acknowledged=True` не является внешним commit proof; метод определяет «не в активной ancestry», а не историческое «никогда не подтверждалось». Нельзя использовать этот API как автоматическое основание удаления/retention или называть его полным recovery. Для такой гарантии нужны независимые durable commit receipts/журнал и более точная классификация displaced/unknown generations. При будущем восстановлении потерянного/неверного CURRENT этот вопрос обязателен.

## Положительные выводы и следующая работа

- Versioned WB main/buyout и CURRENT/FINAL по выполненным controls работают, no-op стабилен, прежний pinned snapshot читается. CAS не теряет проверенные конкурирующие updates; caller после stale должен перечитать и повторно построить полный batch.
- Ozon FINAL candidate строится из прежних месячных bytes + входящего месяца, annual относится к тому же core generation; в сценарии двух процессов после явного повторения сохранены все три месяца.
- Quarantine отказывает для active ancestors, неверных pins/ack/IDs и отсутствующего/битого CURRENT; текущий committed snapshot в успешных/отказных проверках не изменён. Ни один test не вычисляет новые финансовые checksum для «ремонта» повреждения; quarantine хранит bytes как evidence, не как VERIFIED financial replacement.
- Исправить R96-1/R96-2/R96-3, передать новый точный SHA. Старые интерфейсы/ingest/external readers не объявлять переведёнными на поколения; migration и полноценный restore отдельные задачи с F01–F24. Core G1–G4 остаётся принятым на своей проверенной версии.

Никаких merge/deployment/Redis/маркетплейс API/Actions execution/новых каналов; P01 NOT VERIFIED. Журнал и Skill обновляются только подтверждёнными результатами; код исправляет коллега самостоятельно.
