import bundle from './generated/bundle.json';
import type { Action, Decision, Extraction, Order, Outcome } from './types';

export const policy = bundle.policy;
export const TODAY = policy.today;
const MAX_MINOR = 100_000_000_000;

export function minor(value: string): number {
  if (!/^\d+(?:\.\d+)?$/.test(value) || value.length > 40) throw new Error('Enter a nonnegative decimal amount.');
  const [whole, fraction = ''] = value.split('.');
  if (BigInt(whole) > 1_000_000_000n || (BigInt(whole) === 1_000_000_000n && /[1-9]/.test(fraction))) throw new Error('Amount exceeds the supported range.');
  const rounded = BigInt(whole) * 100n + BigInt((fraction + '00').slice(0, 2)) + (fraction.length > 2 && fraction[2] >= '5' ? 1n : 0n);
  if (rounded > BigInt(MAX_MINOR)) throw new Error('Amount exceeds the supported range.');
  return Number(rounded);
}

export function major(value: number): string {
  if (!Number.isSafeInteger(value) || value < 0 || value > MAX_MINOR) throw new Error('Invalid minor-unit amount.');
  return `${Math.floor(value / 100)}.${String(value % 100).padStart(2, '0')}`;
}

function day(value: string): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Use an ISO calendar date.');
  const time = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 10) !== value) throw new Error('Invalid calendar date.');
  return time / 86400000;
}

export function validateOrder(order: Order, today = TODAY): void {
  if (!['BRL', 'MXN', 'USD'].includes(order.currency)) throw new Error('Unsupported currency.');
  if (!['processing', 'in_transit', 'delivered'].includes(order.status) || !['delivered', 'in_transit', 'exception'].includes(order.carrier_status)) throw new Error('Unsupported order or carrier status.');
  if (!order.items.length || order.items.length > 20 || order.items.some(item => !item.name)) throw new Error('An order needs between one and twenty named items.');
  const total = order.items.reduce((sum, item) => sum + minor(item.price), 0) + minor(order.shipping_fee);
  if (total > MAX_MINOR) throw new Error('Order total exceeds the supported range.');
  const now = day(today);
  day(order.estimated_delivery);
  if (order.status === 'processing' && (order.shipped_at || order.delivered_at)) throw new Error('Processing orders cannot have shipment or delivery dates.');
  if (order.status !== 'processing' && !order.shipped_at) throw new Error('Shipped orders need a shipment date.');
  if ((order.status === 'delivered') !== Boolean(order.delivered_at)) throw new Error('Delivery date must match delivered status.');
  if (order.shipped_at && (day(order.shipped_at) > now || day(order.estimated_delivery) < day(order.shipped_at))) throw new Error('Check the shipment and estimate dates.');
  if (order.delivered_at && (day(order.delivered_at) > now || (order.shipped_at && day(order.delivered_at) < day(order.shipped_at)))) throw new Error('Check the delivery date.');
}

export function evaluate(extraction: Extraction, order: Order | null, customer: string, today = TODAY): Decision {
  const result = (outcome: Outcome, clause_ids: string[], reason: string, actions: Action[] = []): Decision =>
    ({outcome, actions, clause_ids, policy_version: policy.version, reasons: [reason]});
  if (order && order.customer_id !== customer) return result('needs_human', ['ID-1'], 'ownership_denied');
  if (!order) return result('needs_human', ['XX-0'], 'order_unresolved');
  validateOrder(order, today);
  if (extraction.order_id !== order.order_id) return result('needs_human', ['XX-0'], 'order_unresolved');
  if (extraction.intent === 'shipping_status' && extraction.claim === 'none') return result('information', [], `carrier_${order.carrier_status}`);
  const subtotal = order.items.reduce((sum, item) => sum + minor(item.price), 0);
  const total = subtotal + minor(order.shipping_fee);
  const actions: Action[] = [];
  let amount: number | null = null;
  let clause: 'RF-1' | 'RF-2' | 'RF-3' | 'SB-1';
  if (extraction.intent === 'cancel_subscription') {
    if (!order.subscription_id) return result('needs_human', ['XX-0'], 'subscription_unresolved');
    clause = 'SB-1';
    actions.push({kind: 'cancel_subscription', order_id: order.order_id, amount: null, currency: null, subscription_id: order.subscription_id});
    if (!order.shipped_at) amount = total;
  } else if (extraction.intent === 'refund_request') {
    if (['changed_mind', 'damaged', 'wrong_item'].includes(extraction.claim)) {
      clause = extraction.claim === 'changed_mind' ? 'RF-1' : 'RF-2';
      if (!order.delivered_at) return result('needs_human', [clause], 'delivery_unconfirmed');
      if (day(today) - day(order.delivered_at) > policy.windows[clause]) return result('deny', [clause], 'outside_window');
      amount = clause === 'RF-1' ? subtotal : total;
    } else if (extraction.claim === 'not_delivered') {
      clause = 'RF-3';
      if (order.carrier_status === 'delivered' || order.delivered_at) return result('needs_human', [clause], 'carrier_dispute');
      if (day(today) - day(order.estimated_delivery) < policy.windows['RF-3']) return result('deny', [clause], 'not_late_enough');
      amount = total;
    } else return result('needs_human', ['XX-0'], 'unsupported_claim');
  } else return result('needs_human', ['XX-0'], 'unsupported_intent');
  if (amount !== null) {
    if (amount > minor(policy.limits[order.currency])) return result('needs_human', [clause, 'LM-1'], 'refund_over_limit');
    actions.push({kind: 'refund', order_id: order.order_id, amount: major(amount), currency: order.currency, subscription_id: null});
  }
  return result('approve', [clause], 'pending_confirmation', actions);
}
