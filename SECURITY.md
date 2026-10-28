# Security boundaries

This is a fictional-data prototype. OpenAI integration implemented; live verification and empirical results not yet performed. Optional local provider transport requires a recruiter-supplied terminal/environment key and explicit run consent. It has no production authentication, payment execution or customer messaging. CLI customer/actor flags and browser ownership controls are simulation inputs, not security identities. Do not connect real orders, customers, financial services or credentials.

Replay misses and integrity failures stop explicitly. ReplayClient rejects live/record modes; opt-in local live execution is separate and has no silent replay fallback. Keys are excluded from HTTP contracts, browser storage, reports and recordings. The localhost server enforces Host/Origin/CSRF and never exposes a remote bind option. SDK-inferred custom headers are discarded before requests; the boundary-tested SDK version is pinned. The browser contains public synthetic fixtures and must never be treated as a private data store. Approval records authorization only; no financial operation occurs.

Phrase-based validation, money parsing and language detection have bounded coverage. Passing the synthetic checks is not a security guarantee or evidence of model reliability. For code issues, use the repository's private vulnerability reporting feature if available; do not include secrets or personal data in public issues.


No real API call or credential was used in implementation/CI/release verification. Intercepted SDK tests and mock recordings establish contract behavior only. `store=false` is not a Zero Data Retention claim. Spending guards are per-process estimates, not guaranteed provider billing caps; unknown usage remains reserved even after acknowledgement.
