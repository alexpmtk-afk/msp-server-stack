# Отдельный пакет локального Redis квот — VM-817589

**Архитектура PR111 утверждена владельцем. PACKAGE READY, INSTALL NOT EXECUTED.**
Этот PR подготавливает единственный local quota Redis поверх завершённых A/B.
До root выполнения — независимая проверка точного SHA/пакета/команды ChatGPT.
WB/Ozon API, report timers, старые клиенты и их tokens не включаются/не меняются.

## Один шаг администратора ПОСЛЕ независимой проверки

В существующей root-консоли VM-817589 вставить целиком одну строку из
[ROOT_ONE_LINE.txt](ROOT_ONE_LINE.txt). Она копирует entry в fresh root0700 stage,
фиксирует mode0600 и owner root, проверяет literal SHA256, и только потом
исполняет его. Entry проверяет bundle/manifest/каждый из14 payload files ДО
extraction/execution в другом fresh root-owned snapshot.

Файлы уже на этом VPS:
- `/home/hermes/workspace/msp-quota-redis-entry.py`;
- `/home/hermes/workspace/msp-quota-redis.tar`.

Хеши зафиксированы в PACKAGE_SUMMARY.json и самой команде. В репозитории лежат
те же exact bytes, включая tar. Source/user-writable home не считается trusted:
до root-execution выполняется проверка скопированных bytes, а не доверие пути.
Пароли в чат не нужны. Никаких sudoers/NOPASSWD и агента от root.

## Поставка и происхождение

- Redis7.0.15, Ubuntu build `5:7.0.15-1ubuntu0.24.04.5`, скачан через APT download
  из Ubuntu noble-updates. InRelease проверен gpgv Ubuntu archive keyring,
  signing key F6ECB3762474EDA9D21B7022871920D1991BC93C. Это зафиксированный
  distro security build, не заявление об upstream latest.
- Redis executable взят из verified redis-tools ELF (`redis-check-rdb`, штатный
  redis-server symlink указывает на него); в пакете обычный файл redis-server.
  Отдельный redis-check-aof нужен offline recovery. Назначение определяется
  basename; оба режима фактически испытаны.
- Включены private libjemalloc и liblzf с исходными Ubuntu checksums и licences.
 15 уже существующих host libraries зафиксированы SHA256; на drift installer
  останавливается до изменений, не обновляет системные библиотеки.
- Никаких apt/dpkg install, maintainer scripts, сетевого pip/download, глобального
  redis-server или изменения Ubuntu services во время root установки.
- 14 payload files+manifest,6174720 bytes. Exact payload hashes/modes —
  BUNDLE_MANIFEST.json. Две сборки дали идентичные bytes. Tar не содержит
  symlink/hardlink/absolute/escaping paths. Runtime-lock описывает provenance.

## Что установщик делает и чего не делает

### Preflight и защитные границы

Требует root; перепроверяет root snapshot/inventory/hashes. Проверяет существующие
A/B:17 accepted app modules, unchanged readonly probe, фактический A/B receipt,
existing msp-reports UID995/GID985. Не создаёт и не меняет этого пользователя,
не читает/копирует WB master или pilot token. Отсутствие report API approval
обязательно. Host shared libraries должны совпасть с lock.

До изменений проверяет отсутствие своих target paths/account/unit/drop-ins,
свободу loopback16379, минимум256MiB free disk/5000 inodes и512MiB MemAvailable.
Это запас для Redis, не ресурсная приёмка годовых CSV/бизнес-архива.

### Только новый Redis

Создаёт отдельного сервисного пользователя **msp-quota-redis** (system/no-login),
не включённого в группы msp-reports/Hermes. Existing msp-reports остаётся клиентом.
Другие пользователи/права/службы не модифицируются.

| Объект | Права и назначение |
|---|---|
| `/opt/mcp/quota-redis` | root0755; immutable bins0755/libs+helpers0644/licences |
| `/etc/msp-quota-redis` | root:msp-quota-redis0750; config/ACL/root initialization markers0640 |
| `/var/lib/msp-quota-redis` | Redis service UID/GID0700; только AOF/quota state |
| `/var/lib/msp-quota-redis-install` | root0700; private phase/complete receipts0600 |
| `/opt/mcp/backups/msp-quota-redis` | root0700; stopped snapshots/restore checks |
| existing private `/etc/msp-marketplace-reports/redis-readonly.env` | новый file root0600, parent не chmod-ится; только Redis read principal |
| existing `/etc/msp-marketplace-reports-executor/redis-runtime.env` | новый file root0600; runtime Redis URL+REQUIRE_REDIS=1, без permission gate |
| `/etc/systemd/system/msp-quota-redis.service` | root0644; только новый Redis, не report worker |

Каждый файл получает explicit fchmod до fsync: mode0644 под umask077 проверен
тестом. Не повторяется дефект PR108. Existing secret dirs и A/B journal modes
не меняются. Нет recursive chmod/chown родителей.

## Локальный доступ, ACL и persistence

Это НОВЫЙ endpoint по утверждённой архитектуре: `127.0.0.1:16379`, DB0 dedicated
quotas. Не найденный старый адрес и не loopback старого REMOTE. Bind127.0.0.1,
protected-mode yes, unit IPAddressDeny=any/Allow127.0.0.1/32. После старта installer
независимо проверяет ss: listener только127.0.0.1. Публичный порт/ACL firewall
не открывается. Старые hosts автоматически к этому endpoint не подключены.

Default ACL user выключен. При установке отдельно генерируются два случайных
256-bit passwords, не попадающие в argv/log/GitHub. ACL хранит SHA256 passwords;
plaintext есть только в двух root0600 EnvFiles. Сервер не получает WB credentials.

- quota_runtime: только WB/Ozon key patterns marketplace-rate:v1:wb:* и ozon:*,
  GET/SET/TIME/EVAL, SCAN/MGET для существующего snapshot, connection handshake.
  Нельзя FLUSH/CONFIG/ACL/ключи вне namespace; реальный Lua bypass outside prefix
  также проверен на отказ.
- quota_readonly: PING/TIME/INFO server/EXISTS/PTTL и handshake, без GET/EVAL/SET.
  Redis-py может посылать HELLO/AUTH/SELECT/CLIENT SETINFO/SETNAME; поведение7.0
  с закреплённым redis-py8.1.0 испытано DEFAULT RESP3 и explicit RESP2.

Persistence: AOF on, appendfsync always, no eviction, aof-load-truncated no,
no-appendfsync-on-rewrite no, save RDB schedule off. Memory64MB + systemd limit256MB.
После first empty init root закрывает temporary bootstrap-permit и создаёт
root-owned initialized marker. Все будущие service starts требуют существующий
AOF manifest; если data state исчез — HOLD, не пустая quota DB. Повреждённый AOF
не обрезается автоматически. Redis restart-on-failure bounded2/60s, но guard
не даёт ошибке пройти через пустую инициализацию. Own Redis enable-at-boot —
не запуск report schedule; ни одного report timer это не создаёт.

AOF/fsync не объявляется абсолютной гарантией физического power-loss. Обнаружить
подмену на правдоподобный старый backup одним existence guard невозможно:
любое восстановление требует reconciliation и удержания provider approval.

## Совместимость и C после root установки

Существующий sender не меняется. Runtime EnvFile готовится, **но не подключается
к заблокированному pilot unit** и не ставит MSP_REPORTS_SHARED_QUEUE_VERIFIED.
Existing network deny/approval absence остаются. Подключение/снятие network deny
будет частью отдельного E после verified finance-client cutover.

Установщик запускает ТОЛЬКО Redis и отдельный transient READ_ONLY check как
msp-reports с EnvFile read principal, без WB token. Проверяет закреплённые версии
client8.1.0/server7.0.15 и DEFAULT/RESP2. Никаких provider factory, try_acquire,
EVAL или synthetic/live reservations на production Redis при установке.
Создание начальных файлов AOF — служебная инициализация, не запрос квоты.

Public итог: `/opt/mcp/quota-redis/installation.json` (root0644).
Private complete inventory в STATE/complete.json: hashes+modes+UID/GID файлов
и директорий; generated-secret hashes не попадают в public output. Старый
A/B bootstrap-result.json сохраняется как историческая receipt — его C не
переписывается. Новый C брать из отдельного Redis installation.json.

При полном успехе: state REDIS_INSTALLED_PROVIDER_BLOCKED,
C READ_ONLY_PASS_LUA_TESTED_ONLY_OFFLINE, live_quota_reservations0,
provider_calls0/api false. Shared-with-old-clients остаётся NOT_VERIFIED.

## Повторная установка, ошибки и восстановление

- Unknown existing account/path/unit/drop-in → preflight STOP без overwrite.
- Partial STATE → STOP/reconciliation, без смены паролей/переинициализации.
- Complete STATE → проверка exact manifest/files/dirs/groups/AOF guard,
  NO restart/rotation. Outer fresh-stage verifier при повторе также безопасно
  отказывает существующему stage; исходную команду автоматически не повторять.
- Phase receipts fsync, stdout только phase/error TYPE. Ошибка после start может
  оставить новый Redis/config активным; не удалять неизвестное partial state и
  не делать новую credential generation. Provider всё время blocked.

Установленный helper `/opt/mcp/quota-redis/manage.py` запускается под root:
1. `hold` создаёт root-owned HOLD, затем останавливает только quota Redis.
   Guard сохраняет HOLD при reboot. Новый sender fail-closed; это не остановка
   сторонних WB клиентов.
2. `backup --name NAME` допускается только при stopped Redis, копирует только
   DATA (без credentials), запрещает links/unknown targets, сверяет hashes,
   сохраняет private manifest. Не перезаписывает backup.
3. `verify-backup --name NAME` сверяет backup hashes, восстанавливает в отдельную
   private verify-копию и запускает redis-check-aof **без --fix**. Live data не
   заменяет, сервис остаётся stopped/HOLD. Нет авто-reset ключей.
4. Реальное восстановление DATA по проверенной копии — отдельное root действие
   после сверки последних request journals/cooldowns и исключения in-flight
   запросов. Сохраняются snapshots, request budget не откатывается. Эта команда
   не автоматизирует опасный rollback live quota state.
5. `resume-after-reconcile --owner-reconciled` требует удалённый provider approval
   (сам его не удаляет), inactive provider unit, exact known HOLD и valid AOF.
   Снимает HOLD и стартует только quota Redis. Нового E/запуска отчётов не даёт.

Для отмены неуспешной установки админ удерживает/останавливает только новую
msp-quota-redis.service, сохраняет DATA/credentials/receipts. Не удаляет A/B,
не останавливает Hermes/Telegram/1C и не повторяет useradd автоматически.
Off-host encrypted backup/retention не настроены этим пакетом: local backups
и offline verification не доказывают защиту от потери всего VPS.

## Реальные испытания без WB/Ozon API

24 tests PASS. Десять используют настоящие бинарные файлы Redis из поставки
на временном private UNIX socket (TCP port0), не системную службу:
- DEFAULT/RESP2 и existing readonly probe с точным synthetic key;
- anonymous/readonly write/EVAL/admin/outside-prefix denial;
- реальный existing async controller Lua acquire/try_acquire/defer/snapshot;
- конкуренция двух клиентов и двух отдельных процессов; другой seller/Ozon keys;
- 429-style cooldown, backend unavailable без SQLite fallback;
- подтверждённая запись переживает настоящий SIGKILL/restart (не physical power-loss);
- повреждённый AOF отказывает без auto-truncate;
- stopped backup → отдельная restore copy → actual redis-check-aof → replay/value.

Остальные tests: explicit0644/0600 под077, first-start permit, missing AOF HOLD,
operator HOLD survives start, root refusal, repeat/partial install без rotation,
backup helper boundaries и loopback listener checks. Synthetic keys не являются
seller quota keys; никакой production Redis/config не изменялся.

Подготовленный неактивный шаблон `quota-redis-offline.workflow.yml.example` валидирует published tar+manifest+source equality и
запускает те же tests на Hosted Ubuntu24.04 с Redis client по existing hash lock;
никакого root server install. GitHub-токен не имеет workflow scope: активный новый workflow
не опубликован, права токена не расширялись. Поэтому24 tests — локальный реальный
прогон ci_check.py на exact artifact, не приписанный GitHub CI PASS. Существующий
Secret scan остаётся включён. Шаблон готов к отдельной активации администратором GitHub.
Локальная проверка systemd-analyze с заменёнными existing paths/user: syntax PASS,
**реальный новый root service/BPF/UID permissions ещё NOT VERIFIED**.
Источник ACL/persistence: https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
и https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/ .

## Старые клиенты и следующие gates

CLIENT_REGISTER.csv продолжает реестр без контакта с сервисами/выключения.
Legacy finance clients всё ещё UNKNOWN; новый local Redis не ограничивает их
напрямую. Нужны metadata владельцев и отдельный подтверждённый cutover D либо
явная адаптация сохраняемых клиентов к общей квоте. Новый токен старый не отзывает.
E и расписание не разрешены этим PR. Ozon получает свою Client-Id/global/method
quota, не WB global bucket; его method/worker acceptance остаётся отдельной.
