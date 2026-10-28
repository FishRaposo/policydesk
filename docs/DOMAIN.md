# Domain: Grão Norte (fictional)

Prototype status: synthetic replay only; no model or real customer system is connected. The policy source is `src/policydesk/data/policy.yaml`; orders are in `src/policydesk/data/orders.yaml`. Original seed: `seed/DOMAIN.md`.

**Grão Norte is an invented coffee-subscription startup.** It ships beans and gear from São Paulo to customers in Brazil, Mexico and the United States, and answers support in Portuguese, Spanish and English. Every customer, order and clause here is made up. The policy is written to exercise the pipeline, not to describe consumer law anywhere.

## Frozen date

All date logic uses `POLICYDESK_TODAY`, default **2026-11-02**, so evals give the same answer on any day. Fixture dates are written relative to it.

## Policy v1

Stored in `policy/v1.yaml`. Each clause has an id, a short text in all three languages (the draft step cites these verbatim), and a machine rule the engine implements. The YAML text and the engine must agree; a test renders each rule's inputs and checks the outcome named in its text.

| Id | Rule | Outcome |
|---|---|---|
| **ID-1** | The order must belong to the customer writing in. | Otherwise `needs_human`. The reply reveals nothing about the order |
| **RF-1** | Change of mind: refund of the item subtotal (not shipping) if requested within 7 calendar days of delivery. | `approve` refund = item subtotal; after day 7 → `deny` |
| **RF-2** | Damaged or wrong item: full refund including shipping if reported within 30 days of delivery. | `approve` refund = subtotal + shipping; after day 30 → `deny` |
| **RF-3** | Not delivered: full refund including shipping when the order is 10 or more days past its estimated delivery and the carrier hasn't marked it delivered. | `approve`. Carrier says delivered → `needs_human`. Under 10 days late → `deny` with the new estimate |
| **SB-1** | Subscriptions can be cancelled any time; cancellation takes effect at the next cycle. The current cycle's box is refunded only if it hasn't shipped. | `approve` cancel; plus `approve` refund of the current box if unshipped |
| **LM-1** | Any refund above BRL 400, MXN 1,500 or USD 80 goes to a person. | An `approve` refund over the limit becomes `needs_human` (both clause ids kept) |
| **XX-0** | Anything the clauses above don't cover. | `needs_human` |

**Precedence:** ID-1 first (stop if it fires) → the claim clause (RF-1/2/3, SB-1) → LM-1 on any approved refund → XX-0 if nothing matched. Shipping-status questions with no claim get `information` with the carrier status and no clause beyond the order lookup. The current-box cancellation refund includes shipping. If LM-1 applies, the entire request is handed off and no pending cancellation or refund is created.

**Amounts** are `Decimal` in the order's currency, rounded half-up to 2 places. The customer's stated amount is recorded and ignored.

## Fixtures

`fixtures/orders.yaml`: 12 customers, about 30 orders, chosen so every clause and every boundary has at least one order that hits it.

| Field | Example |
|---|---|
| `order_id` | `GN-1007` |
| `customer_id` | `C-03` |
| `customer_language` | `pt` (the language they usually write in; tickets may differ) |
| `currency` | `BRL` / `MXN` / `USD` |
| `items` | `[{sku: "BEAN-CATUAI-500", name: "Catuaí 500 g", price: "79.90"}]` |
| `shipping_fee` | `"14.90"` |
| `status` | `delivered` / `in_transit` / `processing` |
| `shipped_at`, `estimated_delivery`, `delivered_at` | ISO dates relative to the frozen date |
| `carrier_status` | `delivered` / `in_transit` / `exception` |
| `subscription_id` | `SUB-02` or null |

Boundary orders to include: delivered exactly 7 and 8 days ago (RF-1), exactly 30 and 31 (RF-2), exactly 9 and 10 days past estimate (RF-3), refunds just under and just over each currency's LM-1 limit, a subscription box shipped and one not shipped, and one order whose carrier says delivered while the customer says it never arrived.

Customers: four write in Portuguese (BRL), four in Spanish (MXN), four in English (USD), with two "switchers" whose tickets mix languages. Names are invented and obviously fictional; no real people, addresses or phone numbers.
