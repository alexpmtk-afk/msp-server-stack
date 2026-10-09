# AGENTS.md

When handling **MSP Marketplace Telegram signals** or the SIG-002 price-advice case, agents must use the canonical `docs/signals/REVIEWED_RULES_2026-10-05.md` and the Hermes manual Skill `apps/hermes/msp_signals_skill/SKILL.md`; passive background processing uses `apps/msp_signal_notify/notify.py`. In particular, SKU + `_N` days with **no** production/inbound date in the signal means **recommend raising price** (not «cannot determine»). The skill is instructions only; no marketplace write actions are authorized. Do not change Hermes Gateway or the MSP daily timer when deploying this skill.

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
