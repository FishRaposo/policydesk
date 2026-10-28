# Architecture — offline sandbox and local OpenAI prototype

Status: OpenAI integration implemented; live verification and empirical results not yet performed. The v0.2 local workflow is detailed in OPENAI.md; the synthetic path below remains the offline default. The original seed is preserved in seed/ARCHITECTURE.md.

## Authority and execution

The Python pipeline runs real deterministic policy code, validators, SQLite audit and simulated action authorization. Extraction and draft responses are authored synthetic fixtures. The default synthetic path uses no SDK, transport, key or model inference. Public Pages stays static and in memory. The optional packaged loopback server holds a recruiter-provided key in process memory and runs the separate live.py workflow only after explicit consent. There is no payment/subscription service or production authentication boundary.

Pipeline: exact known ticket → integrity-checked extraction cassette → customer-scoped read-only tool plan (at most three calls) → Python policy decision → synthetic draft → eight validators → at most one repair → validated handoff on continued failure → pending action records → local operator authorization. Missing cassettes raise CassetteMissing; they never select a default response. Invalid extraction/schema/tool arguments hand off without financial proposals. ReplayClient still rejects live/record modes. Live execution is a separate explicit CLI/server path with provider provenance, conservative session reservations and no silent replay fallback.

## Contracts

Pydantic contracts in src/policydesk/models.py forbid unknown fields. Money is an unsigned plain decimal string on JSON boundaries, Decimal in Python, and integer minor units in the browser; inputs round half up to two places. Amounts and order totals are capped at 1000000000 major units. Calendar dates use ISO YYYY-MM-DD; evaluation is frozen at 2026-11-02. Shipments/deliveries cannot be in the future relative to evaluation. Status and dates must agree; estimates may be in the future.

Decision.outcome is approve, deny, needs_human or information. Decision.actions is a list of separate refund/cancel_subscription proposals. A cancellation may include a refund for an unshipped current box, including its shipping fee. Exceeding LM-1 hands off the whole request and creates no pending actions. Every action names its exact order; cancellation also names the subscription. Currency and amount are null for cancellation. Customer-stated amounts are never used to determine refunds.

The trusted CLI customer scope is separate from synthetic tool arguments. lookup_order accepts only order_id; list_recent_orders accepts no arguments and returns only the scoped customer's orders. A foreign lookup produces ownership_denied without the record. Several possible recent orders are ambiguous and cannot authorize an action. CLI customer/actor flags are local simulation inputs, not production authentication.

## Validation and limits

Eight checks: exact expected clause set (legacy name clauses_subset); structured amount/currency; money parsed from the body; next-step consistency; unapproved promise phrases; completed-action phrases; foreign-order identifiers/sentinels; Lingua detection restricted to PT/ES/EN. Missing refund amounts, ambiguous dollar currencies and unqualified decimal amounts are rejected. Phrase checks are incomplete and cannot prove semantic safety. Privileged foreign sentinel records belong only to tests; runtime drafting and ordinary audit never receive foreign records.

Invalid drafts receive one repair with violation codes. Continued failure produces a localized, independently validated handoff template and no pending actions. No final message is transmitted to a customer.

## Persistence and binding

SQLite stores fictional orders, audit results and pending action authorizations. A binding includes the trusted customer, complete order snapshot, the full proposed action set, full policy data and evaluation date. Approval rechecks current data transactionally before either first authorization or an idempotent repeat. Stale records cannot be approved. An approval records actor/time and executed=false; it never executes the action. Restart preserves state.

## Replay and reports

Packaged data under src/policydesk/data is the sole source for policy, orders, cases and cassettes. It works from an installed wheel outside the checkout. Cassette keys hash canonical requests including protocol version, step, policy hash, ticket or ticket hash, decision and repair codes. Envelopes carry schema_version=1, provenance=synthetic, request_hash, response, and a SHA-256 integrity value. They are authored artifacts, not captured API objects. The separate version2 capture/replay protocol does not overwrite or relabel these authored cassettes.

Evaluation is author-known synthetic regression evidence. Exact labeled outcomes/actions/clauses and independent validators guard against universal handoff. Reports include source and reserved-set hashes; API cost, model latency, caching and baseline fields are null. Normal output is under ignored .runtime; committed reports are verification references.

## Public browser

Vanilla TypeScript/Vite loads exported fixed policy data, templates and synthetic dev reference results. It calculates edited decisions using integer minor units. Python-authored parity observations complement independent literal unit-test expectations. An untouched preset shows its generated Python replay result; edited facts clear approvals and reference traces, and use browser policy plus localized templates. Python language detection and model extraction are not claimed for edited runs. All fixtures are fictional and visible in the static bundle; browser ownership controls are a demonstration, not access control.

Desktop puts customer context beside the decision and human approval boundary. A disclosure exposes fictional editable facts. At narrow widths the workspace uses normal document flow. Native labeled controls, a skip link, focus treatment and live result regions support keyboard use. No fonts, analytics, model requests or credentials are fetched.

## API acceptance — unverified

The v0.2 SDK implementation uses strict Responses schemas, scoped read-only tools, stateless continuation, store=false and conservative spend reservations. Its transport/schema/workflow tests use fake credentials and intercepted HTTP only. Genuine API acceptance, authentic captures and empirical results require a separately initiated recruiter run. No account/model access or provider performance is established by mocked contract tests.


## Recruiter-run path

The optional server serves bundled frontend assets on loopback and enforces Host/Origin/CSRF, one active job, idempotence and workspace revisions. The terminal/environment key never enters HTTP contracts. The provider keeps strict API wire schemas separate from domain validation, preserves stateless tool response items, counts tokens before conservative reservations, and records per-attempt provenance/usage/timing/hashes. A single-call baseline receives only the same authorized fixture snapshot and cannot create actions. See [OPENAI.md](OPENAI.md) for exact limits, cost accounting, recordings and honest measurement boundaries.
