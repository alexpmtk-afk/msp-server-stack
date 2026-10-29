# Передача ChatGPT ↔ Hermes

Дата: 28.10.2026. Инициатор: ChatGPT. Hermes пока не подключён к выполнению задач из-за лимитов.

## Обязательная схема
Одна актуальная ветка main после принятия PR; все незавершённые работы живут в конкретных PR/ветках. Перед новой работой перечитать `PROJECT.md`, `DECISIONS.md`, этот файл и `docs/MSP_GITHUB_VPS_WORKFLOW.md`. Старые сообщения чата и локальная копия VPS не являются более свежим источником, чем проверенный GitHub commit + deployment manifest.

## Текущая работа
- Репозиторий: `alexpmtk-afk/msp-server-stack`.
- Ветка: `feat/msp-marketplace-report-archive-20261028`.
- Изменения: локальный CSV архив, чтение/проверка, контрольные суммы, локальный импорт, годовая сборка Ozon, тесты.
- Статус на момент подготовки: не слито в main, не установлено на VPS, реальные API/кабинеты не проверены.
- Лог новых этапов и принятых решений писать сюда в собственном PR, не перетирать чужие записи.

## Границы полномочий
Hermes/ChatGPT могут разрабатывать, проверять, коммитить и открывать PR. Слияние и установка на VPS требуют явного отдельного согласования. Значения токенов/личные отчёты не публиковать. Когда Hermes будет доступен, первым делом поручить только чтение локальной среды: свободное место, права папок, наличие (да/нет) каждого из шести credentials и отсутствие конфликтующих служб. Только после принятия PR — установку.

## Проверка источников
Старый `alexpmtk-afk/marketplaces-mcp-ru` использует Google Drive как канон. Его текущие API-контракты могут быть полезны, но переносить код с Google-зависимостями целиком нельзя. Ничего не изменять в старом проекте.

## Финальный отчёт
Раздельно: созданная ветка/PR, код и тесты, состояние main, VPS и реальный API-доступ. Никогда не писать PASS по VPS/кабинету без подтверждённого выполнения.

## Подтверждения 28.10.2026
- Черновик PR: https://github.com/alexpmtk-afk/msp-server-stack/pull/89 (без слияния и установки).
- GitHub-hosted `MSP Marketplace Reports Offline Tests`: PASS на подготовительном коммите `3b11d197e6f15fbbf20991a422648a6550f1a43f`, Secret scan PASS. Последующие изменения должны получить собственную проверку.
- Разрешённый read-only канал `[REMOTE] status`: https://github.com/alexpmtk-afk/msp-server-bridge/issues/717; результат PASS, 2026-10-28T09:07:42Z: VPS VM-817589, 58G диск, 20G занято, 38G свободно; /opt/mcp существует. Этот результат не подтверждает права каталога, наличие ключей или развертывание новой системы.
- Не путать этот VPS с историческим Marketplaces MCP сервером VM-684381.

## Обновление 28.10 — после подтверждения владельца, что реквизиты всех кабинетов имеются
- В эту же рабочую ветку и PR №89 добавлены `apps/msp_marketplace_reports/providers.py` (строгие read-only схемы WB/Ozon), `runtime.py` (фиксированные URL, безопасный файл реквизитов, локальный ограничитель запросов), `ingest.py` (ручная пробная загрузка одного WB отчёта / месяца Ozon и Ozon CURRENT), отдельные испытания пагинации и защиты секретов.
- НИ ОДИН реальный API вызов, запись на VPS или перенос токенов на момент этой фиксации не выполнялись.
- `ingest.py` не следует использовать для массового производственного обновления до регистрации COMPLETE покрытия и восстановления после сбоев; CURRENT и FINAL записи пока не являются многофайловой транзакцией.
- Следующие обязательные проверки: проверка новой версии CI; проверка отсутствия токенов в Git; read-only аудит местонахождения ключей и реального сервера; проверка квот и полей ответа одного WB/Ozon кабинета.

## Подготовка безопасной передачи токенов с Windows — 28.10.2026
- Владелец подтвердил: токены WB/Ozon доступны **только на его локальном ПК**.
- Подготовлены `scripts/windows/Send-MspMarketplaceTokens.ps1` (ввод девяти значений скрыт, JSON только в памяти, SSH stdin) и `scripts/remote/msp_reports_credentials_receiver.py` (получение как root, файл `0600`, каталог `0700`, запрет перезаписи без `--replace`, закрытая резервная версия).
- Подробная инструкция: `docs/marketplace-reports/CREDENTIAL_TRANSFER.md`. Тесты: `tests/test_msp_marketplace_receiver.py`. Секреты в GitHub отсутствуют; передачу ещё НЕ выполняли.
- НЕ использовать Hermes для ввода токенов; требуется лишь разрешённая установка приемника и доверенный SSH-доступ с ПК владельца.
- После загрузки отдельно согласовать ограниченный доступ конечного сервисного пользователя к защищённому файлу: в режиме `root:root 0600` непривилегированный процесс не сможет читать ключи. Не делать `chmod 644`.

## VPS: результат проверки от владельца, 28.10.2026
- Прямой запуск владельцем безопасной Bash-проверки через WinSCP/консоль: `HOST=VM-817589`, `USER=root`, `/opt/mcp` существует, `/opt/mcp/secrets` существует, `/opt/mcp/secrets/msp-marketplace-reports/cabinets.json` отсутствует, `sudo -n` доступен.
- Это проверка наличия и полномочий, не установка и не подтверждение получения токенов.
- Следующий шаг: создать отдельный root:root каталог `msp-marketplace-reports` с режимом `0700` и проверить `stat`; результат ожидается от владельца. Не считать выполненным заранее.

## VPS: подтверждение защищённого каталога владельцем 28.10.2026
- Владелец выполнил `stat` непосредственно на VPS; ответ: `OWNER=root;GROUP=root;RIGHTS=700;TYPE=directory` для `/opt/mcp/secrets/msp-marketplace-reports`.
- Каталог существует с ограниченными правами. **Отсутствие файла ключей проверялось ранее; сами ключи на сервер не переносились.**
- Следующий шаг: проверка доступа к пустому каталогу через WinSCP, без загрузки реквизитов на этом шаге.

## Проверка терминала 28.10.2026
- Владелец выполнил `test -t 0` и дважды получил `INTERACTIVE=NO`, в том числе после рекомендации открыть PuTTY. Следовательно, режим интерактивного ввода `--interactive` пока нельзя использовать — не пытаться вводить секреты в видимый ввод Bash.
- Безопасная альтернатива уже подготовлена в ветке: `scripts/windows/Send-MspMarketplaceTokens.ps1`, передаёт JSON из памяти Windows в `stdin` SSH с `-T` (без требования TTY); серверный `scripts/remote/msp_reports_credentials_receiver.py` принимает поток. Нужны разрешённое развертывание приёмника на VPS, проверенный SSH-доступ с Windows, сверка отпечатка сервера и проверка отсутствия логирования секретов.
- Следующее действие: проверить наличие штатного `ssh.exe` на Windows, без обращения к токенам. Ничего не утверждать о переносе, пока не получен факт установки файла с ограниченными правами и подтверждённая безопасная проверка.

## Проверка Windows OpenSSH
- Владелец выполнил в локальном Windows PowerShell `Get-Command ssh.exe`; результат `SSH_WINDOWS=YES`.
- Следующий шаг — подключиться из Windows PowerShell к *известному из WinSCP* VPS через `ssh -tt -p <PORT> <USER>@<HOST>`, сверив отпечаток сервера при первом контакте; после подключения проверять `hostname`, `whoami`, `test -t 0`. Секреты не вводить до подтверждения защищённого терминала и согласованной установки приёмника.

## Подтверждён вход Windows PowerShell → VPS по ключу (28.10.2026)
- Владелец проверил `ssh -i ~/.ssh/msp_remote_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -p 22 root@<адрес VPS> "hostname; whoami"`. Ответ: `VM-817589`, `root`. SSH-авторизация по существующему ключу PASS, пароль не требуется. IP сервера в публичный репозиторий не добавляем.
- Исправлен Windows-отправитель: теперь требует явный `-IdentityFile` и ожидает размещённый оператором приёмник `/root/msp_reports_credentials_receiver.py`, а не ещё не установленный checkout `/opt/mcp/projects/msp-server-stack`.
- Следующий шаг: скачать фиксированную проверенную версию серверного приёмника (без ключей) и передать через защищённый WinSCP или scp в `/root`, затем выполнить `--check`. Наличие файла и импорт секретов не утверждать до фактической проверки.

## Серверный приёмник передан по SCP (28.10.2026)
- Windows PowerShell: владелец выполнил SCP с действующим отдельным ключом `msp_remote_ed25519` от локального файла `msp_reports_credentials_receiver.py` в `/root/msp_reports_credentials_receiver.py` на VM-817589; SCP сообщил 100%, 9495 байт, exit без ошибки.
- **Пока не проверены** Git blob SHA (`6392a2ceabfe5b1890ca2667028ee38a07eb073d`) на VPS и `python3 /root/msp_reports_credentials_receiver.py --check`. Никаких секретов в чат не передавалось.
- Следующий шаг: оператор выполняет только проверку целостности и `--check`; при любом FAIL не вводить реквизиты.

## Приёмник: предварительная проверка прав — FAIL (28.10.2026)
- Владелец запустил на VM-817589 `git hash-object /root/msp_reports_credentials_receiver.py` и `python3 ... --check`.
- Результат: `FILE_CHECK=PASS` (эталон Git blob `6392a2ceabfe5b1890ca2667028ee38a07eb073d`), затем `ERROR=secrets parent directory unsafe`.
- Скрипт требует: `/opt/mcp/secrets` — обычный каталог (не ссылка), владелец root, отсутствует групповая/общая запись (режим & 0022 = 0). Существующий `msp-marketplace-reports` ранее подтверждён как root:root 0700.
- **НЕ изменять права `/opt/mcp/secrets` вслепую**, там могут располагаться секреты других служб. Оператору запрошена только безопасная диагностика `stat -c 'OWNER=%U;GROUP=%G;RIGHTS=%a;TYPE=%F' /opt/mcp/secrets`.
- Перенос ключей НЕ начинался, защитные проверки сработали штатно.

## Причина отказа приёмника и решение (28.10.2026)
- На VPS `FILE_CHECK=PASS` для первой версии приёмника (Git blob `6392a2ceabfe5b1890ca2667028ee38a07eb073d`), но `--check` выдал `ERROR=secrets parent directory unsafe`.
- Владелец проверил `stat /opt/mcp/secrets`: `OWNER=hermes;GROUP=hermes;RIGHTS=700;TYPE=directory`. Это защищённый каталог другого проекта; **не менять владельца и права**.
- В PR №89 изменён канонический путь нового архива с `/opt/mcp/secrets/msp-marketplace-reports/cabinets.json` на `/etc/msp-marketplace-reports/cabinets.json` (при создании root:root 0700/0600). Данные и службы Hermes не затрагиваются. Версия приёмника, которую пользователь ранее скопировал в `/root`, УСТАРЕЛА и требует замены и повторной проверки.
- Следующий шаг: проверить `stat /etc` на сервере без изменения файлов. Затем заменить программу в `/root` строго новой версией и выполнить `--check`. Секреты ещё не передавались.

## VPS: безопасный системный каталог подтверждён (28.10.2026)
- Владелец выполнил `stat /etc`: `OWNER=root;GROUP=root;RIGHTS=755;TYPE=directory`. Проверка каталога-родителя нового `/etc/msp-marketplace-reports/cabinets.json` — PASS (нет права записи для группы/прочих).
- Оператору предложено из Windows обновить `/root/msp_reports_credentials_receiver.py` с фиксированного коммита `6eaf17f9013be799454434ef49835fdede785a18`; ожидаемый Git blob SHA нового файла: `a721cff3cf6531874613ffba547cc8e77600d6ab`.
- Пока не подтверждена передача новой программы, `--check` нового хранилища и наличие ключей; запрещено запускать старую версию для приёма секретов.

## VPS: новая версия приёмника передана через SSH (28.10.2026)
- Владелец выполнил загрузку обновлённого приёмника из коммита `6eaf17f9013be799454434ef49835fdede785a18` через SCP в `/root/msp_reports_credentials_receiver.py`; вывод: `100% 9483` байта, без ошибок.
- Новая версия использует `/etc/msp-marketplace-reports/cabinets.json`, не `/opt/mcp/secrets` (который принадлежит Hermes).
- Следующая проверка владельцем: `git hash-object` должен дать `a721cff3cf6531874613ffba547cc8e77600d6ab`, затем `python3 /root/msp_reports_credentials_receiver.py --check` должен вернуть `RECEIVER_READY=YES;SECRETS_RECEIVED=NO`.
- Пока результаты проверки на VPS не получены. Реальные токены не передавались, сервисы не запускались.

## VPS: приёмник прошёл обе проверки — 28.10.2026
- Пользователь выполнил на VM-817589 проверку установленной в `/root/msp_reports_credentials_receiver.py` программы: `FILE_CHECK=PASS` против Git blob `a721cff3cf6531874613ffba547cc8e77600d6ab`.
- Результат проверки `python3 ... --check`: `RECEIVER_READY=YES;SECRETS_RECEIVED=NO`.
- Подготовительный корневой каталог `/etc` проверен отдельно как `root:root 755`; приёмник готов сам создать `/etc/msp-marketplace-reports` (root:root 0700) и файл (0600) при успешном приёме.
- **Реальные девять реквизитов пока не переданы**. Следующий этап: скачать Windows-отправитель `scripts/windows/Send-MspMarketplaceTokens.ps1` с закреплённой версии GitHub и отдельно подтвердить скачивание. Только затем запускать его через уже проверенный ключ `msp_remote_ed25519`. Не показывать и не присылать реквизиты.

## Windows: отправитель скачан владельцем (28.10.2026)
- В локальном Windows PowerShell скачан `Send-MspMarketplaceTokens.ps1` из фиксированного коммита `a3302966005e905d21d470d55d7b99cc5d0ac182`, результат `Name=Send-MspMarketplaceTokens.ps1;Length=5621`.
- Подготовлен следующий шаг: локальный запуск из Windows PowerShell с подтверждённым ключом `msp_remote_ed25519` и `root` на VPS VM-817589. Программа сначала делает удалённый `--check` без реквизитов, затем скрыто запрашивает 3 токена WB и 3 пары Client-Id/API-Key Ozon.
- **На момент этой записи фактический запуск отправителя и передача реквизитов не подтверждены.** После выполнения просить у владельца только безопасный итог `RESULT=...`, не сами значения.

## Windows PowerShell: ошибка разбора кодировки и исправление (28.10.2026)
- Владелец запустил локальный `Send-MspMarketplaceTokens.ps1` (5621 байт), который в Windows PowerShell 5.1 завершился `ParserError`: `Missing closing ')'`, `The string is missing the terminator` и `Try statement is missing its Catch or Finally block`. **Исполнение не началось, секреты не запрашивались и не передавались**.
- Причина вероятнее всего: скачанная версия `.ps1` содержала русские подписи UTF-8 **без BOM**, которую Windows PowerShell 5.1 при `-File` мог декодировать как системную кодовую страницу; ошибки строк/скобок — типичный эффект неправильного прочтения типографических символов.
- Исправление в PR №89: UTF-8 BOM добавлен в `scripts/windows/Send-MspMarketplaceTokens.ps1`, Git blob `21780de414e2d211f1b84dd97b39feefa135bf5d` (коммит `584332413e606b26baee5f9ed5becc8e8d0252c4`). Добавлена проверка синтаксического разбора настоящим Windows PowerShell 5.1 в GitHub Actions (`0f989711aec22967e79a9ace3b9df33c2242a8f3`).
- Дальше: после PASS теста Windows скачать новую версию с закреплённого коммита, проверить BOM (первые байты EF BB BF), сначала отдельно выполнить разбор `Parser.ParseFile` без запуска и только затем запускать безопасный отправитель. Старая копия в Downloads подлежит замене. Приёмник `/root/` на VPS уже проверен и не менялся.

## Finance API integration check (2026-10-28)
- A manual read-only WB list trial returned HTTP 400 (Bad Request); no financial data was stored.
- Published API schema confirms the request path, POST method, weekly period, date-only format and limit=10 are supported; the reason for the 400 remains unknown without provider error details.
- Do not make rapid retry calls; at most one per minute per seller. No credentials should be added to this document.

## WB API trial: response parsing failure (2026-10-28)
- Second manual trial of WB sales report list produced `JSONDecodeError: Extra data: line 1 column 5`. The script expected JSON and therefore failed before displaying the HTTP status or error category. Ubuntu apport printed a secondary unrelated exception for `-c`. No report was stored and no token value appeared in captured output.
- Official WB finance API documentation specifies POST `/api/finance/v1/sales-reports/list` with JSON body containing `dateFrom`, `dateTo`, optional `period`, `limit`, `offset`; supplied request syntax appears consistent. Root cause of HTTP 400 remains unconfirmed.
- Avoid retrying immediately because the endpoint permits one request per seller per minute. Next diagnosis: first inspect *presence only* of HTTPS/ALL proxy settings on VPS (without printing URLs); then, if necessary, classify response type and status from one bounded retry without printing body or credentials.

## Potential geo-based access restriction, October 28 2026
- Operator checked urllib proxy detection on VM-817589: HTTPS_PROXY_CONFIGURED=NO; ALL_PROXY_CONFIGURED=NO; TARGET_PROXY_BYPASS=NO.
- Operator hypothesizes foreign German datacenter IP may trigger WB network filtering. This is NOT confirmed by current HTTP 400 or non-JSON body.
- Historical evidence: official Wildberries API announcement once said incoming API data from outside Russia was temporarily disabled and later resumed (https://t.me/s/wb_api_notifications/151). Does not prove an active geo restriction on 2026-10-28.
- Previous query syntax aligns with published API schema. Next safe step: diagnose response metadata and body type without displaying body, credentials or marketplace data, and avoid tight retries. Do not alter infrastructure / route until evidence establishes network-level rejection.

## 2026-10-28 WB finance API: response envelope diagnosis
- User ran one read-only POST /api/finance/v1/sales-reports/list on VM-817589: HTTP=400; BODY_TYPE=PLAIN_TEXT_OR_OTHER; CONTENT_TYPE=TEXT; BLOCK_HINT=NO. Therefore response was not normal documented JSON error object; geographic filtering is still an unproven hypothesis.
- Previous urllib.getproxies() check: HTTPS_PROXY_CONFIGURED=NO; ALL_PROXY_CONFIGURED=NO; TARGET_PROXY_BYPASS=NO. No configured proxy; cannot exclude provider's gateway/firewall.
- Published WB API docs confirm POST body dateFrom/dateTo, period=weekly, limit<=1000, offset=0 and specify that account balance GET /api/v1/account/balance is a separate read-only Finance-category method.
- Next diagnostic: a single authorized GET to /api/v1/account/balance for the same cabinet, display only HTTP status and response content-type class (do NOT print balance, financial JSON, tokens). If this also fails with text/plain 400, network/host-level rejection becomes more plausible; if GET works, focus on reports method or token scope. Observe WB request limits.

## 2026-10-28 Wildberries second-method trial
- The operator tested authorized `GET https://finance-api.wildberries.ru/api/v1/account/balance` against cabinet `wb_laser_master` from VM-817589, printing only status and type. Result: `TEST=WB_BALANCE;HTTP=400;CONTENT_TYPE=TEXT`.
- Together with finance sales-reports/list repeated `HTTP=400;BODY_TYPE=PLAIN_TEXT_OR_OTHER;CONTENT_TYPE=TEXT`, the evidence points to a problem common to both finance methods. Geo/IP policy, API gateway, or shared authentication formatting remain competing hypotheses. No proof of a geo-block or of token expiry.
- Official WB docs: JWT metadata locally includes `exp` timestamp and `s` permission bitmask (Finance = position 13). Next recommended step: inspect only expiry/category flags *offline*, without copying tokens or issuing more API requests. JWT payload decoding alone does not validate signature, revocation, actual permissions or account status. No provider reports downloaded.

## 2026-10-28: локальная проверка JWT — ошибка диагностической команды
- Команда для проверки JWT выдала `TypeError: unsupported operand type(s) for &: 'NoneType' and 'int'` в Bash консоли WinSCP. Это означает, что при проверке у `wb_laser_master` заявленное поле `s` было `None` или отсутствовало. Неправильный порядок проверки типа в предложенном тернарном выражении вызвал ошибку. При такой проверке запросы к WB не выполнялись и файл секретов не изменялся.
- Исправленный вариант сначала проверяет, что `s` целое число, затем применяет маску `1<<12` (позиция 13 — Finance), при отсутствии возвращает `UNKNOWN`. Аналогично обрабатывает отсутствующий `exp`. Нельзя выводить JWT, содержимое payload или персональные идентификаторы. Структура JWT не подтверждает подлинность или статус у WB.

## WB token syntax offline test (2026-10-28)
- On VM-817589, local read-only JWT metadata check for `wb_laser_master` returned TOKEN_FORMAT=OTHER, TOKEN_TYPE=UNKNOWN, FINANCE_SCOPE=UNKNOWN, EXPIRED=UNKNOWN, S_CLAIM=MISSING_OR_NONNUMERIC.
- These UNKNOWN values follow from the non-JWT structure; do not infer expiry, Finance permissions or geo-block from them. Earlier Finance host requests returned 400 text/plain from the same cabinet.
- WB official documentation describes API tokens as JWT and requires Personal/Service with Finance permission for finance reports. Next: offline-only structure classification for all three WB credentials (dot segments, Bearer prefix, whitespace, length bucket), printing no token fragments, claims, IDs or secret values. No further provider calls until configuration issue resolved.

## 2026-10-28: три WB credentials имеют неверную для JWT структуру
- Локальная (без сети) проверка сервера показала одинаковые безопасные метаданные всех трёх WB полей: DOTS=0, BEARER_PREFIX=NO, SPACES=NO, LENGTH_CLASS=SHORT (<100). Исходные значения не выводились.
- Официальная документация WB API описывает токены как JWT; у типового JWT три сегмента через две точки. Соответственно сохранённые короткие строки не соответствуют структуре действующих JWT API-токенов. HTTP 400 text/plain для двух методов Finance не позволяет подтвердить геоблокировку; прежде нужно установить, почему были введены короткие значения.
- Следующий безопасный шаг: владелец проверяет СВОЙ ИСХОДНЫЙ WB API-токен (в локальном исходнике или кабинете), только по признаку двух точек, не отправляя содержимое в чат. До сверки и защищённой замены не повторять запросы WB. Ozon credentials не затрагивать.
- Уязвимость процедуры подготовки: серверный `validate_bundle` проверяет лишь наличие строк/границы длины, но не JWT-структуру WB. Перед будущим использованием укрепить валидацию и добавить тесты, чтобы эта ошибка не повторялась.

## 28.10.2026: Root cause confirmed — incorrect masked-paste input
- Operator inspected contents of `/etc/msp-marketplace-reports/cabinets.json`: all 9 credential values are a single ASCII control character `U+0016` (Ctrl+V), not actual API secrets. Values were never successfully transferred. This explains why all three WB fields were short with DOTS=0 and may account for the HTTP 400 failures. Do not attribute these responses to geography at this stage.
- Source of corruption: using Ctrl+V in Windows PowerShell `Read-Host -AsSecureString` resulted in a literal control character in each field. Original receiver validated only non-empty strings, allowing invalid values.
- In feature branch and draft PR #89: sender now immediately rejects control characters, non-JWT-shaped WB inputs and nonnumeric Ozon Client-Id; instructs right-click / Shift+Insert for paste. Receiver independently validates all 9 fields, prevents replacing existing file with invalid content. Automated tests cover Ctrl+V, WB and Ozon bad formats.
- **The VPS currently still runs the earlier receiver**, and its stored JSON still contains invalid placeholders. Both scripts must be replaced with reviewed versions before a deliberate `-ReplaceExisting` transfer. Do not use existing JSON to send provider requests.
- Upon corrected transfer, protected receiver creates a root-only backup of the previous (invalid) file and atomically replaces the active file. Never print or post new real tokens. Verify only output code, file permissions and category/format offline.

## 2026-10-28: восстановление ввода, код проверен
- Исправлены отправитель Windows и приёмник VPS. При вводе управляющих символов, включая ASCII 0x16 (Ctrl+V), передача теперь запрещена; сервер повторно валидирует источник. Введены проверки формы JWT у WB и цифрового Client-Id у Ozon.
- Коммит рабочей ветки с полным исправлением: `0970e33cebab1b5007b11666228fddce44c59faa`; контрольные суммы Git blob: Windows `.ps1` `bddd2c8dbbcda7139716b821961b062c49f562b9`, VPS `.py` `8375ab23319c9bcc5c108ee2e5378871633fc1de`.
- GitHub Actions на коммите: Linux offline tests PASS, Windows PowerShell 5.1 syntactic parse PASS, secret scan PASS.
- Следующая задача оператора: скачать обе версии из указанного коммита, передать только приёмник в `/root/` через SCP, проверить Git hash и `--check`; затем отдельно протестировать paste без секретов и отправить действительные значения с `-ReplaceExisting`. **Больше не использовать старую версию Windows-скрипта.** На VPS сейчас хранится некорректный файл с однобайтовым U+0016 в 9 полях. Никакого вызова API до исправления.

## 28.10.2026: оператор исправил кабинеты вручную, локальная проверка PASS
- В WinSCP пользователь вручную заменил все 9 некорректных реквизитов в `/etc/msp-marketplace-reports/cabinets.json` реальными значениями (секреты в GitHub не публиковались).
- Локальная проверка на VPS: `SECURITY=PASS`, `WB_FORMAT=PASS`, `OZON_FORMAT=PASS`, `CABINETS=6`. Директория root:root 0700, файл root:root 0600; у всех трёх WB полей видимая JWT-структура, у трёх Ozon комплектов формат корректен.
- Эта проверка подтверждает формат и права, не доказывает авторизацию либо наличие разрешений. Следующий шаг — единственный read-only запрос GET к WB Finance `/api/v1/account/balance` для `wb_laser_master`, печатать только HTTP/тип ответа, без данных кабинета. После успешной авторизации переходить к историческим отчётам.

## 2026-10-28: WB Лазер-Мастер successfully authenticated
- After manually correcting all nine credential fields, the operator ran read-only GET `https://finance-api.wildberries.ru/api/v1/account/balance` with `wb_laser_master`: `TEST=WB_LASER_MASTER;HTTP=200;RESPONSE=JSON`.
- Confirms that the corrected WB credential works with the account balance finance API from VM-817589. Earlier HTTP 400 responses with literal `U+0016` credentials were not evidence of geo/IP blocking. This result does not establish access to every Finance API method or other cabinets.
- Next step: one read-only POST `https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list` for 2026-10-01..2026-10-27, `period=weekly`, `limit=10`, `offset=0`. Respect 1 request/minute for this reports endpoint. Print only HTTP, JSON container type and report count; no seller financial details or token values.

## 2026-10-28: WB Лазер-Мастер weekly report list PASS
- Оператор выполнил авторизованный read-only POST `/api/finance/v1/sales-reports/list`, `dateFrom=2026-10-01`, `dateTo=2026-10-27`, `period=weekly`, `limit=10`, `offset=0`. Ответ `TEST=WB_WEEKLY_REPORTS;HTTP=200;RESPONSE=JSON;REPORT_COUNT=8`; верхний уровень действительно массив из 8 записей. Данные деталей и сам список пока не сохранены в архив.
- Обязательно учесть: `reportType=1` основной отчёт, `reportType=2` отчёт по выкупам; возвращённых записей может быть несколько за одну неделю, в т. ч. из-за разбиения на границе месяцев. Код `providers.py` сейчас **фильтрует только reportType=1**; до развёртывания проверить полный набор типов и решить, как без потерь сохранять все финансовые документы (отдельные типы/фрагменты). Не считать 8 записей восемью неделями.
- Следующий узкий тест — повторить вызов с теми же параметрами после выдержки лимита (не чаще 1/мин на кабинет), вывести только `reportType`, `dateFrom/dateTo`, без ID, ФИО и денежных полей. После — корректировать архиватор и загрузку детализации.

## 2026-10-28: подтверждены типы WB, доработан архиватор
- Реальный ответ WB Лазер-Мастер на `POST /api/finance/v1/sales-reports/list` (01–27.10.2026): `HTTP=200;REPORTS=8;TYPE_1=4;TYPE_2=4`; периоды пар: 01–04, 05–11, 12–18, 19–25 октября. Это 8 документов в 4 периодах, а не 8 недель.
- В проекте PR #89, не на VPS: `wb_discover_all` сохраняет оба типа, `wb_discover_main` оставлен как совместимый фильтр; `wb_detail` сверяет тип с исходным реестром; тип 2 архивируется в отдельном `wb_weekly_finance_buyout` (`finance/weekly/buyout`), тип 1 — `finance/weekly/main`. `wb-list` видит оба, `wb-one` направляет по типу. Запрещено без согласованной методики объединять суммы двух документов или удалять вторые как дубли.
- Тесты обновлены: оба типа, ошибка неизвестного типа, несовпадение типов в детализации, отдельные CSV и контроль целостности. GitHub Actions для коммита `19a2b13e55ea74cae4f28cc19ab1bf2f30243a24`: offline tests PASS, secret scan PASS. Код сервера ещё не устанавливался; детализации не скачивались.
- Следующий шаг на VPS: безопасно извлечь через read-only API список пар `reportType/reportId` для тестирования одного `reportType=1` методом `/api/finance/v1/sales-reports/detailed/{reportId}`; при вводе реальных данных не печатать секреты/финансовые показатели. Соблюдать лимит 1 запрос в минуту.

## 28.10.2026 — идентификаторы последних закрытых WB отчётов
- На VPS пользователь проверил `/api/finance/v1/sales-reports/list` за 19–25.10.2026 (WB Лазер-Мастер): `HTTP=200;REFERENCES=TYPE_1_ID=883801632,TYPE_2_ID=883801636`.
- Номера являются идентификаторами документов для API `POST /api/finance/v1/sales-reports/detailed/{reportId}`; соответствующие финансовые строки пока не загружены и не сохранены.
- Следующий безопасный шаг: один ограниченный read-only запрос детализации типа 1 по `reportId=883801632`, `limit=100`, `rrdId=0`, отобразить только HTTP, количество строк и результаты структурной проверки `reportId`, `reportType`, `rrdId`; не публиковать сведения о продажах, товарные поля, покупателей или токены. Сохранение полных деталей и постраничная проверка до 204 — после успешного испытания.

## 28.10.2026 — первая детализация WB успешно проверена
- Кабинет `wb_laser_master`, основной отчёт `reportId=883801632`, период 19–25.10.2026: read-only `POST /api/finance/v1/sales-reports/detailed/883801632` с `limit=100`, `rrdId=0` дал `HTTP=200;ROWS=100;STRUCTURE=PASS` (проверены `reportId`, `reportType=1`, положительные целочисленные `rrdId`).
- Ровно 100 при `limit=100` не доказывают завершения выборки. Сохранять как полный отчёт нельзя. По документации WB начинать с `rrdId=0`, на следующей странице передавать последний `rrdId` предыдущего ответа, до HTTP 204; ограничение 1 запрос в минуту на кабинет.
- До ввода в боевую эксплуатацию проверить полный постраничный обход, независимые CSV для типа 1 и 2, SHA256/метаданные, статус покрытия. На VPS пока детализация в архив не записана.

## 28.10.2026 — подготовлена одноотчётная загрузка WB (не установлена на VPS)
- GitHub feature-branch commit `29b05a19dae0138bc983dab6976fd5809e59d3c9`: `ingest.py` action `wb-one` теперь принимает подтверждённые `--report-id` и `--report-type {1,2}` и не делает повторное сканирование реестра за весь год; `wb_detail` загружает страницы по 10000 до HTTP 204 с проверкой ID/типа и курсора. Только после полной выборки записи передаются в локальный CSV с контролем SHA256. Архив типа 1 и 2 раздельный.
- CI в GitHub для этого коммита: offline tests PASS, Windows PowerShell 5.1 parse PASS, secret scan PASS. Добавлены тесты точечного импорта типа 2 и отказа при несовпадении типа. Фактическая загрузка данного отчёта на VPS пока не выполнялась.
- Следующее действие оператора: установить проверенный код как изолированную копию в `/root/msp-report-trial` с закреплением коммита и отдельно запустить точечную одноотчётную загрузку (после явной команды). Не влиять на действующие службы МСП и не сливать PR.

## 2026-10-28 — КРИТИЧЕСКАЯ ЗАЩИТА API (поручение владельца)
- Владелец напомнил строгий действующий регламент старой системы WB/Ozon: нельзя превышать лимиты и рисковать блокировкой API. До сверки регламента массовая загрузка приостановлена.
- Исходный старый код: `alexpmtk-afk/marketplaces-mcp-ru/core/rate_limit.py`, `core/client.py` и `docs/rate-limit-contract.md`; также `RATE_LIMITING.md` в архиве Drive. Старый REMOTE координирует запросы в общей очереди Redis/Valkey; WB — учёт продавца и метода/группы, Ozon — Client-Id и более строгие ограничения метода, повторные попытки/страницы проходят через ту же очередь; 429 использует Retry-After и X-Ratelimit-Retry; при потере Redis — никакого запроса (fail closed). Контроллер атомарный, независимый от обновления ключа.
- Новый `runtime.py` до доработки имел только `WB_WAIT_SECONDS=63` и `OZON_WAIT_SECONDS=5` на локальном файле по имени кабинета, не общую очередь: не гарантируется координация с другими клиентами, нет соблюдения конкретных квот методов, нет общей реакции на 429. Огромная историческая загрузка могла повторять страницы с начала после ошибки.
- **Безусловное условие допуска**: интеграция с проверенной общей очередью (или равноценный проверенный координируемый механизм), актуальные конкретные правила каждого используемого отчётного метода, выделенные ключи продавцов, атомарное резервирование ВСЕХ запросов, сохранение прогресса, ограничение размеров, 429/5xx backoff и Retry-After, тест при недоступности очереди и при параллельных запусках.
- Пока этот пункт не выполнен, в текущем `runtime.ReadOnlyHTTP.__call__` добавлен защитный блок: `API DOWNLOAD BLOCKED: shared seller/method rate controller is not verified`. Это только в ветке PR #89; на VPS старые ручные запросы не затрагиваются. Старый установочный фиксированный commit `29b05a19dae0138bc983dab6976fd5809e59d3c9` больше **не использовать для загрузки**.
- `Шаг 27` (загрузка изолированной копии и офлайн-тесты) сам по себе не отправляет запросов к WB/Ozon, но запуск `wb-one`, `wb-list`, `ozon-...` до отдельного снятия блокировки **запрещён**.

## 2026-10-28: общий Redis-контроллер подключён в ветке (без разрешения на работу с API)
- Сверен исходный код старой системы `alexpmtk-afk/marketplaces-mcp-ru`: `core/rate_limit.py` Git blob `a1f612ee6eecfd53ada28379737fd7d71a8116ca`, `core/client.py` (хешированный `sid` WB / `Client-Id` Ozon), `docs/rate-limit-contract.md`. Подтверждены атомарные Redis Lua-сценарии, общая очередь, 429 с `Retry-After` / `X-Ratelimit-Retry`, отказ при недоступности Redis.
- В PR #89 добавлен `apps/msp_marketplace_reports/shared_rate_limit.py` — канонический контроллер с сохранёнными Redis key/Lua format, и `quota.py` — адаптер для read-only финансовых API. В `runtime.py` перед каждым POST резервируются очереди продавца/метода. Для двух WB finance endpoints локально заложены консервативная группа `1 req/min` и дополнительный запас 65 сек для одного продавца; при 429 сохраняется общая пауза. Числа — защитная политика, не утверждение о квоте другого метода.
- Ключ очереди строится по WB JWT `sid`, а не строке токена или имени кабинета; у Ozon — по Client-Id. Данные продавца и секреты наружу не печатаются. Все вызовы Ozon finance в новом адаптере **заблокированы** до уточнения лимитов каждого финансового метода.
- Включение на VPS требует **обеих** предпосылок: существующий, реально общий Redis endpoint с совместимыми ключами и переменная `MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES` только после проверки инфраструктуры. Без подтверждения, Redis или его доступности — `API DOWNLOAD BLOCKED`, сетевых запросов не выполняется. Не включать до отдельной команды. Наличие Redis на новом `VM-817589` пока не проверено.
- Добавлены офлайн-тесты `tests/test_msp_marketplace_quota.py`: стабильность продавца при замене WB токена, общая группа list+detail, защита незаявленных методов/Ozon, остановка при неутверждённом Redis, 429 заголовки/HTTP-date. GitHub Actions коммита `9fecd67684cc7f9d263d57097a6763935c4ad69d`: offline tests PASS, Windows PS 5.1 parser PASS, secret scan PASS.
- **Открытые блокеры:** проверить совместимость текущей конфигурации Redis и общей очереди на VM-817589 с уже работающими сервисами, уточнить точные rate_scope финансовых методов WB в старом каталоге и лимиты всех используемых Ozon endpoints, протестировать отказ Redis и параллельную резервацию (не через живой API). Реализовать безопасные контрольные точки постраничного скачивания: сейчас `wb_detail` буферизует весь отчёт и при занятом слоте прервётся без сохранения прогресса. До устранения этого ограничение массовой загрузки остаётся в силе.
- Следующий шаг от владельца: безопасная локальная диагностика присутствия Redis на VM-817589 (без чтения/изменения настроек других служб и без запросов к маркетплейсам).

## 2026-10-28 16:56 MSK: проверка локального порта Redis на новом VPS
- Владелец выполнил read-only TCP проверку `socket.connect_ex(("127.0.0.1",6379))` на `VM-817589`: `REDIS_LOCAL=CLOSED`.
- Доказано только отсутствие принимающего подключения TCP сервиса на 127.0.0.1:6379 в момент проверки. Наличие/отсутствие пакета Redis/Valkey, контейнера, UNIX socket, альтернативного порта или отдельного сервера не установлено.
- Новую очередь Redis не разворачивать, сервисы не запускать и не менять. До установления фактического расположения общего контроллера Marketplace MCP и проверки совместимости не включать `MSP_REPORTS_SHARED_QUEUE_VERIFIED`, не запускать чтение WB/Ozon из архиватора.
- Следующий шаг: чистая локальная инвентаризация Redis/Valkey (`systemctl`, установленные бинарники, контейнеры), без чтения секретов, изменения служб и внешних API-запросов. Гермесу переданы задачи независимой проверки.

## 2026-10-28: дополнительная read-only инвентаризация Redis/Valkey VPS
- Оператор выполнил `systemctl is-active redis-server redis valkey`, `command -v redis-server valkey-server redis-cli` и необязательный поиск названия контейнера Docker.
- Результат: `SERVICE_redis-server=inactive`, `SERVICE_redis=inactive`, `SERVICE_valkey=inactive`, `PROGRAM_redis-server=NOT_FOUND`, `PROGRAM_valkey-server=NOT_FOUND`, `PROGRAM_redis-cli=NOT_FOUND`; в выводе нет `CONTAINER=...`.
- Это не доказывает отсутствия произвольно названного контейнера, Unix socket или удалённого Redis. На `127.0.0.1:6379` ранее `REDIS_LOCAL=CLOSED`.
- Не устанавливать/запускать новый Redis и не включать `MSP_REPORTS_SHARED_QUEUE_VERIFIED`: до общей очереди неизвестна совместимость со старой инфраструктурой. Запросы WB/Ozon архиватором остаются запрещены.
- Следующее действие: локальная диагностика только чтением `systemctl`/`ps`/`command -v` для возможного Marketplace MCP, Docker/Podman и Redis, без раскрытия окружения, секретов или запросов к API.

## 2026-10-29: повторная read-only инвентаризация VPS, Marketplace MCP не найден
- Оператор выполнил проверку `command -v docker podman`, `systemctl list-units --all --type=service` с отбором по `redis|valkey|marketplace|mcp`, `ps -eo comm=` с отбором по `redis|valkey|marketplace`.
- Вывод: `docker=NOT_FOUND`, `podman=NOT_FOUND`, пустые списки SERVICES и PROCESSES. Совместно с прежним `REDIS_LOCAL=CLOSED` и отсутствующими `redis-server/valkey-server/redis-cli` — нет признаков локальной общей очереди на этом VPS, но не исключён сторонний сервер или произвольно названный процесс.
- Запрет загрузки WB/Ozon через новый архиватор остаётся. Следующая безопасная проверка: список unit-файлов по `hermes|gateway|marketplace|mcp|redis|valkey` и названия подкаталогов `/opt/mcp`, без чтения секретов и изменения инфраструктуры. Не устанавливать Redis и не предполагать, что очереди уже общие.

## 2026-10-29 — ChatGPT: изолированное исправление B5, передано Hermes на независимую проверку
- Основание: независимая ревизия Hermes `REVIEW_HERMES_20261028.md` в PR #90, дефект B5 — повторное заверение повреждённого CSV. Работа выполнена отдельно от PR #89 и от ветки Hermes: `fix/msp-report-integrity-preflight-20261029`, draft PR #91, база — ветка PR #89.
- Реальное изменение: `archive.py` добавлена `_verify_previous` (проверяет существующую пару CSV+manifest, identity dataset/cabinet/period, schema/status, count, bytes, SHA256). `_import_wb` проверяет прежний CSV *до* merge; `_publish` проверяет прежнее состояние до любого no-op/replacement/snapshot (включая Ozon annual). Несогласованные и осиротевшие файлы блокируют импорт без молчаливого обновления checksum.
- Автоматизированные воспроизведения добавлены в `tests/test_msp_marketplace_reports.py`: повреждение amount WB 10→99 + новый импорт, оставшийся Ozon manifest без CSV, повреждённый Ozon annual при новой месячной загрузке. Подтверждено на коммите `0aa8d2f0cf490b7e5e5ac1662a0e53b95583ddca`: GitHub Actions `MSP Marketplace Reports Offline Tests` success (57 tests, OK; Windows PowerShell 5.1 parse success); `Secret scan` success. Никакого живого API и загрузки на VPS.
- Статус: **CODE=PASS, OFFLINE_TESTS=PASS, GITHUB_PUBLISHED=PASS, INDEPENDENT_HERMES_REVIEW=NOT_VERIFIED, MERGE=NO, VPS_INSTALLED=NO, LIVE_API=NO**.
- Границы: не закрывает B1–B4, B6–B9; в частности нет многофайловой транзакционности B7: ошибка на стадии Ozon annual может произойти после обновления monthly; восстановление и общие снимки ещё не реализованы. Это требует отдельного исправления. Защитная блокировка API сохраняется.
- Следующий шаг: Hermes независимо проверяет diff PR #91 и сценарии B5, отдельно описывает остаточные риски, отвечает на GitHub; не сливать PR без отдельного согласования.

## 2026-10-29 — ChatGPT: доработка B5 по независимой ревизии Hermes, замечания R1/R2
- Hermes на PR #91 подтвердил исправление исходного WB B5, но доказал два дополнительных дефекта: R1 — невалидная `schema` и другие поля manifest предыдущего Ozon FINAL month не блокировали импорт нового месяца; R2 — при повреждении годового Ozon final новый месяц успевал записаться до ошибки. Ссылка на разбор: https://github.com/alexpmtk-afk/msp-server-stack/pull/91#issuecomment-6489153887 . Это **подтверждённые обнаруженные дефекты**, не завершённая ранее защита.
- В отдельной ветке PR #91 ChatGPT реализовал `_verified_ozon_months`, которая проверяет полные `dataset/cabinet/period/schema/status/bytes/rows/sha256` пары каждого месяца по ожидаемому имени файла, включая найденные одинокие CSV/manifest, и `_preflight_ozon_group` под годовым lock до первой записи. Проверяется и старый annual, соответствие всем месяцам. `verify` также проверяет идентичность пути и полную схему метаданных.
- В `tests/test_msp_marketplace_reports.py` добавлены отдельные регрессии R1/R2: восемь повреждений январского metadata при импорте февраля, снимки **всех файлов** до/после отклонённой операции, повреждённый Ozon annual, сиротский январский manifest и нормальная обработка разных столбцов между месяцами.
- На кодовом SHA `8125c23831fd5877c441ff97b9d0f8e24f186882` GitHub Actions `MSP Marketplace Reports Offline Tests` **success: 61 tests OK, Windows PS5.1 PASS**; `Secret scan` PASS. Никаких запросов WB/Ozon, записей на VPS или слияний.
- **Статус: R1/R2 OFFLINE PASS, HERMES RE-REVIEW NOT VERIFIED, MERGE NO, VPS INSTALL NO, API NO.** Система не готова к эксплуатации: B7 (общая атомарная публикация нескольких файлов и доказанное восстановление), B8 (независимый обязательный inventory) и остальные B1–B9 остаются открытыми, где не доказано обратное. Повреждения и частичная публикация после аварии по-прежнему блокируются; автоматически не «лечатся» пересчётом checksum. Полное B7 recovery — отдельная задача.
- Следующий шаг: Hermes повторно проверяет PR #91 на точной опубликованной голове, reproduces R1/R2, сверяет unchanged snapshots и передаёт новые замечания в PR. Затем ChatGPT исправляет, если обнаружены ошибки.

## 2026-10-29 — ChatGPT: R3 типизация чисел JSON в финансовом manifest, после замечания Hermes

- Источник дефекта: независимая ревизия Hermes PR #91, комментарий https://github.com/alexpmtk-afk/msp-server-stack/pull/91#issuecomment-6489388997 ; Python `True == 1` позволял манифесту с `schema: true` или `rows: true` проходить проверку вместо JSON integer `1`, несмотря на неканонический тип. Hermes подчеркнул, что R1/R2 PASS, R3 отдельное унаследованное замечание.
- **Исправление выполнено ChatGPT** в `archive.py::_verify_previous`: `schema`, `rows`, `bytes` строго `type(value) is int`; bool, float (в том числе 1.0), числовые строки и null запрещены. Некорректный manifest отклоняется до любой публикации/резервной записи; та же проверка используется в `verify`, `_publish`, Ozon preflight зависимых месяцев/годового и WB merge. Остальные поля по-прежнему проверяются по значениям.
- Добавлены **три** регрессионных `test_r3_*` (11 вариантов нецелочисленных полей в Ozon CURRENT/no-op, искажённые schema/rows у чужого месячного Ozon FINAL, и annual rows:true до обновления месяца). Тесты сравнивают снимок файлов по байтам до/после отказа, проверяют `verify=False` и что нормальный no-op снова разрешён после восстановления подлинного manifest.
- GitHub Actions на кодовом коммите `bfe2ded77c00eb733baa2454cd6620d255b7f6da`: `MSP Marketplace Reports Offline Tests` **PASS, 64 tests OK**, PowerShell PS5.1 parse PASS, `Secret scan` PASS. Только искусственные CSV, ни API WB/Ozon, ни секреты, ни VPS не использованы.
- **Статус:** `R3_CODE=PASS; R3_CI=PASS; HERMES_INDEPENDENT_REVIEW=PENDING; PR91=OPEN/DRAFT; MAIN_MERGE=NO; VPS_DEPLOY=NO; LIVE_API=NO`. Не утверждать, что R3 принят Hermes, до его фактического независимого ответа.
- **B7=OPEN:** группа Ozon monthly/annual по-прежнему не обновляется транзакционно; при OSError между записью CSV/manifest возникает состояние fail-closed без автоматического восстановления. Для B7 отдельно требуется проверяемая процедура сохранения предыдущего поколения и восстановления с отказами на каждом шаге; никакой авто-пересчёт checksum повреждённого архива не разрешён.
- Дальше один рабочий цикл с Hermes: получить независимую R3 ревизию нового SHA, затем определить и реализовать B7 с разделением разработки и приёмки; о новых письменных поручениях сообщать владельцу только по завершении согласованной работы.

## 29.10.2026 — ChatGPT, первая изолированная реализация B7, PR #95

- После независимого R3 PASS Hermes (PR #91) начата разработка B7 согласно [матрице 24 категорий](https://github.com/alexpmtk-afk/msp-server-stack/blob/16f812e328473303f68bbca7ff65bc3749e8bd32/docs/marketplace-reports/B7_FAULT_TEST_PLAN_20261029.md). ChatGPT самостоятельно создал опытный модуль `generation_store.py`, тесты `tests/test_msp_marketplace_generations.py` и дополнил CI в изолированной ветке `feat/msp-marketplace-b7-generations-core-20261029`, draft PR #95 к ветке PR #91.
- Реально реализованы opt-in полный набор immutable CSV+manifest в одном поколении для WB/CURRENT и всех месячных+годового Ozon FINAL, один переключаемый CURRENT указатель, пинованный читатель, строгие JSON/type/hash/identity проверки, lock/expected parent, обнаружение потери ответа после commit, read-only reconciliation с выделением orphan и без самовольной перезаписи. Путь поколения не совпадает со старым canonical CSV layout.
- Добавлены негативные сценарии: прерывание до и после commit, испорченный pointer/generation, несоответствие Ozon annual/monthly, повтор JSON ключа, внешние пути и symlink, конфликт двух писателей, заброшенные staged поколения, read предыдущей immutable generation. На кодовом `bc7c9bb040894c3443d69ea223e5df9afdf37a40` **81 unittest OK**, Windows parse PASS, Secret scan PASS; GitHub Actions run 40863212217 и 40863212225.
- **Не реализовано:** подключение старого `archive.import_csv / verify`, `ingest`, CLI и всех CSV читателей к новым поколениями; проверенная процедура физического восстановления/удаления staged, миграция legacy, полнота fault matrix F01–F24, SIGKILL/durable power-loss. `reconcile` только обнаруживает, **не восстанавливает**. Нельзя объявлять B7 PASS. Текущий архив и server untouched.
- Развертывание / merge / API / Redis / scheduler: **NO**. Требуется независимая Hermes ревизия точного SHA, особенно пригодность scope, crash windows, path safety, неизменяемость предыдущих поколений и реалистичность будущей миграции.
- Подробный инженерный документ этого PR: `docs/marketplace-reports/B7_GENERATIONS_IMPLEMENTATION_20261029.md`. Следующая фаза после ревизии: исправить найденные ошибки и спроектировать безопасное переключение старых потребителей вместе с восстановлением; проверять отдельно и без production.

- **Дополнение CI B7:** В новом генераторе `reconcile` не создаёт пустые области при чтении; тесты на synthetic metadata сделали детерминированными. Итоговый код на SHA `aa1588875ab250038d879d5035581e136d99c3f0`: **82 tests OK** в GitHub Actions (run 40863611918), PowerShell parser PASS, secret scan PASS (40863611747). Базовая ветка PR #91 остаётся отдельно; PR #95 draft, Hermes B7 review pending, merge/installation/API NO.

## 29.10.2026 — ChatGPT, B7 Hermes G1–G4 самостоятельная доработка после FAIL (draft PR #95)

- Hermes независимо отклонил первоначальный B7 core `0217ba4` (G1 staged read, G2 неверная UNKNOWN классификация, G3 неподтверждённая история, G4 отсутствие fsync новых parent directories); остальная 24-категорийная матрица B7 открыта.
- Реально исправлено в `generation_store.py`: публичное чтение только через подтверждённую от CURRENT цепочку и обязательный SHA pin; неизвестный commit при пропаже CURRENT с поколениями; parent descriptor SHA256 в `schema=2` и проверка всей истории; fsync каждого созданного родителя вплоть до `generations`, каталога стадии и lock. Запрещено silently resolve символьный link root; полная hostile FS race защита не заявлена.
- Добавлены и пройдены G1–G4 регрессии в `tests/test_msp_marketplace_generations.py`; контракты старых синтетических тестов адаптированы к строгому pin. **На кодовом SHA `effe7f7809f61521ff44b857feaa4c2d3a0fb97c` GitHub: 89 unittest OK, PowerShell PASS, Secret scan PASS.** Подробности в `docs/marketplace-reports/B7_GENERATIONS_IMPLEMENTATION_20261029.md`.
- **Статус:** `G1-G4_OFFLINE_CI_PASS`, `HERMES_REVIEW_PENDING`; `B7=OPEN`, `P01=NOT_VERIFIED`; `MAIN_MERGE=NO`, `VPS_DEPLOY=NO`, `LIVE_API=NO`. Следующий шаг: Hermes воспроизводит четыре оригинальных контрпримера на точной новой голове PR #95, проверяет аварийный ввод и негативные сценарии. Затем ChatGPT сам устраняет новые замечания; далее B7 legacy migration/recovery только после этого этапа.

## 29.10.2026 — G4-R1 Hermes FAIL → самостоятельное исправление ChatGPT

- На `97decf831a2499d1dc0d4d93395a46a1626cbaaa` Hermes независимо подтвердил G1=PASS, G2=PASS, G3=PASS, но G4=FAIL: после успешного mkdir и отказа fsync родителя повторный запуск прежнего `_ensure_scope_durable` пропускал необходимую синхронизацию для уже существующих каталогов. Репродукция: 5 уровней, новый год и SIGKILL.
- Исправил `generation_store.py::_ensure_scope_durable`: на КАЖДОЙ попытке синхронизируются и уже существующие, и новые каталоги вместе с родителями от anchor до scope, без вывода durability из `exists()`; ошибка любого `fsync` блокирует переход `CURRENT`.
- Новые синтетические испытания `test_g4_r1_*`: шесть уровней отказ/повтор, новый год после истории и реальный дочерний SIGKILL перед `fsync(parent)`. На `5184521de18e61a336f4fbc71a358e87ba44512a` — **92 tests OK**, Windows parser PASS, secret scan PASS, runs `40868193379`, `40868193380`.
- Итог по исправлению: `G4-R1_LOCAL_CI=PASS`, `HERMES_RECHECK=PENDING`. `B7=OPEN`, `P01=NOT_VERIFIED`; никаких merge/deploy/API/Redis. Полная устойчивость при аварийной потере питания `NOT VERIFIED`.

## 29.10.2026 — ChatGPT: B7 этап 2, офлайн-интеграция и ограниченное сохранение следов аварий, draft PR #96

- Входная точка: независимый Hermes PASS для G1–G4 на 407d14470db1ccb073a3278067be142a3dbd339b; 92 штатных + 201 независимый сценарий. P01 общая очередь по-прежнему NOT VERIFIED; работа с сервером и API заблокирована.
- Создан отдельный draft PR #96 в ветке feat/msp-marketplace-b7-offline-adapter-recovery-20261029 поверх PR #95, без merge. Код ChatGPT: versioned_archive.py (отдельный opt-in импорт локальных CSV для WB main/buyout, Ozon CURRENT и FULL годовых групп Ozon FINAL; проверка наличия старого layout, CAS по CURRENT, закреплённый CSV reader и read-only scoped verify), generation_recovery.py (ТОЛЬКО подтверждённое оператором сохранение внелинейных поколений в evidence под lock/CAS без удаления данных и без переключения CURRENT).
- CLI: добавлены отдельные import-csv-versioned, verify-versioned и quarantine-uncommitted. Существующие import-csv, verify, status НЕ МЕНЯЛИ своё назначение: не перенаправляются к новым поколениям и не выполняют скрытое восстановление. Не включались вызовы providers, scheduler, Hermes, Redis или кабинетов.
- Проверки на искусственных данных: WB merge, idempotent/no-op, wrong reportType, conflict, Ozon monthly/annual single generation, pinned former reader, lost-after-CURRENT CommitUncertainError без ложного rollback, конкурентный stale CAS, запрет смешения с legacy, quarantine+повтор после перемещения/потери ответа, отсутствие CURRENT/неверный PIN отказывает без изменения, изоляция кабинета, отсутствие вывода финансовых строк в CLI.
- GitHub Actions code SHA 9f78e82a1328b48469693d3075ed6fdf3fcee717: **108 unittest OK**, Windows PS5.1 parser PASS, Secret scan PASS. Runs: 40871883622 и 40871883585. Это CI разработчика, а не независимая Hermes приёмка.
- Важно: текущий архив и все внешние читатели/ingest НЕ переведены на поколения; миграция legacy, общая блокировка с ещё работающими legacy writers и полное restore отсутствующего/испорченного CURRENT не реализованы. Отдельный карантин не доказывает, что внелинейное поколение никогда раньше не было committed при внешнем откате CURRENT; оператор несёт ответственность за внешнее доказательство. После отключения питания устойчивость NOT VERIFIED.
- Техническая передача: docs/marketplace-reports/B7_OFFLINE_ADAPTER_RECOVERY_20261029.md; независимая ревизия Hermes по конкретной голове PR #96 PENDING. Общие статусы B7=OPEN, P01=NOT_VERIFIED, LIVE_API=NO, MERGE=NO, DEPLOY=NO.
