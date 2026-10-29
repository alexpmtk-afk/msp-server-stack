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

## Продолжение после расширения GitHub-доступа

Проверка исходников дополнительных repo теперь **PASS**, прежнее отсутствие repo-доступа больше не является актуальным блокером. Это не снимает отдельное ограничение на доступ к действующему старому runtime.

- Изучены marketplace-mcp-bridge и mcp-yandex-cloud-infra; найдены исторические transport/workflow сведения. Частные locator-данные сохранены только в [PRIVATE отчёте bridge PR №720](https://github.com/alexpmtk-afk/msp-server-bridge/pull/720), не копируются в публичный stack.
- Инфраструктурный Yandex baseline расходится с REMOTE картой marketplaces-mcp-ru; старые success workflow не приняты за доказательство текущего Redis/backend. Установочные/repair/облачные workflow не запускались.
- Свежая DNS-диагностика опубликованного legacy entry обнаружила несовпадение с source-map адресом. TLS handshake без credentials и без отключения проверки завершился `SSL: WRONG_VERSION_NUMBER`; это не доказательство истёкшего сертификата, авторизации MCP или отказа Redis. Plaintext fallback не использовался.
- Эффективный доступ marketplace-mcp-bridge Actions workflows/runners — HTTP 403. gpt-powershell-bridge metadata — HTTP 404 (недоступен либо отсутствует, не утверждать удаление). Исторические инструкции отсылают к Windows-каналу; его текущая работоспособность NOT VERIFIED.
- Нужен существующий разрешённый read-only executor к актуальному хосту. Следующий доступ для проверки маршрута: Contents к gpt-powershell-bridge/подтверждение его существования; для workflow/run/job history — Actions read Marketplace bridge; API списка registered self-hosted runners требует отдельно Administration read (опционально, не выдавать автоматически). Никаких паролей/ключей в чате. Сначала подтвердить hostname/identity, затем service config/PING/namespace/совпадение общих buckets без startup cleanup и записи слотов.

**P01 по-прежнему NOT VERIFIED, но поиск существенно продвинут.** Найденный документ/старый маршрут/новый DNS нельзя автоматически считать работающей общей очередью. Ничего не сливалось, не устанавливалось, Redis и службы не менялись, маркетплейс API не вызывались.

## Повторная проверка расхождения подключений

Действующий PAT Hermes подтверждён (`/user` 200, ожидаемый owner); GPT repo остаётся 404 и через REST main/bridge-v2, и через read-only GraphQL. Marketplace Contents 200, private Actions 403 с `Resource not accessible by personal access token`; аналогичный private control MSP bridge также Contents 200 / Actions 403. Это ограничение конкретного PAT, не отсутствие repo/runner/очереди; успешный коннектор коллеги с ним не отождествляется.

Корректировка: история Actions требует `actions=read`, а runner-list endpoint — `administration=read`. Header отражает требования endpoint, не выданные права. Точный token resource selection извне не установлен; проверить его и Contents read для GPT repo может владелец подключения, без передачи токена в чат. Права не менялись.

Прочитан доступный исторический CURRENT_PC_ACCESS.md: WORK executor обозначен, но online/identity/действующая whitelist не подтверждены. Коллега сообщает, что bridge-v2 историческая; сначала нужен main README и указанная им текущая policy, не запуск старого маршрута. Подробный диагноз и безопасные ответы API — в [PRIVATE bridge PR №720](https://github.com/alexpmtk-afk/msp-server-bridge/pull/720). P01 остаётся NOT VERIFIED.

## 2026-10-29 — Hermes: проверка безопасной выдержки PR №729

- **DOCUMENT REVIEW=PASS:** прочитан точный `c5c460dc240a42053b19cab7e73da42f857cbbcd`, безопасная выдержка актуальной политики; сопоставлена с PRIVATE PR №720. Исторические инструкции не приняты за online/runtime. Оригиналы недоступны подключению Hermes: независимое соответствие исходникам **NOT VERIFIED**, это не новый успешный доступ к исходному repo.
- **P01 / LIVE READ-ONLY CHANNEL=NOT VERIFIED:** не определён точный существующий read-only workflow/launcher/whitelist с закреплённой версией и допустимыми inputs; online исполнителя, конечная identity и общая Redis очередь не подтверждены.
- Один следующий шаг: коллега через уже доступное Contents-подключение фиксирует контракт существующей разрешённой read-only диагностики в PRIVATE bridge, без запуска и без создания новой операции. Если операции нет, это отдельный подтверждаемый блокер.
- Полное заключение — REVIEW_P01_PR729_C5C460DC.md в PRIVATE PR №720; ответ коллеге публикуется в PRIVATE PR №729. Рекомендуется связный source commit SHA и точное указание требования Administration read именно для runner-list REST endpoint. Права не расширялись, Actions не запускались, чужая ветка и runtime не менялись.
