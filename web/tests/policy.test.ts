import { describe, expect, test } from 'vitest';
import parity from '../src/generated/parity.json';
import { evaluate, minor, validateOrder } from '../src/policy';
import type { Extraction, Order } from '../src/types';

describe('policy sandbox wiring', () => {
  test('browser policy independently returns item-only change-of-mind refund', async () => {
    const modulePath = '../src/policy.ts';
    const policy = await import(modulePath);
    const order = {
      order_id: 'GN-TEST', customer_id: 'C-01', currency: 'BRL',
      items: [{ name: 'Fictional coffee', price: '79.90' }], shipping_fee: '14.90',
      status: 'delivered', shipped_at: '2026-09-01', estimated_delivery: '2026-10-01',
      delivered_at: '2026-10-26', carrier_status: 'delivered', subscription_id: null,
    };
    const result = policy.evaluate({ language: 'en', intent: 'refund_request', claim: 'changed_mind',
      order_id: 'GN-TEST', customer_stated_amount: '9999.00' }, order, 'C-01');
    expect(result.outcome).toBe('approve');
    expect(result.actions).toEqual([{ kind: 'refund', order_id: 'GN-TEST', amount: '79.90', currency: 'BRL', subscription_id: null }]);
  });
});

describe('Python/browser differential observations', () => {
  test.each(parity.map((row, index) => ({...row, index})))('observation $index', (row) => {
    expect(evaluate(row.extraction as Extraction, row.order as Order, row.customer_id)).toEqual(row.expected);
  });
});

describe('independent browser boundary oracles', () => {
  const base = parity[0].order as Order;
  const extraction = {...parity[0].extraction, order_id: 'GN-DIFF', intent: 'refund_request', claim: 'not_delivered'} as Extraction;
  test.each([
    ['2026-10-24', 'in_transit', 'deny'], ['2026-10-23', 'in_transit', 'approve'],
    ['2026-10-23', 'delivered', 'needs_human'],
  ])('RF-3 at %s with carrier %s', (estimate, carrier, outcome) => {
    const order = {...base, items: [{name: 'Fictional coffee', price: '10.00'}], status: 'in_transit',
      delivered_at: null, estimated_delivery: estimate, carrier_status: carrier} as Order;
    expect(evaluate(extraction, order, 'C-DIFF').outcome).toBe(outcome);
  });
  test('shipping status proposes no action', () => {
    const result = evaluate({...extraction, intent: 'shipping_status', claim: 'none'}, base, 'C-DIFF');
    expect(result.outcome).toBe('information');
    expect(result.actions).toEqual([]);
  });
  test('decimal arithmetic rounds half up without binary float drift', () => {
    expect(minor('1.005')).toBe(101);
    expect(minor('1.004')).toBe(100);
    expect(minor('999999999.99')).toBe(99999999999);
  });
  test.each(['-1', 'NaN', 'Infinity', '1e2', '1000000001', '1000000000.004', '1,20'])('rejects invalid amount %s', (value) => {
    expect(() => minor(value)).toThrow();
  });
  test.each(['2026-02-30', '2026-11-03', '0000-01-01'])('rejects invalid/future delivery %s', (value) => {
    expect(() => validateOrder({...base, delivered_at: value})).toThrow();
  });
  test('zero calendar year is rejected even when shipment chronology is coherent', () => {
    expect(() => validateOrder({...base, shipped_at:'0000-01-01',estimated_delivery:'0000-01-02',delivered_at:'0000-01-02'})).toThrow();
  });
});
