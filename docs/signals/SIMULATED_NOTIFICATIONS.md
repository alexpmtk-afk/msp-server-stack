# MSP signal notifications — simulation only

Scope: the **six** partially reviewed signal types `SIG-002`, `SIG-016`,
`SIG-015`, `SIG-021`, `SIG-022`, `SIG-032`.

This integration does not perform any changes to marketplace prices, stock,
campaigns, or product attributes. It produces an explicitly labeled **TEST**
notification in the existing Telegram topic **АП_Лазер / Удалённый сервер**.

## Runtime chain

```text
Hermes Gateway existing Bot API polling (unchanged)
  -> channel_archive persistent SQLite
  -> independent msp-signal-notify.service (Hermes user, read-only archive)
  -> classify one of six signals and prepare simulated report
  -> existing apps/msp_data_sync/run_with_alerts.py:send_telegram
  -> existing Hermes bot outgoing Telegram Bot API
  -> АП_Лазер / Удалённый сервер (topic 758)
```

No second `getUpdates` loop, no second bot, no Telegram gateway restart.
The MSP data sync service and timer remain independent.

## Onboarding and idempotence

On first service launch, the notifier records a high-watermark of the
currently archived channel message IDs and **does not backfill history**.
After that, new posts trigger a simulated report within approximately one
60-second polling interval configured in `systemd/user/msp-signal-notify.service`, provided the services and network are healthy. This is the *scan interval*, not a guaranteed end-to-end delivery deadline.
Message edits can cause a fresh report if the content fingerprint changes.
SQLite `/opt/mcp/data/msp/msp_signal_notifications.sqlite3` tracks confirmed
deliveries separately from the daily MSP sync alert state. Unrecognized
messages produce no notification. A Telegram send failure is retried, not
marked delivered; a timeout occurring after a successful Telegram delivery may
cause a repeated message on retry (Bot API has no sendMessage idempotency key).

## Price advisory

For `SIG-002`, read the market SKU from parentheses, the stock-coverage
days from `_N`, and the incoming delivery date in the same source row.
The decision boundary is `today (Europe/Moscow) + N days`:

* next incoming shipment **on or before** boundary: do not raise price;
* shipment **after** boundary: recommend raising price;
* ambiguous, missing, or expired dates: request verification, do not invent.

The notifier does not select a new price or contact any marketplace API.

## Other five signals

The message explicitly says each result is an *imitation*:
FBS zeroed, stock restored, advertising paused, or product attributes updated.
None of those writes is attempted, and no text may claim verified completion.

## Operation

* Service source: `systemd/user/msp-signal-notify.service`.
* Current versioned `ExecStart` uses `--interval 60` (seconds); do not use the retired five-second setting.
* Entry point: `apps/msp_signal_notify/notify.py`.
* Input: `/home/hermes/.hermes/channel-archive/messages.sqlite3` (read-only).
* Output: Telegram Bot API via the existing `send_telegram` function.
* Token: inherited locally through `EnvironmentFile=/home/hermes/.hermes/.env`.
* Source code never prints, stores, or copies the token.
* Guard: `MSP_SIGNAL_TEST_MODE=1` must be set before execution.
* To stop: `systemctl --user stop msp-signal-notify.service`.
* Testing: `python3 -m unittest discover -s tests -p test_msp_signal_notify.py -v`.

When redeploying or recovering the simulator, check the existing token path, archive schema, unit tests and active `systemctl --user` unit before making any change. Do not infer actual execution or delivery from the polling interval alone. Business-action automation remains disabled.
