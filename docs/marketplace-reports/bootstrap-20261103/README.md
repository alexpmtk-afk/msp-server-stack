> **03.11: обнаружен runtime-дефект umask077. Не повторять этот bootstrap для частичной установки. Использовать [проверяемый recovery](../recovery-20261103/README.md). Исходный архив сохранён как evidence.**

# Один bootstrap-пакет WB для администратора VM-817589

## Конкретный результат

**admin access: NOT_FOUND для финансового bootstrap. bootstrap: READY / NOT EXECUTED.**
Разрешения A/B/C действуют, повторное permission не нужно. Linux root-права
процессу не выданы. Root-бroker msp-devexec найден, но не подходит: policy
разрешает фиксированный devexec payload.py/status/restart, а sandbox ограничивает
write destinations payload/state. Использовать его для useradd/secret-read/units
означало бы обход контракта и изменение соседней рабочей системы. Ничего через
него не отправлялось. Data-sync installer работает только как hermes и требует
готовые каталоги; Actions runner User=hermes. sudo требует пароль. Подтверждённого
доступного администраторского канала в текущей сессии нет; провайдерская root-
консоль не считается существующей только на основании этого документа.

## Одно действие владельца

**Передать этот пакет уполномоченному администратору VM-817589, чтобы он в своей
реально доступной Linux-консоли с root/sudo вставил целиком одну строку из
[ONE_LINE_COMMAND.txt](ONE_LINE_COMMAND.txt).** Пароль в чат не передавать.
Это не инструкция вводить sudo-пароль в WinSCP без TTY и не просьба дать агенту
NOPASSWD:ALL. Если у владельца нет admin console, он передаёт то же одно действие
администратору VPS; наличие такой консоли здесь НЕ подтверждено.

Пакет уже находится на этом VPS:
`/home/hermes/workspace/msp-wb-bootstrap-20261103-final.tar`.
Однострочная команда находится рядом:
`/home/hermes/workspace/msp-wb-bootstrap-20261103-final.command.txt`.
При передаче на другой путь нужно пересобрать только доверенный locator/команду,
а не менять hash ожидаемого архива. Не выполнять `bash`/`sudo python` над
непроверенным script из home: команда содержит собственный verifier и проверяет
bundle/manifest/каждый файл ДО записи/запуска payload. Строку брать из точного
опубликованного commit, а не из изменяемого latest branch.

- Bundle SHA256: `eb2ac87f8ad6221c230fdf28b2cb384645e1018f1845b4d7e60f7a943c67767b`.
- Manifest SHA256: `a6d556ae5aa28b8d07893cc9808dbc599d26641b1eeea586c69cc0bd80c2b059`.
- Code PR104: `c1fee070e9efa0c925a78f266fdf03cb12a173cf` (17 modules unchanged).
- Admin PR107: `4df06d795b494cff167b67489f17b2028142aa79` (helpers/unit unchanged).
- 25 payload files + manifest;808960 bytes; tar содержит только regular files0644,
  без symlink/hardlink/absolute/escaping paths. Состав и каждый digest —
  [BUNDLE_MANIFEST.json](BUNDLE_MANIFEST.json). Redis wheel исходно закреплён
  PR104, без скачивания/пакетного менеджера во время установки.

## Что ровно сделает одна команда

1. Требует root, проверяет byte hash исходного архива, manifest digest, member
   types/paths/size/duplicates и все25 hashes в памяти. Сначала вся валидация,
   затем extraction в root0700 staging под `/var/lib`. Не доверяет tar uid/mode
   как доказательству root ownership; каталоги/файлы создаёт сам root.
2. Повторяет payload inventory/hash/root-ownership checks внутри install.py.
   До изменений проверяет неизменность системного Python3.12 executable,
   инструменты, новые target paths, отсутствие user/group, source metadata,
   минимум1GiB свободного места и10000 inodes в target mounts. Это bootstrap
   reserve, НЕ оценка места для неизвестного финансового отчёта/годового backfill.
3. Создаёт system user/group msp-reports, no home, nologin, без sudo/доп.групп;
   immutable release, archive0700, root-only backup и control/pilot directories.
   Никакого recursive chmod/chown родителей /opt/mcp, /etc, Hermes.
4. Ставит17 accepted modules, plan и tools в root-owned release. Создаёт venv
   на существующем закреплённом `/usr/bin/python3`, **без pip/apt/network**.
   Распаковывает verified pure-Python redis wheel в новый venv после проверки
   путей. Только штатные Python links и lib64→lib. Не копирует чужой runtime.
   Проверяет import redis8.1.0 без соединения. При дрейфе системного Python
   hash — STOP до изменений, не скрытое обновление интерпретатора.
5. Этап B: root читает protected master, пишет только wb_laser_master.token в
   exclusive root0600 copy внутри root0700 parent. Другие кабинеты не копируются.
   Сверяет содержимое/режим/owner источника до/после приватно; hashes секретов
   не публикует. При existing/partial/uncertain copy — STOP, не overwrite.
6. Ставит blocked system unit msp-wb-pilot.service: pilot-only LoadCredential,
   IPAddressDeny=any + PrivateNetwork=yes, no timer/enable/restart/approval/gate.
   Применяет daemon-reload без restart существующих служб. Прогоняет syntax
   check и ТОЛЬКО новый transient smoke unit как msp-reports: real fsync/rename/
   readback/hash, release read-only, master/direct-copy denied, runtime credential
   exactly1 cabinet/field, network denial. Downloader не запускает.
7. Проверяет создание private backup/restore-каталогов и сохранение/восстановление
   синтетического marker с hash; удаляет marker после проверки. Initial snapshot
   пустой, как новый archive. **Off-host encrypted backup/retention и backup
   настоящего отчёта этим не доказываются**; до массовой работы нужны отдельный
   выбранный backup target/retention и проверка настоящего coherent snapshot.
8. C: использует ТОЛЬКО специально подготовленный root0600 approved config
   `/etc/msp-marketplace-reports/redis-readonly.env`, если он уже существует.
   Разрешены лишь штатные MARKETPLACE_MCP_REDIS_* assignments, без gate/LD/PYTHON
   переменных. Не угадывает endpoint и не читает произвольные Hermes secrets.
   В отдельный transient READ_ONLY unit WB токен не передаётся. Вызывает принятый
   probe PING/TIME/INFO, без queue/Lua/key writes. Handshake описан в PR107.
   Если файла нет — A/B остаются установленными, C честно
   `NOT_CONFIGURED_APPROVED_BACKEND_REQUIRED`; backend нужно предоставить через
   администратора из утверждённого источника, не через чат. Это не C PASS.
9. Сравнивает соседние system service health snapshots, сохраняет root-only
   complete receipt и public redacted result. Нет финансовых API/отзыва токенов.

## Куда записывает

| Target | Права/состав |
|---|---|
| `/var/lib/msp-wb-bootstrap-package-<bundle hash prefix>` | root0700 verified extraction; files0600 |
| `/var/lib/msp-wb-bootstrap` | root0700 phase receipts, complete.json0600 |
| `/opt/mcp/projects/msp-marketplace-reports-releases` | root0755; CODE SHA release0755 |
| release + `.venv` | root-owned, dirs0755, regular files0644; reviewed runtime links |
| `/opt/mcp/data/msp-marketplace-reports` | msp-reports0700; only executor write-root |
| `/opt/mcp/backups/msp-marketplace-reports` | root0700; initial-empty-snapshot + restore-check |
| `/etc/msp-marketplace-reports-pilot` | root0700; one pilot copy0600 |
| `/etc/msp-marketplace-reports-executor` | root0755; approval ABSENT |
| `/etc/systemd/system/msp-wb-pilot.service` | root0644, blocked, not enabled/started |

**Читает:** verified staging, source cabinets.json (только B), existing system
Python/runtime/CA, user/group metadata, fixed neighbor service metadata, approved
Redis env если есть. **Не пишет:** source credentials, sudoers, devexec policy/
payload, Hermes/Telegram/1C/signal files, Redis keys, queues, other service units.

## Остановка, повтор и откат

Любая ошибка → STOP_OR_UNCERTAIN с phase/error TYPE, без значений секретов.
Phase receipts fsync; нет автоматического стирания сомнительных файлов или
повторного secret copy. Existing targets/user/group → fail before mutation.
Partial install → reconciliation, не повторять useradd/chmod/secret-read вслепую.
Команда extraction при уже существующем staging тоже безопасно отказывает;
повтор не удваивает установку. Root installer на complete.json умеет проверить
readback без повторного B/API; полный inventory включает созданные venv files
и exact runtime links.

Администратор при необходимости вызывает **тот же verified root-owned install.py**
с `--rollback-unit`: проверяет receipt/hashes и inactive state, убирает ТОЛЬКО
точный новый pilot unit, reload manager; сохраняет account/code/data/secret copy
для reconciliation. Частичное состояние без complete receipt эта команда
не уничтожает. Удаление данных, secret copy или account не автоматизируется.
Старый REMOTE не является вариантом rollback. Никакой отзыв токенов не выполняется.

## Проверки и что ещё не доказано

13 новых offline tests PASS на системном Python3.12, включая настоящий scratch
venv + verified Redis import с запрещёнными network connect/DNS; tar traversal,
link/duplicate/hash rejection, exclusive-write/fsync uncertainty, root refusal.
Две независимые сборки дали одинаковые bytes/digest. Bash syntax и одна физическая
строка launcher PASS. Archive+manifest readback PASS. Сам installer от hermes
проверен на ROOT_REQUIRED до каких-либо root writes. Прежние195+8 не повторялись.

**НЕ выполнены:** root installation, systemd runtime/LoadCredential/storage на
реальных targets, Redis backend compatibility, real report backup/restore,
quota/conflict exclusion. Package READY — не INSTALL PASS и не API GO.
После admin run публичный result:
`/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf/bootstrap-result.json`.
По нему Hermes продолжит readback; raw secret/Redis env в чат не нужны.

## Автономность после bootstrap

Рабочий процесс запускается systemd как msp-reports и пишет архив без sudo;
код/venv не требуют переустановки на каждую страницу. Budget/cursor/wait остаются
принятыми механизмами PR104. **Сейчас scheduling/скачивание не включены**, потому
что E запрещён. После отдельного quota/conflict/API допуска понадобится одноразовая
активация согласованного supervisor/расписания; затем штатные запуски под отдельным
user не требуют постоянных root прав агента. Этот пакет не даёт hermes права
произвольно запускать команды от msp-reports и не утверждает, что расписание уже
работает. Ozon modules сохранены, но Ozon autonomous dispatcher здесь не создан:
первая вертикаль WB, Ozon method/runtime acceptance отдельная задача.
