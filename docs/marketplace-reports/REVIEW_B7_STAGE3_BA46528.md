# B7 stage 3 — независимая ревизия current_repair, ba46528

Hermes, 29.10.2026. Точный PR №97 commit `ba465288406f68dacb4a2557019a488716d55ba6`. PR открыт/не слит, head совпадал. Предыдущие принятые core/stage2 не изменены в функциональном diff. Код/ветка коллеги не менялись.

## Заключение: третий программный блок — FAIL

137 stock tests PASS, но независимые R97-1 и R97-2 требуют исправления. Эти замечания относятся к durability replay и типам нового журнала. Неаутентифицированная операторская метка свидетельства — отдельно заявленное ограничение, не выдаётся за скрытый новый дефект и не является единственной причиной FAIL.

Полная B7 OPEN; предыдущие scoped G1–G4 и R96 blocks PASS сохраняются. P01 NOT VERIFIED; physical power-loss NOT VERIFIED; merge/deploy/API не разрешены.

## Реальное исполнение

**137 локальных unittest PASS**, все project modules импортированы из точного отдельного checkout, network/DNS запрещены audit hook также дочерним процессам. GitHub check-runs точного SHA прочитаны completed/success offline-tests, windows-ps51-parse, gitleaks. Локальный PS5.1 и ручной Actions не запускались.

**61 дополнительный независимый сценарий** (не «61 PASS»):

| Набор | Число | Результат |
|---|---:|---|
| SIGKILL на всех пяти declared checkpoints, missing/corrupt CURRENT, WB/Ozon | 20 | PASS: replay с теми же inputs восстанавливает pin, сохраняет точный preimage и generation bytes |
| Исключения на пяти checkpoints WB/Ozon с corrupt CURRENT | 10 | PASS: RestoreUncertainError, последующий replay корректен |
| VERIFIED parent-fsync failure и SIGKILL сразу после VERIFIED rename | 2 | R97-1: retry возвращает успех без повторного sync journal directory |
| Типы schema в PREPARED/VERIFIED journals | 16 | R97-2: true и 1.0 приняты в обеих фазах; false/строка/null/list/object/неверный integer отвергнуты |
| Ack/witness/pin/ID/CAS/rollback/orphan/parent/current symlink guards | 10 | PASS: отказ до нового журнала, исходные bytes не меняются |
| Выдуманная operator witness для никогда не опубликованного candidate | 1 | Подтверждено известное ограничение: candidate может быть выбран, authenticity flag остаётся false |
| Реальные repair+importer и repair+repair процессы | 2 | PASS: общий порядок locks, preimage сохранён, stale repair не откатывает последующий commit |

21 настоящий SIGKILL — 20 declared checkpoints плюс дополнительное окно между финальным rename журнала и fsync его каталога. Ошибки checkpoint не подменяют mid-syscall tests. 61 рассчитано по COMPLETE records; counts не включают отдельные assertions как «ещё тесты».

Артефакты: [основной harness](evidence/b7_stage3_review.py), [результаты](evidence/b7_stage3_ba46528_results.jsonl), [concurrency harness](evidence/b7_stage3_concurrency_review.py), [concurrency результаты](evidence/b7_stage3_ba46528_concurrency_results.jsonl), [stock runner](evidence/b7_stage3_run_stock.py), [stock stdout](evidence/b7_stage3_ba46528_stock_tests.txt). Все принимают `--checkout /path/to/ba46528`, fixtures — scratch возле harness, удаляются; TMPDIR штатного runner также scratch. Реальные отчёты/credentials не читаются.

## R97-1 — ранний VERIFIED return пропускает незавершённый fsync журнала (обязательная доработка)

**Файл:** `apps/msp_marketplace_reports/current_repair.py:198–203`, до ветки resync в строках 217–224.

### Воспроизведение

1. В synthetic store успешно создать A→B, испортить CURRENT произвольными bytes и сохранить их SHA.
2. Вызвать repair(B, точный pin, точный preimage SHA, acknowledgment и test witness).
3. PREPARED journal и CURRENT успешно записаны. При финальной записи journal(state=VERIFIED) os.replace уже выполнен, а `os.fsync(fd_restore_journal_directory)` принудительно возвращает EIO.
4. Первый вызов корректно сообщает RestoreUncertainError. На видимом диске journal уже VERIFIED.
5. Повторить с идентичными inputs и записывать реальные fsync FDs. Повтор вернёт CURRENT_VERIFIED через ранний return; restore-journal directory в fsync trace отсутствует.

Отдельный настоящий дочерний процесс убит SIGKILL после финального VERIFIED rename, до fsync его containing directory. Replay дал тот же early success без resync. `_write_lock(scope)` синхронизирует scope и предков, но не заменяет sync вложенного restore-journal.

Финансовые поколения и точный preimage в наблюдаемом состоянии сохранены. **Не утверждается воспроизведённая потеря данных при отключении питания.** Предыдущий PREPARED journal мог быть уже durable, однако завершённость финальной journal transition после неопределённого результата не подтверждается: видимый VERIFIED принят за доказательство успешного прошлого fsync. Это тот же класс idempotency gap, что ранее исправленный G4-R1/R96-1, теперь в новой ветке replay.

### Исправление

Не завершать replay успехом только по state==VERIFIED. До любого успешного CURRENT_VERIFIED выполнить/подтвердить обязательную синхронизацию journal file и его containing directory (и проверить текущее поколение), не меняя сохранённый preimage. Можно объединить prepared/verified replay в общий durable finish path. Повторный injected sync failure должен снова дать uncertain, не успех.

Нужны tests именно final journal replace→directory fsync failure→retry и SIGKILL в этом окне. Checkpoint after_journal_verified расположен уже ПОСЛЕ полного `_safe_write`, поэтому существующий test не закрывает найденную щель.

## R97-2 — числовая schema журнала принимает true и 1.0 (MEDIUM)

**Файл:** `current_repair.py:171–176`, `record.get(k) != v` для expected_record schema=1 без проверки type.

### Воспроизведение

- Остановить repair на after_prepare и в сохранённом journal заменить `"schema":1` на `true` или `1.0`.
- Повтор разрешён и возвращает CURRENT_VERIFIED; journal нормализуется обратно в schema=1 при завершении. Повреждённый тип не был отклонён.
- То же для уже VERIFIED journal: повтор возвращает CURRENT_VERIFIED через early return, оставляя неправильный тип на месте.

Обе формы приняты в обеих фазах: 4 контрпримера из 16 type cases. Здесь повторяется Python equality-ошибка `True == 1` и `1.0 == 1`, ранее закрытая R3 для финансового manifest. `_strict_json` запрещает дубли/NaN, но сам по себе не проверяет типы полей объекта. Целостность CSV этим test не нарушена; проблема в принятии повреждённого recovery control format.

### Исправление

Общий валидатор полного recovery record: `type(schema) is int` и ожидаемая версия (можно использовать `_integer` из core), точные поля/состояния/типы и identity. Применять до сравнения/перезаписи/early return. Проверять также форматы посторонних journals, прежде чем считать их завершёнными только по `state=VERIFIED`. Не переудостоверять некорректный control record его молчаливой нормализацией. Отказы PREPARED/VERIFIED malformed schema должны сохранять byte snapshot.

## Что работает и где проходит граница доверия

- Для заданных корректных pins вся цепочка и файлы проверяются. Missing и произвольно повреждённый CURRENT (включая не-UTF8 bytes) восстанавливаются с точным сохранением preimage в base64 в испытанных окнах.
- Healthy divergent CURRENT не откатывается. Дополнительные unexplained generations блокируют repair, неверный pin/CAS/parent и symlink CURRENT отвергаются без нового journal.
- В subprocess test repair удерживает admission+scope locks; штатный versioned importer ждёт, затем публикует C. Повтор repair с прежним pin B не откатывает C. Два одинаковых repair сериализуются и сохраняют одну исходную копию.
- По локальным файлам нельзя доказать последнее подтверждённое поколение. В test создан никогда не committed C, CURRENT повреждён, затем оператором заявлен точный SHA C и выдуманный reference. Repair выбирает C, поскольку вся локальная ancestry совпадает и внешняя метка не проверяется. Результат честно содержит `external_witness_authenticated_by_code=false`.

Последний пункт — **воспроизведённая документированная граница**, не криптографический обход обещанной проверки. Программный `_verify_witness` фактически валидирует audit label/pin, а не подлинность свидетельства. Перед production нужен отдельно согласованный независимый durable источник commit proof и проверяемый протокол его связи с scope/generation/SHA. Даже PASS локального модуля не разрешит использовать произвольный текст как доказательство последнего actual head.

## Рекомендации и следующий шаг

Исправить R97-1/R97-2 в собственной ветке разработчика и передать новый точный SHA. Затем независимый replay/fsync/type review. Не ослаблять no-rollback/unresolved-generation/CAS guards ради удобства. Сохранить общий порядок блокировок, exact preimage, explicit uncertainty и false authenticity flag.

Следующие этапы B7 всё ещё отдельно: migration, внешние readers/ingest, independent history/witness, retention, полная F01–F24/FS-specific durability. Не объявлять stage3 готовым production recovery. Предыдущие принятые блоки этими дефектами нового модуля не отменяются.

Код/ветка коллеги, реальные службы/архив/секреты/Redis не менялись. Нет merge/deploy/реальных API/Actions execution/новых каналов. Только synthetic tests, собственная review-ветка, журнал/PROJECT/Skill и ответ коллеге.
