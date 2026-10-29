# R96-4 — независимая приёмка ceec4fe; второй opt-in блок B7

Hermes, 29.10.2026. Точный PR №96 commit `ceec4fe6a9649ea547c0900d5e45b667868bec7f`. Head совпадал с проверяемым SHA; PR открыт/не слит. Предыдущий FAIL R96-4 на a0df0d5 остаётся историей. Ветка/код коллеги не менялись.

## Заключение: R96-4 PASS

Три первоначальных counterexample закрыты **у обоих штатных импортёров**: symlink root, `.locks` и lock-file не создают и не меняют файлы вне выбранного корня. Вложенные/dangling symlinks и дополнительные hardlinks отклоняются. Повторное использование обычного lock сохраняет inode/bytes; исходные R96-1–R96-3 и core G1–G4 не регрессировали в проведённых проверках.

**Второй программный блок B7 принят в заявленной офлайн opt-in границе на ceec4fe.** Это отдельный versioned import/reader и ограниченный операторский quarantine при исправном CURRENT, а не готовая миграция/полное аварийное восстановление. **Полная B7 OPEN; P01 NOT VERIFIED; physical power-loss NOT VERIFIED.** Нет разрешения merge/deploy/API.

## Реальное исполнение

**120 локальных stock unittest PASS**, все apps.msp_marketplace_reports.* импортированы из точного отдельного checkout; connect/DNS заблокированы audit hook, включая дочерние процессы. GitHub check-runs точного SHA прочитаны completed/success offline-tests/windows-ps51-parse/gitleaks. PowerShell 5.1 локально не запускался; Actions не запускались вручную.

**143 дополнительных независимых сценария PASS:** 71 admission/path, 68 regression/control stage2 и 4 core контроля. Подсчёт выполнен по COMPLETE records, без суммирования внутренних assertions как самостоятельных tests.

### Admission/path: 71

| Набор | Число | Проверенный результат |
|---|---:|---|
| 16 запрещённых форм пути × оба импортёра | 32 | Отказ, outside bytes неизменны, FD leak нет |
| Повтор обычного существующего lock × оба импортёра | 2 | Тот же inode и sentinel bytes, повторный import no-op |
| Каждый из 12 фактических admission os.open × оба импортёра | 24 | EACCES до финансовой публикации, FD leak нет, outside пуст |
| Ошибка mkdir root/.locks × оба импортёра | 4 | Отказ, финансовые CSV/generations не появляются, FD leak нет |
| Подмена ancestor/root/.locks/lock-file непосредственно перед no-follow open × оба импортёра | 8 | Отказ, файлы в target вне root не появляются |
| Подмена текстового `.locks` после открытия его FD | 1 | Lock создаётся в закреплённом исходном каталоге (переименованном внутри root), не в цели symlink |

16 форм: root link, root dangling link, ancestor link, вложенный ancestor link, `.locks` link/dangling, lockfile link/dangling, hardlink, FIFO, directory вместо lockfile, regular file вместо `.locks`, regular file вместо root, отсутствующий parent, `..` traversal и filesystem `/` как root. Существующий symlink target содержал искусственный sentinel — проверена его неизменность, не только отсутствие новых файлов.

12 open points — реальная длина конкретного scratch path, не универсальная константа для всех установок. Инъекция EACCES не означает перебор всех errno. Для запретных путей проверялось количество открытых FD до/после; чужие FD names/содержимое не выводились.

### Повтор R96-1–R96-3: 68

- 2 source/evidence sync failure→повторный failure→успешный retry: обе директории есть в реальной fsync-трассе; bytes и active pin сохранены.
- 4 настоящих SIGKILL карантина: до rename, после rename, до source sync, после обоих sync; новый запуск повторяет оба sync.
- 12 последовательных legacy/versioned порядков для всех 6 datasets; второй importer отказывает без изменения имеющихся файлов.
- 24 legacy CSV/meta/dangling-link guard cases, 6 mixed-state detection cases, 6 нормальных versioned import/noop/update/pinned-read controls.
- 6 реальных multiprocess mixed races: обе стороны выигрывают admission lock, для WB/CURRENT/FINAL; второй ожидает, затем отказывает, dual layout не создаётся.
- 2 concurrent versioned writer cases: общий lock сериализует операции; сохраняются все 3 WB строки или 3 Ozon месяца и согласованный annual.
- 3 full-plan validation cases: недопустимый второй candidate не приводит к первому переносу.
- 3 partial-progress cases: before-hook второго элемента, его rename error, rename executed then response error. RecoveryUncertainError с observed progress/ID; retry сохраняет оба дерева.

### Core controls: 4

Повторены исходные public staged-read, missing CURRENT, parent repack/forged pin и normal parent-fsync trace: G1/G2/G3/G4 PASS. Private candidate validation не выдаётся за публичный committed read. Это targeted regression control, не повтор всех 201 случаев из исторической приёмки 407d144.

## Оценка исправления

`archive.py::_lock` больше не делает path-based `mkdir(parents=True)`/`open(a+b)`. Каждый компонент проходит O_DIRECTORY|O_NOFOLLOW через parent dirfd; root и `.locks` создаются относительно закреплённых FD. Lock открывается O_NOFOLLOW относительно locks_fd и проверяется fstat (regular file, st_nlink==1). Дескрипторы удерживаются до unlock, закрываются на испытанных error paths. Legacy importer больше не скрывает root symlink вызовом resolve до admission.

Общий cabinet/dataset namespace и порядок admission→generation lock сохранены. Тесты со штатными процессами подтвердили взаимное исключение, а не только совпадение имени lock-файла. Ожидаемое новое ограничение — предки root должны существовать, `..` и filesystem root запрещены. При миграции/установке этот контракт нужно учитывать явно, не обходить no-follow добавлением resolve.

## Граница конкурентного filesystem threat model

Проверены подмена ссылкой **перед** открытием directory/file и закрепление уже открытого `.locks` FD при изменении его текстового имени. Не обнаружен обход, перенаправляющий lock open в symlink target, в этих сценариях.

Это **не доказательство confinement всех финансовых CSV путей против любого внешнего писателя после admission**. Payload/recovery операции пока имеют собственные path-based участки; docs автора прямо оставляют subsequent hostile replacement вне принятой гарантии lock helper. Не утверждаем защиту от администратора/процесса с правом произвольно переносить/удалять archive trees и переписывать trust anchors. Не заявляем, что никакой внешний unlink/recreate lock namespace невозможен. Перед эксплуатацией нужны исключительное владение деревом и согласованная дисциплина всех writers; более сильный hostile-FS контракт — отдельная задача. Не превращаем известную границу в обещание абсолютной безопасности.

## Артефакты

- [Admission harness](evidence/b7_r96_4_admission_review.py), [результаты](evidence/b7_r96_4_ceec4fe_admission_results.jsonl).
- [Stage2 regression harness](evidence/b7_r96_4_regression_review.py), [результаты](evidence/b7_r96_4_ceec4fe_regression_results.jsonl).
- [Core controls](evidence/b7_r96_4_core_control.py), [результаты](evidence/b7_r96_4_ceec4fe_core_results.jsonl).
- [Stock runner](evidence/b7_r96_4_ceec4fe_run_stock.py), [stdout](evidence/b7_r96_4_ceec4fe_stock_tests.txt).

Каждый harness принимает `--checkout /path/to/ceec4fe`. Fixtures — scratch рядом с harness, удаляются после исполнения. TMPDIR штатного запуска — scratch. Все финансовые строки искусственные; credentials не читались, сеть запрещена.

## Что дальше

Новых блокирующих дефектов в заявленной границе не найдено. Можно продолжать офлайн-разработку следующих частей B7 с новым SHA и отдельной независимой приёмкой: проверенная migration, единые внешние readers/ingest/verify, recovery неизвестного/повреждённого CURRENT с независимым commit proof, retention и оставшиеся F01–F24. Сохранять evidence, UNKNOWN/UNCERTAIN и fail-closed; не пересчитывать checksum повреждённых данных ради нового VERIFIED.

Не считать acknowledgment доказательством исторического never-committed при внешнем rollback. Не заявлять physical power-loss, нагрузочную/FS-specific эксплуатационную готовность. Core и stage2 acceptance не разрешают live API/Redis, merge или deployment.

Код/ветка коллеги, службы, рабочий архив и секреты не менялись. Только собственный review/evidence, журнал/PROJECT/Skill и ответ коллеге.
