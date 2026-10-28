# Local technical operations

Prerequisites: Python 3.12; uv; Node >=22.12; npm. Dependencies must be installed before network-free runtime checks. No API key is needed or used.

## Install and check

```text
uv sync --locked
uv run ruff check .
uv run pyright
uv run pytest
uv run policydesk demo
uv run policydesk list-cases
uv run policydesk eval --split heldout
uv run policydesk report
uv run policydesk approve ACTION_ID --actor demo-operator
cd web
npm ci
npm test
npm run build
npm run preview
npm run test:browser
```

Open http://127.0.0.1:4177/policydesk/. Browser approval is local, in-memory simulation. Python approval persists authorization in SQLite but performs no external action. The customer and actor CLI arguments are local fixture inputs, not authenticated identities.

The CLI defaults to .runtime/policydesk.sqlite and .runtime/reports; --db and --output-dir override those locations. Replay run accepts only an exact known ticket/customer/language combination; list-cases lists development inputs. Unknown text, changed evaluation dates or mismatched decisions can cause CassetteMissing. This is intentional and does not imply a working general-purpose bot.

The browser is a policy sandbox, not free-text model inference. Choose a preset, inspect its Python reference, then expand Fictional order facts to edit controlled inputs. After edits, the browser uses policy calculations and localized templates. Reset restores the preset and clears approval.

## Reproduction

uv run python scripts/export_web.py regenerates web/src/generated. uv run python scripts/verify_artifacts.py compares fresh exports/reports with committed references. uv run python scripts/offline_check.py denies outbound Python sockets while exercising both splits and approval. npm run test:browser checks browser operation after the browser context goes offline.

The initial fixture authoring scripts are archival construction tools. They refuse to overwrite frozen cases/cassettes. Do not rerun them to hide a regression.

## This Windows workspace

uv is available as python -m uv. Use a project cache if shared-cache ACLs fail: set UV_CACHE_DIR to .runtime/uv-cache. The managed Python 3.12.15 executable is discoverable through py -0p. Native permission tests were required here because sandbox-created pytest temporary directories were inaccessible; use a project-local --basetemp and keep complete failures separate from passing runs. This is a host observation, not a general pytest requirement.

Local browser tests use the installed Edge channel; CI uses Playwright Chromium. A Chromium-family pass does not establish Firefox/WebKit compatibility. Both runtime dependency installation and CI browser installation require network access.

