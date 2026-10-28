# МСП — локальный архив отчётов WB/Ozon (этап 0)

Это отдельный, неустановленный пока модуль для VPS МСП. Он не меняет рабочий Marketplaces MCP, заказы, цены, рекламу, Bitrix или существующие службы. На текущем этапе **API-загрузчиков и расписания нет**; предусмотрен безопасный импорт уже полученных CSV в локальную структуру.

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
