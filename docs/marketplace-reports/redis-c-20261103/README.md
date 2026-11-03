# C: существующий Redis и безопасное подключение — 03.11.2026

## Итог

**A/B подтверждены readback, не переустанавливались. C пока NOT CONFIGURED.**
Подходящий существующий backend, доступный с VM-817589 и доказанно общий для WB
finance clients, **не найден/не подтверждён**. Это не утверждение, что Redis
вообще не существует: закрытые конфиги root недоступны Hermes, внешний Redis
может не иметь локальной службы или стандартного порта.

## Что установлено самостоятельно

- Прочитан реальный bootstrap-result.json: A PASS, B REUSED_NOT_RECOPIED,
  storage_smoke PASS, uid995/gid985, state INSTALLED_API_BLOCKED, api false,
  provider_calls0. Все17 установленных модулей и Redis probe checksum MATCH.
- Свежий GitHub read канонического marketplaces-mcp-ru:
  SHA0510a409ab589c639930fbca35afb3e68d874f81; tree не truncated.
  [ARCHITECTURE](https://github.com/alexpmtk-afk/marketplaces-mcp-ru/blob/0510a409ab589c639930fbca35afb3e68d874f81/ARCHITECTURE.md)
  и [rate-limit contract](https://github.com/alexpmtk-afk/marketplaces-mcp-ru/blob/0510a409ab589c639930fbca35afb3e68d874f81/docs/rate-limit-contract.md)
  указывают local loopback Redis старого REMOTE, не опубликованный наружу.
  Этот адрес НЕ переносился на новый VPS и сетевой probe к нему не выполнялся.
  Retired Yandex/Lockbox не является подтверждённым current backend.
- Текущее bridge tree b901fdc299cc41dbd6cee5c83281c6c335895d0d не содержит
  dedicated Redis/Valkey/terraform deployment paths по ограниченному search.
  Это не доказательство отсутствия конфигурации в secret store.
- На новом VPS в разрешённом shell нет Redis env names; видимых system unit
  names redis/valkey нет, слушателей6379/6380 в local ss нет; /etc/redis,
  /etc/valkey и исторический secret path отсутствуют. Не сканировались чужие
  адреса/порты, не создавался Redis, не вызывался controller factory.
- Current protected /etc/msp-marketplace-reports и
  /opt/mcp/secrets/msp-marketplace-reports root0700. Невозможность stat/read
  redis-readonly.env под закрытым parent — PERMISSION_DENIED, не ABSENT.

Машиночитаемые границы: evidence.json.

## Механизм WB quota, который нужно подключить

В установленном quota.py owner берётся из seller sid, затем SHA256; не token
hash и не display-name кабинета. Finance list/detail используют canonical scope
finance, договор1req/min и local safety65s, preserved wait66s. Общие ключи
marketplace-rate:v1:wb:<seller-derived-owner>...; их точные identities не
публикуем и не угадываем. Atomic Redis admission требуется для каждого клиента,
а не новый независимый Redis, локальный flock или отдельная namespace.

Подтверждение backend должно включать фактический endpoint, DB, TLS/CA/auth/ACL,
identity продавца и scope/key derivation; участие остальных finance clients
доказывается отдельно. Code equality и успешный PING не доказывают sharing.
MSP_REPORTS_SHARED_QUEUE_VERIFIED остаётся выключенным, Lua/квоты не меняются.
Старый server не ищется: его доступность/отключение не выводятся из этих данных.

## Один конкретный root-шаг без переустановки

В существующей root-консоли VM-817589 выполнить одну строку из
[ROOT_ONE_LINE.txt](ROOT_ONE_LINE.txt). Source уже на VPS:
`/home/hermes/workspace/msp-wb-stage-c.py`.
Команда создаёт только root-only snapshot диагностического скрипта, сверяет
literal SHA256 и запускает его с -I -B. Сам root запуск здесь не выполнен.

Скрипт:
1. Смотрит только bounded inventory четырёх согласованных config directories и
   пяти relevant units. Для .env выводит **только Redis variable names**, не
   значения/адреса/passwords. Cabinets/tokens/JSON не открывает. Symlink,
   hardlink, unsafe owner/mode/oversized file → STOP.
2. Не назначает любой найденный env «утверждённым». Не копирует source env целиком,
   не создаёт config, не выбирает кандидата автоматически.
3. Если designated approved `/etc/msp-marketplace-reports/redis-readonly.env`
   уже существует root0600, проверяет Redis-only assignments, exact installed
   manifest/code/probe/runtime checksum/links из complete receipt.
4. Только после этого отдельный transient msp-wb-stage-c-readonly выполняет
   неизменённый installed Redis probe как msp-reports. Нет WB credentials,
   downloader, flags, timer, reload/restart соседних служб. Read-only commands
   PING/TIME/INFO server, DEFAULT+RESP2 identity comparison; никаких SET/EVAL,
   SCAN/KEYS, try_acquire/defer/очередей. AUTH/HELLO/SELECT/CLIENT SETINFO могут
   выполняться самим клиентом как handshake, без изменения quota keys.
5. Если approved env отсутствует, выводит C NOT_CONFIGURED вместе с redacted
   inventory. Это конкретная проверка скрытой конфигурации, НЕ C PASS.

Script SHA256: `057d1526c7b486c2a994da8df44ee15a9a3974122d9c92cbffdf3c2bdeac864b`.
6 новых synthetic tests PASS; source/script readback и shell syntax verified.
Никаких новых тестов195/23 или повторного A/B. Existing receipt не переписывается.

## Что требуется для подключения после root-результата

Если inventory покажет реальный исходный Redis config, нужно привязать его к
текущему утверждённому finance controller, а не к unrelated cache. Администратор
без передачи секретов в чат предоставляет Redis-only projection в designated
root0600 env, оставляя источник неизменным; не WB токен и не весь env кабинетов.
Если доказанного source нет и после root check — нужен фактический backend от
администратора действующей интеграции. Это недостающий технический input, не
повторное permission A/B/C. Новый Redis не создавать и старый loopback не туннелить.

На этом этапе connection НЕЛЬЗЯ заполнить выдуманным hostname, портом из примера
или localhost нового VPS. CA/ACL compatibility проверяются под msp-reports; права
original secrets не ослабляются ради успешного probe. Не требуется повторный
useradd, копирование токена, установка dependency или service restart.

## Что можно доказать без WB/Ozon API

- фактические client/backend versions, DNS/TCP/TLS/auth/CA при approved endpoint;
- PING/TIME/INFO и default/RESP2 compatibility; backend identity comparison
  внутри двух соединений, без вывода run_id/координат;
- exact known-key EXISTS/PTTL только после утверждённого private key inventory;
  нынешняя команда их не угадывает и не посылает;
- source/runtime owner/scope/namespace checks без token output.

READ_ONLY не проверяет atomic Lua scheduling, async-controller admission,
отсутствие других клиентов и provider permissions. Отдельный bounded write-test
существующего Redis controller потребует самостоятельного допуска: C сейчас
запись не разрешает. Missing keys/тишина/нет429 не доказывают отсутствие старых
финансовых запросов.

## До первого реального WB отчёта

1. Подтверждённый backend и C read-only PASS либо честный конкретный failure.
2. Доказанная seller-scoped shared quota и исключение конфликтующих клиентов.
   Отзыв токенов/отключение интеграций без отдельного D не выполняется.
3. Runtime atomic admission остаётся NOT VERIFIED, пока нет разрешённого proof.
4. Отдельный E для одного wb_laser_master/main883801632,max3 durable send entries;
   network/gate/approval включаются только тогда. Не весь2026 и не Ozon activation.

Архив и пользователь уже работают; к их установке не возвращаемся. C не объявляем
закрытым до фактического runtime результата. Real API/provider calls и Redis writes0.
