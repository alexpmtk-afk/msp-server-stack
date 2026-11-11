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


## Strict-umask partial recovery — 11 November 2026

Second owner invocation reached activation preparation but failed at trust(DROP.parent,0755). Launcher uses umask077, so mkdir(...,0755) created0700. No executor start/API entry: unit still last started9Nov, no drop-in, network denied; exact partial snapshot `/var/lib/msp-ozon-final.esz6i2qs` and empty executor state retained. Fix finalizes new directory mode explicitly; recovery accepts ONLY this pinned old payload (manifest1f40f499ed24c79771a63fb5e0a3f6e1fda02307a08c6ff55722ea5a10d925dd), matching minimal credential/plan, exact empty0711 state and empty root0700 drop directory. It changes only that literal directory mode, preserves prior snapshot/secrets and never deletes/resets any journal or consumed entry. Any state file/changed payload/foreign control HOLD. 16 network-denied tests PASS, including actual umask077 regression and exact empty-state recovery/tamper refusal. Revised artifact is PREPARED, not installed or provider-verified.


## Existing unit approval condition — 11 November 2026

Third owner invocation produced public HOLD_NO_WORKER_RECEIPT, entry_consumed=false, cleanup=true. Live systemd DBus Conditions showed WB approval.json requirement remained unmet; ConditionTimestamp11Nov09:11, no new ExecMainStartTimestamp. No provider dispatch. Exact skipped receipt SHA229e8b8ae9a631b92e91ba9a158b2dc363a2ef73307b9e7e37fc6e23e06ce87c and snapshot `_impcshq` manifestf4cf55dcf1064c37a20e0fa4de679f83b94525a3fe6732858b6a17eca158b604 pinned. New override resets condition list, explicitly reinstates archive-directory guard and points approval condition to this Ozon attempt. Does not create WB API approval.

Real unprivileged systemd fixture reproduced skipped base condition, then ran a harmless marker worker with identical replacement condition; PASS, zero provider calls, no root executor changes. RemainAfterExit=yes is used ONLY by fixture to retain properties for observation (inactive oneshots can be garbage-collected and show reset properties); actual executor remains oneshot/no restart. 17 network-denied tests PASS. Startup stderr retained privately with sanitized error class/executor fields exported when worker result missing. Recovery accepts only pinned skipped receipt + verified payload + empty state + absence of cleaned credential + no foreign controls; atomically archives original receipt under condition-skipped suffix, preserving it and all prior evidence. Any prior state file or altered receipt HOLD. Revised root artifact PREPARED_NOT_EXECUTED.


## Ozon pilot VERIFIED; closed-month history PREPARED —11.11.2026

Actual January2026 Dmitrieva realization:151unique rows,200,raw/CSV hash/date/value checks, read access and restored inactive isolated unit confirmed. Originalpilot collected, not allOzon finances. Fixed30JanOct report campaign prepared in `ops/ozon-history-20261111/STATUS.md`, verifiedpilot reused withoutHTTP, max29newsendentries, same executor/sharedRedis/controllerlock; one deterministic nonblocking root supervisor, noLLM/timer/newqueue. Nine network-denied tests PASS on3.14/3.12 and actual151-row offlinepublication roundtrip PASS (zero productionwrites/API). Package reproducible and one-line launcher ready; NEW ROOT LAUNCH NOT EXECUTED. After operator launch read exact public ozon-history-2026 receipt and reconcile all3 canonicalannualscopes before complete. Shareddefault-profile instruction installed: docs/data-sources/OZON_FINANCIAL_REPORTS.md. Daily/currentWB andNovember excluded.


## Actual six-cabinet reading VERIFIED; Ozon collection COMPLETE —11.11.2026

Independent read audit source/result: `ops/marketplace-access-audit-20261111/`. Consumed all6WBmain/buyout archives fully with raw-value/hash checks, selectedOctober380/5276/2569rows(Dmitrieva/Laser/Novokshenov). Verified all30Ozonraw/staged/published monthly snapshots and pinned receipts against three annual business-value unions;1724/9167/3313annualrows,150/878/476Octoberrows. Realreceiver identities matched. No newAPIrequests or sourcewrites. Backgroundhistory rootunit successful/inactive; workerinactive/privateNetworkyes/noDropIns. CollectionJanOctrealization complete, readingwithoutroot proved. Canonicalsource updated. This doesnot prove unrestrictedwebcabinet/allAPI/allperiod access or allOzonexpense coverage; WBdaily/current and OzonNovember excluded.


## Ozon semantics sources —11.11.2026 PARTIAL

Official SellerEducation source located but actual browser403/redirect challenge prevents currentarticletext; not read. Historic primarymoderator evidence + attributedschemamirror + real30reports establish46 observedfieldbindings,14204rows,14525populated-block observedidentity checks. Practical guide and sourceflags installed, but currentnormativeformulas/fullXLSX mapping remainpending. Importantcorrection: monthlyOzon reportdoesnot give arbitrarydailysales; orderdate isnotrealizationdate. No money/source/API/scheduler changes. Canonical: docs/data-sources/ozon-financial-reports/; evidenceacceptance: ops/ozon-report-semantics-20261111/PROVENANCE.md.


## Ozon official PDF reconciled —11.11.2026

Owner-provided official six-page realization article read including illustrations; linked official XLSX confirms closing totals C28=F24-J24 and C29=G24-K24. Canonical guide and46-field map updated, source-reconciliation.json records SHA256/scope. Full source copies retained only on server. Closing document is distinct from downloaded posting API; API total remains empirical, not normative. Daily endpoint subscription/32-day limitation documented, not enabled or called. No source-report/API/root changes. Shared default-profile read entrypoints updated.


## Owner replaces Ozon primary source with accruals —11.11.2026

Realization-only30/30 does NOT complete desired Ozon financial base. Retain old files as separate reference, never sum overlapping sources. New permanent JanOct accrual scope30cabinet-months/912cabinet-days, Dmitrieva→Laser→Novokshenov; November excluded. Lossless candidate reader handles POSTING/ITEM/NON_ITEM/CONTAINER_FEES and unknowns, raw preserved, Decimal, no aggregate-of-all-money-fields. First pinned root package in ops/ozon-accruals-20261111: only types+January15FIRSTpage forDmitrieva, max2sendentries, same existing worker/controller/Redis, no timer/LLM/globalflag.35network-denied testsPASSon3.14/3.12 incl mockedcapture and bootstrap/unknown-outcome cases. PREPARED_NOT_EXECUTED; currenthermesUID1001 no passwordlessroot. Fullmonth/backfill/coverage/reconciliation not executed. Current detailedschema from attributedMissiaL mirror; primaryOzon2008 confirms bydayallaccruals and typespurpose. Emptylast_id is only candidateexhaustion, not proven financialcoverage. Read actualrootreceipt before retry; retain originalbudgets/raw onHOLD. Shareddefaultsourcepriority updated.


## Actual accrual capture VERIFIED; January month PREPARED —11.11.2026

Owner rootcommand succeeded. Independentraw HTTP200/digest validation:138types and15Jan15accruals forDmitrieva,ITEM10/POSTING4/NON_ITEM1;10observedtypeIDs all known. Acquiring/logistics/returnprocessing/storage and generalfees actuallypresent. Workerinactive/PrivateNetworkyes/noDropIns; originalcapture complete as capture ONLY, not verifiedfinancialcoverage. New ops/ozon-accrual-month-20261111 package prepared: fixedDmitrievaJan2026 all31days, exacttypes/day15seeds reused withzeroHTTP, max128newentries/10pagesday, existingquota/worker/controller, no timer/LLM.14networkdenied testsPASSon3.14/3.12 incl actual15rowseedreplay and fullmocked31dayCSVroundtrip. Newmonth ROOT NOT EXECUTED. Emptylast_id remains candidateexhaustion; aftercollect statusMONTH_COLLECTED_NOT_RECONCILED notCOMPLETE. Must reconcile actualcabinetexport before all30months. Originalrealization unmodified and not taskcompletion.


## January accrual collection actually complete as capture, external reconciliation pending

DmitrievaJan2026 all31candidate days/728rows(POSTING205/ITEM447/NON_ITEM76). Independently replayed30newHTTP200 retained pages + exactJan15seed; matched allnested sourcevalues to monthCSV, unique(day,accrual_id)keys, datecoverage, percurrencyDecimalnet and metadatahashes. ZeroAPIcalls duringaudit; no lostunknownfields/types/overlaps. monthCSV SHA7089e1dca18b155e8f9e5e4155d8bbd9c86849f18e391cab1db6f2c6ae42d68e. Worker/supervisorinactive and isolationrestored. NOT verifiedfinancialcoverage: await independent JanuarycabinetXLSX accruals+compensationsbyproduct (not realization). Uploadfolder /home/hermes/workspace/ozon-accruals-20261111/incoming/. WholethreecabinetJanOcttask notdone. Observeralreadydeclaredbygenericdataregistry; receipt MONTH_COLLECTED_NOT_RECONCILED mapsreview, notdone; norestart or newbackground task needed. Evidence ops/ozon-accrual-month-20261111/actual-month-validation.json and verify_month.py.
