# Published recruiter setup verification — 2026-10-28

**OpenAI integration implemented; live verification and empirical results not yet performed.**

The published Windows install and terminal-to-browser flow passed using fake keys. The separate workflow checks used intercepted SDK transport. No actual OpenAI request, key validation, model listing or token-count request was made, and no real credential was accessed.

## Artifact and environment

The audit followed the public README's wheel command verbatim, from a fresh working directory outside the project checkout:

```bash
uv tool run --python 3.12 --from "policydesk[live] @ https://github.com/FishRaposo/policydesk/releases/download/v0.2.0-prototype.1/policydesk-0.2.0.dev1-py3-none-any.whl" policydesk serve --enable-live
```

- Release: `v0.2.0-prototype.1`, source `cc86638ca98b5fdb8d5e0397b57b85f6b6f32317`, distribution `0.2.0.dev1`.
- Downloaded wheel SHA-256: `faee9312e635d7fbb2d19b0cdf572e7eec22e0c6a9fbd02067bc584616ba81be`, matching GitHub's asset digest.
- Windows x64, uv `0.13.5`, freshly downloaded managed Python `3.12.15`; 32 runtime distributions installed into the isolated uv environment.
- Resolved versions included OpenAI `2.54.0`, FastAPI `0.162.0`, Uvicorn `0.54.0`, Pydantic `2.14.1`, Typer `0.27.3` and Lingua `2.2.0`. These are observed versions, not a promise about future floating dependency resolution.

Fresh `UV_CACHE_DIR`, `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR` and `UV_PYTHON_INSTALL_DIR` paths isolated the installation. The child environment allowed only necessary Windows variables and explicit QA settings; it inherited no API credentials, active virtual environment or developer Python path. Node.js was absent from the application PATH. A separate browser test driver used Node.js; the packaged application did not.

Dependency downloads were allowed. Before any fake key was entered, an external, acceptance-only Python startup guard confirmed it was loaded in the installed process and restricted networking to loopback. Separate synchronous and asynchronous negative controls to a reserved documentation address were blocked before a connection; application processes produced no outbound attempts. The guard was not added to the product or release wheel.

## Observed results

| Flow | Result |
|---|---|
| Exact released launcher, real terminal, hidden fake key | Passed; input did not appear in terminal output |
| Empty input or a key containing internal whitespace | Safely rejected without echoing the input |
| Ctrl+C at the hidden prompt | Aborted safely; no key accepted |
| Fake `OPENAI_API_KEY` | Started without a key prompt |
| Noninteractive input without an environment key | Failed with exit 2 and interactive-terminal guidance; no echo fallback |
| Printed loopback URL and bundled assets | Loaded from installed `site-packages`, without source checkout or Node at runtime |
| Defaults and disclosures | Model, allowances, limits, fictional data and exact unverified-live status visible |
| Startup and browser navigation | No Run clicked, no mutation requests, no provider attempts or external browser requests |
| Keyboard and 390/768/1440 layouts | Passed without horizontal overflow or page errors |
| Credential exclusion | Fake values absent from browser/config, application runtime files, reports and recordings |

The SDK-intercepted browser suite separately passed nine checks against the same installed wheel: ticket completion, authorization-only behavior, valid/invalid edit revocation, compound approvals, downloads, recording provenance, a complete 27-pair mock comparison, cancellation with incomplete pairs retained, and the three layouts. Those model responses, costs and durations are mocked test data, not empirical results.

Regression checks also passed: 226 Python tests, Ruff, Pyright, 315 browser unit checks, 23 static/mock browser checks, byte-identical generated reports/exports and outbound-denied replay over all 60 synthetic cases.

## Corrections and limits

No packaged-runtime defect was found in these checks. Main's README now limits the unsupported-arbitrary-text statement to synthetic replay; local OpenAI mode accepts new fictional ticket text. The setup guide clarifies enabled/disabled key handling and the verified terminal failures. The released wheel, tag, assets and installer URL remain unchanged at the owner's request.

The added cancellation check initially encountered a fully completed mock comparison before its first status response: the instantaneous mock transport never yielded to the server loop. The test fixture now yields briefly like network I/O so an active job can be cancelled. This is a test-only synthetic delay, not a production change or API latency observation.

QA harness errors were retained separately: a Windows child-process wrapper initially failed to wait; the first budget assertion expected `1` instead of the documented `1.00`; noninteractive output needed UTF-8 decoding; and sanitizing the browser driver's environment initially removed Windows browser-discovery variables. None established a product defect; corrected harnesses produced the results above.

This is a Windows clean-install observation and a mocked workflow check, not genuine provider acceptance. Real account/model availability, billing behavior, token usage, costs, model quality, latency and baseline performance remain unverified. Hosted Windows/Linux checks cover installation and intercepted contracts; they do not establish Linux terminal-prompt acceptance or any real OpenAI behavior.
