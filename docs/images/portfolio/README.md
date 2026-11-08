# Portfolio images

Three 1000×750 cards for PolicyDesk, from the sandbox's own captures.

| File | What it shows | Source |
|---|---|---|
| `pd-01-cover.png` | A damaged-item claim: eligible under `RF-2`, USD 40.00 proposed, held at the approval boundary | `docs/media/approval-1440.png` |
| `pd-02-refusal.png` | Someone else's order: `ID-1` denies ownership, no order data revealed, routed to a person | `docs/media/refusal-1440.png` |
| `pd-03-trail.png` | The decision trail naming who did each step, with authorization recorded as simulated | `docs/media/proof-frame-02.png` |

**What the cards claim, and what they do not.** The policy decisions are deterministic code — the
refusal is a rule (`ID-1`), not a prompt instruction — and authorization is separate from execution,
which is why the eligible case still waits for a person. The trail card exists to make that legible:
extract, lookup, decide and draft are labelled by source, so a synthetic fixture cannot be mistaken
for a model verdict.

**Provenance.** The sandbox is a synthetic prototype: fictional data, no model calls, no financial
actions, and its own banner says so. The live OpenAI path is implemented and empirically unverified;
the card repeats that rather than implying it ran. Crops are cut at whitespace, laid out 1000×750 and
downscaled with Lanczos.
