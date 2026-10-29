## Отчёты, которыми можно пользоваться

Для ЛЮБОЙ задачи МСП по заказам, штукам, суммам, дням/неделям/месяцам читать [общий реестр](docs/data-sources/APPROVED_REPORTS.md). При отсутствии нужных данных в QRsite MCP использовать зарегистрированный отчёт `_01_заказы`, а не искать таблицы на Drive. SQL-инструкция на сервере: `/opt/mcp/data/msp/msp_report_catalog.sqlite3`; команда `python3 /home/hermes/.local/share/msp/approved-reports/report_catalog.py guide --report orders`. Сервисный аккаунт сервера проверен; 403 отдельного коннектора ChatGPT не отменяет этот доступ. Точный ID — только в приватном локаторе/серверном registry.json. Не менять исходный отчёт.

## Совместная работа GitHub и VPS — полномочия от 27.10.2026

Для обоих MSP-репозиториев действует [единый регламент](docs/MSP_GITHUB_VPS_WORKFLOW.md). В рамках порученной задачи Hermes может создавать отдельные ветки, коммиты и PR, включая их публикацию. Это заменяет прежнее «GitHub изменяет только ChatGPT». Прямые изменения `main`, слияние PR и установка на VPS требуют отдельного согласования. Перед работой сверять актуальную базу, открытые PR и незакоммиченные изменения; не затирать работу другого помощника. Этот раздел не меняет бизнес-семантику и не разрешает операции с маркетплейсами или исходной базой.

## МСП: получение оценок — обязательное правило 28.10.2026

Для WB/Ozon и рейтинга сначала читать
`docs/self-purchases/RATING_HISTORY_SOURCES_20261028.md` и новый
Skill msp-self-purchases/references/RATING_HISTORY_SOURCES_20261028.md.
comments/by_period дают оценки без требования текста и четырёх полных
счётчиков. Считать даты и 1–5★; дата — только review_date, свои оценки
отдельно. Не объявлять выборку полной и не очищать рейтинг вычитанием 5.
Рабочий отдельный вход Hermes и манифест указаны в инструкции. Это выше
старого пункта 30. Основной отчёт/службы не заменены.

## МСП Самовыкупы — действующий приоритет 27.10.2026

**Количество:** SQLite `self_purchase.quantity` / «Кол-во выкупов» — общий план для карточки, повторяющийся в строках. Это НЕ фактически купленные единицы каждой строки и НЕ опубликованные оценки. Одна завершённая строка — одно зарегистрированное событие. Не суммировать `quantity` и не приравнивать план/строки к опубликованным 5★ отзывам.

**Окна:** анализировать каждую зарегистрированную `review_date` отдельно, в равных полностью завершённых окнах ДО/ПОСЛЕ до 90 дней, без дня T и без наложения ПОСЛЕ на следующую записанную дату отзыва. Действующая модель привязывает базовое ДО к первой дате серии, а ПОСЛЕ — к текущему checkpoint. Если несколько отзывов записаны в один день, одна временная контрольная точка со счётчиком записей; если нет завершённых суток — `POST_WINDOW_PENDING`. Общий итог серии ДО первого / ПОСЛЕ последнего — только дополнительно, не взамен поэтапного. Примеры 30 дней являются архивными либо явным параметром. Канон: `docs/self-purchases/PER_REVIEW_CHECKPOINT_WINDOWS_20261023.md` и `apps/msp_self_analytics/series_analysis.py`.

**Доказательность:** дата в реестре не подтверждает публикацию. MPSTATS `sales` — оценка заказов, не независимые оплаченные продажи. Собственные заказы учитывать отдельно; не вычитать их без проверенной связи и полноты источника. `wb_sku(comments)` и `by_period` — неполные наблюдения; сохранённый запрос `lk_wb_card_table` дал 403. Количество новых 4–5★ без подтверждённого датированного распределения остаётся UNKNOWN. Разница накопительных счётчиков не является числом новых публикаций. Причинная эффективность не доказана. Денежную окупаемость по поручению владельца временно не рассчитывать. Не изменять маркетплейсы, заказы, отзывы или SQLite.

**Ответственность:** ChatGPT и Hermes могут готовить отдельные ветки, коммиты и PR по регламенту владельца от 27.10.2026. Слияние выполняется только по отдельному разрешению; владелец подтвердил слияние этой задачи 28.10.2026. Публикация GitHub не доказывает работу на VPS. Читать `docs/self-purchases/PROJECT_COMPASS.md`, `docs/self-purchases/NONFINANCIAL_SOURCE_CONTRACT_20261026.md` и `apps/hermes/msp_self_purchases_skill/SKILL.md`.

## МСП Самовыкупы — неподтверждённая похожесть не является контрольной группой

MPSTATS `wb_similar` возвращает **кандидатов**, а не гарантированно сопоставимые товары. Если отсутствует проверяемое описание назначения и ключевых характеристик, не включать кандидатов в контрольный расчёт как доказанные аналоги. Предварительный детерминированный `peer_prefilter.py` работает только со структурой предметов и идентификаторами, но не утверждает эквивалентности. См. [регламент](docs/self-purchases/PEER_PREFILTER_20261022.md). Итоговая история по `review_date`, quantity и реальным оценкам строится исключительно по проверенным источникам.

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

<!-- MSP_SIGNAL_REGISTRY_START -->
## Единый реестр сигналов МСП — 29.10.2026

Для SIG-002/015/016/021/022/032 и анализа их отработки сначала читать
`/opt/mcp/projects/msp-server-stack/docs/signals/SIGNAL_REGISTRY.md`
(локальная копия `/home/hermes/.local/share/msp/signal-registry/OPERATIONS.md`).
Реестр SQLite: `/opt/mcp/data/msp/msp_signal_registry.sqlite3`;
вход: `python3 /home/hermes/.local/share/msp/signal-registry/registry.py status`,
затем `show --id ID`. Обратная связь в Удалённом сервере и Hermes Group —
отработка, но НЕ подтверждение успешного действия. Результат сохранять отдельно
по товару/площадке/кабинету с доказательствами, имитацию не выдавать за факт.
При ручной работе связывать сохранённую обратную связь через `link` и добавлять
непокрытые журналами исполнителей результаты через `record-action` по инструкции.
Неоднозначные сообщения не закрывают сигнал; не угадывать связь по названию.
Не запускать повторно действия/отправки ради заполнения реестра.

### Обязательность с 29.10.2026
Владелец поручил Hermes вести реестр постоянно для всех чатов и агентов сервера.
Каждый считанный сигнал, обратная связь и действие подлежат записи; работа не
завершена до проверки записи через show. Навык:
`/home/hermes/.hermes/skills/productivity/msp-signal-registry/SKILL.md`.
Автосбор охватывает подключённые журналы; ручные/новые исполнители обязаны
дополнять их через record-action/link. При сбое фиксировать пробел и сверять
квитанции, не повторять внешнее действие ради заполнения реестра.
<!-- MSP_SIGNAL_REGISTRY_END -->
