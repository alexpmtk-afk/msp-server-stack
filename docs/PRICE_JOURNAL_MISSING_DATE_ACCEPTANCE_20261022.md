# Приёмка решения владельца: нет даты в журнале цен — тихий игнор

**Дата:** 22.10.2026  
**Статус:** IMPLEMENTED_AND_VERIFIED_ON_REMOTE.  
**Исходное решение:** [PRICE_JOURNAL_MISSING_DATE_POLICY.md](PRICE_JOURNAL_MISSING_DATE_POLICY.md).  
**Журнал решения:** [DECISION_PRICE_NO_DATE_20261022.md](self-purchases/DECISION_PRICE_NO_DATE_20261022.md).

## Что действительно применено

1. GitHub `msp-server-stack` commit `61487aae0aa55eeaab9dfb22aa49278a1f01f884`: код, тесты, правила для агентов, Hermes Skill source, обе семантики цен и документация.
2. REMOTE `/opt/mcp/projects/msp-server-stack/apps/msp_data_sync/sync.py`: ранний молчаливый пропуск строк с пустой датой **обоих** журналов цен.
3. REMOTE `/opt/mcp/projects/msp-server-stack/apps/msp_data_sync/run_with_alerts.py`: бесшумный сброс старого уведомления о восстановлении журнала цен, без подавления будущих реальных ошибок датированных строк.
4. REMOTE `/home/hermes/.hermes/skills/productivity/msp-self-purchases/references/PRICE_JOURNAL_MISSING_DATE_POLICY.md`: канон политики установлен. Действующие `SKILL.md`, `PROJECT_COMPASS.md`, `DECISIONS_AND_DEVIATIONS.md`, `MSP_SELF_01_SOURCE_MATRIX.md` дополнены явным приоритетным правилом, **без перезаписи обнаруженных локальных расширений**.
5. Исходные `MEETING_TRANSCRIPT_2026-10-21.md` и `INITIAL_VISION_V1_2026-10-21.md` оставлены побайтно неизменными.

## Доказательства

- [Private REMOTE #502](https://github.com/alexpmtk-afk/msp-server-bridge/issues/502) — `RESULT=PASS_CUTOVER`; unit tests PASS, backup SQLite/кода PASS, stage обоих журналов PASS, продакшн `price_journal_current` `status=success`, `rejected=0`; 3 494 строки источника, из них 2 разрешённых пропуска (`skipped_technical`), 3 492 сохранённых бизнес-события, никаких изменений исторических цен. Старое уведомление закрыто в состоянии `silent-price-recovery`, **без отправки сообщения**.
- [Private REMOTE #506](https://github.com/alexpmtk-afk/msp-server-bridge/issues/506) — выявлена дополнительная локальная информация в Hermes references; прямая замена была заблокирована.
- [Private REMOTE #508](https://github.com/alexpmtk-afk/msp-server-bridge/issues/508) — `RESULT=PASS`: append-only локальных справочников Hermes, новый policy reference, сохранность старых дополнений и замороженных первоисточников, успешное `hermes skills list`, без изменений Gateway, SQLite и Telegram.

Безопасность: резервные копии находятся в защищённых каталогах `/opt/mcp/backups/msp/`, пользователь `hermes`; конфиденциальные значения не копировались в открытый репозиторий. Никакого изменения исходных Google Sheets не потребовалось.

## Окончательное рабочее правило

**Пустая/пробельная дата в журнале цен означает, что строка не учитывается.** Не считать это ошибкой, не присылать уведомления, не включать как проблему в отчёты пользователю, не задавать по ней повторных вопросов. Исторические ошибки не удалять (аудит), но не интерпретировать как действующие. Другие подлинные ошибки датированных ценовых событий обрабатываются обычно.

**Примечание об обновлениях:** локальная версия Hermes Skill содержит собственные дополнительные материалы, поэтому маркер `current_public_commit` оставлен на базовой редакции, а новая политика закреплена отдельно через `owner_price_policy_commit`. В будущих обновлениях не переписывать существующие файлы по одному только GitHub SHA; сверять локальные расширения и выполнять аддитивное обновление либо согласованное слияние.
