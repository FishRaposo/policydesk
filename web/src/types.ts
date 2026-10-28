export type Language = 'pt' | 'es' | 'en';
export type Currency = 'BRL' | 'MXN' | 'USD';
export type Outcome = 'approve' | 'deny' | 'needs_human' | 'information';
export interface Order {
  order_id: string; customer_id: string; currency: Currency;
  items: {name: string; price: string}[]; shipping_fee: string;
  status: 'processing' | 'in_transit' | 'delivered';
  shipped_at: string | null; estimated_delivery: string; delivered_at: string | null;
  carrier_status: 'in_transit' | 'exception' | 'delivered'; subscription_id: string | null;
}
export interface Extraction {
  language: Language; intent: 'refund_request' | 'cancel_subscription' | 'shipping_status' | 'other';
  claim: 'changed_mind' | 'damaged' | 'wrong_item' | 'not_delivered' | 'none';
  order_id: string | null; customer_stated_amount: string | null;
}
export interface Action {
  kind: 'refund' | 'cancel_subscription'; order_id: string; amount: string | null;
  currency: Currency | null; subscription_id: string | null;
}
export interface Decision {
  outcome: Outcome; actions: Action[]; clause_ids: string[]; policy_version: string; reasons: string[];
}
export interface Reply {
  body: string; cited_clause_ids: string[]; stated_amount: string | null;
  stated_currency: Currency | null; next_step: string;
}
export interface Trace { step: string; provenance?: string; status?: string; violations?: {code: string; detail: string}[]; [key: string]: unknown }
export interface Scenario {
  id: string; language: Language; tags: string[];
  ticket: { customer_id: string; language: Language; message: string };
  extraction: Extraction; order: Order;
  reference: {decision: Decision; reply: Reply; trace: Trace[]; violations: unknown[]; repair_attempted: boolean};
}
