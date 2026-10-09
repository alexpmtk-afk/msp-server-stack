# Hermes MSP signals Skill — runtime acceptance (2026-10-09)

## Canonical skill and purpose

- Source: `apps/hermes/msp_signals_skill/SKILL.md`.
- Installer: `scripts/deploy/install-msp-signals-skill.sh`.
- REMOTE target: `/home/hermes/.hermes/skills/productivity/msp-signals/`.
- Six reviewed types only: SIG-002, SIG-016, SIG-015, SIG-021, SIG-022, SIG-032.
- Approved SIG-002 rule: known SKU and `_N` remaining stock days but **no production/inbound date** → **recommend raising price** because no production order is planned in the business meaning of that signal.
- Neither the skill nor its model acceptance runs marketplace actions or Telegram sends.

## Evidence

- Installation: private REMOTE bridge issue [#209](https://github.com/alexpmtk-afk/msp-server-bridge/issues/209). Outcome PASS. Git checkout and skill files pinned to `7b077c496fba1af839e5119e9201446861f99638`; 5 static contract and 8 passive notifier unit tests PASS; Hermеs `skills list` discovered `msp-signals`; installed reference bytes match canonical sources; no restart of gateway, notifier or daily sync timer.
- Model acceptance: private bridge issue [#210](https://github.com/alexpmtk-afk/msp-server-bridge/issues/210). Two independent fresh one-shot runs: (A) explicitly preloaded `--skills msp-signals`; (B) natural Hermes skill discovery without `--skills`. Both returned PASS for all four assertions and exit code 0.

| Synthetic scenario at 2026-10-09 | Expected and observed outcome |
| --- | --- |
| SKU 123456789 `_6` without any inbound date | RAISE — PASS in both model modes |
| SKU 234567890 `_3`, inbound 2026-10-12 | NO_RAISE — PASS in both |
| SKU 345678901 `_3`, inbound 2026-10-14 | RAISE — PASS in both |
| SKU 456789012 `_3`, malformed date 35.10.2026 | UNKNOWN — PASS in both |

## Limits

These runs prove that new model sessions using the installed Skill can make the required decisions. They do not prove that a previously open Hermes conversation with an older context has refreshed its cached skill instructions, nor do they prove an end-to-end live manual reprocessing of the user’s actual Telegram signal. In a stale manual session, create a fresh session or explicitly load `msp-signals` before retesting. Do not re-send older notifications unless asked.

Automatic passive notifier continues independently with a 60-second interval. Actual marketplace execution stays disabled.
