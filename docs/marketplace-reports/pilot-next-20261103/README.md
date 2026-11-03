# Только оставшиеся gates первого WB pilot

A/B/C приняты владельцем; Redis installation receipt подтверждает
REDIS_INSTALLED_PROVIDER_BLOCKED, provider_calls0. Не переустанавливать и не
повторять инфраструктурный аудит. Старый REMOTE недоступен; не подключаться.

## 1. Runtime quota acceptance (без provider)

`synthetic_quota.py` подготовлен,
но на установленном Redis НЕ выполнялся. Это отдельный write scope, не READ_ONLY C.
Нет открытия WB credential, HTTP transport/factory, отчётного approval или gate YES.
Не меняет службы/ACL, не рестартует Redis, не читает/удаляет business keys.

Оператор после отдельного допуска synthetic writes запускает проверенную root-owned
копию скрипта transient unit как existing msp-reports, существующим venv Python,
с защищённым root0600 EnvironmentFile
`/etc/msp-marketplace-reports-executor/redis-runtime.env`.
Проверить SHA скопированных bytes до запуска. Для transient unit:
User/Group=msp-reports, UMask0077, NoNewPrivileges, ProtectSystem=strict,
ProtectHome=yes, PrivateTmp=yes, IPAddressDeny=any, IPAddressAllow=127.0.0.1/32,
RuntimeMaxSec=30. Не загружать кабинеты/approval и не стартовать msp-wb-pilot.
Аргумент `--synthetic-write-approved`, MARKETPLACE_REQUIRE_REDIS=1 обязательны.

Используется неизменённый installed controller/quota, pinned accepted release.
Сначала offline проверяется identity двух искусственных JWT с одним sid:
list/detail дают один finance60s + safety65s. Затем ВЕСЬ owner component
заменяется уникальным synthetic-pilot-RANDOM, до любого Redis вызова.
Создаются только4 искусственных ключа с TTL не более715секунд (контроллер
штатно сохраняет11 интервалов), не очищаются вручную. Один короткий прогон:
- два async клиента, ровно одно admission на одного synthetic owner;
- независимый другой synthetic owner;
- defer90sec, второй клиент получает отказ с ожиданием;
- результат без credentials/keys, provider_calls0, API false;
-20sec inner timeout, никаких retries/loops или реального ожидания65сек.

PASS доказывает installed async Lua/ACL/config path, но НЕ cross-host exclusion
и не работоспособность будущего systemd network allow для WB. Redis outage,
restart/AOF и two-process atomic tests уже приняты offline; не рестартовать
установленный Redis ради повторения. Probe failure => STOP, gate не открывать.
Два новых теста проверяют target boundaries и фактический runner на изолированном
Redis с тем же ACL: TEST_RESULTS.txt. Никаких live synthetic writes не было.

## 2. Исключение конфликтов при недоступном REMOTE

Локальный Redis не может запретить HTTP со старого хоста. New token/тишина/65сек
не доказывают исключение. Не снижать лимит в надежде, что старый клиент редок.

Рекомендуемый cutover — current WB seller portal/support, не SSH REMOTE:
1. Владелец/админ кабинета wb_laser_master получает metadata полного списка
   персональных/сервисных интеграций с доступом «Финансы»: название, владелец,
   expiry/status, categories, известный потребитель. Никаких token values в чат.
   Кандидаты из source register: old MarketplaceClient direct и archive_queue;
   это entrypoints, не два доказанных процесса. QRsite finance UNKNOWN.
2. Для каждой integration зафиксировать effect на цены/остатки/Telegram/1C.
   Отдельный finance-only доступ можно отозвать только после отдельного D approval.
   Если токен общий с ценами/остатками, сейчас НЕ отзывать; согласовать отдельную
   migration non-finance consumers и её проверку, либо подтверждённый selective
   finance restriction через WB. Возможность сменить scope существующего токена
   не предполагается. Нет безопасной селективной процедуры — STOP.
3. Админ предоставляет подтверждение фактического прекращения ВСЕХ иных finance
   доступов пилотного seller (эффективное время, metadata evidence, включая
   сервисные интеграции и возможность автоматического перевыпуска). При неполном
   списке запросить WB support; UNKNOWN не менять на EXCLUDED.
4. После подтверждённого cutover выдержать transition window по последним
   известным in-flight/cooldown и актуальному WB contract.65sec — только нижняя
   локальная safety, не доказательство завершения unknown старого HTTP/retry.
   Если effective-time/in-flight bounds неизвестны, нужны подтверждения WB/админа;
   произвольная пауза не заменяет evidence. Новая квота учитывает только новый worker.

Не открывать Redis в сеть. Сохранить прямого legacy finance client можно лишь
после отдельного проектирования private connectivity+same DB/owner/rules и его
адаптации, что при недоступном REMOTE сейчас невыполнимо. Новый executor обслуживает
финансовые consumers архивом, не создавая ещё один API sender. Новый token сам
старый не отзывает. Отключений/отзывов/изменений интеграций этим планом не выполнено.
При сохранении запрета на old access changes и отсутствии доказанного stop
гарантированно бесконфликтный pilot технически невозможен.

## 3. Bounded E после1–2 и отдельного разрешения API

Точный installed plan: wb_laser_master,2026,report883801632,type1,max_send_entries3.
Не расширять до списка кабинетов/годового backfill. Сначала без API проверить
private credential claims/expiry/seller mapping и finance eligibility внутри
root-controlled validation, выводить только PASS/FAIL. Не доверять одному
самостоятельно декодированному JWT как криптографическому доказательству доступа;
реальную валидность проверит только отдельно разрешённый запрос WB.
Текущий срок/доступность report и актуальный официальный method contract проверить
по документации перед E; получить документацию не равно API вызову.

Подготовить scoped root-owned runtime drop-in: существующий Redis runtime EnvFile,
REQUIRE_REDIS=1. MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES выставлять только после
runtime PASS И cutover evidence, не ради теста. approval.json создать с short expiry,
точными plan/code hashes/archive root, тремя true gates и ссылкой на evidence
только после E. Снять сетевой deny для финансового HTTP только scoped изменением
pilot unit, сохранив остальные hardening/службы. Это будущая отдельная reviewed
операция, не выполненная часть подготовки. Нет таймера/Restart/auto retry budget reset.

Первый запуск — existing bounded executor, только fixed finance detail report;
любой HTTP attempt включая retry расходует budget, не более3 durable send entries.
Остановить при401/403/неожиданном payload/неверном report,429 сохраняет cooldown,
backend failure блокирует HTTP, uncertain сохраняет бюджет, paused не COMPLETE.
Число страниц неизвестно: если3 entries не хватает, PAUSED_BUDGET и отдельное
решение о продолжении, без сброса cursor/budget. Terminal204 + staged pages,
manifest/CSV/суммы/идентификаторы отчёта проверяются; DONE с
provider_coverage_proven=false НЕ объявлять полной финансовой сверкой отчёта.
Повторная локальная reconciliation без новых API; отчёт: calls/entries/pages/rows,
checksum, path, completeness status. По окончании убрать временное E approval
в рамках разрешённого pilot closure, не меняя токены/other services.

## Состояние этой подготовки

LIVE synthetic = NOT_EXECUTED; cutover = UNKNOWN; E = NOT_AUTHORIZED.
Цены/остатки/Telegram/1C не менялись. A/B/C CLOSED.
