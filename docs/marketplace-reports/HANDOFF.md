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

## 2026-10-28 — независимая ревизия Hermes (без допуска к API)

- База ревизии: `b6935eb16e29e73a931af45ab0abdccc38a46f49`; старый проект `0510a409ab589c639930fbca35afb3e68d874f81`. Полный результат: [REVIEW_HERMES_20261028.md](REVIEW_HERMES_20261028.md), собственная ветка `review/hermes-marketplace-archive-20261028`; не изменяет чужую feature-ветку.
- PASS: изучены текущие документы/программы и поздняя хронология; 54 изолированных теста OK, CI исходной версии прочитан. Свежая read-only диагностика VM-817589 подтвердила CLOSED на локальном Redis 6379, отсутствие корня архива, root:root 0700 у каталога реквизитов. Закрытый cabinets.json не читался: его состояние и root trial-копия независимо NOT VERIFIED.
- FAIL: новый `scope=msp_finance_reports` не совпадает со старым `finance`: даже общий Redis не объединит эти buckets. Отдельные тесты показали перезапуск WB с rrdId=0 после ошибки и при повторе завершённого wb-one, повторное заверение повреждённого WB CSV, пропуск удаления всех monthly_source при сохранённом Ozon annual. Исправления WB блокируются конфликтом вместо управляемого версионирования; multi-file recovery/checkpoint отсутствуют. Детали, точные файлы и способы исправления — в ревизии.
- NOT VERIFIED: реальный Redis старого сервера и конфигурация общей очереди, её конкуренция/отказы, актуальные Ozon-контракты, полный WB отчёт и остальные кабинеты. Исторические результаты владельца не объявлены повторно выполненными.
- Следующее безопасное действие: определить фактическую очередь Marketplace MCP на VM-684381 через разрешённый read-only канал; не устанавливать независимую очередь на новом VPS. Approval не включать, WB/Ozon не вызывать. Никаких развёртываний, изменений служб/данных/секретов/расписаний или слияния PR №89 ревизия не выполняет.

## 2026-10-29 — полный план завершения и обязательная фиксация знаний

- По поручению владельца подготовлен [ACTION_PLAN_20261029.md](ACTION_PLAN_20261029.md): P01–P12, все ошибки B1–B9, безопасность реквизитов, Ozon-контракты, CI, интеграционные испытания, согласованная установка, пилоты, история шести кабинетов, восстановление и read-only доступ коллег.
- PASS: перед планированием заново проверены SHA и состояние PR №89/№90; оба открыты и не слиты. Исправления и испытания будущих этапов НЕ объявлены выполненными.
- Введено обязательное закрытие каждого шага: действие → независимая проверка → безопасное доказательство PASS/FAIL/NOT VERIFIED → HANDOFF/PROJECT/DECISIONS/семантика → канонический и применимый установленный Skill → commit/PR/CI/read-back. GitHub, VPS и установленный Skill учитывать раздельно.
- План опубликован в собственной ветке ревизии PR №90; первый приоритет — P01 (подтверждение фактической общей очереди). Разрешение на merge, развёртывание, допуск API, массовую историю или расписание этим документом не выдаётся. Production и чужая feature-ветка не менялись.

- PASS: в текущем default-профиле обновлена маршрутизация существующего Skill `data-pipeline-operations` и установлен [проектный справочник Hermes](HERMES_HANDOFF_GUIDE.md), byte-identical локальной reference-копии; SHA256 `166b9e0305b3498f314c3c5f192a925e2edee4018eac04c525347e6633560c54`. Проверены YAML-метаданные и ссылка маршрутизации. Это инструкция планирования/передачи, не новый API-инструмент и не установка приложения. Новый специализированный Skill проекта остаётся задачей плана.

- Сверка в ходе публикации: учтена новая запись коллеги от 29.10 из `40349bc0d5566c6377ad00a824351705561736eb` об отсутствии признаков локального Marketplace MCP/Redis. Это результат оператора, не новый запуск Hermes. Программные файлы не изменились; план и блокеры остаются применимыми. Обе хронологии сохранены в собственной ветке.

## 2026-10-29 — Hermes: независимая проверка PR №91 и отдельная диагностика P01

- Проверены old `40349bc0d5566c6377ad00a824351705561736eb` и PR №91 `e98000b0ae309ea0677bcabcbb39486b31e1cd28`. [Результат B5](REVIEW_B5_PR91_20261029.md), искусственные harness/stdout включены в evidence. PASS: исходная B5 воспроизведена до и заблокирована после; 57 штатных тестов, 132 target-corruption и 6 corrupt-no-op случаев прошли.
- **B5 acceptance=FAIL:** R1 — остальные месячные Ozon-источники обходят полную проверку metadata (schema=2 → успешный новый annual и verify=True); R2 — заранее повреждённый annual блокирует импорт только после изменения monthly. B7 fault injection подтверждает fail-closed после CSV→manifest crash, но процедуры recovery нет. Код PR №91 не менялся; замечания передаются автору.
- [P01 отдельный результат](P01_QUEUE_DISCOVERY_20261029.md): **NOT VERIFIED** — на VM-817589 не найдены признаки локальной legacy очереди и настроенного доступа к старому экземпляру; подтверждены TCP refusal=111, отсутствие именованных units/processes/binaries и legacy MCP connections. Контракт старого GitHub не доказывает runtime. Нужен существующий разрешённый read-only маршрут к фактическому legacy runtime; токены и пароли не нужны в чате.
- Никаких маркетплейс API/реальных отчётов, Redis-записей, изменений чужих веток, merge, установки, перезапуска служб или расписаний. Результаты публикуются в собственной ветке PR №90 и обсуждениях №91/№90, с read-back.

- Инструкции проверки integrity/recovery и поиска очереди дополнены в установленном reference существующего Skill `data-pipeline-operations`; каноническая копия — HERMES_HANDOFF_GUIDE.md, SHA256 `6c455e3e79f547f6708c8cd00d842c25e8d37a142dc3eafe05edadaefcb4c3f1`. Это новые инструкции ревизии, не установка приложения или исправления PR №91.

## 2026-10-29 — Hermes: повторная независимая проверка точного 309592e4

- [Отчёт повторной проверки](REVIEW_R1_R2_309592E4.md): **R1=PASS, R2=PASS** на `309592e4cef5af617ed8e9e07060dce739d6a1f2`. Исходные R1/R2 повторены до/после; новые отказы сохраняют все файлы архива и backups побайтно. 61 штатный тест/CI PASS; 132 group-corruption, 6 consistency, обычный импорт/исправление/no-op и повторная B5-матрица проверены на искусственных данных.
- **B7=OPEN:** три fault points оставляют неполную публикацию, verify=False, retry блокируется без новых изменений; восстановления/атомарного multi-file commit нет. Унаследованное R3: boolean `true` принимается как schema=1/rows=1 из-за сравнения без строгих JSON-типов; наблюдается до и после, не новая регрессия R1/R2, вынесено отдельно.
- Заключение: принять выполненность R1/R2 в объёме независимой проверки; это не разрешение merge, установки или API. Код/ветка PR №91 не изменены. Harness и фактический stdout — в evidence; результаты передаются автору PR №91.
- P01 перепроверена доступными read-only средствами: локальный Redis refusal=111; новые каналы доступа к старому runtime не обнаружены; legacy main по свежему fetch остаётся 0510a409. **NOT VERIFIED**, необходим конкретный разрешённый read-only маршрут к действующему старому экземпляру, не секреты в чате. Никакой Redis не устанавливался.

- В установленном Skill reference закреплён отдельный тест JSON boolean↔integer и разделение scoped acceptance/regression/B7. Каноническая копия HERMES_HANDOFF_GUIDE.md синхронизирована; SHA256 `d3172a3a9204cf59bfe2ac6434d3b9be1a9d539d1f8d630bc8cec7424c80d53f`. Это инструкции проверки, не установка архиватора.

## 2026-10-29 — Hermes: дополнительный GitHub-доступ проверен, P01 продолжена

- **REPOSITORY_ACCESS=PASS:** новые Contents reads Marketplace bridge и infra реально выполнены. Сведения о маршрутах/истории проверены без запуска workflow. Прежнее «нет доступа к дополнительным repo» больше не считается блокером.
- Найдены конфликт исторических Yandex/REMOTE инструкций и несовпадение свежего DNS с production source map. Публичный legacy TLS вход возвращает WRONG_VERSION_NUMBER до подтверждённого HTTP/MCP; никакой TLS bypass/plaintext fallback не использован.
- **P01=NOT VERIFIED:** backend/DB/namespace/PING/совместимость bucket не доказаны. Точные недостающие разрешённые источники: gpt-powershell-bridge metadata 404, Marketplace bridge Actions workflows/runners 403. Исторический Windows маршрут требует подтверждения нынешней identity/доступности.
- Подробный PRIVATE отчёт опубликован в [bridge PR №720](https://github.com/alexpmtk-afk/msp-server-bridge/pull/720), commit `287eaaad0d9a9db4cb652bc90d2a00a5e9419ee2`, содержимое прочитано обратно. Частные SSH locator/key paths в публичный stack не переносились; безопасный итог — P01_QUEUE_DISCOVERY_20261029.md.
- Коллеге передаётся результат в PR №90. Чужие исходники/ветки, старые службы, Redis, конфигурация авторизации и текущие финансовые данные не менялись; никаких merge/install/маркетплейс API/запусков mutating workflow.

- Skill reference дополнен разделением Contents/Actions/execution и проверкой актуальности DNS/TLS/historical workflows; публичная каноническая guide-копия совпадает с установленной reference, SHA256 `1c1ab518289cb3695eef29c9caa67c27caa8e9b25bcdce0f8cc49679a8bc1132`. Приватные locator-данные в Skill не записывались.

## 2026-10-29 — Hermes: диагноз различий GitHub-подключений

- PASS: действующий fine-grained PAT и ожидаемый account проверены через /user; REST/GraphQL подтвердили недоступность GPT repo именно этому подключению, не его отсутствие. Marketplace и MSP private controls: Contents 200, Actions 403 с явным отказом PAT. Состояние выбора repo/permissions в настройках не читалось и не менялось.
- Исправлена прежняя неточность рекомендаций: Actions read — workflow/run/job history; Administration read — API списка self-hosted runners, не обязательный первый шаг. Public Actions 200 не доказывает PAT permission.
- Документированный WORK executor найден только в старом pointer; текущие main README/policy GPT repo недоступны. Bridge-v2 учитывается как историческая по уточнению коллеги. Online Windows, разрешённый read-only operation, конечный host и Redis NOT VERIFIED; ничего не исполнялось.
- Подробности и safe API evidence в PRIVATE PR №720; публичная P01-выжимка и Skills уточнены. Коллеге предлагается безопасный снимок текущей main/policy в уже доступном PRIVATE bridge как вариант совместного изучения без передачи credentials и без изменения PAT. Это не execution permission.

- Синхронизирован установленный pipeline reference с HERMES_HANDOFF_GUIDE.md, SHA256 `2cd216454e32fda8c955b468ff6d107182de53df0e14852696ceecb918ef6802`; обновлена auth-reference Github Skill. Установка приложения, права GitHub и службы не менялись.

## 2026-10-29 — Hermes: проверка безопасной выдержки PR №729

- **DOCUMENT REVIEW=PASS:** прочитан точный `c5c460dc240a42053b19cab7e73da42f857cbbcd`, безопасная выдержка актуальной политики; сопоставлена с PRIVATE PR №720. Исторические инструкции не приняты за online/runtime. Оригиналы недоступны подключению Hermes: независимое соответствие исходникам **NOT VERIFIED**, это не новый успешный доступ к исходному repo.
- **P01 / LIVE READ-ONLY CHANNEL=NOT VERIFIED:** не определён точный существующий read-only workflow/launcher/whitelist с закреплённой версией и допустимыми inputs; online исполнителя, конечная identity и общая Redis очередь не подтверждены.
- Один следующий шаг: коллега через уже доступное Contents-подключение фиксирует контракт существующей разрешённой read-only диагностики в PRIVATE bridge, без запуска и без создания новой операции. Если операции нет, это отдельный подтверждаемый блокер.
- Полное заключение — REVIEW_P01_PR729_C5C460DC.md в PRIVATE PR №720; ответ коллеге публикуется в PRIVATE PR №729. Рекомендуется связный source commit SHA и точное указание требования Administration read именно для runner-list REST endpoint. Права не расширялись, Actions не запускались, чужая ветка и runtime не менялись.

## 2026-10-29 — Hermes: повторная проверка PR №729 f2ee4980

- DOCUMENT REVIEW=PASS: прочитан точный `f2ee4980a4204adda9fe8b997a77c40bf7814eea`; два MSP workflow непосредственно сверены с `e245a49593c668816825568deecc4676c3f59240`. Они обслуживают новый Linux runner, не старый Marketplace MCP. GPT workflow напрямую остаётся недоступен (404): его описание — результат чтения коллеги, не самостоятельное чтение Hermes.
- Искусственная shell-проверка подтвердила: `redis-cli`-заглушки с exit 1 + `|| true` не мешают итоговому PASS. Реальный Redis не вызывался. PASS исторического сценария не является доказательством очереди.
- P01=NOT VERIFIED; иной подходящий разрешённый вход не подтверждён. Bounded поиск в workflow нового моста не доказывает отсутствия каналов вообще. Локально вновь проверены новый host, отсутствие SSH-каталога пользователя и listeners 6379/6380, но это не состояние старой машины.
- Минимальное действие для отдельного решения владельца: одна фиксированная проверка identity/служебных metadata в уже существующей владельческой SSH/консольной сессии старого сервера. Точная команда и границы в PRIVATE PR №720, REVIEW_P01_PR729_F2EE4980.md. Команда НЕ запускалась и не является разрешением создания нового канала. Redis/PING/совместимость ключей потребуют следующей проверки.
- Чужие ветки, PAT, службы и очередь не менялись; нет Actions dispatch/rerun, SSH, Redis, маркетплейс API, merge или установки.

## 2026-10-29 — финальная ревизия документации PR №729

**PASS** для точного `65cea51afd7240c454170e087b604ccfc7e3381e`: все замечания предыдущего review закрыты; новых нет. Документация этого этапа завершена по результату проверки, не слита и не установлена. Источники доказательств и границы утверждений разделены; консольная диагностика остаётся несогласованной и невыполненной. **P01=NOT VERIFIED**: текущий исполнитель, старый сервер и общая Redis очередь не подтверждены. Результат фиксируется в PRIVATE PR №720 и комментарии №729; исходники коллеги не менялись. Никаких Actions/SSH/Redis/API, расширения прав, обходных подключений, merge или deployment.

## 2026-10-29 — Hermes: R3 независимо PASS, B7 план приёмки

- Точный PR №91 head `2f1c9427e4245e9af452bcce063c85215016cbbf` проверен против `309592e4...`. R3 воспроизведена на старой версии и устранена на новой. **R3=PASS**; локально 64 штатных tests, 1008 независимых числовых случаев и 72 malformed JSON случая PASS. Все отказные проверки включали побайтовый snapshot файлов/backup и verify; сеть запрещена. CI check-runs точного SHA прочитаны success.
- [Полный отчёт и harness](REVIEW_R3_2F1C9427.md); новых блокирующих регрессий нет. Унаследованная неоднозначность повторных JSON keys J1 описана отдельно, не R3 FAIL.
- [B7_FAULT_TEST_PLAN_20261029.md](B7_FAULT_TEST_PLAN_20261029.md): 24 категории будущих аварийных испытаний, читатели/commit point/recovery/проверка поколений. Сейчас только анализ и план, не B7 acceptance и не реализация. ChatGPT программирует, Hermes проверяет точный будущий SHA.
- P01=NOT VERIFIED; офлайн-работа разрешена. Защитный API block не менялся. Код коллеги, службы и рабочий архив не трогались; merge/deploy/API/Redis/Actions execution отсутствуют.
