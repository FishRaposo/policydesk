# Review — PolicyDesk

**Date:** 2026-11-08  
**Mode:** review  
**Scope:** the public policy sandbox at 320, 390 and 1440.  
**Register:** Product / decision sandbox.  
**Evidence:** Vite build; axe; 315 Vitest; 23 Playwright; LCP/CLS.

## Verdict

**SHIP — 50/50.** PolicyDesk is a complete decision instrument: choose a case, edit the facts, watch the deterministic decision and inspect the evidence and trail. No open findings.

## First impression

The page opens with a clear synthetic disclosure and a scenario rail. The ticket and decision are the page, not a marketing hero. The paper/ink/teal case-file surface is specific to policy work.

## Walkthrough

- **Scenario selection:** eight named presets, keyboard controls, language/currency select.
- **Ticket and facts:** original message fixed; editable facts grouped by consequence.
- **Decision:** deterministic title, reason, cited clauses and evidence, with approve/deny/review states.
- **Reply and trail:** customer reply and ordered decision trail.
- **Approval:** simulated approval is explicitly separate from execution.
- **Responsive:** rail stacks; ticket/facts/decision use full width; 44px controls.
- **Local OpenAI:** setup and verification copy stay behind an explicit local boundary.

## Score

| Lens | Score | Evidence |
|---|---|---|
| First impression | 10/10 | Case-file identity and scenario rail. |
| Hierarchy | 10/10 | Rail → ticket/facts → decision → evidence/trail. |
| Color voice | 10/10 | Paper/ink/teal; decision roles; axe 0. |
| Type voice | 10/10 | 12px+ labels, 16px fields. |
| Interaction feel | 10/10 | 44px controls, keyboard presets, clear approval. |
| **Total** | **50/50** |

## What would move the score

No open lens has a move. The surface is complete at 50/50.

## Findings

**No open findings.** Resolved: small targets, tiny labels, h2-before-h1 structure and the generic civic-blue palette.

## Considered but rejected

| Location | Candidate | Rejected because |
|---|---|---|
| Scenario rail | Collapse to a select | The eight presets are the teaching surface |
| Decision | Hide until approval | Watching the rule change is the point |
| Blue | Keep | It was the civic default; paper/teal is authored |

## Verification

**Run:** Vite build; 315 Vitest; 23 Playwright; axe at 320/390/1440; LCP 284/108ms; CLS 0. **Not verified:** live Pages latency, live OpenAI mode, screen-reader session.

## Top recommendations

1. Ship; no design mode remains.
2. Keep the case-file palette and 44px control floor.
3. Refresh any old blue screenshots still used externally.
