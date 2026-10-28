# Prototype release procedure

Target: FishRaposo/policydesk; tag v0.1.0-prototype.1; Pages base /policydesk/. Public presentation requires finalized exact copy bytes, through Claude or the owner's documented 2026-10-28 existing-wording override. No stable release or live-model claim is authorized by prototype QA.

1. Finalize the `docs/COPY_HANDOFF.md` outputs under the documented authority and truthfully record that authority in config/publication.json. Run the strict check (`uv run python scripts/check_release.py`); ready=false blocks publication. Do not hide unresolved README markers or replace them with invented results. An owner override is not Claude approval.
2. Run the Python/browser/clean-clone/offline/reproduction/secret checks against the final source. Regenerate derived reports only explicitly; preserve reserved cases, hashes and prior failed evidence. Capture proof from the actual production build, then encode its GIF.
3. Commit and push finalized files to the private staging main first. Verify the remote SHA and contents before making it public, so the seed draft is never exposed as a finished project.
4. Change the repository to public, set its approved description/topics/website and enable hosted Actions. Configure GitHub Pages to use Actions. Ordinary topics should describe the actual synthetic policy prototype; do not imply measured OpenAI API usage.
5. Dispatch the checks workflow on main. The deployment job requires ready=true, the public repository, successful Python/browser/secrets jobs, and main. Verify the run and the actual Pages URL; skipped deployment is not success. Check that hashed assets load beneath /policydesk/, interactions work, synthetic provenance is visible, and no provider/backend is contacted.
6. Create the v0.1.0-prototype.1 prerelease on the verified main revision with factual notes under the documented copy authority. Observe its tag/target/release URL.
7. Apply finalized profile/site content in their actual source repositories. Include project page, catalog, demo/media links, sitemap and machine-readable listing. Verify deployed links. Refresh hub snapshots only afterward.
8. Replace agenttrace's profile pin with PolicyDesk, preserving the rest of the current pins and retaining agenttrace in the catalog. Verify the final profile state through the current GitHub UI.
9. Append the hub handoff with observed CI/Pages/release/profile/pin evidence and update FTH-036/FTH-037 status and document stamps. Public integration stays pending if any observation or finalized copy is absent.

Private staging starts with Actions disabled; enable it only for the authorized public launch. Actual hosted CI, Pages, release, profile/site and pin observations belong in the build log/handoff. GitHub authentication must be used through normal tools; never print or store a token.
