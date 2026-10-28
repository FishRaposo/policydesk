# Recruiter prototype release procedure

Target: FishRaposo/policydesk, tag `v0.2.0-prototype.1`, Python metadata `0.2.0.dev1`, Pages base `/policydesk/`. The v0.1 release remains immutable historical evidence.

**OpenAI integration implemented; live verification and empirical results not yet performed.**

1. Implement only the owner-approved local BYOK scope. Agents/CI/release verification use fake keys and intercepted SDK HTTP; no actual API request, token-count request, model listing, key validation or paid smoke test is allowed. The recruiter initiates their own future requests.
2. Check Python lint/types/tests and browser unit/build/static/local-server acceptance. Preserve failures and original reserved/cassette bytes. Independently review authority, spending/unknown usage, captured request integrity, local HTTP/key boundaries, durable authorization and paired grading.
3. Rebuild derived synthetic reports/exports explicitly, then compare fresh bytes. These remain author-known synthetic checks, never API measurements. Capture actual public UI and explicitly mock-transport local UI; never label mock screenshots or token timings as genuine model evidence.
4. Build frontend, run scripts/package_web.py, build wheel/sdist, inspect artifact contents and install the wheel into a clean environment. Verify bundled assets without Node at runtime. Run the loopback browser suite using that installed interpreter and mocked SDK HTTP. Require hosted Windows/Linux installed checks and hosted Chromium acceptance.
5. Finalize factual setup instructions and exact status wording under the accepted plan and documented owner authority. Update exact README/case-study hashes and target in config/publication.json. Run scripts/check_release.py and a secret scan. No Claude review is implied by owner authorization.
6. Push the feature branch and require hosted checks. Fast-forward main only after passing checks, then observe the actual main run and Pages deployment. Public Pages must remain static with no local/backend/provider probing and no API-key form.
7. Create the prototype prerelease on the verified main revision with the bundled wheel and source distribution. Verify tag target, prerelease status, download URLs and uploaded SHA-256 digests against local artifacts. Do not replace v0.1 assets or claim a live-provider acceptance run.
8. Record exact hosted/source/package/browser observations and limitations in the build log and hub handoff. Update applicable task/stamp/manifest records while preserving unrelated work and identity/canon ownership.

Never print/store a token or actual API key. Runtime files, reports, captures and test data stay ignored. API account access, real costs/latency, empirical baseline improvements and independent human evaluation remain unverified until a separately initiated genuine run exists.

## Observed v0.2 delivery — 2026-10-28

- Release source: `cc86638ca98b5fdb8d5e0397b57b85f6b6f32317`; [main CI and deployment](https://github.com/FishRaposo/policydesk/actions/runs/40637871352) passed every job.
- [Prototype prerelease](https://github.com/FishRaposo/policydesk/releases/tag/v0.2.0-prototype.1), including public wheel/source download URLs, prerelease flag and exact tag target verified.
- Wheel SHA-256: `faee9312e635d7fbb2d19b0cdf572e7eec22e0c6a9fbd02067bc584616ba81be`.
- Source archive SHA-256: `773552b87a1c2a116416df3014b2329143c3b018a2902d33825f7898e5af6b76`.
- Uploaded GitHub digests and freshly downloaded files match. Pages UI/setup/status/layouts verified; browser observed no backend, localhost or OpenAI request. Verification used only fake-key SDK transport and synthetic data.
