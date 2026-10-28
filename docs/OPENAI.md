# Recruiter-run OpenAI integration

**OpenAI integration implemented; live verification and empirical results not yet performed.**

No actual API request, API credential access or empirical model run was performed during implementation, CI or release verification. SDK contract tests use fake keys and intercepted HTTP. Those tests are not provider acceptance or model evaluation. Model availability, account billing and API behavior on a recruiter's account remain unverified.

## Install and launch

The release wheel bundles the compiled browser, so Node.js is unnecessary at runtime. Install uv, then use the exact wheel launcher in the README. When live execution is enabled, `policydesk serve --enable-live` reads `OPENAI_API_KEY` or, if it is unset, asks with a non-echoing terminal prompt. Without `--enable-live`, it neither reads a key nor prompts for one. There is no key CLI argument, browser field, saved setting, analytics or hosted proxy.

Run the launcher in an interactive terminal for hidden entry. Empty input and input containing internal whitespace are rejected; Ctrl+C aborts without accepting a key. Noninteractive execution without `OPENAI_API_KEY` fails safely instead of falling back to echoing. The first install may download Python and the language-detector package before the prompt appears; these are dependency downloads, not OpenAI API requests.

The [clean-install verification record](SETUP_VERIFICATION.md) distinguishes real terminal/browser setup checks from intercepted SDK workflow tests. It does not establish live provider behavior or empirical results.

The app serves only http://127.0.0.1:8765/policydesk/. Startup does not validate the key or list models. A ticket or comparison starts only when the recruiter explicitly clicks Run. HTTP and browser controls contain no key; the server process contacts the fixed OpenAI endpoint directly with the chosen key. SDK ambient authorization headers are discarded, and the exact tested SDK version is pinned. OpenAI/httpx/httpcore debug logs are suppressed. Exiting the process releases its key reference; no secure RAM erasure is promised.

From a source checkout:

```bash
uv sync --locked --extra live
npm ci --prefix web
npm run build --prefix web
uv run --extra live python scripts/package_web.py
uv run --extra live policydesk serve --enable-live
```

Without `--enable-live`, the local server does not read a key and refuses live jobs. Public GitHub Pages remains the static synthetic sandbox and never probes a localhost backend.

## CLI

```bash
uv run --extra live policydesk run "My fictional order GN-1007 arrived damaged" --customer C-01 --language en --mode live --confirm-spend --max-cost-usd 0.05
uv run --extra live policydesk benchmark --compare --confirm-spend --max-cost-usd 1.00 --repeats 3
```

Optional flags: `--model gpt-6.1-terra`, `--record`, and `--output-dir`. Live ticket commands also accept `--session-limit-usd`. Replay stays the default and never reads a key. Baseline comparison is a separate explicit command; the original synthetic evaluator is unchanged.

## Execution and data boundaries

The Responses API extracts structured claims and can use only `lookup_order` and `list_recent_orders`. Customer scope is bound by the application, never supplied by a model tool argument. Foreign-order records are never returned to the model. Python decides eligibility and amount; a structured reply passes the eight validators or receives one repair with the original rejected draft and violations. Continued failure produces a local handoff template. There are no model-facing mutation tools.

Limits: three read-only tool calls, six generation requests including repair, 32,000 input tokens and 2,048 output tokens per request, 30 seconds per request and 120 seconds per pipeline workflow. SDK retries are disabled. Responses are non-streaming and use `store=false`; this is not a Zero Data Retention claim. Required response items are carried through stateless tool continuations in memory. Only fictional data belongs in this prototype.

The loopback HTTP service enforces its exact Host, Origin, JSON and CSRF boundary. Only one job can run across tabs. Duplicate submissions reuse a job. Workspace changes and cancellation revoke durable SQLite authorizations, including actions produced by a worker finishing after the edit. Approval records authorization only, with `executed=false`; it never calls a financial, subscription or customer-messaging service. Customer/actor selection is simulated, not production authentication.

## Costs and latency

The dated model/pricing allowlist supports GPT-6 Luna and GPT-6.1 Terra, low reasoning and Standard processing. Before each generation, the app counts input tokens and reserves conservative input/cache-write plus maximum output cost. Defaults are $0.05 per ticket and $1.00 per comparison/session. Recruiters can explicitly change the allowance. These guards apply to the local process and are not an OpenAI project billing cap.

Reports distinguish ordinary input, cached input, cache writes and output tokens. Reasoning tokens are already part of output and are not charged twice. For the configured 30-minute cache lifetime, cache-write prices are total write rates, not extra surcharges. Missing usage or missing/mismatched returned billing metadata stops pricing and retains a reservation. Authentication/quota/transport failures preserve unknown cost rather than inventing zero. Acknowledgement allows another run but does not remove the held reservation. Cancellation stops new requests but does not guarantee provider cancellation or charge reversal.

Estimated USD is computed from reported usage and the versioned rates; discounts, taxes and invoice reconciliation are outside this app. Request IDs, requested/returned model/tier, SDK version, source/prompt/schema hashes and timestamps accompany attempts. Count and generation round trips are separate, workflow duration includes local work, and time-to-first-token is null. No round-trip measurement is described as pure inference time.

## Paired comparison and records

The recruiter suite selects one approval, denial and handoff case in each language from existing unfaulted development cases. Three repeats produce 27 planned pairs. Execution order alternates deterministically. Both systems use the same model, settings, policy, ticket and customer-authorized fixture snapshot. The pipeline uses tools; the one-call baseline receives authorized facts directly. This architectural difference is disclosed in reports. Baseline output is analysis-only and never creates pending actions.

The common primary grader checks completion, gold outcome/actions/clauses and bounded reply validators against expected labels. Extraction correctness is a separate diagnostic, not a prerequisite for the baseline. Reports retain failures, incomplete pairs, unknown costs, sample sizes, median/p95 method, paired differences and language breakdowns. The corpus is author-known, agent-labeled regression data, without human calibration or independent generalization evidence. There is no model judge.

JSON/Markdown reports and SQLite files belong under `.runtime`. Recording is off by default. Opt-in captures use a separate schema, immutable request snapshots, response integrity and model/source/schema hashes; credentials and headers are excluded. Injected transports are explicitly `mock_openai_transport`, never authentic recordings. `policydesk replay-recording PATH` validates integrity without credentials or network and preserves original measurement timestamps. Its replay duration is not a new provider measurement.

## Official references — checked 2026-10-28

- [Authentication](https://developers.openai.com/api/reference/overview#authentication)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) and [function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Responses usage/reference](https://developers.openai.com/api/reference/python/resources/responses/methods/create), [token counting](https://developers.openai.com/api/docs/guides/token-counting), [SDK retries](https://developers.openai.com/api/reference/python#retries)
- [Pricing](https://developers.openai.com/api/docs/pricing) and [cache-write accounting](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Data controls](https://developers.openai.com/api/docs/guides/your-data) and [evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
