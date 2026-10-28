# Tasks

Work top to bottom. **Only M0 blocks the first release.** Each task lands as its own commit (conventional commits) with its tests. Log coding-agent sessions in [BUILD-LOG.md](BUILD-LOG.md).

## M0 — first release

| Id | Task | Done when |
|---|---|---|
| M0-01 | Scaffold: `uv` project (Python 3.12), `openai`, `pydantic`, `typer`, `pyyaml`, `lingua-language-detector`; dev: `pytest`, `ruff`, `pyright`. MIT `LICENSE`, `.gitignore`, `.env.example`, `CLAUDE.md` containing `@AGENTS.md` | `uv sync --locked && uv run pytest` passes on an empty suite; `ruff check` and `pyright` clean |
| M0-02 | `openai_client.py`: the only `openai` import. Modes `replay`/`record`/`live`, canonical cassette keys, `CassetteMissing`, run budget guard, cost from `usage` × `config/prices.yaml`, `store: false` on every call | Tests: replay with a missing cassette raises; record writes one cassette per distinct request; the budget guard stops before a call that would cross the limit; no test touches the network |
| M0-03 | Policy v1 + fixtures: `policy/v1.yaml` (three-language clause texts), `fixtures/orders.yaml`, `policy/engine.py` | One test per clause and per boundary in DOMAIN.md (day 7/8, 30/31, 9/10 days late, each LM-1 limit ±0.01, shipped/unshipped box, carrier-says-delivered); amounts are `Decimal`, half-up |
| M0-04 | Validators: all eight checks in ARCHITECTURE.md, money parser, `phrases.yaml` | The 25+ bad-draft suite in EVALS.md blocks every case; one clean draft per language passes |
| M0-05 | Extract step: strict tools `lookup_order`, `list_recent_orders`, tool loop (max 3 rounds), `TicketExtraction` via `responses.parse`, JSON-schema snapshot tests | Replay test on 3 dev tickets (one per language, one needing `list_recent_orders`) returns the labelled extraction |
| M0-06 | Draft + repair + hand-off: `DraftReply`, one repair with violations fed back, hand-off note for the person; `PendingAction` with binding hash; `approve` command re-checks the hash | Replay tests: an approve reply says "pending confirmation"; a forced validator failure triggers exactly one repair, then hand-off; approving after the order amount changes is refused |
| M0-07 | Baseline: one-call bot, same model, policy in the prompt | Runs on the same cases through the same report code |
| M0-08 | Eval harness + cases: write and label the 36 held-out cases first and hash them; then the 24 dev cases; `evals/run.py`, `metrics.py`, JSON + Markdown report | `policydesk eval --split heldout --baseline` in replay reproduces the committed report byte-for-byte (timestamps aside) |
| M0-09 | Record and report: one `record` run on dev, prompt work on dev only, then one `record` run on held-out; commit cassettes and report. Fish reads every held-out final reply and records the result in the report | Report committed; README table filled from it |
| M0-10 | CI (GitHub Actions, no secrets): `uv sync --locked`, ruff, pyright, pytest, held-out hash check, replay eval + byte-compare, unsafe-reply gate (policydesk held-out = 0), placeholder gate (`! grep -nE "FILL:|TODO|\[FISH" README.md`; add `docs/CASE_STUDY.md` to it in M1-05. Don't point it at the whole `docs/` folder: this file names the markers), secret scan (gitleaks) | All jobs green on `main` |
| M0-11 | README: replace every `FILL:` from the committed report, each number next to the command that produced it; label source stated honestly | Placeholder gate passes |

### Release gate (all true before the repo goes public)

- [ ] Fresh clone into an empty folder: the README quickstart works verbatim with no key and no network
- [ ] CI green on `main`, including the placeholder gate and the unsafe-reply gate
- [ ] No `.env`, key or customer-like data in history (gitleaks clean)
- [ ] Every README number traces to `reports/heldout-*.md` and its command
- [ ] Limitations section matches what actually happened (review done or not)
- [ ] `git status` clean after `demo`, `eval` and the tests
- [ ] Repo public, MIT detected, About line set (no counts in it), topics: `openai`, `responses-api`, `structured-outputs`, `function-calling`, `llm-evals`, `customer-support`, `portuguese`, `spanish`
- [ ] Tag `v0.1.0`

## M1 — recruiter-ready

| Id | Task | Done when |
|---|---|---|
| M1-01 | FastAPI: `POST /tickets`, `GET /tickets/{id}`, `POST /actions/{id}/approve` | API tests in replay mode |
| M1-02 | Web demo (Vite + TypeScript, no framework): ticket in, decision with cited clause, reply, the approval step; three presets (approve, injection refused, foreign order). Static build reads bundled sample results and says "Interactive sample data" | Works offline after load; keyboard-usable; readable at 390px, 768px, 1440px |
| M1-03 | GitHub Pages deploy of the static demo | Link in the README's first screen |
| M1-04 | Proof GIF (approve + one refusal, silent, looping) and the script that records it | GIF above the fold |
| M1-05 | `docs/CASE_STUDY.md`: problem, approach, measured result, what went wrong, what I'd change, and a sixty-second version to say aloud | Every number from the committed report |

## M2 — when there's slack

| Id | Task |
|---|---|
| M2-01 | Receipt photo for damaged-item claims (vision input in the extract step; the photo informs the claim, never the amount) |
| M2-02 | Batch API for full eval runs (cheaper, slower) with the report noting which mode ran |
| M2-03 | A public write-up in Portuguese and Spanish: "Your support bot shouldn't decide refunds" — the method, the baseline comparison, the code |
| M2-04 | Export eval results as evalforge saved-response JSONL and step traces in agenttrace format (optional; no hard dependency) |
| M2-05 | Re-run the held-out set on the next model release and publish the diff |
