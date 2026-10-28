# Implementation research — checked 2026-10-27 / local execution 2026-10-28

Question: what does the prototype require now, and what remains necessary for an authentic OpenAI-backed measurement?

## Current delivery

An offline Python workflow and static TypeScript sandbox need no API key, provider budget, backend hosting, database service, domain purchase or subscription. Dependency installation requires network access. SQLite and fictional fixtures are sufficient for local authorization/history. The static browser artifact has no customer-data boundary or live inference.

## Official sources and implications

- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs — Responses supports structured output and Python responses.parse/text_format. A future adapter must handle refusals/incomplete outputs and strict schemas. This prototype does not exercise the API.
- Function calling: https://developers.openai.com/api/docs/guides/function-calling — strict function schemas and matching call IDs; reasoning items need preservation across applicable tool continuations. A future stateless adapter needs explicit continuation tests and store=false. These capabilities remain unverified here.
- Models: https://developers.openai.com/api/docs/models/gpt-6-luna and https://developers.openai.com/api/docs/models/gpt-6.1-terra — seed model IDs exist in official documentation. Availability for this account is unknown; no access test or cost measurement was performed. Recheck availability and prices before an authorized run.
- Deprecations: https://developers.openai.com/api/docs/deprecations — hosted Evals becomes read-only on 2026-10-31 and is scheduled to shut down on 2026-11-30. The local harness has no dependency on that product.
- Vite: https://vite.dev/guide/ — vanilla TypeScript is supported; its documented Node floor is 20.19+ or 22.12+. The project chooses Node >=22.12 and locks installed dependencies. It was built locally with Node24.21.0.
- GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages — artifact upload/deploy jobs, Pages environment and minimal pages/id-token permissions. The project build must use /policydesk/ as its base and deployment must wait for checks and copy readiness.
- GitHub pins: https://docs.github.com/en/account-and-profile/how-tos/profile-customization/pinning-items-to-your-profile — up to six pins. The accepted launch choice replaces agenttrace with PolicyDesk while retaining agenttrace in the catalog.

## Remaining prerequisites for the empirical milestone

User authorization for an explicit spending cap; suitable existing API credit and account access; a separately tested provider adapter with retry-aware conservative budget controls; current model/price configuration; source/prompt freeze; a genuinely fresh independently reviewed evaluation set; authentic recording provenance and immutable raw failures; paired baseline and pipeline measurements; human review of the resulting replies; Claude finalization of public claims. No item is implied complete by synthetic replay results.

## Local delivery constraints

Sandboxed GitHub CLI authentication initially failed because network access was restricted. Native verification on 2026-10-28 confirmed the existing FishRaposo authentication is valid; no credential refresh or disclosure was needed. Connected GitHub tools support reading and Git object writes, but expose no repository-creation or release/settings operation; native gh is the available fallback. The owner explicitly waived the Claude wait for this prototype on 2026-10-28 and authorized using existing wording with factual corrections. config/publication.json records owner_override and exact finalized-copy hashes; this is not Claude review. The hub github/ trees are snapshots, not source repositories.
