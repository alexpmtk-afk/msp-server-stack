# Reviewed signal rules — 2026-10-05

These are the six signal types that were explicitly discussed with the user and partially reviewed on REMOTE. They are decision/routing instructions only. Automatic execution is disabled until approved API/MCP action tools and result verification are available.

## 1. SIG-002 — «Поднять цену»

**Новая утверждённая бизнес-семантика от 27.10.2026 имеет приоритет.** Полное объяснение в `apps/hermes/msp_signals_skill/references/production-orders.md`, раздел 6. Сигнал из `_04_работа с платным хранением / низкий остаток` уже рассчитал `_N` дней обеспеченности **конкретной карточки**; не пересчитывать его из таблиц продаж или остатков. Числовой SKU берётся из скобок; каждый блок `Товар N:` анализировать отдельно, включая переносы строк.

1. Через `product_listing` сопоставить SKU с внутренним артикулом. Проверить оба текущих каталога `production_sewing_order`, `production_metal_order`, фильтр `requester=МП`. Без даты в самом Telegram **не значит** нет заказа.
2. Количество фактической передачи пусто → 0. Заказ минус факт → непереданный остаток (минимум 0). В металле не полагаться на G «Осталось». Просмотреть все строки и комментарии: отмены, переносы, партии, брак у производителя; не двойной подсчёт завершённых.
3. Если до окончания `_N` по московской дате есть подтверждённая положительная производственная партия → **НЕ ПОДНИМАТЬ**. До склада Ozon логистику **не оценивать**: работает схема FBS с собственного склада. Если нет соответствующей будущей партии и данные достоверны → **ПОДНЯТЬ**, кроме подтверждённой распродажи/вывода из ассортимента → **НЕ ПОДНИМАТЬ**. При значимой неопределённости → **УТОЧНИТЬ**.
4. Актуальные остатки FBS при действительно необходимой проверке брать только из 1С через QRsite; обычного решения по сигналу они не требуют. Цена на маркетплейсе никогда не меняется автоматически.

**Примеры, подтверждённые владельцем 27.10.2026:** Ozon 3721851671, `_9`, 38 шт. 29.10 и 76 шт. 23.11 — **НЕ ПОДНИМАТЬ**, ранняя партия внутри 9 дней. WB 366748699 — распродажа и снятие с производства, **НЕ ПОДНИМАТЬ**, хотя простое сравнение с отсутствующей партией дало бы повышение.

## 2. SIG-016 — «Нужно обнулить FBS для распродажи FBO»

Meaning: when FBO stock is intentionally prioritized, disable the FBS stock for the exact item/account/marketplace.

Important:

- do not zero FBO;
- do not propagate the action to another product/account;
- internal articles must be preserved exactly;
- no automatic action until a verified API/MCP method, result check and repeat-safety contract exist.

## 3. SIG-015 — «Карточки с обнулёнными остатками»

Only the first handling variant is currently agreed.

Data-source priority:

1. marketplace cabinet data used by the calculation;
2. 1C data is considered the more reliable stock source by user instruction.

For the agreed variant:

1. identify marketplace, company, SKU and matching internal article;
2. verify whether the related FBS-zero action was actually executed for the matching SIG-016 case;
3. verify the related exception in the Marketplace program;
4. the described corrective action is to remove that exception — not delete the product card or Telegram message.

The exact consequences and safe restoration logic are not yet approved. Automatic execution remains disabled.

## 4. SIG-021 — «Превышен расход по РК»

The signal identifies an advertising campaign whose spend is already considered unacceptable by the upstream rule.

Agreed action: pause exactly that campaign.

Do not:

- delete the campaign;
- invent an additional threshold;
- automatically resume it.

A safe API action tool is still expected. After any future pause request, read back the campaign state; a successful request alone is not proof that the pause actually applied.

## 5. SIG-022 — «Аномально высокий ДРР»

The signal identifies an advertising campaign with an upstream-calculated unacceptable DRR.

Agreed action: pause exactly that campaign.

The numeric value after the underscore is the DRR value in fractional form, not the amount by which a threshold was exceeded.

The same execution restrictions as SIG-021 apply.

## 6. SIG-032 — расхождение размеров/веса с контрольными данными

Recognition is semantic: the message says that items have a mismatch in dimensions or weight versus control data. The leading item count is not the signal type and may change.

Known rule:

- compare marketplace cabinet values with control actual dimensions/weight from the comparison table;
- user described a trigger when deviation is greater than 15% by a side or by weight;
- the exact percentage formula, units and rounding still need to be formalized;
- missing characteristics are a separate observed branch whose handling is not yet agreed.

No correction action is defined. Do not choose replacement values or edit marketplace cards automatically.
