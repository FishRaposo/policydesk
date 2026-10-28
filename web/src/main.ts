import './style.css';
import {mountLocalRuntime} from './local';
import rawBundle from './generated/bundle.json';
import { major, minor, policy, TODAY } from './policy';
import { Sandbox } from './state';
import type { Extraction, Language, Order, Scenario } from './types';

const scenarios = rawBundle.scenarios as Scenario[];
let language: Language = 'pt';
let sandbox = new Sandbox(scenarios[0]);
const app = document.querySelector<HTMLDivElement>('#app')!;
const names = ['Damaged item', 'Outside return window', 'Prompt injection', 'Another customer’s order', 'One repair succeeds', 'Repair fails → handoff', 'Cancel an unshipped box', 'Cancel after shipping'];
const labels: Record<string, string> = {approve: 'Eligible · approval required', deny: 'Denied by policy', needs_human: 'Human review required', information: 'Information only'};

function node<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text?: string): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function select(labelText: string, name: string, options: [string, string][], value: string): HTMLDivElement {
  const field = node('div', 'field');
  const label = node('label', '', labelText); label.htmlFor = `field-${name}`;
  const control = node('select'); control.name = name; control.id = label.htmlFor;
  for (const [key, text] of options) {
    const option = node('option', '', text); option.value = key; option.selected = key === value; control.append(option);
  }
  field.append(label, control); return field;
}
function input(labelText: string, name: string, value: string | null, type = 'text'): HTMLDivElement {
  const field = node('div', 'field');
  const label = node('label', '', labelText); label.htmlFor = `field-${name}`;
  const control = node('input'); control.name = name; control.type = type; control.id = label.htmlFor; control.value = value ?? '';
  if (type === 'text' && ['subtotal', 'shipping_fee'].includes(name)) control.inputMode = 'decimal';
  field.append(label, control); return field;
}
function button(text: string, className = 'button'): HTMLButtonElement {
  const control = node('button', className, text); control.type = 'button'; return control;
}
function section(title: string, className = ''): HTMLElement {
  const block = node('section', `panel ${className}`); block.append(node('h2', '', title)); return block;
}

app.innerHTML = `<header class="topbar"><a class="brand" href="./"><span class="brand-mark" aria-hidden="true">P</span>PolicyDesk</a><span class="header-context">Policy sandbox</span><a class="source-link" href="https://github.com/FishRaposo/policydesk">Source ↗</a></header>
<div class="disclosure" role="note"><strong>Synthetic prototype.</strong> Fictional data, synthetic replay and templates. No model calls or real financial actions.</div>
<div class="workspace"><aside class="scenario-rail" aria-label="Synthetic ticket scenarios"><h2>Ticket scenarios</h2><div id="language-control"></div><nav id="scenario-list" aria-label="Choose a synthetic scenario"></nav><div class="rail-note"><strong>Fixed policy v1</strong><p>Evaluation date: ${TODAY}<br>All dates use calendar days.</p><p>Edit the fictional facts to see where the decision changes.</p></div></aside>
<main id="workbench" tabindex="-1"><div class="workbench-heading"><div><p class="context-label" id="case-id"></p><h1 id="case-title"></h1></div><button type="button" class="button secondary" id="reset">Reset scenario</button></div>
<div class="ticket-and-facts"><section class="panel ticket-panel" aria-label="Fictional customer ticket"><div class="panel-topline"><h2>Customer ticket</h2><span class="sample-label">Fictional</span></div><div id="ticket-meta" class="metadata"></div><blockquote id="ticket-message"></blockquote><p class="helper">The original message stays fixed. Edited facts below are your sandbox assumptions, not a new extraction.</p></section>
<div id="decision-region" aria-live="polite" aria-atomic="true"></div></div>
<section class="panel facts-panel" aria-label="Editable fictional order facts"><details id="facts-details"><summary>Fictional order facts <span class="summary-hint">Edit to recalculate</span></summary><form id="facts-form" novalidate></form></details></section>
<div class="evidence-grid"><section class="panel" aria-label="Fictional policy evidence"><div class="panel-topline"><h2>Policy evidence</h2><span class="sample-label">Fictional v1</span></div><div id="clauses"></div></section><section class="panel" aria-label="Synthetic customer reply"><div class="panel-topline"><h2>Customer reply</h2><span id="reply-origin" class="sample-label"></span></div><p id="reply-body" class="reply-body"></p><div id="checks"></div></section></div>
<section class="panel trace-panel" aria-label="Synthetic execution trace"><div class="panel-topline"><h2>Decision trail</h2><span id="trace-origin" class="sample-label"></span></div><div id="trace"></div></section>
<footer class="workspace-footer"><p>API cost, model latency, caching and real-model comparison: <strong>unmeasured</strong>.</p><p>Browser approvals are an in-memory simulation. This fictional policy is not consumer law. Refreshing clears the session.</p></footer></main></div>`;

const languageControl = select('Ticket language', 'language', [['pt', 'Português · BRL'], ['es', 'Español · MXN'], ['en', 'English · USD']], language);
document.querySelector('#language-control')!.append(languageControl);
languageControl.querySelector('select')!.addEventListener('change', event => {
  language = (event.target as HTMLSelectElement).value as Language;
  sandbox = new Sandbox(scenarios.find(s => s.language === language)!); render();
});

function renderList(): void {
  const list = document.querySelector('#scenario-list')!; list.replaceChildren();
  for (const [index, scenario] of scenarios.filter(s => s.language === language).entries()) {
    const control = button('', 'scenario-button');
    control.setAttribute('aria-pressed', String(scenario.id === sandbox.scenario.id));
    control.append(node('span', 'scenario-index', String(index + 1).padStart(2, '0')), node('span', 'scenario-name', names[index]));
    control.addEventListener('click', () => {sandbox = new Sandbox(scenario); render();});
    list.append(control);
  }
}

function renderForm(): void {
  const form = document.querySelector<HTMLFormElement>('#facts-form')!; form.replaceChildren();
  const order = sandbox.order;
  const subtotal = major(order.items.reduce((sum, item) => sum + minor(item.price), 0));
  form.append(
    select('Order ownership', 'ownership', [['own', 'This customer'], ['foreign', 'Another customer']], order.customer_id === sandbox.scenario.ticket.customer_id ? 'own' : 'foreign'),
    select('Request', 'intent', [['refund_request', 'Refund'], ['cancel_subscription', 'Cancel subscription'], ['shipping_status', 'Shipping status'], ['other', 'Other']], sandbox.extraction.intent),
    select('Claim', 'claim', [['changed_mind', 'Changed mind'], ['damaged', 'Damaged item'], ['wrong_item', 'Wrong item'], ['not_delivered', 'Not delivered'], ['none', 'None']], sandbox.extraction.claim),
    select('Currency', 'currency', [['BRL', 'BRL'], ['MXN', 'MXN'], ['USD', 'USD']], order.currency),
    input('Item subtotal', 'subtotal', subtotal), input('Shipping fee', 'shipping_fee', order.shipping_fee),
    select('Order status', 'status', [['processing', 'Not shipped'], ['in_transit', 'In transit'], ['delivered', 'Delivered']], order.status),
    select('Carrier status', 'carrier_status', [['in_transit', 'In transit'], ['delivered', 'Delivered'], ['exception', 'Exception']], order.carrier_status),
    input('Shipment date', 'shipped_at', order.shipped_at, 'date'), input('Estimated delivery', 'estimated_delivery', order.estimated_delivery, 'date'),
    input('Delivery date', 'delivered_at', order.delivered_at, 'date'),
    select('Subscription', 'subscription', [['yes', 'Attached'], ['no', 'None']], order.subscription_id ? 'yes' : 'no'),
  );
  const hint = node('p', 'helper form-note', 'Dates and status must agree. Clear shipment and delivery dates for an unshipped box.');
  form.append(hint);
}

function handleFormChange(): void {
  const values = new FormData(document.querySelector<HTMLFormElement>('#facts-form')!);
  const value = (name: string) => String(values.get(name) ?? '');
  const next = {...sandbox.order, customer_id: value('ownership') === 'own' ? sandbox.scenario.ticket.customer_id : 'C-FOREIGN',
    currency: value('currency'), items: [{name: 'Fictional coffee', price: value('subtotal')}], shipping_fee: value('shipping_fee'),
    status: value('status'), carrier_status: value('carrier_status'), shipped_at: value('shipped_at') || null,
    delivered_at: value('delivered_at') || null, estimated_delivery: value('estimated_delivery'),
    subscription_id: value('subscription') === 'yes' ? 'SUB-SANDBOX' : null} as Order;
  const extraction = {...sandbox.extraction, intent: value('intent'), claim: value('claim')} as Extraction;
  sandbox.update(next, extraction); renderResults();
}
document.querySelector<HTMLFormElement>('#facts-form')!.addEventListener('input', handleFormChange);
document.querySelector<HTMLFormElement>('#facts-form')!.addEventListener('change', handleFormChange);
document.querySelector('#facts-form')!.addEventListener('submit', event => event.preventDefault());
document.querySelector('#reset')!.addEventListener('click', () => {sandbox.reset(); render();});

function renderResults(): void {
  const region = document.querySelector('#decision-region')!; region.replaceChildren();
  const decision = sandbox.decision;
  const panel = section('Policy decision', `decision-panel ${decision?.outcome ?? 'invalid'}`);
  if (!decision) {
    panel.append(node('p', 'decision-title', 'Check the fictional inputs'), node('p', '', sandbox.error ?? 'Invalid inputs.'));
    region.append(panel);
  } else {
    panel.append(node('p', 'decision-title', labels[decision.outcome]), node('p', 'decision-reason', decision.reasons.join(', ').replaceAll('_', ' ')));
    const actions = node('div', 'actions');
    for (const [index, action] of decision.actions.entries()) {
      const row = node('div', 'action-row');
      row.append(node('div', 'action-description', action.kind === 'refund' ? `Proposed refund · ${action.currency} ${action.amount}` : 'Cancel subscription · next cycle'));
      const approved = sandbox.approved.has(index);
      const control = button(approved ? 'Authorization recorded · simulated' : 'Simulate approval', approved ? 'button approved' : 'button');
      control.disabled = approved;
      const binding = sandbox.binding();
      control.addEventListener('click', () => {sandbox.approve(index, binding); renderResults();});
      row.append(control); actions.append(row);
    }
    if (!decision.actions.length) actions.append(node('p', 'no-action', 'No action is pending approval.'));
    panel.append(actions, node('p', 'helper', 'Human approval boundary · authorization is separate from execution. Editing any fact clears all approvals.'));
    region.append(panel);
  }

  const clauses = document.querySelector('#clauses')!; clauses.replaceChildren();
  for (const id of decision?.clause_ids ?? []) {
    const row = node('div', 'clause-row');
    row.append(node('span', 'clause-id', id), node('p', '', policy.clauses[id as keyof typeof policy.clauses][language]));
    clauses.append(row);
  }
  if (!decision?.clause_ids.length) clauses.append(node('p', 'helper', decision ? 'Order information only; no refund clause applies.' : 'A valid decision will show its policy clauses here.'));
  const reply = sandbox.reply();
  const replyBody = document.querySelector<HTMLElement>('#reply-body')!;
  replyBody.textContent = reply?.body ?? 'Correct the fictional inputs to preview a template reply.'; replyBody.lang = language;
  document.querySelector('#reply-origin')!.textContent = sandbox.edited ? 'Localized template' : 'Synthetic replay';
  const checks = document.querySelector('#checks')!; checks.replaceChildren();
  checks.append(node('p', 'check-summary', !decision ? 'No checks available for invalid inputs.' : sandbox.edited
    ? 'Template preview · deterministic decision and money formatting. Python language detection was not run in the browser.'
    : 'Python reference · all eight final-reply checks passed on this synthetic preset.'));
  document.querySelector('#trace-origin')!.textContent = sandbox.edited ? 'Edited browser inputs' : 'Python reference · synthetic';
  const trace = document.querySelector('#trace')!; trace.replaceChildren();
  const reference = sandbox.referenceTrace();
  if (reference) {
    const list = node('ol', 'trail');
    for (const step of reference) {
      const item = node('li');
      const title = step.step.replaceAll('_', ' ');
      const detail = step.violations?.length ? step.violations.map(v => v.code).join(', ') : step.status ?? (step.step === 'extract' || step.step === 'draft' || step.step === 'repair' ? 'synthetic response fixture' : 'deterministic code');
      item.append(node('strong', '', title), node('span', '', detail)); list.append(item);
    }
    trace.append(list);
  } else {
    trace.append(node('p', 'helper', 'The original replay trace was cleared after your edit. No extraction, tool call, model draft, or Python validator execution is implied by this browser result.'));
    const list = node('ol', 'trail');
    for (const [name, detail] of [['Structured facts', 'Your fictional sandbox inputs'], ['Policy v1', decision ? labels[decision.outcome] : 'Invalid inputs'], ['Localized template', 'No model call'], ['Human approval', sandbox.approved.size ? 'Simulated authorization recorded' : 'No execution']]) {
      const item = node('li'); item.append(node('strong', '', name), node('span', '', detail)); list.append(item);
    }
    trace.append(list);
  }
}

function render(): void {
  renderList(); renderForm();
  const index = scenarios.filter(s => s.language === language).findIndex(s => s.id === sandbox.scenario.id);
  document.querySelector('#case-id')!.textContent = `${sandbox.scenario.id} · fictional ticket`;
  document.querySelector('#case-title')!.textContent = names[index];
  document.querySelector('#ticket-meta')!.textContent = `${sandbox.scenario.ticket.customer_id} · ${sandbox.scenario.order.order_id} · ${language.toUpperCase()}`;
  const message = document.querySelector<HTMLElement>('#ticket-message')!;
  message.textContent = sandbox.scenario.ticket.message; message.lang = language;
  renderResults();
}
render();
void mountLocalRuntime();
