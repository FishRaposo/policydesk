import bundle from './generated/bundle.json';
import { evaluate, policy, validateOrder } from './policy';
import type { Decision, Extraction, Language, Order, Reply, Scenario, Trace } from './types';

export function template(decision: Decision, language: Language): Reply {
  const text = bundle.templates[language];
  let body = text[decision.outcome];
  if (decision.outcome === 'information') {
    for (const reason of decision.reasons) {
      if (reason.startsWith('carrier_') && reason in text) body += ' ' + text[reason as keyof typeof text];
    }
  }
  const refund = decision.actions.find(a => a.kind === 'refund');
  if (refund) body += ' ' + text.refund.replace('{currency}', refund.currency ?? '').replace('{amount}', refund.amount ?? '');
  if (decision.actions.some(a => a.kind === 'cancel_subscription')) body += ' ' + text.cancel;
  const next_step = decision.outcome === 'approve' ? refund ? 'refund_pending_confirmation' : 'cancellation_pending_confirmation'
    : ({ deny: 'denied', needs_human: 'handed_off', information: 'information' })[decision.outcome];
  return {body, cited_clause_ids: [...decision.clause_ids], stated_amount: refund?.amount ?? null,
    stated_currency: refund?.currency ?? null, next_step};
}

export class Sandbox {
  order: Order;
  extraction: Extraction;
  decision: Decision | null = null;
  error: string | null = null;
  edited = false;
  approved = new Set<number>();
  revision = 0;
  constructor(readonly scenario: Scenario) {
    this.order = structuredClone(scenario.order);
    this.extraction = structuredClone(scenario.extraction);
    this.calculate();
  }
  private calculate(): void {
    try {
      validateOrder(this.order);
      const calculated = evaluate(this.extraction, this.order, this.scenario.ticket.customer_id);
      this.decision = this.edited ? calculated : structuredClone(this.scenario.reference.decision);
      this.error = null;
    } catch (error) {
      this.decision = null;
      this.error = error instanceof Error ? error.message : 'Invalid fictional inputs.';
    }
  }
  update(order: Order, extraction: Extraction): void {
    this.order = structuredClone(order);
    this.extraction = structuredClone(extraction);
    this.edited = true;
    this.revision++;
    this.approved.clear();
    this.calculate();
  }
  reset(): void {
    this.order = structuredClone(this.scenario.order);
    this.extraction = structuredClone(this.scenario.extraction);
    this.edited = false;
    this.revision++;
    this.approved.clear();
    this.calculate();
  }
  binding(): string {
    return JSON.stringify({customer: this.scenario.ticket.customer_id, order: this.order,
      extraction: this.extraction, actions: this.decision?.actions, policy, revision: this.revision});
  }
  approve(index: number, expectedBinding: string): void {
    if (this.error || !this.decision || this.decision.outcome !== 'approve' || !this.decision.actions[index]) throw new Error('No pending action can be authorized.');
    if (expectedBinding !== this.binding()) throw new Error('Inputs changed. Review the current action again.');
    this.approved.add(index);
  }
  referenceTrace(): Trace[] | null {
    return this.edited ? null : structuredClone(this.scenario.reference.trace);
  }
  reply(): Reply | null {
    if (!this.decision) return null;
    return this.edited ? template(this.decision, this.extraction.language) : structuredClone(this.scenario.reference.reply);
  }
}
