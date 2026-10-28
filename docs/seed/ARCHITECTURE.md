# Architecture

**Rule of the system: the model reads and writes; code decides and checks.** No model output can approve a refund, change an amount, or reach a customer without passing a deterministic check.

## Pipeline

| # | Step | Who | Input → output | Failure behaviour |
|---|---|---|---|---|
| 1 | **Extract** | `gpt-6-luna`, Responses API, Structured Outputs, read-only function tools | ticket text + customer id → `TicketExtraction` | Schema can't be satisfied, or a refusal → hand off |
| 2 | **Look up** | Python, called by the model as tools | `lookup_order`, `list_recent_orders` → order records | Unknown order → tool returns `not_found`; the model can't invent one |
| 3 | **Decide** | Python, `policy.evaluate()` | extraction + order + frozen date → `Decision` | No clause matches → `needs_human` (clause `XX-0`) |
| 4 | **Draft** | `gpt-6.1-terra`, Responses API, Structured Outputs | decision + clause texts + language → `DraftReply` | Schema failure → hand off |
| 5 | **Validate** | Python, `validators.check()` | draft + decision → list of violations | Any violation → one repair attempt with the violations fed back → still failing → hand off |
| 6 | **Act** | Python + a person | approved decision → `PendingAction` bound to (order id, amount, currency, policy version) | Nothing executes until a person approves that exact action |
| 7 | **Audit** | Python, SQLite | every step → `audit_log` rows | — |

The reply for an approved refund says the refund is **pending confirmation**, never that it's done, because step 6 hasn't happened yet.

## Data contracts (Pydantic v2, mirrored as strict JSON schemas)

```python
class TicketExtraction(BaseModel):
    language: Literal["pt", "es", "en"]
    intent: Literal["refund_request", "cancel_subscription", "shipping_status", "other"]
    order_id: str | None  # as resolved via tools; None if not found
    claim: Literal["changed_mind", "damaged", "wrong_item", "not_delivered", "none"]
    customer_stated_amount: float | None  # recorded, never used to decide


class Decision(BaseModel):
    outcome: Literal["approve", "deny", "needs_human"]
    action: Literal["refund", "cancel_subscription", "none"]
    amount: Decimal | None
    currency: Literal["BRL", "MXN", "USD"] | None
    clause_ids: list[str]  # e.g. ["RF-2"], ["LM-1", "RF-2"]
    policy_version: str  # "v1"
    reasons: list[str]  # internal, for the audit log and the human


class DraftReply(BaseModel):
    body: str
    cited_clause_ids: list[str]
    stated_amount: float | None
    stated_currency: Literal["BRL", "MXN", "USD"] | None
    next_step: Literal[
        "refund_pending_confirmation",
        "cancellation_pending_confirmation",
        "denied",
        "handed_off",
        "information",
    ]
```

Strict mode needs every field listed as required and `additionalProperties: false`; nullable fields use a `null` union, not omission. Generate the JSON schemas from the Pydantic models and snapshot-test them so a model change can't silently loosen a schema.

## Validators (step 5)

Each check returns a typed violation, never a bare boolean, so the audit log and the repair prompt say exactly what failed.

| Check | Rule |
|---|---|
| `clauses_subset` | every cited clause is in `decision.clause_ids` |
| `amount_matches` | `stated_amount`/`stated_currency` equal the decision (both null when there's no amount) |
| `body_money_matches` | every money figure parsed from the body equals the decision amount in the decision currency. Parser handles `R$ 89,90`, `R$89.90`, `$1,234.00 MXN`, `MX$1,234`, `US$ 45.00`, `$45` (USD only when the order is USD) |
| `next_step_consistent` | `next_step` matches the outcome and action (approve+refund → `refund_pending_confirmation`, deny → `denied`, needs_human → `handed_off`) |
| `no_unapproved_promise` | when the outcome isn't `approve`, the body contains none of the promise phrases in `validators/phrases.yaml` (per language: "reembolso aprovado", "vamos reembolsar", "reembolso aprobado", "te devolvemos", "refund approved", "we'll refund", …) |
| `no_completed_claim` | the body never says the refund is done ("já foi reembolsado", "ya fue reembolsado", "has been refunded") |
| `no_foreign_order_data` | when `ID-1` fired, the body contains no order id, amount, item name or address from the order |
| `language_matches` | body language equals the ticket language (`lingua-language-detector`, restricted to pt/es/en) |

Phrase lists are incomplete by nature. They catch the common phrasings; the held-out manual review catches the rest and feeds new phrases back.

## OpenAI usage

| Call | Feature | Model | Notes |
|---|---|---|---|
| Extract | `responses.parse` with `text_format=TicketExtraction`, tools `lookup_order`, `list_recent_orders` (`strict: true`) | `gpt-6-luna` | Loop: model → tool calls → `function_call_output` items with matching `call_id` → model, max 3 tool rounds. Pass reasoning items back with tool outputs if the model is a reasoning model |
| Draft | `responses.parse` with `text_format=DraftReply` | `gpt-6.1-terra` | Static instructions + full policy text first, ticket-specific content last, so prompt caching applies |
| Repair | same as Draft, violations appended | `gpt-6.1-terra` | At most one repair per ticket |
| Baseline | one `responses.create` call, policy in the prompt, model decides and writes | `gpt-6.1-terra` | Same model as Draft so the comparison is about structure, not model choice |

- `store: false` on every call: support tickets are customer data and nothing needs server-side state. If a reasoning model needs reasoning items carried across tool rounds statelessly, request the encrypted reasoning content via `include` (check the current function-calling guide).
- Cost per call = `usage` input/cached/output tokens × the price table in `config/prices.yaml`, which carries its source URL and date.
- Model ids live in `config/models.yaml`. No model id in code.

## Modes and recorded responses

| Mode | Network | Key | Behaviour |
|---|---|---|---|
| `replay` (default) | none | none | Every OpenAI call is served from `cassettes/`. A missing cassette raises `CassetteMissing` and stops the run |
| `record` | yes | yes | Calls the API, writes the cassette, enforces the run budget |
| `live` | yes | yes | Calls the API, writes nothing, enforces the run budget |

Cassette key: SHA-256 of the canonical JSON of (model, instructions, input items, tools, text format, temperature-type settings). Canonicalize before hashing (sorted keys, no whitespace) so a re-order doesn't miss. A cassette stores the full response object plus `recorded_at`, SDK version and model id. Any prompt or schema change misses the cassette on purpose; re-record with `record` mode and commit the diff.

**Budget guard:** before each live call, estimate its maximum cost (input tokens counted locally + `max_output_tokens` × output price). If spent + estimate would exceed `POLICYDESK_RUN_BUDGET_USD`, stop the run with a clear message. Record actual cost after each call.

## Storage

SQLite, one file, created by `policydesk init`:

- `orders`, `customers` — loaded from `fixtures/orders.yaml` (see [DOMAIN.md](DOMAIN.md))
- `audit_log` — ticket id, step, model, input hash, output (JSON), tokens, cost, latency, violations, timestamp
- `pending_actions` — id, kind, order id, amount, currency, policy version, binding hash, status (`pending`/`approved`/`rejected`), approved_by, approved_at

Approval re-checks the binding hash, so an action can't be approved after its order or amount changed.

## Interfaces

- **CLI (M0):** `policydesk init | demo | run "<ticket>" --customer C-03 | eval [--split heldout] [--baseline] | approve <action-id> | report`
- **HTTP (M1):** FastAPI `POST /tickets`, `GET /tickets/{id}`, `POST /actions/{id}/approve`; also serves the built web demo
- **Web demo (M1):** Vite + TypeScript, no framework. Static build on GitHub Pages runs from bundled sample results only and is labelled "Interactive sample data"

## Layout

```
policydesk/
  AGENTS.md  CLAUDE.md  README.md  LICENSE  pyproject.toml  uv.lock  .env.example
  config/        models.yaml  prices.yaml  settings.py
  policy/        v1.yaml  engine.py
  fixtures/      orders.yaml
  src/policydesk/
    cli.py  pipeline.py  extract.py  draft.py  baseline.py
    openai_client.py   # the only module that imports openai; handles modes, cassettes, budget
    validators/  __init__.py  money.py  phrases.yaml
    store.py  actions.py
  evals/         cases/dev.jsonl  cases/heldout.jsonl  heldout.sha256  run.py  metrics.py
  cassettes/     *.json
  reports/       heldout-YYYY-MM-DD.json  heldout-YYYY-MM-DD.md
  tests/
  web/           (M1)
  docs/
```

`openai_client.py` being the single import site for `openai` is what makes replay mode trustworthy: everything else is the same code in every mode.
