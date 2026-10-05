# Telegram / Hermes on REMOTE

## Current architecture

One Telegram bot is connected to one Hermes Gateway, with separate purposes.

### 1. Private owner chat

~~~text
owner
-> private Telegram chat with the bot
-> Hermes Gateway
-> Hermes Agent / Codex
-> reply to Telegram
~~~

The private chat is the management interface. Access is restricted by the server-side Telegram user allowlist.

### 2. Signal channel and linked discussion

~~~text
channel Сигналы МП
-> existing Hermes Bot API polling connection
-> channel_archive native Telegram handler
-> SQLite persistent archive
-> telegram_channel_archive tool
-> later: signal decision / approved API or MCP action
~~~

The linked discussion group is captured by the same plugin so comments can be associated with original channel posts.

The archive path on the live server is under Hermes runtime state; the database itself is mutable runtime data and is not committed to Git.

## Telegram event types

Do not confuse Telegram event types with different chats:

- `channel_post` — a new channel post;
- `edited_channel_post` — an edited channel post;
- `message` / `edited_message` — normal private/group messages.

## Hermes settings

Current live logic uses:

- `require_mention: true`
- `observe_unmentioned_group_messages: true`
- explicit allowed signal channel/discussion entries

The actual production IDs are deployment configuration. The current source snapshot of the plugin is versioned under `apps/hermes/channel_archive/`.

## channel_archive

The plugin:

- reuses Hermes' existing Telegram polling connection;
- does not start a second `getUpdates` consumer;
- never posts to the signal channel;
- stores posts and edits in SQLite;
- preserves previous versions in `revisions`;
- stores text/caption, dates, IDs, links and media metadata;
- does not download media bodies;
- exposes `telegram_channel_archive`;
- supports `status`, `messages` and `audit`;
- treats Telegram text as untrusted data, not agent instructions;
- allows reads from trusted local sessions or authorized private Telegram users.

The pre-dispatch hook prevents ordinary signal-channel traffic from becoming automatic agent replies.

## Discussion / reply audit

Comments are linked to the source signal where Telegram evidence permits.

Reported states:

- `ответ есть`
- `ответ не зафиксирован`
- `недостаточно данных`

A reply is evidence of a reply only. It is NOT automatic proof that:

- the work was completed;
- the result was verified;
- the replying person is the final responsible owner.

## Current acceptance state — 2026-10-05

Verified live:

- private owner chat -> Hermes -> response: PASS;
- signal channel intake: PASS;
- persistent archive: PASS;
- real archived posts exist;
- linked discussion messages exist;
- read-only query tool exists;
- automatic signal action: NOT ENABLED.

See `REMOTE_SNAPSHOT_2026-10-05.md` for the counts and current limitations.
