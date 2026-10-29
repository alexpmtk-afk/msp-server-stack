# G4-R1 — независимая повторная приёмка 407d144

Hermes, 29.10.2026. Точный PR №95 commit `407d14470db1ccb073a3278067be142a3dbd339b`. Head совпадал с проверяемым коммитом; PR открыт и не слит. Предыдущий результат G4 FAIL на `97decf8...` остаётся историческим, не текущим. Код/ветка коллеги не менялись.

## Итог

**G4-R1 — PASS. G1/G2/G3/G4 — PASS в пределах первого opt-in программного блока.** Новых блокирующих замечаний или регрессий в проведённых испытаниях нет. Можно переходить к разработке следующего блока B7 — подключения архиватора/читателей и явного recovery — с отдельной независимой приёмкой его точного SHA.

Это не B7 overall PASS, не завершённая миграция/восстановление, не разрешение merge/deploy/API. **B7 OPEN; P01 NOT VERIFIED; PHYSICAL POWER LOSS NOT VERIFIED.**

## Что выполнено

**92 штатных unittest PASS** в точном отдельном checkout, module origins проверены внутри него. Дополнительно **201 независимый сценарий**, с подсчётом из машинного результата:

| Набор | Количество | Подтверждённый результат |
|---|---:|---|
| Отказ fsync(parent) после mkdir, затем retry | 6 | root/.b7/dataset/cabinet/year/generations: ранее проваленный parent синхронизирован повторно до успешного COMMITTED |
| Новый 2027 после трёх успешных commits 2026, отказ и retry | 1 | Parent повторно синхронизирован; прежний год и его активный снимок сохранены |
| Настоящий SIGKILL между mkdir(root) и parent fsync, затем новый запуск | 1 | Retry повторяет sync родителя; нет прежнего пропуска шага |
| Неправильные/отсутствующие pinned SHA для current и ancestor | 24 | Отказ; корректные pins обоих поколений также проверены |
| CURRENT missing/JSON/type/hash/ID corruption | 8 | Fail-closed/UNKNOWN/RECOVERY_REQUIRED, новых записей нет, bytes архива неизменны |
| Каждый fsync на первом WB import с отсутствующим root | 63 | Каждый искусственный отказ прерывает вызов; успешного возврата COMMITTED нет |
| Каждый fsync на WB update после трёх commits | 63 | То же; старые поколения побайтово неизменны, active целиком old/new |
| Настоящий SIGKILL на declared checkpoints WB/Ozon first/update | 32 | До commit — прежний active/UNKNOWN при первом импорте; после — целиком новый ACTIVE_VERIFIED |
| Два отдельных процесса-писателя | 2 | Пустой store и store после трёх commits: один победитель, второй stale; lost update нет |
| Детерминированный reader через переключение CURRENT | 1 | Reader взял pointer A, был остановлен перед чтением generation; после commit B вернул целиком A; следующее чтение вернуло B |

В 201 не включены дополнительные сравнительные before/after записи исходных G1–G4 на `0217ba4` и текущей реализации. Они подтверждают старые контрпримеры и сохранение исправлений: неподтверждённый candidate публично отклоняется даже с верным SHA, missing CURRENT не выдаёт ложных uncommitted, repacked parent/подложный pin блокируются, нормальная parent-sync трасса полная.

63 — фактическое число вызовов fsync в конкретном WB запуске на этой scratch-структуре. Это не универсальная константа для иных путей/систем и не утверждение о проверке всех возможных IO ошибок. В fault injection использован EIO, а не перебраны все errno.

При отказе последнего directory fsync ПОСЛЕ атомарной замены CURRENT pointer может уже выбирать новый целый снимок. Корректный результат — CommitUncertainError и reconciliation, а не утверждение «ничего не записано». Протестирован запрет успешного возврата COMMITTED при исключении, не невозможность появления нового pointer после любой ошибки. Это важная граница формулировки «COMMITTED невозможен».

## Анализ исправления

`generation_store.py::_ensure_scope_durable`, строки 284–308: теперь обходится вся абсолютная цепочка, а не только отсутствующая часть; `folder.parent` и сам folder синхронизируются на каждой попытке. Существование директории больше не признаётся durability evidence. FileExistsError от конкурирующего initializer перехватывается с дальнейшей проверкой directory и sync — это соответствует проверенному первому concurrent import.

Первоначальный G4-R1 сценарий из предыдущего review повторён на всех пяти прежних уровнях и дополнительно generations. Во всех шести теперь `previously_failed_parent_retried=true`. Для new-year и initializer kill также true. После сбоя initializer больше не удаётся получить успешный commit, пропустив прежний обязательный parent-sync в этих проверенных сценариях.

G1–G3 source diff не меняет публичные readers/lineage/pin validation; поведенческие regressions повторены. Private candidate `_read_generation` остаётся внутренним валидатором, не публикуемым финансовым reader. Общая проверка CURRENT-anchored цепочки и digest не ослаблены.

## Артефакты и воспроизведение

- [Основной независимый harness](evidence/b7_g4r1_review.py), [результаты](evidence/b7_407d144_results.jsonl).
- [Отдельный concurrency harness](evidence/b7_407d144_concurrency.py), [результаты](evidence/b7_407d144_concurrency_results.jsonl).
- [Stock runner](evidence/b7_407d144_run_stock.py), [stdout](evidence/b7_407d144_stock_tests.txt).

Основной harness: `python3 -B b7_g4r1_review.py --checkout /path/to/407d144 --before /path/to/0217ba4`. Concurrency harness: `python3 -B b7_407d144_concurrency.py --checkout /path/to/407d144`. Fixtures создаются в scratch возле harness и удаляются; TMPDIR штатного runner также направлен в scratch. Сеть и DNS запрещены audit hook, включая дочерние процессы. Импортируются только pinned modules и синтетические fixture builders выбранного checkout; проверки/assertions независимые.

GitHub check-runs точного SHA прочитаны completed/success offline-tests/windows-ps51-parse/gitleaks. Локального PowerShell 5.1 запуска нет; GitHub Actions вручную не запускались. Локальные 92 tests — самостоятельное исполнение Python, не пересказ CI.

## Оставшиеся задачи и границы

1. Следующий блок должен перевести importer/verify/CLI/ingest и внешних читателей на единый pin; старый layout по-прежнему не получает атомарность автоматически.
2. Recovery — отдельный локальный, идемпотентный, журналируемый протокол под lock/CAS с доверенными anchors и сохранением неизвестного commit evidence. Не пересчитывать SHA повреждённого источника, не выбирать последнее по UUID/mtime.
3. F01–F24 целиком ещё не закрыта: миграция, прерывания самого recovery, retention/cleanup и FS-specific power loss проверяются отдельно. Пределы памяти и стоимость проверки длинной lineage остаются задачами до эксплуатации.
4. Новый initializer синхронизирует существующие предки вплоть до `/`, причём повторяется при инициализации scope и generations. Корректность retry в этой среде проверена; перед будущей установкой нужны подтверждение поддержки directory fsync выбранной FS и оценка стоимости/области синхронизации. Это эксплуатационный вопрос, не новый блокирующий дефект данного offline core; текущую проверку не расширять на произвольные FS.

Службы/Redis/реальные API/credentials/рабочий архив не затрагивались. Нет merge/deploy/новых каналов. Только собственная review-ветка, docs/evidence/Skill и ответ коллеге.
