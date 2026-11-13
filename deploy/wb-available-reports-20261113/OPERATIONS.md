# WB report availability upgrade V2

PREPARED_NOT_INSTALLED. Supersedes the unexecuted optional-buyout V1 candidate.
Existing protected release934_py03 is pinned in upgrade-baseline.json.
Use ROOT_WB_AVAILABLE.txt from a Linux root console; one physical Bash line.
The complete archive/manifest/launcher are pinned in package-receipt.json.
No sudo password is available to Hermes; no privilege boundary is bypassed.

The narrow upgrade verifies the full immutable accepted source and exact wiring,
pauses ONLY the WB coordinator, waits for its owned sender to exit, reconciles
only matching owned controls with the accepted helper, and takes both locks.
It replaces ONLY WB coordinator ExecStart, schedule/installation root_release
and policy fields. No timer/sender/runtime/credential reinstallation, Ozon
change, new backfill, budget reset or source deletion. Existing pending cycle,
nonce, attempts, retained HTTP and notices survive. New policy reassesses
settled source-verified waits; IN_FLIGHT/HOLD are not silently bypassed.

Five existing modules change: worker/controller/plan/notify/catalog; policy.py
is added. Catalog snapshot allow_empty=True is INTERNAL verification only:
validate the real view even when one type has never existed; public snapshot
still rejects missing requested data by default. No fabricated financial rows.
Tests exercise all three publication variants with real CSV/catalog publication,
daily-to-weekly replacement, no false Telegram intent, both-absent retries,
listed-but-uncaptured checks, quota/integrity/unknown-outcome retention and
transaction lock ordering. They use synthetic responses with network denied,
not production fetch/send. Verification.json records exact executed suites.

After root execution, independently read policy fields, ExecStart, immutable
manifest, upgrade receipt, both timers, actual cycle result and sender state.
Normal absence of the counterpart must no longer cause waits/notices.
A configured timer alone is not successful production continuation.
Do not rerun V1/base install or clear source/attempt/notification ledgers.

## WB_ANY_REPORT_V2_20261113 — уточнение владельца13.11.2026

Это правило заменяет WB_OPTIONAL_BUYOUT_V1_20261113. За кабинет + период
нормальны все три варианта: только основной reportType1, только выкупы
reportType2 или оба вида. Загрузить и проверить все документы, перечисленные
WB. Если хотя бы один вид полностью получен/подтверждён, а второй НЕ указан
в завершённом списке WB, период сразу завершён успешно: без20минутных
ожиданий, дополнительных проверок отсутствующего вида и уведомлений в чат.
Правило одинаковое для daily, weekly, первичной докачки и переоценки старой
очереди. При отсутствии ОБОИХ видов сохраняются3дневных/10понедельничных
проверок через20минут и сообщение с кабинетом/площадкой/периодом.

Указанный в WB, но недокачанный документ — не отсутствие: сохранить попытку,
проверки и уведомление о конкретно незагруженном опубликованном документе.
HTTP/квоты/неизвестный исход/повреждённый источник не скрывать под успехом.
Наличие отчёта и завершение задания требуют проверки исходных страниц и
публикации в каталоге; одно имя файла не доказательство. Отсутствие второго
вида не означает нулевые продажи/суммы. Не создавать пустые отчёты или строки.

Следующий daily начинается после последнего подтверждённого weekly ЛЮБОГО
вида, а не после минимальной даты пары. Уже полученный daily заменяется в
активной выборке только реальным weekly того же типа/валюты с полным покрытием;
weekly другого вида не удаляет его финансовые строки. Старые источники,
попытки, сообщения и журналы сохраняются. Технические ожидания квоты отличать
от ошибочного ожидания отсутствующего второго отчёта. Ozon не меняется.

Подготовка не равна установке. Проверять installation.json:
report_availability_policy=WB_ANY_REPORT_V2_20261113, фактический манифест,
ExecStart и квитанцию optional-policy-upgrade.json. Новый пакет находится в
/home/hermes/workspace/wb-available-reports-20261113. Старую root-команду V1
не использовать; текущая — ROOT_WB_AVAILABLE.txt. Привилегированная установка
пока не выполнена. Текущее состояние всегда читать заново.
