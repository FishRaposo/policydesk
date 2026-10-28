# PolicyDesk: code decides, synthetic responses explain

## Problem

A support reply can promise a refund the policy does not allow, quote the wrong amount, or reveal another customer's order. PolicyDesk separates policy authority from response generation and makes the approval boundary visible.

## Approach

The prototype uses a fictional coffee-subscription policy in Portuguese, Spanish and English. Python decides eligibility and amount, validates the reply, records an audit, and creates separate refund/cancellation proposals. The trusted customer scope stays outside tool arguments. A failed reply gets one repair, then a validated handoff.

Approval binds the customer, complete order snapshot, proposed actions, policy and evaluation date. An edit invalidates the authorization. Repeated approval rechecks the binding and records no second execution—because no external execution exists.

An editable static browser sandbox demonstrates the same fixed policy with integer minor units. Unedited presets show generated Python reference results. Edited facts produce a fresh browser decision and localized template, with previous approvals and replay traces cleared.

## Measured result and its boundary

Commands: `policydesk eval --split dev` and `policydesk eval --split heldout`.

The [development report](../reports/dev.md) matches all 24 authored labels; the [reserved report](../reports/heldout.md) matches all 36. The same bounded checks flag no unsafe final reply in either synthetic split. The reports include per-case evidence, source hashes and the frozen reserved-set hash.

These are author-known synthetic regression results. No API call, authentic provider recording, independent model evaluation, human label review, real cost/latency measurement or production outcome occurred. No advantage over a naive model baseline is claimed.

## What went wrong

The first UI layout let the order editor push the human approval boundary below the desktop screen. A browser assertion reproduced it; the layout now puts the ticket and decision together and exposes editing through a disclosure.

Independent code review found a malformed tool argument reaching SQLite instead of handing off. Strict argument validation now rejects it before storage access, and regression tests check the persisted handoff. Review also found Python accepting non-string money and timestamp-like dates that the browser rejected. Both runtimes now enforce the documented interchange contract; a separate zero-year calendar edge is covered.

## What would change next

A real OpenAI Responses adapter needs explicit schema/refusal handling, strict tool continuation, authentic recording provenance and retry-aware spend controls. Only an authorized, capped run with fresh reviewed cases could establish a real baseline comparison, usage cost or model latency.

Phrase detection cannot establish semantic safety on arbitrary replies. A larger independent corpus and human review would be needed before making stronger claims. Authentication, customer messaging and financial execution are separate systems, not hidden prototype capabilities.

## Sixty-second version

PolicyDesk is a synthetic support-policy prototype. Deterministic code decides refunds from a fictional policy; response fixtures explain the decision. The CLI runs the real validators, audit and approval binding, while the static sandbox lets a visitor change fictional facts and watch the outcome change. Any edit clears authorization. The tests and reports show the behavior of this control code on authored cases. They do not show OpenAI API usage, model reliability or production results.
