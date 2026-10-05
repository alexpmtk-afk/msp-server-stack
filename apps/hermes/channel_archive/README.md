# Сигналы МП archive

Channel: `-1003375632914`. Uses Hermes' existing Bot API connection; no second poller, user account, or channel posting. Native PTB handler captures channel posts and edited posts before the core gate. A pre-dispatch hook prevents automatic agent replies in this channel.

Storage: active Hermes home `channel-archive/messages.sqlite3`, private permissions, SQLite WAL. Full text/captions, dates, post IDs, links and media metadata; media binaries are not downloaded. No automatic message expiration. Duplicate deliveries are ignored; text revisions retained. Bot API does not expose old channel history or post deletions. Coverage starts when the collector is attached.

Hermes tool: `telegram_channel_archive`.

Supported actions:

- `status`
- `messages`
- `audit`

The audit view enriches channel posts with observed linked-discussion comments. A reply is evidence of a reply only; it does not prove completion or verify the responsible owner.

Discussion group: `-1003493121508`.

## 2026-10-05 fix

Earlier native-handler starts failed with `ModuleNotFoundError: No module named 'channel_archive'` because the factory used an absolute import after the plugin had been loaded under the `hermes_plugins.*` namespace.

The live source now uses the already imported relative `connect` function and a v2 rewire factory. The current collector is attached and the production archive contains real channel and discussion records.

Runtime SQLite data is not committed to Git.
