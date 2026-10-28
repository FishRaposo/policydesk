# AGENTS.md

Instructions for coding agents (Codex, Claude Code, others) working in this repo.

## Read first

1. [docs/TASKS.md](docs/TASKS.md) — pick the next unfinished task. Only M0 tasks until `v0.1.0` is tagged.
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — contracts, validators, modes. Don't change a contract without updating it there.
3. [docs/DOMAIN.md](docs/DOMAIN.md) and [docs/EVALS.md](docs/EVALS.md) when the task touches policy, fixtures or evaluation.

## Rules

- **The model never decides.** Outcomes and amounts come from `policy/engine.py`. Model-facing tools are read-only. Anything that changes state is created by code and waits for human approval.
- **`openai` is imported in `src/policydesk/openai_client.py` only.** Everything else calls that module.
- **Tests never touch the network.** Default mode is `replay`. Use `record` only when the task says to, with the run budget set, and commit the cassettes it writes.
- **Model ids and prices live in `config/`.** None in code. Re-check the OpenAI models and pricing pages before changing them, and update the source date in `config/prices.yaml`.
- **Don't open `evals/cases/heldout.jsonl` while working on prompts.** Tune on `dev.jsonl`. If a held-out case must change, say so in the commit and in the report.
- **No invented numbers.** Every number in the README or docs comes from a committed report and names its command. `FILL:` markers stay until a measured value replaces them.
- **No secrets.** Never commit `.env`, keys or real personal data. Fixtures are fictional; keep them that way.
- **Fail loudly.** No silent fallback from a failed call or missing cassette to a canned answer.
- One task per commit, conventional commit messages, tests in the same commit. Run `ruff check`, `pyright` and `pytest` before committing.

## Commands

```bash
uv sync --locked
uv run pytest
uv run ruff check . && uv run pyright
uv run policydesk demo
uv run policydesk eval --split heldout --baseline         # replay
POLICYDESK_MODE=record uv run policydesk eval --split dev # costs money; budget-guarded
```

## When you finish a task

Tick it in `docs/TASKS.md` only if its "Done when" was actually run, and add a line to `docs/BUILD-LOG.md` with what you did and anything you got wrong along the way.
