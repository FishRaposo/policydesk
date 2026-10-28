import { expect, test } from 'vitest';
import bundle from '../src/generated/bundle.json';
import type { Scenario } from '../src/types';

test('editing invalidates approvals and hides the original replay trace', async () => {
  const path = '../src/state.ts';
  const { Sandbox } = await import(path);
  const sandbox = new Sandbox(bundle.scenarios[0] as Scenario);
  const binding = sandbox.binding();
  sandbox.approve(0, binding);
  expect(sandbox.approved.has(0)).toBe(true);
  sandbox.update({...sandbox.order, shipping_fee: '15.00'}, sandbox.extraction);
  expect(sandbox.approved.size).toBe(0);
  expect(sandbox.edited).toBe(true);
  expect(sandbox.referenceTrace()).toBeNull();
  expect(() => sandbox.approve(0, binding)).toThrow(/changed/);
  sandbox.reset();
  expect(sandbox.edited).toBe(false);
  expect(sandbox.approved.size).toBe(0);
});

test('invalid inputs clear pending authorization and never show a stale verdict', async () => {
  const path = '../src/state.ts';
  const { Sandbox } = await import(path);
  const sandbox = new Sandbox(bundle.scenarios[0] as Scenario);
  sandbox.approve(0, sandbox.binding());
  sandbox.update({...sandbox.order, delivered_at: '2026-11-03'}, sandbox.extraction);
  expect(sandbox.error).toMatch(/date/);
  expect(sandbox.decision).toBeNull();
  expect(sandbox.approved.size).toBe(0);
  expect(() => sandbox.approve(0, sandbox.binding())).toThrow();
});

test('a foreign-order scenario has no authorization path', async () => {
  const path = '../src/state.ts';
  const { Sandbox } = await import(path);
  const sandbox = new Sandbox(bundle.scenarios[3] as Scenario);
  expect(sandbox.decision.outcome).toBe('needs_human');
  expect(() => sandbox.approve(0, sandbox.binding())).toThrow();
});
