## МСП Самовыкупы — обязательное уточнение даты события (22.10.2026)

В оценке изменений после появления отзыва **T = дата отзыва** (`review_date`) из `Реестр выкупов/отзывов`, а не `Дата выкупа` (`purchase_date`). Дата покупки остаётся для учёта события и задержки до отзыва, но не запускает сравнение после отзыва. Отсутствует `review_date` — не проводить оценку последствий отзыва; не считать ссылку доказательством опубликованной даты без независимой проверки. Два сценария: новые товары без предыдущих оценок; карточки с низким рейтингом. Следить за **новыми датированными отзывами**, рейтингом, доступными заказами/продажами и другими причинами динамики. Старые результаты, рассчитанные относительно покупки, только подтверждают доступность MPSTATS. Канон: [REVIEW_PUBLICATION_EVENT_MODEL_20261022.md](docs/self-purchases/REVIEW_PUBLICATION_EVENT_MODEL_20261022.md); действующие формулы в `apps/msp_self_analytics/`. Не менять оригинальные исторические документы и не выполнять действий, создающих фиктивные заказы или отзывы.

# AGENTS.md

When handling **MSP Marketplace Telegram signals** or the SIG-002 price-advice case, agents must use the canonical `docs/signals/REVIEWED_RULES_2026-10-05.md` and the Hermes manual Skill `apps/hermes/msp_signals_skill/SKILL.md`; passive background processing uses `apps/msp_signal_notify/notify.py`. In particular, SKU + `_N` days with **no** production/inbound date in the signal means **recommend raising price** (not «cannot determine»). The skill is instructions only; no marketplace write actions are authorized. Do not change Hermes Gateway or the MSP daily timer when deploying this skill.

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
