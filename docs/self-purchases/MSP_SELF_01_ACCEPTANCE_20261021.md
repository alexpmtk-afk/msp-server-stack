# МСП Самовыкупы — приёмка первого внедрения 2026-10-21

Цель: зафиксировать проверяемый переход от первоначальной концепции к рабочему источнику данных и базовым правилам поведения Hermes.

## 1. Рабочий импорт МСП (production)

[REMOTE Issue #486](https://github.com/alexpmtk-afk/msp-server-bridge/issues/486): `RESULT=PASS_CUTOVER`.

- Защищённые постоянные резервные копии SQLite и прежнего импортера созданы.
- Изменена только функция `selfbuy` в `apps/msp_data_sync/sync.py`; прочие локальные модификации канонического checkout не тронуты.
- Каталог: 1 558 товаров, +5, rejected=0.
- Источник самовыкупов: 92 строки, rejected=0, 6 вставок, 4 обновления, 69 unchanged, 13 планов за текущий снимок.
- БД после выполнения: 80 завершённых записей, 13 строк реестра планов (в том числе неактивные), 5 ревизий.
- Идемпотентный повтор: 0 новых вставок, 0 обновлений.
- Ранние юридические лица и количества сохранены. Целостность SQLite, FK и отсутствие неожиданных retirements проверены.
- Hermes Gateway, notifier, ежедневный user timer работают без перезапуска.
- **Не подменять этой приёмкой последующий запуск таймера в 08:00 22.10.2026:** его статус проверяется отдельно.

Источники сбоя описаны в [DECISIONS_AND_DEVIATIONS.md](DECISIONS_AND_DEVIATIONS.md), включая ошибку GitHub Actions workflow-level concurrency (старый Issue #479; замена PR #485).

## 2. Hermes Skill и оригинальные документы

[REMOTE Issue #461](https://github.com/alexpmtk-afk/msp-server-bridge/issues/461): первая установка `msp-self-purchases`, проверка оригинальных SHA-256 и `hermes skills list` — PASS.

[REMOTE Issue #488](https://github.com/alexpmtk-afk/msp-server-bridge/issues/488): обновление живых ссылочных документов. В Skill добавлен `MSP_SELF_01_SOURCE_MATRIX.md` и обновлены компас, журнал решений, текст Skill; старые версии сохранены защищённым backup. **Стартовая стенограмма и первоначальная концепция побайтно не изменены**, контроль SHA-256 — PASS. CLI вновь обнаруживает Skill; Gateway не перезапускался.

Источник последнего живого snapshot в Skill: публичный commit `bdeda7cb5657abea38d5e9b53a31d69888884551`. Следующие редакции GitHub-компаса сами по себе не автоматически развёрнуты на REMOTE; нужен проверяемый релиз ссылочных файлов.

## 3. Базовая поведенческая приёмка Hermes

[REMOTE Issue #490](https://github.com/alexpmtk-afk/msp-server-bridge/issues/490): `RESULT=PASS`; одноразовый `hermes chat --oneshot --skills msp-self-purchases`, max-turns 1, запрет инструментов/MCP/сети/shell. Текст ответа не сохранялся, только булевы проверки.

| Тема | Проверка |
|---|---|
| Пропорции 90/5/5 и 80/20 | PASS — оценки участников, не доказанные метрики |
| Исторические первоисточники | PASS — нельзя переписывать |
| Причинный эффект самовыкупов | PASS — не доказан |
| Внешние конкуренты | PASS — MPSTATS как аналитический источник |
| Собственные marketplace API по наличию кода | PASS — не объявлять LIVE_CONFIRMED без реального теста |

**Границы проверки:** это проверка интерпретации предзагруженного Skill, не доказательство автономного чтения каждой ссылки в `references/`, использования реальных MCP-инструментов, получения актуальных продаж или точности прогноза. Отдельная end-to-end проверка с одним SKU обязательна до объявления Hermes готовым аналитиком/прогнозистом.

## 4. Статус разработки и следующий путь

- `MSP-SELF-01A / own catalog + self-purchases`: PASS.
- `MSP-SELF-01B / WB-Ozon own independent sales and available stocks`: NOT YET VERIFIED.
- `MSP-SELF-01C / MPSTATS competitor matching & freshness`: PRIOR RESPONSE-SHAPE PROBES ONLY, targeted runtime check pending.
- `MSP-SELF-01D / formulas, mapping, limitations`: source matrix prepared, formal metric registry and direct-source proof pending.
- Hermes orientation: PASS; full analytical model/forecast: NOT IMPLEMENTED.

Подробный реестр: [MSP_SELF_01_SOURCE_MATRIX.md](MSP_SELF_01_SOURCE_MATRIX.md). Первоначальный замысел: [PROJECT_COMPASS.md](PROJECT_COMPASS.md) и замороженные материалы в приватном msp-server-bridge.
