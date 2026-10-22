# Daily MSP Plan-Fact report (staging)

**Scope:** read-only source Google Sheet `_ЭКОНОМИКА` -> `План-Факт!A1:B30`;
daily (10:30 Europe/Moscow) SQLite snapshot; rendered PNG 643×533; manual-only Telegram photo.
**No existing MSP tables, Hermes services, signal rules or source spreadsheet are altered.**

## Deployment prerequisites

1. Confirm existing **authorized** read access from the Hermes user to the Google spreadsheet.
   `MSP_REPORT_SOURCE_URL` may point to an already authorized export CSV.
   For a restricted sheet, provide `MSP_REPORT_GOOGLE_CREDENTIALS_FILE` to an
   existing read-only service account granted spreadsheet access and install
   `google-auth`. Never turn private financial sheets public to bypass auth.
2. Ensure `Pillow` is installed in the controlled Python environment.
   Do not alter system packages or existing production virtual environments blindly.
3. Provision `/opt/mcp/secrets/msp-daily-reports.env` with permissions restricted
   to `hermes`; optionally `MSP_REPORT_SHEET_ID`, `MSP_REPORT_GID`,
   `MSP_REPORT_DB=/opt/mcp/data/reports/msp_reports.sqlite3`.
4. Deploy `apps/msp_daily_reports/daily.py` to canonical
   `/opt/mcp/projects/msp-server-stack/`. Run tests, take a single initial
   snapshot, query it back and verify database integrity. Only then install
   and enable `systemd/user/msp-daily-reports.{service,timer}`.
5. **Do not** turn on automated Telegram sending until the user requests the
   one-off test and delivery chat/thread have been independently verified.

## CLI

```bash
python3 apps/msp_daily_reports/daily.py sync
python3 apps/msp_daily_reports/daily.py history --date 2026-10-21
python3 apps/msp_daily_reports/daily.py render --date 2026-10-21 --out /tmp/report.png
python3 apps/msp_daily_reports/daily.py send --date 2026-10-21 --chat-id '<verified>' --thread-id '<verified>' --confirm
python3 -m unittest discover -s tests -p 'test_msp_daily_reports.py' -v
```

`send` requires explicit target and `--confirm`, and rejects repeated delivery.
The bot token is passed via `MSP_REPORT_TELEGRAM_TOKEN` (secrets file, never Git).
No send operation is made by `sync` or the timer.

## Source mapping

- Upper left Ultra: B1(date), B4(actual), B5(plan), B8(forecast profit), B9(margin).
- Upper right 30-day Ultra: B25(realization), B2(month plan), B26(profit);
  margin based on rounded B26/B25.
- Lower left Laser-Master: B12(month plan), B13(target profit),
  B14(transfer actual), B15(plan), B16(plan-fact), B18(profit), B19(margin).
- Lower right 30-day Laser-Master: B12/B13 targets, B28 transfer, B29 profit.
  Two percentages visible in original picture have **no authoritative inputs in
  A1:B30**: show an em dash until formula/cell address is confirmed; NEVER invent.
- Source date is **B1 (=TODAY()-1)**, not scheduled synchronization date.
- Same-date source correction creates an incremented revision, not a silent overwrite.
- Keep original displayed percentages including their indicator color.

## Rollout gates

Staged in Git branch only, not evidence of REMOTE installation.
First enable daily **collection only** after positive live reader access test.
After the user requests a Telegram test, read target chat ID, forum topic ID and
bot identity from the existing MSP signal delivery configuration. Send once,
confirm message ID and journal it. Never put financial data in public CI logs.
