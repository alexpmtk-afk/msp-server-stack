# SIG-002: кнопки «Да / Нет» для каждого товара (15.10.2026)

## Решение
Оставляем обработку «Сигналы МП» с интервалом 60 секунд. Для каждого SKU из
нового SIG-002 вместо одного общего отчёта отправляется отдельное сообщение
с рекомендацией и двумя inline-кнопками «Да — поднять» / «Нет — отклонить».

Только нажатие человеком отправляет Orgobot метод orgobot_price_decide с
answer yes/no. Сигнал или совет Hermes НИКОГДА не подтверждает решение
самостоятельно. Процент повышения определяется правилами Orgobot 48/52.

## Компоненты
- apps/msp_signal_notify/notify.py — отдельное Telegram-сообщение на SKU;
- apps/msp_signal_notify/price_buttons.py — одноразовые токены, SQLite,
  разрешённые пользователи и строгие Orgobot MCP методы;
- apps/hermes/msp_price_buttons_plugin/ — регистрация callback через существующий
  Hermes Gateway без второго getUpdates и без нового Telegram-бота;
- apps/msp_data_sync/run_with_alerts.py — опциональный inline reply_markup;
- apps/hermes/msp_signals_skill/SKILL.md — инструкции агента.

Telegram не позволяет расположить inline keyboard в середине одного сообщения.
Поэтому используется одно сообщение на SKU и клавиатура сразу под текстом.

## По умолчанию выключено
MSP_PRICE_BUTTONS_ENABLED=1 — включить отправку отдельных карточек.
MSP_PRICE_LIVE_ENABLED=1 — разрешить обработку нажатий через Orgobot.
MSP_PRICE_BUTTON_ALLOWED_USER_IDS — список числовых ID пользователей.
MSP_ORGOBOT_EXECUTOR_USERNAME — ник исполнителя Hermes Bot.
По умолчанию ни отправка кнопок, ни запись в Orgobot не включаются.

Токен QRsite MCP берётся из защищённого файла
/opt/mcp/secrets/andrey-qrsite.env и никогда не выводится в логи/GitHub.

## Приёмка перед включением
1. Offline-тесты price_buttons, notify, skill, data-alerts — PASS.
2. Read-only проверка поддержки register_platform_handler на версии Hermes VPS.
3. Read-only проверка Orgobot list/decide/status и MCP-разрешения на yes/no.
4. Установка isolated plugin только через разрешённый pinned GitHub runner,
   без патча основного Telegram adapter и без второй подписки getUpdates.
5. С включёнными кнопками, но MSP_PRICE_LIVE_ENABLED=0, проверка одного
   тестового сигнала с двумя товарами: два сообщения, четыре кнопки,
   отсутствуют реальные изменения цен.
6. Проверки user_id, chat_id, thread_id, одноразового token, истечения срока,
   изменённого сигнала, однозначного ожидающего решения и ответственного бота.
7. После отдельной авторизации реального исполнения — ограниченный тест клика,
   проверка command_id и командного статуса через orgobot_price_command_status.

queued/processing не доказывают изменение цены. Даже done подтверждает только
завершение обработки Orgobot; фактическую цену нужно прочитать отдельно.
При неизвестном результате нельзя повторять yes/no: state needs_review.

## Границы
Остальные пять сигналов не изменяются.
Нет SKU, нет уникального waiting решения или нет нужных прав — не исполнять.
На опубликованной ветке код не развёрнут на REMOTE: нужны тесты и guarded deploy.


## Подтверждённые контракты QRsite (live read-only 15.10.2026)

- orgobot_price_decisions_list: limit — integer (необязательный), ответ
  structuredContent.results (массив).
- Элемент: id (решение), market_article (артикул), orgobot_id (правило),
  marketplaceid_id, blockid_id, product_name, responsible_telegram, status,
  percent, channel_id, post_id, created_at.
- Разрешены только orgobot_id 48 или 52, статус waiting, точно совпадающий
  market_article и ответственный Hermes Bot; неоднозначность — запрет исполнения.
- orgobot_price_decide: обязательны decision_id (integer), answer (string yes/no).
- orgobot_price_command_status: обязательный command_id (integer).
- Данные таблиц и SKU из живого ответа в GitHub не публиковались.
- Проверка прав на decide и реальный результат queued/done пока НЕ выполнены.
- Подтверждение: private bridge issues #338 и #340, оба read-only.
