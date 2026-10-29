# P01 — фактическая общая очередь Marketplace MCP, 29.10.2026

## Итог

**P01 = NOT VERIFIED: действующая общая очередь не найдена/не подтверждена доступным каналом.** Подтверждена только ограниченная отрицательная инвентаризация нового VM-817589. Нельзя утверждать, что очереди вообще нет или что старый VM-684381 выключен. Ничего не устанавливали и не перенастраивали.

## Свежие подтверждения на VM-817589

Проверка под `hermes`, UID 1001, без повышения прав. Эти данные получены в данной проверке, не переписаны из старых результатов владельца.

| Проверка | Статус / фактический результат |
|---|---|
| hostname / id | PASS: VM-817589, UID 1001 |
| TCP 127.0.0.1:6379 | FAIL для доступности: connect_ex=111 (отказ подключения) |
| TCP listeners 6379/6380 | PASS: ss не обнаружил listeners |
| System/user unit names marketplace/mcp/redis/valkey | PASS: совпадающих unit-файлов не обнаружено |
| Имена system/user service-файлов с содержимым marketplaces-mcp / MARKETPLACE_MCP / redis-server / valkey-server | PASS: совпадений в доступных каталогах нет; вывод только имён, не содержимого |
| Process comm redis/valkey/marketplace/docker/podman | PASS: совпадений нет; argv/env процессов не выводились |
| docker/podman/redis-server/valkey-server/redis-cli | PASS: command -v не нашёл стандартные команды |
| Доступные верхние каталоги /opt/mcp | data, runtime, projects; projects содержит msp-server-stack, runtime — dev-executor. Локальная копия legacy в scratch — материал ревизии, не работающий сервис |
| MCP подключения текущего Codex | hermes-tools, mpstats, onec-stock; отдельного legacy Marketplace MCP нет |
| mcp_servers текущего Hermes default | onec_stock; отдельного legacy Marketplace MCP нет |
| Имена конфигурации Redis в доступном Hermes .env | MARKETPLACE_MCP_REDIS* / MARKETPLACE_REQUIRE_REDIS / MARKETPLACE_MCP_* не обнаружены; значения не выводились |
| .env production checkout | отсутствует по проверенному пути; это не инвентаризация всех root-конфигураций |
| SSH-каталог текущего пользователя | `/home/hermes/.ssh` отсутствует; доступ к root SSH-конфигурации не установлен |
| Доступные инструменты текущего сеанса | нет legacy WB/Ozon MCP-инструмента состояния очереди; сторонний MPSTATS не доказывает существование этой очереди |

Не сканировались чужие профили, не извлекались кабинеты/ключи, не запускались неизвестные приложения и startup hooks. Нет доказательств относительно альтернативных портов, произвольных имён процессов/контейнеров, удалённых backend или root-only файлов.

## Что доказывает старый GitHub-код, а что — нет

Legacy source baseline `0510a409ab589c639930fbca35afb3e68d874f81`, `docs/rate-limit-contract.md`: заявлена локальная Redis 127.0.0.1:6379 и обязательный MARKETPLACE_REQUIRE_REDIS. `core/rate_limit.py` описывает namespace `marketplace-rate:v1`, stable seller/client identity, atomic Lua и URL/host/DB конфигурацию.

**PASS:** контракт исходников изучен. **NOT VERIFIED:** фактический endpoint/DB/namespace/version/consumer set на историческом VM-684381 и существование самого работающего экземпляра в настоящее время. Loopback старого сервера и loopback нового сервера — разные backend; их нельзя назвать общей очередью.

В `scripts/check_rate_limit_backend.py` есть безопасный read-only PING-путь при `--require-redis`, но также изменяющий Redis режим `--repair-legacy-wb`. Ничего из этого не запускалось: рабочий legacy runtime/авторизованный доступ не найден. Для диагностики нельзя запускать приложение со startup cleanup или добавлять `--repair-legacy-wb`.

## Точный блокер и следующий шаг

Не установлен разрешённый канал исполнения/чтения состояния реально действующего старого Marketplace MCP: нет его настроенного MCP-подключения, доступного SSH-профиля или подтверждённого read-only executor для того хоста. Github исходники и новый серверный dev-executor не дают автоматически доступ к старому серверу.

Следующее необходимое действие — предоставить/подтвердить существующий разрешённый read-only маршрут к действующему экземпляру (или его актуальный безопасный deployment inventory). Нужен маршрут/расположение runtime, НЕ токены WB/Ozon и НЕ пароли в чате. Через него проверить конфигурационный контракт, Redis PING/DB/namespace и совпадение ключей без резервирования запросов или изменения очереди. Не устанавливать новый Redis в качестве обхода.

До подтверждения P01 блокировка архиватора сохраняется. Этот отчёт — отдельный результат P01, не заявление об успешном нахождении очереди.
