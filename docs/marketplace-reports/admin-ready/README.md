# Административная готовность WB — 02.11.2026

## Решение и точные границы

**Подготовка завершена. Установка НЕ выполнена; runtime/P01 NOT VERIFIED; API NO-GO.**
База: PR104 `c1fee070e9efa0c925a78f266fdf03cb12a173cf`, независимо принятая
[ChatGPT](https://github.com/alexpmtk-afk/msp-server-stack/pull/104#issuecomment-6575954086).
17 программных модулей, четыре исходных файла поставки и digest
`aac2431671d539d5653379b85b9a214d21e06fee7d1eb3f99361991949f465c5` не меняются.
195 принятых тестов заново не запускались. Этот пакет — дополнение, не новая
версия загрузчика и не разрешение установки. Старый REMOTE больше не ищем.

Подготовлены два инструмента: root-only выделение одного WB токена и диагностика
Redis READ_ONLY. Они не включены в 17-module code_digest, имеют отдельный
ADMIN_MANIFEST.json. Unit для административного staging использует только
pilot-copy и запрещает IP-сеть. Исходный unit PR104 не изменён.

## 1. Минимальная матрица доступа

| Объект | Владелец/права после отдельного разрешения | Назначение |
|---|---|---|
| `msp-reports` | системный user+group, shell nologin, без sudo/дополнительных групп | один непривилегированный исполнитель |
| `/opt/mcp/projects/msp-marketplace-reports-releases/<accepted-sha>` | root:root, каталоги0755, исходники0644; executables0755 | immutable release; ни hermes, ни executor не пишут |
| `.venv` внутри release | root:root, interpreter/links проверены, не writable исполнителю | `/usr/bin/python3` 3.12; redis8.1.0 по lock/hash, без extras |
| `/opt/mcp/data/msp-marketplace-reports` | msp-reports:msp-reports0700; umask0077 | единственный write-root исполнителя |
| `/etc/msp-marketplace-reports/cabinets.json` | исходные root0600, parent root0700 СТРОГО сохранить | master-файл, runtime его не читает |
| `/etc/msp-marketplace-reports-pilot` | root:root0700 | единственная pilot-copy `wb_laser_master.json` root0600 |
| `/etc/msp-marketplace-reports-executor` | root:root0755, nonsecret approval0644 | immutable plan/code/root/expiry approval; при staging файла нет |
| Redis config/CA | root-controlled, secret root0600 в закрытом каталоге | только выбранный backend/DB; не WB токены |
| unit `/etc/systemd/system/msp-wb-pilot.service` | root:root0644, без timer/Install/Restart | ручной bounded oneshot, не новая очередь |
| backup target | root-only или отдельный approved backup user; encrypted off-host | архив без master/pilot/Redis credentials |

Не делать recursive chmod/chown `/opt/mcp`, `/opt/mcp/data` или `/etc`.
Не добавлять executor в root/hermes/docker/systemd-journal группы и не давать
ему доступ к Hermes/1C/другим кабинетам. UID/GID выбирает администратор и
фиксирует в install receipt; при существующем одноимённом user проверяет его
назначение, а не переиспользует молча.

## 2. Порядок установки и проверки (ПОСЛЕ отдельного разрешения)

Каждый этап даёт запись PASS/FAIL с точным SHA, временем, UID, путями и
контрольными суммами; без секретов. При FAIL остановиться, не продолжать к API.
Это административный runbook, не уже выполненные команды и не root-installer.

1. **Зафиксировать согласованный набор.** Код из exact PR104 SHA выше; admin
   дополнение из exact reviewed SHA этой ветки. Проверить, что между принятием
   и установкой не подменены файлы. Слияние цепочки PR — отдельное решение;
   `git pull` в production не является установкой. Если принят merge SHA,
   сравнить payload с принятыми байтами до исполнения.
2. **Собрать и проверить root-owned staging.** Из доверенного artifact только
   17 listed modules + pilot-plan, original manifest/lock + выбранный staged
   unit и два admin tools. Не распаковывать весь repo как root. Сначала проверить
   bundle digest из согласованной поставки, запретить absolute/`..`/symlink и
   hardlink entries, затем извлечь в свежий root-owned каталог с безопасными
   режимами, пересчитать каждый hash двух манифестов. Установка не запускается
   из hermes-writable checkout. Финальный artifact digest закрепляется после
   принятия этой ветки; пока ready-to-run root command НЕ выпускается.
3. **Проверить существующие условия.** Не создавать/менять working services:
   записать health затрагиваемых и соседних служб, отсутствие старого одноимённого
   unit, версии systemd/Python/venv support, mount/FS, free bytes/inodes и backup
   destination. Неизвестный существующий release/archive — STOP, не overwrite.
4. **Создать identity и storage.** Только утверждённый user/group, release-root,
   архив0700 и pilot/config parents из таблицы. Сверить numeric UID/GID, lstat
   каждого пути/предков и отсутствие symlink/writable ancestors. Исходные права
   master secrets проверить администратором без вывода содержимого; при
   отличии от0700/0600 не исправлять автоматически — STOP.
5. **Установить неизменяемый payload и venv.** Системный Python3.12, без global
   pip/обновления Python/redis-server. Применить существующий hash-locked redis
   wheel из PR104, `--no-index --no-deps --require-hashes` из заранее проверенного
   wheelhouse. Если нет venv/ensurepip, это отдельная согласованная dependency,
   не незаметный apt install. Зафиксировать интерпретатор, package version,
   wheel hash и разрешённые links; executor не владеет кодом/venv.
6. **Выделить один токен.** Из root-owned verified snapshot выполнить
   `select_pilot_credential.py --owner-approved-create-pilot-copy` только после
   специального разрешения secret-read/copy. Читает fixed master path, сохраняет
   только `wb_laser_master.token`, исключает все другие поля/кабинеты. Отказ при
   existing destination, symlink/hardlink/небезопасных правах/duplicate JSON.
   Ничего не печатает из токена. Источник не переписывается; администратор
   независимо сверяет before/after stat+hash приватно. Частичная запись/fsync
   failure = STOP_OR_UNCERTAIN, не автоматическое удаление/перезапись.
7. **Установить только staged unit.** Подставить accepted CODE SHA в пути;
   передавать pilot-copy как LoadCredential с именем `cabinets.json`.
   В staged unit сеть `IPAddressDeny=any`, отсутствуют approval и gate/config;
   unit не стартовать и не enable. `systemd-analyze verify` и readback unit
   подтверждают только syntax/настройки, не sandbox acceptance. daemon-reload —
   отдельное согласованное административное действие, не restart соседей.
8. **Отдельный no-API smoke.** Под executor UID и теми же hardening/LoadCredential
   параметрами, но БЕЗ запуска downloader, сделать private create/write/fsync/
   rename/fsync-dir/read/hash/delete probe в выделенном smoke подкаталоге.
   Проверить отказ доступа к master, другим кабинетам и release write; загруженную
   credential-copy проверить на ровно1 cabinet/1 token field и допустимый mode/UID,
   без вывода данных. Проверить сетевой запрет staged unit. Не вызывать standalone
   с активным approval ради smoke. Проверка LoadCredential должна реально пройти
   существующий `load_credentials`, не только `ls`.
9. **Пройти Redis READ_ONLY acceptance** по разделу3: отдельный diagnostic scope,
   не менять staged unit и не включать WB сеть/флаги. Backend/ACL/CA из доверенного
   источника, никаких сканирований портов/поиска адресов.
10. **Проверить backup/restore.** При остановленных writers снять coherent snapshot
    всего архива, включая скрытые locks/state, staging, page journal, execution
    ledger, CSV, generation manifests, CURRENT, coverage. Сверить file hashes,
    private/encrypted backup и отдельную offline restore-копию, не поверх рабочего
    архива. У storage проверить fsync semantics/ошибки, capacity до запуска.
    Размер отчёта неизвестен: согласовать минимальный свободный reserve и stop
    threshold, запас для staging+CSV+generation+backup; оценка не доказательство
    достаточного места. Проверять bytes И inodes до каждого пилота.
11. **Остановиться: ADMIN READY, API BLOCKED.** Сохранить installed-manifest,
    rendered unit hash, interpreter/dependency receipt, UID/GID, smoke и Redis
    evidence. Наличие готовой установки не разрешает запросы к WB.
12. **Только после нового pilot GO:** закрыть conflict/quota раздел4; согласовать
    финальный unit/network и protected Redis injection, включение исходного gate
    `MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES`, exact approval с expiry и references.
    Разрешающие настройки не генерируются/не ставятся этим пакетом. Один ручной
    запуск: `wb_laser_master/main/883801632`,19–25.10.2026,max3 durable sender entries.
    Проверить terminal204/CSV/hashes/generation/coverage и повтор без API. Если
    budget exhausted — PAUSED_BUDGET; неизвестный размер не превращать в COMPLETE.

## 3. Redis: что действительно можно подтвердить без маркетплейсов

`redis_readonly_probe.py` импортирует только approved control/rate helpers и
клиент; не фабрику backend/queue, не downloader, не `try_acquire`/`defer`.
Сначала admin проверяет approved release и config/CA. В отдельном diagnostic
scope предоставляется только Redis credential, без WB токена, с egress только
к утверждённому Redis/DNS; WB/Ozon egress закрыт. Protected configuration
передаётся в процесс без argv/log; для CLI текущий helper использует штатные
`MARKETPLACE_MCP_REDIS_*` environment внутри scope, не shell history/глобальный env.
Передача env не является вариантом хранения WB токена. Значения не публиковать.

После provisioning команда diagnostic Python имеет форму
`<verified-venv>/bin/python -B <verified-admin>/redis_readonly_probe.py --release <verified-release>`.
Пути фиксируются installed receipt, а не копируются буквально с угловыми скобками.
Опциональный `--explicit-keys-json` принимает закрытый JSON `{ "keys": [...] }`
максимум с3 ТОЧНО установленными canonical keys; не вычислять их по догадке и
не делать SCAN/KEYS. Получать private keys из одобренного seller/rules inventory.

Проверяются DEFAULT protocol и явно RESP2: PING,TIME,INFO server,
опционально EXISTS/PTTL; совпадение run_id между двумя соединениями проверяется
приватно, без вывода id/endpoint/key/token. Вывод — версии, флаги результата и
redacted buckets. Отсутствие key не является proof отсутствия запросов.

**Уточнение wire:** это allowlist прикладных read-команд; redis-py может выполнять
AUTH/HELLO/SELECT/CLIENT SETINFO при handshake. Эти connection-scoped команды
не записывают quota keys, но ACL должен их учитывать. Во время этого этапа нет
EVAL/SET/DEL/FLUSHDB, нет Redis queue creation/changes; клиент диагностического
процесса должен иметь read-only ACL. Нельзя менять общий ACL ради успешного probe.
Ошибка/cluster/proxy identity mismatch/нет INFO = NOT VERIFIED/STOP, а не
автоматическая смена backend или fallback на SQLite.

**Граница результата:** PASS = чтение данным sync-клиентом и двумя protocol cases
с одного backend. Это НЕ PASS atomic Lua, async production controller, cross-host
sharing или seller quota. Если default не работает, RESP2 alone не разрешает
запуск: текущий production client uses default, его изменение — отдельный patch.
При runtime Lua admission нужна отдельно разрешённая bounded write-проверка
существующего controller: согласованный изолированный test-owner, никаких live
seller keys, два процесса/ожидание/TTL/recovery, без provider. Это НЕ новая очередь,
но всё равно Redis writes, которые сейчас запрещены. Если такой допуск не дан,
atomic_lua_admission остаётся NOT_VERIFIED и API не включается. Не давать
инструкцию EVAL против настоящего кабинета как «проверку чтением».

## 4. Практическое исключение старых запросов — без поиска REMOTE

Один новый VPS lock защищает только сотрудничающие локальные процессы.
Для seller-scoped WB finance квоты новый токен не создаёт отдельного продавца.
Практический следующий шаг — владелец открывает **текущий кабинет WB продавца
wb_laser_master**, раздел управления API-доступами/интеграциями, либо обращается
к поддержке, если полного списка/отзыва там нет. Название UI/возможности полного
аудита здесь не утверждаются: это operator check, не проверенная функция API.

1. Составить приватный перечень всех действующих токенов, приложений/делегированных
   доступов и их владельцев, способных вызывать finance APIs. Сохранить redacted
   evidence с seller, точным scope, временем и ответственным; не токены.
2. Для известных нужных клиентов: их администраторы подтверждают реальные
   endpoint/DB/namespace, seller-owner derivation, finance bucket и atomic
   admission всех попыток. Триггеры/cron и ручные пути тоже включить. Не достаточно
   одного controller source SHA, одинакового hostname или подписанного checkbox.
3. Неучтённые/недоступные доступы, включая возможный старый REMOTE: предложить
   владельцу адресный cutover кабинета. **Только после отдельного разрешения**
   остановить доступные finance jobs и отозвать все неподконтрольные finance-
   capable tokens/authorizations по возможностям WB; подтвердить отзыв через
   кабинет/поддержку с временем вступления в силу. Выпуск нового без отзыва старых
   недостаточен. Не отзывать прочие кабинеты/нужные рабочие интеграции молча.
4. Если нельзя подтвердить полный список или отключение всех неизвестных
   finance клиентов, API NO-GO; независимый Redis и ожидание нескольких минут
   это не исправляют. Попросить поддержку подтвердить доступы/отзыв; не искать
   старый хост снова. Допустим путь без отзыва, если все clients доказанно
   согласованы на общей квоте.
5. После подтверждённого отключения выдержать документированный WB/operator
   propagation/in-flight интервал плюс контрольное окно не меньше принятого
  65-секундного safety; если vendor propagation неизвестен — согласовать его,
   не объявлять65 секунд гарантией отзыва. Подтвердить оставшиеся клиенты и
   shared backend перед ограниченным pilot. Пассивные vendor access logs, если
   доступны, помогают, но тишина/нет429/EXISTS=0 не доказывают отсутствие клиентов.

Артефакт допуска: redacted cutover receipt со scope продавца, списком accounted
clients, отзывами/подтверждениями или доказательством shared admission, effective
временем, approved Redis config fingerprint, ответственным и сроком разрешения.
Checkbox `conflicting_clients_excluded=true` только ссылается на эти доказательства.

## 5. Откат и восстановление

- **До активации:** unit не запускается. Зафиксировать partial install; не удалять
  неизвестные существовавшие пути. После согласования убрать только новые unit/
  release/pilot-copy, reload manager; исходные secrets/соседние службы не менять.
  Service account удалять лишь если создан именно этой установкой и нигде больше
  не используется. Архив с неизвестными файлами не удалять.
- **После разрешённого pilot:** запретить новые invocations, root убрать/сделать
  недействительным approval и gate, остановить только pilot unit, дождаться
  отсутствия writer. Interrupt во время HTTP = uncertain entry, budget НЕ
  обнулять. Сохранить журналы/receipts/private credentials до reconciliation.
- **Версия кода:** предыдущий точный immutable release+unit допустим лишь при
  совместимости state. Для первой установки предыдущего executor нет: rollback
  = остановленный контур, НЕ возврат на старый REMOTE. Не запускать старый код
  поверх новых журналов наугад.
- **Данные:** restore только в закрытый отдельный каталог, hashes/CSV/manifest/
  CURRENT/coverage check offline; никакого API auto-resume. Backup может содержать
  меньший budget, поэтому восстановленный ledger не источник разрешения новых
  запросов: reconcile с последними receipts, новый exact approval до запуска.
- **Токены:** отзыв нельзя откатить копированием старого файла. Доступы меняет
  только владелец отдельным действием. Release rollback не реактивирует их.

## 6. Минимальные отдельные разрешения владельца

**A — административное provisioning (можно согласовать раньше API):** конкретный
accepted code+admin SHA, user/group, перечисленные directories/modes, immutable
release+venv/hashed wheel, pilot unit и daemon-reload БЕЗ запуска/таймера,
закрытый backup target/retention, file/LoadCredential/no-network smoke.

**B — чтение/копирование секретов:** root читает исходный JSON, создаёт ТОЛЬКО
pilot token copy; LoadCredential доставляет его executor; отдельно Redis config/CA
для diagnostic scope. Не менять исходные права и не выдавать весь JSON.

**C — runtime Redis validation:** фактический approved endpoint/DB/ACL,
READ_ONLY protocol probe без WB. Предыдущий P01 read-only допуск сохраняется
в его границах, но не разрешает установку/secret provisioning. Atomic Lua test
writes — явное отдельное расширение C, не входит в READ_ONLY.

**D — conflict cutover, если нельзя доказать shared legacy clients:** точный
список останавливаемых интеграций и отзываемых доступов одного продавца,
подтверждение влияния, окно переключения. Сейчас никакого отзыва.

**E — первый API pilot:** только после A/B/C и quota/conflict evidence;
финальный network/config/gate/approval и один отчёт max3 durable entries.
Ни approval A, ни PASS195/Redis PING не заменяют E. Merge и массовая2026
загрузка/расписание/Ozon activation не входят ни в один из этих пунктов.

## 7. Что сделано сейчас, что не сделано

Подготовлены новые admin tools, staged unit, этот runbook и отдельный manifest.
Новые tests используют только synthetic credentials/fake Redis/temp scratch;
никаких реальных Redis/API/systemd/secret reads. Прежние195 не повторялись.
Компоненты VPS не сканировались заново; используем принятый PR104 inventory.
Следующий конкретный шаг: принять exact admin дополнение и согласовать A/B
с отдельным C READ_ONLY, параллельно владелец собирает redacted WB access inventory.
Не ждать завершения годового/Ozon проекта для установки заблокированного WB контура.
