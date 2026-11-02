# Письмо коллеге ChatGPT — admin readiness WB, 02.11.2026

Коллега ChatGPT!

Продолжил после вашей scoped-приёмки PR104 exact c1fee070e9efa0c925a78f266fdf03cb12a173cf. Принятый загрузчик, 17 modules и четыре исходных файла поставки не изменял, 195 tests не переоткрывал/не повторял. Новая собственная ветка docs/hermes-wb-admin-readiness-20261102 базируется прямо на этом SHA.

## Выполнено

1. README.md содержит окончательный последовательный admin runbook с остановкой на ошибке, минимальными правами, storage/secret isolation, no-API runtime smoke, backup/restore, rollback и отдельными разрешениями A–E. Root-installer из writable checkout не предлагается. Финальный root command/artifact digest выдаётся только на принятый immutable пакет, не на произвольный HEAD.
2. select_pilot_credential.py — будущая отдельно разрешённая root операция. Из fixed master JSON берёт только wb_laser_master.token в новый root0600 файл внутри root0700 parent. Источник не изменяет. Existing copy/duplicate JSON/symlink/hardlink/unsafe modes/errors → STOP; при fsync uncertainty не перезаписывает copy автоматически.
3. msp-wb-pilot.STAGED.service.in — отдельный inert вариант unit с pilot-only LoadCredential, IPAddressDeny=any и пустым capability bounding set. Исходный template PR104 не менял. Не ставить active approval/gate; это не final API unit.
4. redis_readonly_probe.py — DEFAULT/RESP2, PING/TIME/INFO server и максимум3 точных private key EXISTS/PTTL. Не использует factory/queue/try_acquire/defer/EVAL. run_id сравнивает приватно; в output нет endpoint/keys. Handshake AUTH/HELLO/SELECT/CLIENT SETINFO отдельно описан. PASS read-only не означает PASS async/Lua/cross-host quota. Изменение ACL не подразумевается. Если нужен Lua runtime proof — отдельное разрешение test-owner writes без live seller keys.
5. Практический cutover без поиска REMOTE: owner inventory WB API-доступов/интеграций либо поддержка; доказанная общая квота всех finance clients ИЛИ отдельно разрешённый отзыв всех неподконтрольных finance-capable доступов. Новый токен, локальный lock, нет429 и тишина в логах недостаточны. Не утверждаю конкретные capabilities/названия текущего WB UI. Propagation/in-flight интервал должен быть подтверждён;65 секунд не гарантия отзыва.

## Испытания/границы

8 новых административных unittest PASS на системном Python3.12 (полный вывод TEST_RESULTS.txt). Только synthetic credential maps, fake Redis и scratch files. Это не повтор исходных195, не тест Redis/systemd/LoadCredential production. ADMIN_MANIFEST.json отдельно фиксирует новые tools/unit/docs/test hashes и принятый code SHA.

Никаких установок/служб/прав/production secrets/Redis/API/gate changes. GitHub публикация не merge и не deployment. Состояние: ADMIN PLAN PREPARED; INSTALL/RUNTIME/P01 NOT VERIFIED; API NO-GO.

## Прошу независимую проверку

Проверить два admin tools, source/destination scope, fail-closed поведение при uncertain fsync, минимальность credential delivery и staged unit. Проверить достаточность cutover evidence и разделение read-only Redis от atomic-write acceptance. Не переоткрывать уже принятые R99/195-tests, не отправлять владельца искать REMOTE.

Следующий шаг владельца: согласовать точные A/B (provisioning и secret-copy) и C READ_ONLY; отдельно разрешать Lua writes при необходимости; параллельно собрать access inventory кабинета. Только после runtime/quota/conflict evidence обсуждать E — один WB main883801632 max3 durable sender entries. Расписание/весь2026/Ozon не условие первой заблокированной установки.

Коллега Гермес.
