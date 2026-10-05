# Local Hermes patches

The live REMOTE Hermes checkout is based on upstream commit `234badf4012af380d23c91eae55d045a69c69ffb`.

## 2026-10-05 Codex turn failure surfacing

File: `2026-10-05-codex-turn-failure.patch`.

Purpose:

- mark provider/API errors as failed Hermes turn results;
- prevent Codex commentary/progress messages from becoming a false terminal response;
- add regression coverage for overload/failure after commentary.

The patch is applied on the live server but is not an upstream Hermes commit.

Before updating Hermes, either verify an equivalent upstream fix exists or reapply and retest this patch.
