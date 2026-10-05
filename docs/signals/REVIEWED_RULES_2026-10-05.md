# Reviewed signal rules — 2026-10-05

These are the six signal types that were explicitly discussed with the user and partially reviewed on REMOTE. They are decision/routing instructions only. Automatic execution is disabled until approved API/MCP action tools and result verification are available.

## 1. SIG-002 — «Поднять цену»

Source: `_04_работа с платным хранением / низкий остаток`.

Interpretation:

- the number after the underscore is days of stock coverage, not units;
- dates are promised production inbound dates;
- the article in parentheses is the marketplace SKU, not the internal article.

Decision per item:

1. take the current calendar date;
2. add N coverage days to get the boundary date;
3. compare with the nearest applicable inbound date;
4. inbound on or before the boundary -> do not raise price;
5. inbound after the boundary -> raise price.

The current day is included in N. Example: 05.10 with N=3 covers 05, 06 and 07 October; inbound on 08.10 is acceptable, 09.10 or later requires a price increase.

Execution is not enabled. The future action tool and the actual price-change amount are still undefined.

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
