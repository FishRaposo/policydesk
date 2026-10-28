# Public-copy handoff — Claude

Current status (2026-10-28): the owner answered "No, just roll with the current one" when asked for Claude-finalized copy. The existing wording was retained where accurate, unsupported live-model/baseline statements and placeholders were corrected, and README/case-study hashes were recorded as owner_override. No Claude review is claimed. This explicit instruction supersedes the waiting dependency for the current prototype release.

The original Claude handoff below remains as technical evidence and an optional later editorial pass, not a current publication blocker.

## Evidence available

- `reports/dev.json` / `.md` and `reports/heldout.json` / `.md`: authored synthetic regression results, source and reserved-set hashes, per-case outcomes/actions/violations. Commands: `policydesk eval --split dev` and `policydesk eval --split heldout`.
- `docs/media/`: actual browser screenshots, three GIF source frames, silent proof GIF and capture manifest. Reproduce with `npm run proof` in web, then `uv run python scripts/build_gif.py`.
- `docs/ARCHITECTURE.md`, `docs/EVALS.md`, `docs/OPERATIONS.md`, `docs/RESEARCH.md`, `SECURITY.md`: implemented contracts, exact commands, research and limitations.
- Local QA commands: `uv run pytest`, `uv run ruff check .`, `uv run pyright`; in web: `npm test`, `npm run build`, `npm run test:browser`. Build log records observed outcomes and review repairs. Recheck current commands before quoting counts.

## Facts public wording must preserve

This is a synthetic-replay prototype with real deterministic policy/validation/SQLite authorization code. Browser edits run a second deterministic policy implementation and localized templates. No model call, authentic API recording, empirical model comparison, production customer handling, real refund, subscription execution or message delivery occurred. Real API cost, model latency, caching and baseline fields are null. The API adapter is deferred and not verified.

The data, company and policy are fictional. Labels are agent_drafted and author-known; no Fish/manual review has occurred. Reserved-set hash integrity is not blind model evaluation. The phrase/money/language validators have bounded coverage. A detected-unsafe count of zero applies only to these synthetic inputs and checks. Static browser fixtures are public data; ownership controls are not authentication. CLI customer/actor inputs are local simulation labels.

## Finalized outputs needed

1. Replace README presentation with accurate prototype wording, technical quickstart links, proof image/GIF, report-linked results and the actual limitations. Do not preserve the seed's empirical baseline table or API-use claim.
2. Write `docs/CASE_STUDY.md` from actual engineering/evaluation evidence and review repairs.
3. Supply a count-free repository description, profile README entry, site catalog card/project page/thumbnail text, and a canon proposal only if the evidence warrants one. Target source repositories are FishRaposo/FishRaposo and FishRaposo/fishraposo.github.io; the hub snapshots are read-only.
4. Record finalization in `config/publication.json`: status=finalized, reviewed_by=Claude, SHA-256 hashes of the finalized README.md and docs/CASE_STUDY.md, and the approved repository_description. Do not set these fields before reviewing the exact bytes.

Codex can apply finalized copy and complete the already-authorized public repository, Pages, prerelease, profile/site and agenttrace pin replacement. No new authorization is needed for those plan steps once the explicit copy dependency is satisfied. See `docs/RELEASE.md` for the ordered technical steps. The current private staging repository and disabled hosted workflows do not establish those public outcomes.
