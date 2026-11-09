# Design system — PolicyDesk

**Register:** Product / decision sandbox. **Direction:** warm paper/ink case file with a teal decision accent.

## Tokens

| Role | Value |
|---|---|
| Ground | `#f4efe5` |
| Surface | `#fffdf8` |
| Ink | `#13251f` |
| Muted | `#4d6156` |
| Accent / teal | `#0f5f57` |
| Success | `#1b6b45` |
| Danger | `#a33a2a` |
| Line | `#d6d0c2` |
| Control | `#7d7566` |
| Focus | `#0f5f57` |

**Type:** Inter utility sans, 16px body, 12px+ labels, 16px mobile fields. **Targets:** 44px buttons, selects, fields, source/brand links and summaries. **Layout:** 1600px workspace, 248px scenario rail, ticket/facts/decision, evidence/reply/trail.

## Composition

- Header: brand, synthetic context, source.
- Disclosure: synthetic prototype boundary.
- Workspace: scenario rail; ticket and editable facts; decision with clauses; reply; decision trail.
- Local OpenAI panel is opt-in and explicitly local.

## States and access

One h1; 44px controls; named fields; skip link; keyboard scenario list; decision color paired with text; reduced motion; mobile 16px fields; axe 0 at 320/390/1440.

## Module record

| Module | Result |
|---|---|
| setup | Brief with user, job, artifact, evidence, drift. |
| checkup | 60/60. |
| smell | 10/10. |
| review | 50/50. |
| deslop | Removed generic civic blue and small targets. |
| typeset | 12px+ labels; 16px mobile fields. |
| recolor | Paper/ink/teal case-file palette. |
| motion | Reduced-motion rule; no decorative motion. |
| interaction | 44px presets, fields, summary links; keyboard. |
| a11y | Axe 0; one h1; skip; named controls. |
| relayout | Rail → ticket/facts → decision → evidence. |
| responsive | 320/390/1440; no overflow. |
| tokenize | CSS variables and shared control classes. |
| finish | Build, 315 Vitest, 23 Playwright, LCP/CLS. |
| refine | Case-file decision instrument. |
| voice | Fictional, deterministic, explicit approval boundary. |
| surface | Scenario, facts, decision, reply, trail, local setup. |
| redesign | Palette and target/heading pass. |

## Evidence map

`web/src/style.css`, `web/src/main.ts`, `web/e2e/*`, `.commandcode/design/*`.
