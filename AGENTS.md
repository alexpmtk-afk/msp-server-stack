## Отчёты, которыми можно пользоваться

Для ЛЮБОЙ задачи МСП по заказам, штукам, суммам, дням/неделям/месяцам читать [общий реестр](docs/data-sources/APPROVED_REPORTS.md). При отсутствии нужных данных в QRsite MCP использовать зарегистрированный отчёт `_01_заказы`, а не искать таблицы на Drive. SQL-инструкция на сервере: `/opt/mcp/data/msp/msp_report_catalog.sqlite3`; команда `python3 /home/hermes/.local/share/msp/approved-reports/report_catalog.py guide --report orders`. Сервисный аккаунт сервера проверен; 403 отдельного коннектора ChatGPT не отменяет этот доступ. Точный ID — только в приватном локаторе/серверном registry.json. Не менять исходный отчёт.

## Совместная работа GitHub и VPS — полномочия от 27.10.2026

Для обоих MSP-репозиториев действует [единый регламент](docs/MSP_GITHUB_VPS_WORKFLOW.md). В рамках порученной задачи Hermes может создавать отдельные ветки, коммиты и PR, включая их публикацию. Это заменяет прежнее «GitHub изменяет только ChatGPT». Прямые изменения `main`, слияние PR и установка на VPS требуют отдельного согласования. Перед работой сверять актуальную базу, открытые PR и незакоммиченные изменения; не затирать работу другого помощника. Этот раздел не меняет бизнес-семантику и не разрешает операции с маркетплейсами или исходной базой.

## МСП Самовыкупы — приоритет 22.10.2026: план серии, не количество в строке

**ОБЯЗАТЕЛЬНО:** source `Кол-во выкупов` / SQLite `quantity` = общее **плановое количество для карточки**, повторяется в каждой строке. Одна завершённая строка = один записанный выкуп; строка с датой отзыва = одна запись об отзыве, НЕ гарантированная опубликованная пятёрка. Нельзя `sum(quantity)` для подсчёта выкупов; ошибочные 136 WB/92 with review ранее выведены из повторяемого плана и **SUPERSEDED**. Сгруппируй все строки `marketplace,store,sku`; ДО = N дней до **первой** даты отзыва; ПОСЛЕ = N дней после **последней** даты отзыва (по умолчанию N=30). Промежуточный вывод допускается при неполной серии 3/5 только на завершённом равном времени, итоговый — после серии. Расчётный канон `apps/msp_self_analytics/series_analysis.py`, `series_report.py`, [решение](docs/self-purchases/SERIES_TARGET_PER_ROW_CORRECTION_20261022.md). Не выполнять действий с искусственными заказами или отзывами.

## МСП Самовыкупы — неподтверждённая похожесть не является контрольной группой

MPSTATS `wb_similar` возвращает **кандидатов**, а не гарантированно сопоставимые товары. Если отсутствует проверяемое описание назначения и ключевых характеристик, не включать кандидатов в контрольный расчёт как доказанные аналоги. Предварительный детерминированный `peer_prefilter.py` работает только со структурой предметов и идентификаторами, но не утверждает эквивалентности. См. [регламент](docs/self-purchases/PEER_PREFILTER_20261022.md). Итоговая история по `review_date`, quantity и реальным оценкам строится исключительно по проверенным источникам.

## Самовыкупы МСП: количество единиц и доказательства отзывов

В обоих сценариях исторической аналитики учитывать `self_purchase.quantity`: число выкупленных единиц, а не число строк. Бизнес-предположение владельца «1 единица — потенциально 1 оценка пять звёзд» НЕ подтверждает фактически опубликованные оценки: нужны уникальные датированные отзывы и проверенные значения. Одна дата отзыва в строке `quantity>1` не доказывает одинаковую дату публикации всех возможных отзывов. Не подменять количеством единиц рейтинг карточки, число фактических отзывов или органические заказы. Канон: [PURCHASE_QUANTITY_REVIEW_EVIDENCE_20261022.md](docs/self-purchases/PURCHASE_QUANTITY_REVIEW_EVIDENCE_20261022.md). Только описательная история, без автоматизации искусственных покупок и отзывов.

## МСП Самовыкупы — обязательное уточнение даты события (22.10.2026)

В оценке изменений после появления отзыва **T = дата отзыва** (`review_date`) из `Реестр выкупов/отзывов`, а не `Дата выкупа` (`purchase_date`). Дата покупки остаётся для учёта события и задержки до отзыва, но не запускает сравнение после отзыва. Отсутствует `review_date` — не проводить оценку последствий отзыва; не считать ссылку доказательством опубликованной даты без независимой проверки. Два сценария: новые товары без предыдущих оценок; карточки с низким рейтингом. Следить за **новыми датированными отзывами**, рейтингом, доступными заказами/продажами и другими причинами динамики. Старые результаты, рассчитанные относительно покупки, только подтверждают доступность MPSTATS. Канон: [REVIEW_PUBLICATION_EVENT_MODEL_20261022.md](docs/self-purchases/REVIEW_PUBLICATION_EVENT_MODEL_20261022.md); действующие формулы в `apps/msp_self_analytics/`. Не менять оригинальные исторические документы и не выполнять действий, создающих фиктивные заказы или отзывы.

# AGENTS.md

When handling **MSP Marketplace Telegram signals** or the SIG-002 price-advice case, agents must use the canonical `docs/signals/REVIEWED_RULES_2026-10-05.md` and the Hermes manual Skill `apps/hermes/msp_signals_skill/SKILL.md`; passive background processing uses `apps/msp_signal_notify/notify.py`. **Superseded for SIG-002 on 27.10.2026:** missing inbound date in the Telegram signal is NOT proof of missing production order. Use the approved `apps/hermes/msp_signals_skill/references/production-orders.md` decision workflow: per-card `_N` coverage; read `product_listing` and both production tables; empty actual-production-received field = zero; compare confirmed incoming to coverage; liquidation/business owner overrides price raise; no Ozon FBO logistics calculation. The skill is instructions only; no marketplace write actions are authorized. Do not change Hermes Gateway or the MSP daily timer when deploying this skill.

## Обязательное правило МСП: журнал цен без даты\n\n**Утверждено владельцем 22.10.2026.** В `price_journal_current` и `price_journal_archive` любая строка с пустой/пробельной колонкой `дата` молча игнорируется, не становится `rejected`, не создаёт `sync_error`, не влияет на `partial` и не вызывает уведомления. Никакой эскалации владельцу. Подробно: [`docs/PRICE_JOURNAL_MISSING_DATE_POLICY.md`](docs/PRICE_JOURNAL_MISSING_DATE_POLICY.md). Применение на REMOTE и в Hermes **подтверждено**: [`docs/PRICE_JOURNAL_MISSING_DATE_ACCEPTANCE_20261022.md`](docs/PRICE_JOURNAL_MISSING_DATE_ACCEPTANCE_20261022.md). Это правило выше устаревших инструкций; непустая, но некорректная дата и другие ошибки датированных строк остаются проверяемыми.\n\n## МСП Самовыкупы — обязательный компас

При ЛЮБОЙ задаче по истории самовыкупов, запуску новых карточек, рейтингу, анализу конкурентов, рекомендации по SKU или прогнозу для Hermes сначала прочитай `docs/self-purchases/PROJECT_COMPASS.md` и `docs/self-purchases/DECISIONS_AND_DEVIATIONS.md`. Для сверки первоначального замысла авторизованному агенту также необходимо обратиться к **приватным** первоисточникам в `alexpmtk-afk/msp-server-bridge/docs/self-purchases/original/`: стенограмма совещания и первоначальная концепция v1.0. Не предполагай, что открытый GitHub-репозиторий автоматически даёт доступ к приватному архиву. Если доступа нет — явно сообщи об этом. Не переписывай первоисточники, изменения фиксируй в журнале решений. Перед утверждением выполнения на REMOTE отдельно проверь локальную копию и доступ Hermes. Не реализуй автоматизацию искусственных заказов или отзывов.

Instructions for chats, coding agents and automated assistants working with this repository.

## Before working with REMOTE

1. Read [docs/REMOTE_INTERACTION.md](docs/REMOTE_INTERACTION.md).
2. Read [inventory/services.yaml](inventory/services.yaml) for the current component map.
3. Do not assume that GitHub access means server access.
4. Use only an authorized execution channel actually available to the current agent/chat.
5. Never request, print, commit or copy production secrets into GitHub.
6. Prefer read-only diagnostics before state-changing actions.
7. After every state-changing action, perform an independent verification and report the result.

If the required REMOTE execution channel is not available, stop at preparation: produce the exact safe task or command for an authorized executor instead of pretending it was executed.
