# МСП — локальный архив отчётов WB/Ozon (этап 0)

Это отдельный, неустановленный пока модуль для VPS МСП. Он не меняет рабочий Marketplaces MCP, заказы, цены, рекламу, Bitrix или существующие службы. На текущем этапе подготовлены **ручные обработчики API и отдельный клиент с ограничением методов**; производственное развёртывание, реестр достоверного покрытия и расписание ещё отсутствуют. Предусмотрен также безопасный импорт уже полученных CSV в локальную структуру.

## Запуск тестов (без сети)

```bash
python3 -m unittest discover -s tests -p 'test_msp_marketplace_reports.py' -v
```

## Команды (после согласования установки)

```bash
python3 -m apps.msp_marketplace_reports.cli --root /path/to/test-archive status
python3 -m apps.msp_marketplace_reports.cli --root /path/to/test-archive verify
python3 -m apps.msp_marketplace_reports.cli --root /path/to/test-archive import-csv --dataset wb_weekly_finance_main --cabinet wb_laser_master --period 2026 --source /path/to/wb_annual.csv
python3 -m apps.msp_marketplace_reports.cli --root /path/to/test-archive import-csv --dataset ozon_final_realization --cabinet ozon_laser_master --period 2026-01 --source /path/to/ozon_2026-01.csv
```

WB — годовой CSV с ключом (reportId, rrdId): новые строки добавляются без дублей; конфликт одного ключа останавливает обновление. Ozon FINAL — месячные CSV и пересобранный годовой файл, месячный источник может быть исправлен. Ozon CURRENT — сменяемые месячные снимки FBO/FBS/начислений. Формат CSV UTF-8 BOM, разделитель `;`.

На каждую запись создаётся `*.csv.meta.json` (число строк, SHA256, идентификатор, период). Старая версия при изменении резервируется в `.backups/`. Запись одного файла атомарна с `fsync`, конкурирующие операции одного набора блокируются через `flock`. Тестовый импорт не является доказательством полноты истории у провайдера. Метка `LOCAL_VERIFIED` намеренно **не равна** `COMPLETE` из API.

ВНИМАНИЕ: обновление пары Ozon `monthly_source + annual` пока не является единой атомарной транзакцией при аварии машины. Проверка `verify` должна проходить после любого импорта. До боевой эксплуатации необходима проверка восстановления после сбоя и реестра покрытия API.

Не коммитить реальные отчёты, реквизиты, токены, файлы `.env`, дампы и резервные копии.

## Ручные проверки API — только после установки и разрешения

Все команды ниже запускаются на VPS оператором, не из GitHub Actions. Реальные токены в аргументы не передаются. Не использовать `sudo` для чтения файлов произвольного происхождения. Файл реквизитов должен быть локальным, защищённым (0600 либо 0640 при доверенной закрытой группе), не ссылкой.

Пример структуры `/opt/mcp/secrets/msp-marketplace-reports/cabinets.json` **только с фиктивными значениями**:

```json
{
  "wb_laser_master": {"token": "REPLACE_LOCALLY"},
  "wb_novokshenov": {"token": "REPLACE_LOCALLY"},
  "wb_dmitrieva": {"token": "REPLACE_LOCALLY"},
  "ozon_laser_master": {"client_id": "REPLACE_LOCALLY", "api_key": "REPLACE_LOCALLY"},
  "ozon_novokshenov": {"client_id": "REPLACE_LOCALLY", "api_key": "REPLACE_LOCALLY"},
  "ozon_dmitrieva": {"client_id": "REPLACE_LOCALLY", "api_key": "REPLACE_LOCALLY"}
}
```

Примеры команд (их ещё **не запускали** на сервере):

```bash
C=/opt/mcp/secrets/msp-marketplace-reports/cabinets.json
python3 -m apps.msp_marketplace_reports.ingest --creds-file "$C" credential-status
python3 -m apps.msp_marketplace_reports.ingest --creds-file "$C" wb-list --cabinet wb_laser_master --year 2026
python3 -m apps.msp_marketplace_reports.ingest --creds-file "$C" wb-one --cabinet wb_laser_master --year 2026 --report-id 123456789
python3 -m apps.msp_marketplace_reports.ingest --creds-file "$C" ozon-final-one --cabinet ozon_laser_master --period 2026-09
```

`123456789` — **не настоящий номер**, его необходимо взять из списка `wb-list`. Для Ozon CURRENT доступна ручная команда `ozon-current --cabinet ...`, однако тройной снимок пока не транзакционный; до отдельного испытания и согласования на реальных кабинетах её не использовать.

Доступные методы строго ограничены: WB POST `/api/finance/v1/sales-reports/list` и `/detailed/{reportId}`; Ozon POST `/v1/finance/realization/posting`, `/v3/posting/fbo/list`, `/v4/posting/fbs/list`, `/v1/finance/accrual/by-day`. Программа не вызывает методы изменения товаров, цен, заказов или рекламы.

Локальное ограничение запросов: 63 секунды между обращениями WB на кабинет, консервативные 5 секунд для Ozon на кабинет; любые 429 завершают текущую попытку без публикации неподтверждённого отчёта. Эти задержки — защитные настройки, **не доказательство действующих квот Ozon**. Перед производственным применением обязательны сверка с провайдером и проверка общего ограничителя при наличии иных приложений с теми же ключами.

**Ограничения текущего этапа:** однократное ручное получение одного WB отчёта или закрытого месяца Ozon; ещё нет общего реестра обработанных отчётов `COMPLETE`, безопасного восстановления с курсора между перезапусками или полноценной массовой загрузки шести кабинетов. Пустой ответ пока приводит к отказу: отсутствие операций нельзя автоматически считать подтверждённым нулём. Встроенный `verify` доказывает только локальную целостность CSV и не подтверждает полноту архива у WB/Ozon.

Для следующей разработки: источник защищённых ключей на VPS, реестр provider coverage, длительная очередь, безопасная двухфайловая/многофайловая публикация и резервирование вне основного диска. Никаких сырых CSV, ключей и дампов в GitHub.
