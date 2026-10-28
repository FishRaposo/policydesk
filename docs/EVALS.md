# Synthetic regression method

The release prototype answers one bounded question: does deterministic policy/validation/approval code behave as labeled on authored synthetic inputs? It does not evaluate an OpenAI model.

## Data and separation

scripts/author_cases.py authored the reserved split first and froze its bytes with SHA-256 before authoring dev cases. There are 24 dev and 36 reserved cases, 20 tickets per language overall. The reserved labels and response fixtures are author-known; the word reserved does not imply a blind model benchmark. The authoring script refuses to overwrite frozen data. Do not open reserved cases while working on future prompts. Exposed cases used to tune a future model workflow become development data; replace the independent evaluation set and disclose the change.

Every label is agent_drafted until Fish actually reviews it. Human review has not been performed. The data, orders and company are fictional. The corpus is small, uses repeated scenario families, and is easier than real support traffic.

## Checks and reproducibility

Run: uv run policydesk eval --split dev
Run: uv run policydesk eval --split heldout

Reports check the complete labeled outcome, proposed action list and clause IDs. Validators run against the authored label, not just the pipeline's own decision. A system that hands off all tickets fails expected approvals and denials. Repair/handoff cases are development fixtures. Baseline comparison raises an explicit unavailable error. No scripted unsafe baseline is presented as a model result.

Reports include per-case evidence, source SHA-256, reserved-data hash, label-source counts and detected violations. JSON and Markdown output is deterministic and has no run timestamp. Exact reproduction is checked by scripts/verify_artifacts.py. Source hashes bind package Python files and packaged YAML/JSON/JSONL/hash data. Reserved dataset integrity uses original bytes.

A detected-unsafe count of zero means these bounded checks found no unsafe final replies on this synthetic set. It does not establish model robustness, paraphrase coverage, production safety or generalization. There is no human-read calibration claim. Phrase and money parsers have finite coverage; Lingua classification is not guaranteed on arbitrary short or mixed-language messages.

API cost, model latency, cached input share and real baseline measurements remain null. Replay execution time is not model latency. Browser parity is agreement between deterministic implementations, not evidence of model accuracy.

## Future empirical milestone

Authorize a separately capped run, implement and verify the SDK adapter/budget controls, freeze prompts and source, obtain genuinely fresh independently reviewed cases, capture authentic provider responses for both systems, preserve failures, measure actual usage and latency, then commission public-copy/canon review. Do not relabel synthetic cassettes as recordings.
