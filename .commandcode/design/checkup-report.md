# Checkup — PolicyDesk

**Date:** 2026-11-08  
**Mode:** checkup  
**Scope:** the public policy sandbox at 320, 390 and 1440; all eight scenario presets.  
**Register:** Product / decision sandbox.  
**Evidence:** Vite production build; axe WCAG 2A/AA; 315 Vitest; 23 Playwright; target/type/overflow measurement; LCP/CLS.

## Verdict

**APPROVE — 60/60.** One h1, no axe violations, no horizontal overflow, no targets under 44px and no text under 12px at every tested width. The warm paper/ink case-file palette replaces the generic civic blue.

## Score

| # | Vital | Status | Score | Evidence |
|---|---|---|---|---|
| 1 | Intentionality | Healthy | 10/10 | Paper/ink/teal case file; scenario rail, ticket, rule evidence and decision trail. |
| 2 | Readability | Healthy | 10/10 | 12px+ labels, 16px mobile fields, clear ticket/decision hierarchy. |
| 3 | Usability | Healthy | 10/10 | Eight presets, editable facts, deterministic decision, simulated approval. |
| 4 | Responsiveness | Healthy | 10/10 | 320/390/1440; no overflow; two-column scenario rail at 390. |
| 5 | Speed | Healthy | 10/10 | Static build LCP 284ms desktop / 108ms mobile; CLS 0; 3 requests. |
| 6 | Accessibility | Healthy | 10/10 | Axe 0; one h1; 44px controls; skip link; keyboard scenario controls; named fields. |
| | **Total** | | **60/60** | No open findings. |

## Composition and prompt fidelity

The scenario rail is the entry point, the ticket/facts sit beside the decision, and the evidence/reply/trail follow the decision. The page never pretends to be a production decision system: the synthetic badge and "no model calls or real financial actions" disclosure sit above the work. The artifact is the customer case, not a generic dashboard.

## Findings

**No open findings.** Resolved:

| # | Severity | Discipline | Location | Before | After | Why |
|---|---|---|---|---|---|---|
| 1 | HIGH | Accessibility/Interaction | `style.css` | 19–23 targets at 40–43px | 44px buttons, selects, fields, source/brand links and summary | Touch users missed controls |
| 2 | MEDIUM | Typography | `style.css` | 11–13px labels | 12px+ labels; 16px mobile fields | Dense labels were hard to read |
| 3 | MEDIUM | Structure | `main.ts` | `Ticket scenarios` was an h2 before the page h1 | Rail title is a p; one h1 (current case) | Heading order now follows the case |
| 4 | LOW | Color | `style.css` | Generic civic blue | Warm paper/ink/teal case-file palette | The interface now belongs to the policy artifact |

## Considered but rejected

| Location | Candidate | Rejected because |
|---|---|---|
| Scenario rail | Convert to a select | The eight named presets are part of the sandbox's teaching value |
| Decision | Hide it until submission | The point is to watch the decision change with facts |
| Palette | Keep blue | It was the domain default; paper/teal reads as a case file |

## Verification

**Run:** Vite build; 315 Vitest; 23 Playwright; axe at 320/390/1440; target/type/overflow; LCP/CLS. **Observed:** axe 0, one h1, no small targets/text, no overflow. **Not verified:** live Pages latency; OpenAI live mode; screen-reader session.

## Next modes

No in-product work remains. Keep the case-file composition and 44px control floor for new scenarios.
