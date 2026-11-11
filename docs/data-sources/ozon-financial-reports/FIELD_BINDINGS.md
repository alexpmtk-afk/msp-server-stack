# Карта полей позаказного месячного отчёта Ozon

Статус: все наблюдаемые поля описаны; полный актуальный текст основной справки недоступен.
Часть описаний — сохранённая копия схемы API, а не заново полученная текущая спецификация.

| Путь JSON | Значение | Основание |
|---|---|---|
| `header.contract_date` | Дата договора | [7] |
| `header.contract_number` | Номер договора | [7] |
| `header.currency_sys_name` | Валюта | [7] |
| `header.doc_date` | Дата формирования документа | [7] |
| `header.number` | Номер отчёта | [7] |
| `header.payer_inn` | ИНН плательщика | [7] |
| `header.payer_kpp` | КПП плательщика | [7] |
| `header.payer_name` | Плательщик | [7] |
| `header.receiver_inn` | ИНН получателя | [7] |
| `header.receiver_kpp` | КПП получателя | [7] |
| `header.receiver_name` | Получатель | [7] |
| `header.start_date` | Начало отчётного периода | [7] |
| `header.stop_date` | Конец отчётного периода | [7] |
| `rows[].commission_ratio` | Процент комиссии по категории | [7] |
| `rows[].delivery_commission.amount` | Сумма раздела | [7] |
| `rows[].delivery_commission.bonus` | Баллы за скидки | [6][7] |
| `rows[].delivery_commission.commission` | Историческая комиссия до30.04.2024 | [7] |
| `rows[].delivery_commission.compensation` | Историческая доплата Ozon до30.04.2024 | [7] |
| `rows[].delivery_commission.price_per_instance` | Цена единицы в разделе | [7] |
| `rows[].delivery_commission.quantity` | Количество единиц в разделе | [7] |
| `rows[].delivery_commission.standard_fee` | Базовое вознаграждение Ozon | [6][7] |
| `rows[].delivery_commission.bank_coinvestment` | Зелёные цены, выплаты партнёров | [7] |
| `rows[].delivery_commission.stars` | Звёзды, выплаты партнёров | [7] |
| `rows[].delivery_commission.total` | Итог начисления раздела | [7] |
| `rows[].item.barcode` | Штрихкод | [7] |
| `rows[].item.name` | Название товара | [7] |
| `rows[].item.offer_id` | Артикул продавца | [7] |
| `rows[].item.sku` | SKU Ozon | [7] |
| `rows[].return_commission.amount` | Сумма раздела | [7] |
| `rows[].return_commission.bonus` | Баллы за скидки | [6][7] |
| `rows[].return_commission.commission` | Историческая комиссия до30.04.2024 | [7] |
| `rows[].return_commission.compensation` | Историческая доплата Ozon до30.04.2024 | [7] |
| `rows[].return_commission.price_per_instance` | Цена единицы в разделе | [7] |
| `rows[].return_commission.quantity` | Количество единиц в разделе | [7] |
| `rows[].return_commission.standard_fee` | Базовое вознаграждение Ozon | [6][7] |
| `rows[].return_commission.bank_coinvestment` | Зелёные цены, выплаты партнёров | [7] |
| `rows[].return_commission.stars` | Звёзды, выплаты партнёров | [7] |
| `rows[].return_commission.total` | Итог начисления раздела | [7] |
| `rows[].row_number` | Номер строки внутри месяца | [7] |
| `rows[].seller_price_per_instance` | Цена продавца после скидки | [7] |
| `rows[].order.posting_number` | Номер отправления | [7] |
| `rows[].order.created_date` | Дата заказа, не дата реализации | [7] |
| `rows[].legal_entity_document.number` | Номер документа invoice | [7] |
| `rows[].legal_entity_document.sale_date` | Дата sale_date документа, роль уточнить | [7] |
| `rows[].delivery_commission.pick_up_point_coinvestment` | Скидка АПВЗ, выплаты партнёров | [4] |
| `rows[].return_commission.pick_up_point_coinvestment` | Скидка АПВЗ, выплаты партнёров | [4] |

## Sources

[4] https://dev.ozon.ru/community/1069-Otchet-o-realizatsii
[6] https://dev.ozon.ru/community/778-Otchet-o-realizatsii-tovara-Bally-za-skidki
[7] https://raw.githubusercontent.com/miilv/ozon-seller-api-skill/main/swagger.json
