# Domain: Grão Norte (fictional)

Prototype status: synthetic replay is the default; an opt-in local OpenAI adapter is implemented but has not been run against the API. No real customer system is connected. The policy source is `src/policydesk/data/policy.yaml`; orders are in `src/policydesk/data/orders.yaml`. Original seed: `seed/DOMAIN.md`.

**Grão Norte is an invented coffee-subscription startup.** It ships beans and gear from São Paulo to customers in Brazil, Mexico and the United States, and answers support in Portuguese, Spanish and English. Every customer, order and clause here is made up. The policy is written to exercise the pipeline, not to describe consumer law anywhere.

## Frozen date

All date logic uses `POLICYDESK_TODAY`, default **2026-11-02**, so evals give the same answer on any day. Fixture dates are written relative to it.

## Policy v1

Stored in `src/policydesk/data/policy.yaml`. Each clause has an ID and text in all three languages. Replies carry the permitted clause IDs; the browser shows localized policy text separately. Deterministic unit tests exercise every rule and boundary. No model or consumer-law interpretation is involved.

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

`src/policydesk/data/orders.yaml` contains fictional order fixtures. `scripts/author_cases.py` documents their original construction; the evaluator and unit tests exercise rule boundaries. The frozen regression dataset is packaged under `src/policydesk/data/cases/`.

| Field | Example |
|---|---|
| `order_id` | `GN-1007` |
| `customer_id` | `C-03` |
| ticket `language` | `pt` / `es` / `en`; trusted separately from the order and replay extraction |
| `currency` | `BRL` / `MXN` / `USD` |
| `items` | `[{name: "Fictional coffee", price: "79.90"}]` |
| `shipping_fee` | `"14.90"` |
| `status` | `delivered` / `in_transit` / `processing` |
| `shipped_at`, `estimated_delivery`, `delivered_at` | ISO dates relative to the frozen date |
| `carrier_status` | `delivered` / `in_transit` / `exception` |
| `subscription_id` | `SUB-02` or null |

Boundary tests include delivery exactly 7/8 days ago (RF-1), 30/31 (RF-2), 9/10 days past estimate (RF-3), below/at/above every currency limit, shipped/unshipped subscription boxes, and carrier delivery disputes. Some boundary orders are constructed by unit tests rather than persisted fixtures.

Customer identifiers are fictional; case languages cover Portuguese (BRL), Spanish (MXN), English (USD), and mixed-language messages with a declared trusted reply language. No real people, addresses or phone numbers are used. API extraction accuracy is unmeasured.
