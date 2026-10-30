# B7 stage 2 — повторная независимая ревизия a0df0d5

Hermes, 29.10.2026. Точный PR №96 commit `a0df0d5d4266392853330dc414d50fbf31bf314e`, baseline `5eb19855b1aa9bc48eb6c3157987a557a411aee6`. Head совпадал с проверенным SHA, PR открыт/не слит. Код/ветка коллеги не изменялись.

## Заключение

| Предмет | Статус |
|---|---|
| R96-1 — карантин: повторить оба directory fsync после uncertain | **PASS** |
| R96-2 — mutual exclusion штатных legacy/versioned importers, dangling metadata links, mixed detection | **PASS** по первоначальным контрпримерам |
| R96-3 — full-plan preflight и явный partial/uncertain result | **PASS** |
| Новая регрессия R96-4 — путь общей admission lock | **FAIL**, обязательная доработка |

По трём переданным исправлениям положительное заключение. Общая приёмка второго блока остаётся **FAIL** до R96-4. Scoped core G1–G4 PASS сохраняется. B7 OPEN, P01 NOT VERIFIED, физический power-loss NOT VERIFIED. Отсутствие ещё не написанного полного restore/migration не является новым дефектом этого patch.

## Реальное исполнение

**118 локальных stock tests PASS**, module origins проверены внутри точного checkout, connect/DNS запрещены audit hook. GitHub check-runs точного SHA прочитаны success offline-tests/windows-ps51-parse/gitleaks; PowerShell 5.1 локально не исполнялся, Actions вручную не запускались.

**71 дополнительный независимый сценарий на текущем коммите:** 68 regression/control сценариев и 3 path counterexamples. Это НЕ «71 PASS». Дополнительно те же 3 path probes повторены на старой версии для классификации регрессии и в 71 не включены.

| Группа | Число | Результат |
|---|---:|---|
| Source/evidence fsync failure, повторный отказ и затем успешный retry | 2 | PASS: оба каталога реально fsync на последнем retry, active/retained bytes сохранены |
| Quarantine SIGKILL до rename, после rename, перед source sync, после обоих sync | 4 | PASS: новый запуск повторяет оба fsync, bytes сохранены |
| Legacy→versioned и versioned→legacy последовательно для всех datasets | 12 | PASS: второй штатный importer отказывает, старые файлы неизменны |
| Legacy CSV/meta и dangling CSV/meta symlink для всех datasets | 24 | PASS: versioned import блокируется |
| Искусственный mixed state для всех datasets | 6 | PASS: оба verify отказывают |
| Нормальный versioned import/noop/update/pinned-read для всех datasets | 6 | PASS |
| Настоящие процессы legacy/versioned: обе стороны выигрывают lock, WB/CURRENT/FINAL | 6 | PASS: второй ждёт common lock, затем отказывает; dual layout не создан |
| Два штатных versioned процесса, WB и Ozon FINAL | 2 | PASS: сериализованы, обе записи сохранены, итог 3 строки/месяца в одном snapshot |
| Недопустимый второй candidate: file collision/both dirs/missing candidate | 3 | PASS: до первого переноса, snapshot unchanged |
| Второй candidate: before-hook exception/rename error/rename executed then error | 3 | PASS: RecoveryUncertainError, observed moved list и candidate доступны; retry сохраняет оба дерева |
| Root/.locks/lock-file symlink path probes | 3 | R96-4 воспроизводится, см. ниже |

Наблюдаемые совпадения байтов после SIGKILL не являются тестом отключения питания. Error-after-effect у rename классифицируется uncertain, observed moved list не выдаётся за полный durable факт.

## Повтор первоначальных дефектов

### R96-1 PASS

Для сбоя исходного generations и сбоя evidence каталог уже был перемещён. Затем повторно вводился отказ на retry (already-retained branch), и вызов вновь отказывал через RecoveryUncertainError. После снятия инъекции трасса **реальных os.fsync** содержит оба каталога. SIGKILL окна дают тот же положительный результат. CURRENT и активное поколение не переключались, сохранённые bytes совпадают.

### R96-2 PASS в согласованной границе штатных entrypoints

`archive.import_csv` и `versioned_archive.import_csv_versioned` используют общий lock cabinet/dataset; guard расположен внутри него. При реальной конкуренции первый процесс удерживался сразу после flock, второй подтвердил попытку входа и не прошёл к защищённому участку до освобождения первого; после этого второй отклонён. Испытаны обе стороны для WB main, Ozon CURRENT и FINAL. Прежнее interleaving после проверки перед publish штатному legacy writer больше не доступно: он ждёт тот же lock.

Новый reader не подмешивает legacy; обе проверки выявляют вручную инъецированное двойное состояние. Низкоуровневый publish_batch и произвольные сторонние writers общему admission protocol автоматически не подчиняются — это заявленная граница, а не новый обход штатного контракта.

### R96-3 PASS

Конфликты всего плана найдены до evidence relocation; первый candidate остаётся на месте. Ошибки после начала операции, включая before-hook второго элемента и неопределённый исход его rename, дают RecoveryUncertainError с observed progress и ID текущего candidate. Новый запуск со старым корректным active pin завершает сохранение обоих деревьев и повторяет sync. Raw GenerationError после переноса первого элемента в этих первоначальных сценариях больше не воспроизводится.

## R96-4 — общий lock создаёт/открывает файл вне archive root до проверки пути (MEDIUM)

**Файлы:** `versioned_archive.py::import_csv_versioned`, вход в `_lock` перед `_assert_no_legacy`; `archive.py::_lock`, около строки 175: `folder.mkdir(...); lock.open("a+b")` без запрета symlink. Это новый dependency-path regression versioned importer; собственный core `_write_lock` имеет более строгую проверку и не является источником проблемы.

### Repro A: symlink самого root

1. В scratch создать пустой outside и `archive -> outside`.
2. Подать корректный WB CSV в штатный import_csv_versioned(root=archive).
3. Новая версия правильно в итоге отказывает по symlink, **но до отказа** создаёт `outside/.locks/wb_laser_master__wb_weekly_finance_main.lock`.
4. На `5eb1985` то же обращение отказывало без внешнего файла.

### Repro B: symlink `.locks`

1. Root — обычный каталог, `root/.locks -> outside`.
2. Вызвать тот же штатный импорт.
3. Результат **COMMITTED**, при этом в outside создан `wb_laser_master__wb_weekly_finance_main.lock`.

### Repro C: symlink lock-файла

1. Root и `.locks` обычные; `<lockname> -> outside/injected.lock` (target пока отсутствует).
2. Вызвать импорт.
3. Результат **COMMITTED**, создан `outside/injected.lock`.

На прежнем adapter эти два lock-пути вообще не использовались и outside files оставались пустыми; на текущем — файл создаётся штатным API. Использованы только пустые искусственные outside-каталоги. **Финансовые CSV за пределами root не писались, секреты не читались и утечка не заявляется.** Обнаружен выход file/locking side effects за root и побочная запись ещё до отказа корневой проверки. Доступ к постороннему существующему файлу через ту же open-ссылку может также дать нежелательную блокировку — такой эксплуатационный эффект не запускался на реальных файлах.

Наличие общей блокировки R96-2 необходимо и правильно. Ошибка в том, что её собственный путь не защищён и в versioned API она выполняется раньше path validation. Нельзя исправлять это удалением общего lock или возвратом к двум независимым lock namespaces.

### Способ исправления

- Перед любым mkdir/open admission lock проверять lexical expanded root/ancestors, `.locks` и lock path согласно единой политике запрета symlink; отрицательный root case должен завершаться без внешних side effects.
- Проверку вынести в общий безопасный lock helper обоих штатных entrypoints; для lock-file open использовать запрет follow (`O_NOFOLLOW`, проверка обычного файла). Для более сильной гарантии против конкурентной замены каталогов нужен dirfd/no-follow confinement, а не только exists/is_symlink перед open. Не заявлять hostile-FS race защиту без отдельного теста.
- Добавить regressions для root link, `.locks` link, dangling и существующего lock-file link; за пределами root не должно появляться файлов. После изменения повторить обе смешанные гонки: они должны остаться сериализованными в том же namespace/порядке locks.

Исправление за разработчиком. Замечание не переоткрывает R96-1/R96-2/R96-3 и не отменяет целостность сохранённых финансовых поколений в текущих positive tests, но мешает полной приёмке второго блока.

## Артефакты

- [Регрессионный harness](evidence/b7_r96_repeat_review.py), [результаты](evidence/b7_r96_a0df0d5_results.jsonl).
- [Минимальные path probes](evidence/b7_r96_lock_path_probe.py), [текущий результат](evidence/b7_r96_a0df0d5_path_results.jsonl), [baseline 5eb1985](evidence/b7_r96_5eb1985_path_results.jsonl).
- [Stock runner](evidence/b7_r96_a0df0d5_run_stock.py), [stdout](evidence/b7_r96_a0df0d5_stock_tests.txt).

Harness/probe принимают `--checkout /path/to/pinned-checkout`. Все fixtures создаются в scratch рядом с harness и удаляются, TMPDIR stock runner — scratch. Connect/DNS запрещены также детям. 71 сценарий подсчитан программно из COMPLETE и текущих path records; baseline records отдельно.

Остальные границы сохраняются: quarantine — не восстановление битого CURRENT; внешний rollback может сделать previously committed generation внелинейным, acknowledgment не external commit proof; power-loss и вся F01–F24 не закрыты. Migration/readers/retention требуют отдельной разработки и приёмки.

Ветка/код коллеги, рабочие службы, финансовый архив, credentials, Redis не менялись. Нет merge/deploy/маркетплейс API/Actions execution/новых каналов. Только synthetic tests, собственный review, журнал/Skill и сообщение коллеге.
