# Natural-language multipart input (opt-in)

## Intended behavior

An authenticated owner in the existing scoped private Telegram chat can start a persistent multipart collection using an **exact standalone Russian-language sentence** instead of typing a command or choosing the number of parts.

Example conversation:
- User: `Сейчас отправлю задание частями`
- Worker-side collection acknowledges: `Части сохранены: 0/?. Выполнение не запущено.`
- User: first ordinary message
- User: second ordinary message
- User: `Всё, приступай`
- The collector assembles one task and the existing queue handles it in bounded blocks.

No task executes before the explicit end. There is no timer-based implicit dispatch and **no classifier that guesses the intent of arbitrary messages**. This preserves normal Hermes conversation and prevents unfinished instructions from being executed.

## Supported exact phrases

Start:
- `Сейчас отправлю задание частями`
- `Я сейчас отправлю задание несколькими сообщениями`
- `Я отправлю задание несколькими сообщениями`
- `Сейчас опишу задачу в нескольких сообщениях`
- `Начинаю большое задание`

Finish **only when a manual collection is open**:
- `Всё, приступай`
- `Это всё, приступай`
- `На этом всё, приступай`
- `Задание завершено, приступай`

Cancel **only when a manual collection is open**:
- `Отмени сбор задания`

Case and trailing period/exclamation marks are ignored. A phrase must occupy the entire message. If it occurs as a quote or as part of a longer message, it is treated as ordinary task text, not a command.

The previous `/task begin`, `/task end`, `/task status`, `/task cancel` and numbered `TASK 1/N` protocols remain supported without any behavior change.

## Feature gate

Only activate with JSON boolean `"natural_multipart_enabled": true` in the scoped worker configuration used by the native Telegram ingress. Missing or non-boolean values are treated as OFF. Enabling this flag requires the live Gateway's plugin handler to load the new operator source: changing a JSON file on disk alone does not prove that the running handler adopted it. Do not restart the Gateway solely to install this convenience feature.

## Safety / acceptance

- Existing owner/chat/session authentication remains mandatory.
- At most one open collection per scoped conversation.
- Messages are durably persisted with hashes; replay and conflicting-part protection are unchanged.
- The feature does not enable Development Executor writes or change the Telegram outbox cutover.
- The rollout requires confirmed healthy existing Worker and Gateway, no active collection, a backup of modified files/config, unit tests, a reversible plugin hot reload, and a real user-origin acceptance.
- Tests: `tests/operator/test_natural_multipart.py`, `test_multipart.py`, and core operator boundary suite via GitHub Actions.
