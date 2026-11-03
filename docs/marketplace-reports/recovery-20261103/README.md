# Исправление umask077 и продолжение PR108

## Подтверждение причины

Root install PR108 остановился на A_UNIT_SMOKE после B_PILOT_COPY_CREATED.
Владелец сообщил exit2 smoke; независимо повторно проверено: smoke.py и runtime.py
в installed release имеют600 root:root. Текущий transient smoke уже LoadState=not-found:
его default Result=success/ExecMainStatus=0 НЕ доказывают успешную прежнюю проверку.
Root/sudo для текущего Hermes по-прежнему недоступен, установка им не продолжалась.

Точный дефект: os.open(...,0644) под umask077 даёт0600. Новый write_new делает
fchmod(fd,requested_mode) после flush перед fsync. Private default0600 сохраняется.
Подтверждение RED→GREEN: regression реального файла под umask077 сначала дал
384 вместо420 (octal0600 вместо0644), после изменения PASS.

**Исходный bootstrap/архив PR108 повторно НЕ запускать.** Его immutable bytes
оставлены для provenance и сверки уже установленной версии. Fresh installer source
исправлен; recovery ниже отдельно продолжает именно известное частичное состояние.
Принятый финансовый код PR104 не менялся.

## Одна команда под root

[ROOT_ONE_LINE.txt](ROOT_ONE_LINE.txt) содержит одну короткую Bash-строку для уже
использованной владельцем root-консоли VM-817589. Она копирует только recovery.py
в свежий root0700 mktemp stage, делает root0600 snapshot, сверяет literal SHA256
и только затем выполняет Python с -I -B. Не выполнять исходный python script
из writable home напрямую. Пароли/токены в чат не нужны. A/B/C уже разрешены.

Source уже размещён на VPS: `/home/hermes/workspace/msp-wb-repair.py`.
Проверяемый script SHA256:
`d8f29e56e7f8a3b17561ab56582e333ac5c89441f76a3ff0b313a893d0c0ec21`.
Он совпадает с опубликованным repair.py и REPAIR_MANIFEST.json. Сам root-run
ещё не выполнялся; source/tests PASS не равно runtime PASS.

## Проверки до изменения прав

1. Требует root. Проверяет parent ownership/modes исходного root snapshot
   `/var/lib/msp-wb-bootstrap-package-eb2ac87f8ad6221c`.
2. Проверяет literal checksum original install.py до его import. Импортирует
   только проверенные helpers, **не main()**. Сверяет весь original bundle
   manifest/inventory/hashes и exact manifest digest
   `a6d556ae5aa28b8d07893cc9808dbc599d26641b1eeea586c69cc0bd80c2b059`.
3. Проверяет system Python hash, существующий msp-reports no-login, private paths
   metadata, отсутствие API approval и точные четыре original phase receipts.
   Existing complete/неизвестный phase/content → STOP, не автоматическая миграция.
4. Проверяет exact release inventory:17 принятых modules+smoke+Redis probe+plan+
   manifest, rendered blocked unit, все wheel bytes и5 generated venv scripts/cfg,
   exact allowed runtime links. Отдельно независимо сверены5 readable generated
   runtime hashes с живым VPS; остальные600 files проверит root перед chmod.
5. Все regular files открываются O_NOFOLLOW, проверяются checksum, owner/group0,
   single link, mode600/644. Держит FD до завершения всех проверок. Проверяет
   inode/path до первого fchmod. Любой mismatch блокирует ВСЕ mode changes.
   Разрешены только пустые исходные archive/backup, ожидаемые dirs0755/0700;
   неизвестные дополнительные файлы или stage smoke → STOP с reconciliation.

## Что изменяется

Только **20 явно перечисленных nonsecret файлов**:
-17 принятых Python modules (нужны runtime и code digest);
-smoke.py и redis_readonly_probe.py;
-pilot-plan.json (нужен чтению CLI).

Mode600→644 через FD; owner/group остаютсяroot. Уже644 не трогаются.
INSTALL_MANIFEST.json и unit могут оставаться600: их читает root, расширять права
не требуется. Venv уже644/755 и не chmod-ится recovery. Нет recursive chmod/chown.

**Токены, source/pilot directories, archive и existing journals НЕ chmod-ятся.**
Original master/token content root-script не читает и не хеширует: metadata only.
Нет useradd/groupadd/copy_one и повторной B persistent-copy. Для smoke systemd
повторно передаёт уже существующий pilot file через private LoadCredential
непривилегированному процессу, как и предусмотрено B; новый master copy не создаётся.

## Продолжение A/B/C

После repair:
- systemd-analyze verify существующего exact unit, без его переписывания/reload;
- новый transient **msp-wb-recovery-smoke** как msp-reports с PrivateNetwork и
  IPAddressDeny, прежним закрытым archive и существующим LoadCredential;
- real create/write/fsync/rename/hash/readback/storage+network denial+credential
  shape checks через unchanged accepted smoke.py, без downloader;
- synthetic backup/restore marker roundtrip внутри root-only backup. Это только
  проверка сохранения marker и пустого initial archive; offhost/retention/restore
  настоящих отчётов ещё не доказаны;
- C READ_ONLY через неизменённый probe только при существующем approved root0600
  `/etc/msp-marketplace-reports/redis-readonly.env`. Никаких догадок endpoint,
  Redis writes/Lua/queues/API. Если config отсутствует — C NOT_CONFIGURED;
- сверка текущего neighbor health before/after и bytes/modes прежних journals;
- новые recovery receipts в `/var/lib/msp-wb-bootstrap-recovery`, новый
  STATE/complete.json (только если отсутствует), public bootstrap-result.json0644.

Старые phase receipts не меняются/не удаляются. Cursor/budget не создаются и
не сбрасываются. Public result: A PASS, B REUSED_NOT_RECOPIED, C честный результат,
api_enabled=false. Первая успешная попытка readback; повтор завершённого recovery
проверяет installed hashes и не повторяет smoke/B/API. Partial recovery STOP,
не автоматическое повторение после неизвестного исхода.

Соседние Hermes/Telegram/1C/signal services не запускаются/не перезапускаются.
Нет reset-failed чужих units, scheduler, gate, downloader, token revocation.

## Испытания

23 tests PASS =13 затронутых bootstrap+10 новых recovery/mode tests.
Network-denied scratch venv/import также вошёл в13;195 provider tests не повторялись.
Новые проверки: real0644 под077, private0600, all-checks-before-chmod при позднем
bad hash, owner/link/mode rejection, unchanged token/journal modes, idempotent
permission repair, uncertain fchmod failure без rewrite, nonroot refusal,
проверка опубликованного self-contained script/manifest.
Полный вывод: TEST_RESULTS.txt. Root runtime/storage/systemd/Redis после repair
пока NOT VERIFIED; результат будет в bootstrap-result.json после root запуска.
