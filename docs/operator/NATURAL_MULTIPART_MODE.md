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

Only activate with JSON boolean `"natural_multipart_enabled": true` in the scoped worker configuration used by the native Telegram ingress. Missing or non-boolean values are treated as OFF. Enabling this flag requires the live Gateway's plugin handler to load the new operator source: changing a JSON file on disk alone does not prove that the running handler adopted it. Any Gateway restart requires separate owner approval, a scoped preflight/rollback and independent live callback-attachment readback; do not perform an automatic restart.

## Safety / acceptance

- Existing owner/chat/session authentication remains mandatory.
- At most one open collection per scoped conversation.
- Messages are durably persisted with hashes; replay and conflicting-part protection are unchanged.
- The feature does not enable Development Executor writes or change the Telegram outbox cutover.
- The rollout requires confirmed healthy existing Worker and Gateway, no active collection, a backup of modified files/config, unit tests, a proven plugin reattachment (or separately approved scoped Gateway restart), and a real user-origin acceptance.
- Tests: `tests/operator/test_natural_multipart.py`, `test_multipart.py`, and core operator boundary suite via GitHub Actions.

## Runtime status and operator updates — 12 October 2026

- The natural-language ingress was **activated earlier** on REMOTE by an owner-approved, single-service Hermes Gateway restart (private bridge #254). A separate read-only audit #256 confirmed the running PID, control socket, native callback registration, `natural_multipart_enabled=true` and disabled production DevExec writes.
- The owner's subsequent real Telegram multipart control input **reached the durable queue**, but task `e00d1337-0412-59f0-a8c3-3a4a074af0ea` was blocked in planning by `plan_required`: the model returned the exact `{"plan":{"blocks":[...]}}` envelope. A read-only saved-receipt preflight (#264) validated the original block under the candidate normalization. No production recovery or model repeat has been attempted.
- The latest **draft** PR #32 contains additional, *not-yet-deployed* queue, checkpoint, previous-block context, receipt, metrics and plugin binding fixes. GitHub's enlarged portable operator suite is currently **134/134 PASS**; this does not verify live Telegram delivery or REMOTE service integration.
- **Do not assume plugin hot-reload works.** Earlier hot reload trials (#242/#243) did not replace the already wired Telegram handler, despite passing unit tests. The plugin now reloads its queue dependency chain **when it is actually wired**; it does not automatically rewire a live cached PTB callback.
- For a future deployment, pin exact source digests and a rollback manifest; verify Gateway/Worker idle state and saved receipts, then update each service only through a separately approved, scoped procedure. Confirm the new worker runtime and the Gateway's active handler are actually using the new code. Never equate a copied file, an import, or `adapters_rewired` with runtime acceptance.
- Keep existing collection, task, execution and outbox journals authoritative. Never replace the live journal with a stale backup or replay unknown mutations, model planning, or Telegram deliveries blindly. Leave the blocked owner task untouched until a reviewed saved-receipt recovery procedure is accepted.
