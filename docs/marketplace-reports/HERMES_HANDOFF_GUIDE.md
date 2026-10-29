# MSP official marketplace financial archive — working handoff

Scope: independent official WB/Ozon report archive for six cabinets, VPS-first; not marketplace writes, purchases or reviews, not existing daily spreadsheet reports.

Canonical project: alexpmtk-afk/msp-server-stack, docs/marketplace-reports/. Read PROJECT.md, DECISIONS.md, latest HANDOFF.md, accepted plan, SOURCE_CONTRACTS/RATE_LIMIT_CONTRACT when present, and the deployment manifest before execution. Refresh remote state; old PR numbers and this note are not permanent version pins.

Planning publication 29.10.2026: [PR 90](https://github.com/alexpmtk-afk/msp-server-stack/pull/90) contains the independent review and [ACTION_PLAN_20261029.md](https://github.com/alexpmtk-afk/msp-server-stack/blob/review/hermes-marketplace-archive-20261028/docs/marketplace-reports/ACTION_PLAN_20261029.md), based on development PR 89. At this publication both were open and unmerged; recheck before use. Source changes being published do not prove VPS installation.

Owner requires confirmed results to update HANDOFF, current PROJECT/DECISIONS and source/status semantics, canonical Skill and applicable installed instructions, with commit/PR/read-back. Failures and NOT VERIFIED also remain visible. Never encode a planned command or inferred API contract as proven workflow. Public GitHub holds safe contracts/tests/results, not real reports, credentials, private seller identifiers or connection secrets.

The current plan routes: actual common queue and official contracts → quota/resume/integrity/security fixes → isolated tests → separately approved installation/pilots → separately approved history → verified backup/restore and read-only interfaces. Default API block, per-method/cabinet approval, no autonomous PR merge, production deployment or download timer remain. Do not set the shared-queue approval variable merely because the owner says to start work on a plan.

Detailed task-specific instructions should move to the canonical project Skill as implemented and tested; do not duplicate speculative operational commands here. Update the installed Skill only with applicable confirmed instructions and record its source/hash independently from application installation. Do not change another Hermes profile.

## Integrity preflight review and recovery

Validate every existing input dependency, not just the currently replaced destination: annual rebuilds consume older monthly files whose identity/schema/size need the same validation. Check the whole affected group under its lock before the first write or backup. Separately inject a failure between CSV and manifest publication: a correct fail-closed integrity check may block retry of its own interrupted output; that needs explicit verified restoration/generation recovery, not bypassing validation. Distinguish the original B5 reproducer passing from acceptance of the whole patch; publish exact counterexamples and source SHA.

Queue discovery: a legacy repository's local Redis contract and stdio example config do not locate its currently running server. Record negative local inventory separately from NOT VERIFIED remote runtime; do not install another Redis, start an application with cleanup hooks, or run repair flags to resolve missing evidence.

For manifest review, test JSON booleans separately from numbers: Python equality accepts True as 1, so schema/count validation requires explicit type rules. Classify a demonstrated inherited type weakness separately from a regression in the reviewed patch, and keep scoped R1/R2 acceptance separate from unfinished B7 recovery or deployment/API approval.

When repository access is expanded, verify Contents, Actions/history/runner access and actual execution/auth separately: repository permissions metadata alone is insufficient. Compare source maps with current DNS/TLS metadata without bypassing TLS, and treat cloud-era/snapshot/preservation workflows as historical until verified; never run mutating preservation/deploy workflows as diagnostics. Keep private transport/key-path details in private bridge records and publish only safe summaries.

For GitHub access mismatches, report this connection separately from a colleague connector. GitHub workflow/run/job history uses Actions read; the repository runner-list endpoint uses Administration read. Old bridge-v2 pointers do not establish the current execution policy: first read main/current policy. Do not infer runner offline, repo deletion or Redis failure from a PAT 403/404.

## P01: безопасная выдержка политики — не исполнение (29.10.2026)

Выдержка коллеги в PRIVATE bridge PR №729, commit c5c460dc240a42053b19cab7e73da42f857cbbcd, проверена как безопасная справка. SOURCE_READ коллеги не равен независимому чтению оригинала Hermes. Blob IDs фиксируют файлы; для связного снимка нужен общий tree/commit SHA. Пул WORK не равен конкретному текущему runner или конечному серверу. До использования маршрута нужен контракт уже существующего read-only workflow/launcher/script/whitelist с точным commit, допустимыми inputs и обезличенным output. Отсутствие такого контракта не разрешает создавать произвольный shell-канал. Чтение безопасной выдержки не подтверждает online/SSH/Redis и не разрешает dispatch. Текущее поручение исключает изменение PAT, запуск Actions и новые каналы. Следующий шаг — через доступное подключение коллеги прочитать существующий контракт, а не выполнять его.
