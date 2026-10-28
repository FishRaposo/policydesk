import type {Order} from './types';

export const VERIFICATION_WARNING = 'OpenAI integration implemented; live verification and empirical results not yet performed.';
export function isLocalRuntime(document: Pick<Document, 'querySelector'>): boolean {
  return document.querySelector('meta[name="policydesk-runtime"]')?.getAttribute('content') === 'local';
}
interface Ticket {customer_id:string; language:string; message:string}
interface Config {
  csrf_token:string; enabled:boolean; models:{id:string;label:string}[]; limits:Record<string,unknown>;
  session_budget:Record<string,unknown>; workspace_revision:number;
  fictional_customers:{customer_id:string;label:string}[]; orders:Order[];
  workspace?:{ticket:Ticket;order:Order|null}; verification_status:unknown;
}
interface Job {id:string;status:string;revision:number;stale:boolean;progress:unknown[];result:Record<string,unknown>|null;error_code:string|null}
function el<K extends keyof HTMLElementTagNameMap>(tag:K, text?:string, className=''):HTMLElementTagNameMap[K] {
  const n=document.createElement(tag); n.className=className; if(text!==undefined)n.textContent=text; return n;
}
function action(text:string, secondary=false) {const b=el('button',text,`button${secondary?' secondary':''}`);b.type='button';return b;}
function field<T extends HTMLElement>(text:string, control:T, id:string) {
  const wrap=el('div',undefined,'field'); const label=el('label',text);label.htmlFor=id;control.id=id;wrap.append(label,control);return wrap;
}
function dropdown(options:{id:string;label:string}[]) {
  const s=el('select'); for(const o of options){const opt=el('option',o.label);opt.value=o.id;s.append(opt);}return s;
}
function json(value:unknown) {return JSON.stringify(value,null,2)??'Unavailable';}
function details(title:string,value:unknown) {const d=el('details');d.append(el('summary',title),el('pre',json(value)));return d;}

/** The public bundle can import this module; only the server marker enables HTTP. */
export async function mountLocalRuntime():Promise<void> {
  if(!isLocalRuntime(document)) {
    document.querySelector('.disclosure')?.append(el('p',VERIFICATION_WARNING));
    const setup=el('section',undefined,'panel local-setup');setup.setAttribute('aria-label','Local OpenAI setup');
    setup.append(el('h2','Run OpenAI locally'),el('p',VERIFICATION_WARNING),el('p','Install the project with its live extra, then start the local server:'),el('code','policydesk serve --enable-live'),el('p','Enter your OpenAI key in the hidden terminal prompt. Open the loopback URL printed by the launcher. Choose fictional inputs and a budget, then explicitly run a ticket or paired comparison. The public page remains a synthetic sandbox.'));
    const instructions=el('a','Installation and launcher instructions','source-link');instructions.href='https://github.com/FishRaposo/policydesk#try-openai-locally-with-your-own-key';setup.append(instructions);
    document.querySelector('.workspace-footer')?.before(setup);return;
  }
  document.querySelector<HTMLElement>('.workspace')!.hidden=true;
  const disclosure=document.querySelector('.disclosure')!;disclosure.textContent=VERIFICATION_WARNING;
  const panel=el('main',undefined,'local-workspace');panel.id='local-workspace';panel.tabIndex=-1;
  const skip=document.querySelector<HTMLAnchorElement>('.skip-link');if(skip)skip.href='#local-workspace';
  panel.append(el('p','Local runtime · fictional data · authorization only','context-label'),el('h1','Run OpenAI locally'),el('p','Your key stays in the local server process. Provider requests start only after you explicitly run a ticket or comparison. Nothing is sent to a customer and no financial action is executed.','helper'));
  const status=el('p','Loading local configuration…','local-status');status.id='local-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');panel.append(status);
  document.querySelector('.workspace')!.before(panel);
  const get=async <T>(path:string):Promise<T>=>{const r=await fetch(path,{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw new Error(`Local request failed (${r.status}).`);return r.json() as Promise<T>;};
  let config:Config;
  try{config=await get<Config>('/api/config');}catch{status.textContent='Local configuration unavailable. Restart the launcher and reload this page.';return;}
  const post=async <T>(path:string,body:unknown):Promise<T>=>{
    const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-PolicyDesk-CSRF':config.csrf_token},body:JSON.stringify(body)});
    if(!r.ok)throw new Error(`Local request rejected (${r.status}). Check the inputs, budget and active job.`);return r.json() as Promise<T>;
  };
  let revision=config.workspace_revision,dirty=true,busy=false,job:Job|null=null,saveTimer:ReturnType<typeof setTimeout>|undefined,pollTimer:ReturnType<typeof setTimeout>|undefined;
  let saved:Promise<void>=Promise.resolve();
  const form=el('form',undefined,'panel local-controls');form.addEventListener('submit',e=>e.preventDefault());form.append(el('h2','Fictional ticket workspace'));
  const grid=el('div',undefined,'local-grid');
  const customer=dropdown(config.fictional_customers.map(c=>({id:c.customer_id,label:`${c.label} · ${c.customer_id}`})));
  const language=dropdown([{id:'pt',label:'Português'},{id:'es',label:'Español'},{id:'en',label:'English'}]);
  const order=dropdown([{id:'',label:'No order fixture'},...config.orders.map(o=>({id:o.order_id,label:`${o.order_id} · ${o.customer_id} · ${o.currency}`}))]);
  const model=dropdown(config.models);const message=el('textarea');message.rows=4;message.maxLength=8000;
  const orderData=el('textarea');orderData.rows=9;orderData.spellcheck=false;
  const budget=el('input');budget.type='text';budget.inputMode='decimal';budget.value='0.05';budget.required=true;budget.maxLength=64;
  const comparisonBudget=el('input');comparisonBudget.type='text';comparisonBudget.inputMode='decimal';comparisonBudget.value='1.00';comparisonBudget.required=true;comparisonBudget.maxLength=64;
  const session=el('input');session.type='text';session.inputMode='decimal';session.value=String(config.session_budget.limit_usd??'1.00');session.required=true;session.maxLength=64;
  const initial=config.workspace;customer.value=initial?.ticket.customer_id??config.fictional_customers[0]?.customer_id??'';language.value=initial?.ticket.language??'pt';message.value=initial?.ticket.message??'';order.value=initial?.order?.order_id??'';orderData.value=json(initial?.order??null);
  grid.append(field('Fictional customer',customer,'local-customer'),field('Local ticket language',language,'local-language'),field('Order fixture',order,'local-order'),field('OpenAI model',model,'local-model'),field('Maximum job cost (USD)',budget,'local-budget'),field('Maximum comparison cost (USD)',comparisonBudget,'local-comparison-budget'),field('Session spending limit (USD)',session,'local-session'));
  form.append(grid,field('Local ticket message',message,'local-message'),field('Editable fictional order JSON',orderData,'local-order-data'));
  const record=el('input');record.type='checkbox';record.id='local-record';const recordLabel=el('label',' Save local recording');recordLabel.htmlFor=record.id;recordLabel.prepend(record);
  form.append(recordLabel,el('p','Recordings contain fictional prompts, tool data and model responses on this machine. Use fictional data only.','helper'));
  const preview=details('Data preview and execution limits',{});const previewBody=preview.querySelector('pre')!;
  form.append(preview,el('p','Paired comparison: 9 development cases × 3 repeats × both systems. The baseline is analysis only and cannot authorize actions. The job budget bounds the whole comparison; insufficient budget preserves incomplete results.','helper'));
  const controls=el('div',undefined,'local-actions');const run=action('Run using my OpenAI key'),compare=action('Run paired comparison',true),cancel=action('Cancel local job',true),acknowledge=action('Acknowledge unknown cost',true);
  cancel.disabled=true;acknowledge.hidden=!Boolean(config.session_budget.unknown_cost??config.session_budget.blocked);
  controls.append(run,compare,cancel,acknowledge);form.append(controls);
  const result=el('section',undefined,'panel local-output');result.id='local-result';result.setAttribute('aria-label','Local job result');
  const approval=el('div');approval.id='local-authorization';const reports=el('div',undefined,'local-actions');
  panel.append(form,result,approval,reports,details('Verification status',config.verification_status));
  function workspace() {return {ticket:{customer_id:customer.value,language:language.value,message:message.value},order:JSON.parse(orderData.value) as Order|null};}
  function updatePreview(){try{previewBody.textContent=json({workspace:workspace(),revision,model:model.value,pricing:config.models.find(profile=>profile.id===model.value),ticket_max_cost_usd:budget.value,comparison_max_cost_usd:comparisonBudget.value,session_limit_usd:session.value,record:record.checked,limits:config.limits,session_budget:config.session_budget});}catch{previewBody.textContent='Order JSON is invalid. Correct it before running.';}}
  function availability(){run.disabled=compare.disabled=busy||!config.enabled;cancel.disabled=!busy||job===null;}
  function clearAuthorization(){approval.replaceChildren();reports.replaceChildren();}
  async function refreshBudget(){
    try{const latest=await get<Config>('/api/config');config.session_budget=latest.session_budget;acknowledge.hidden=!Boolean(latest.session_budget.unknown_cost||latest.session_budget.blocked);updatePreview();}
    catch{status.append(document.createTextNode(' Session budget refresh unavailable; inspect the local server before another run.'));}
  }
  function persist():Promise<void>{
    clearTimeout(saveTimer);const task=saved.catch(()=>{}).then(async()=>{
      if(!dirty)return;const snapshot=workspace();const encoded=json(snapshot);const response=await post<{revision:number}>('/api/workspace',snapshot);revision=response.revision;
      dirty=json(workspace())!==encoded;updatePreview();
    });saved=task;return task;
  }
  function edit(){
    dirty=true;clearAuthorization();status.textContent=job?'Inputs changed · previous result and authorization are stale.':'Fictional inputs changed. Save occurs locally before a run.';
    // Queue revocation before preview/save can parse malformed fictional inputs.
    saved=saved.catch(()=>{}).then(async()=>{const response=await post<{revision:number}>('/api/workspace/invalidate',{});revision=response.revision;});
    void saved.catch(()=>{status.textContent='Server invalidation failed. Do not reuse previous authorizations; check the local server.';});
    updatePreview();clearTimeout(saveTimer);saveTimer=setTimeout(()=>{void persist().catch(()=>{status.textContent='Fictional inputs were not saved. Check the order JSON and try again.';});},350);
  }
  for(const control of [language,message,orderData])control.addEventListener('input',edit);
  customer.addEventListener('change',()=>{const own=config.orders.find(o=>o.customer_id===customer.value);order.value=own?.order_id??'';orderData.value=json(own??null);edit();});
  order.addEventListener('change',()=>{orderData.value=json(config.orders.find(o=>o.order_id===order.value)??null);edit();});
  for(const control of [model,budget,comparisonBudget,session,record])control.addEventListener('input',updatePreview);
  async function poll(id:string):Promise<void>{
    try{
      const current=await get<Job>(`/api/runs/${encodeURIComponent(id)}`);job=current;
      const stale=current.stale||current.revision!==revision||dirty;
      status.textContent=`Job ${current.status}${stale?' · stale inputs; authorization unavailable':''}${current.error_code?` · ${current.error_code}`:''}`;
      result.replaceChildren(el('h2','Local job result'),el('p',`Provenance: ${String(current.result?.provenance??'pending · local server')}`),details('Job progress',current.progress));
      if(current.result){
        const reply=current.result.reply;
        if(typeof reply==='object'&&reply!==null&&'body' in reply){const quote=el('blockquote',String(reply.body));quote.lang=language.value;result.append(quote);}
        const decision=current.result.decision;
        if(typeof decision==='object'&&decision!==null&&'outcome' in decision)result.append(el('p',`Policy decision: ${String(decision.outcome)} · authorization only`));
        const metrics=current.result.metrics??current.result.summary??null;
        const metricView=details('Metrics and comparison summary (null means unavailable)',metrics);metricView.open=true;
        result.append(metricView,details('Result, decision and reply',current.result));
      }
      busy=['queued','running','cancelling'].includes(current.status);availability();clearAuthorization();
      if(!busy){void refreshBudget();}
      if(!busy&&current.result){
        for(const format of ['json','md']){const a=el('a',`Download ${format.toUpperCase()} report`,'button secondary');a.href=`/api/runs/${encodeURIComponent(id)}/report?format=${format}`;a.download=`policydesk-${id}.${format}`;reports.append(a);}
        if(!stale&&current.status==='completed'){
          const actions=current.result.pending_actions;
          if(Array.isArray(actions))for(const pending of actions){
            if(typeof pending!=='object'||pending===null||!('id' in pending))continue;
            const row=el('div');const b=action('Record local authorization',true);row.append(el('p',`Proposed action · ${json(pending)}`),b);approval.append(row);
            b.addEventListener('click',()=>{b.disabled=true;const requestedRevision=revision;void post(`/api/approvals/${encodeURIComponent(String(pending.id))}`,{revision,run_id:id}).then(value=>{if(!dirty&&revision===requestedRevision)row.replaceChildren(el('pre',json(value)));}).catch(()=>{status.textContent='Authorization rejected. The result may be stale.';});});
          }
        }
      }
      if(busy)pollTimer=setTimeout(()=>{void poll(id);},700);
    }catch{busy=false;availability();clearAuthorization();status.textContent='Job status unavailable. Check the local server before retrying.';}
  }
  async function start(kind:'ticket'|'comparison'){
    if(busy||!config.enabled)return;
    const decimal=/^(?:0|[1-9]\d*)(?:\.\d+)?$/;
    const allowance=kind==='comparison'?comparisonBudget.value:budget.value;
    if(!decimal.test(allowance)||!decimal.test(session.value)||!/[1-9]/.test(allowance)||!/[1-9]/.test(session.value)){status.textContent='Enter positive plain decimal USD budgets.';return;}
    busy=true;job=null;availability();clearAuthorization();clearTimeout(pollTimer);status.textContent='Saving fictional workspace…';
    try{
      await persist();if(dirty)throw new Error('Inputs changed while saving; run again.');
      const request={kind,revision,model:model.value,max_cost_usd:allowance,session_limit_usd:session.value,record:record.checked,confirm_spend:true,idempotency_key:crypto.randomUUID()};
      const started=await post<{id:string}>('/api/runs',request);status.textContent='Job queued';await poll(started.id);
    }catch{busy=false;availability();status.textContent='Run not started. Check the fictional inputs, positive budget, and any active local job.';}
  }
  run.addEventListener('click',()=>{void start('ticket');});compare.addEventListener('click',()=>{void start('comparison');});
  cancel.addEventListener('click',()=>{if(!job)return;cancel.disabled=true;void post(`/api/runs/${encodeURIComponent(job.id)}/cancel`,{}).then(()=>{status.textContent='Cancellation requested. Any in-flight provider request may still incur cost.';}).catch(()=>{status.textContent='Cancellation request failed. Check the local server.';cancel.disabled=false;});});
  acknowledge.addEventListener('click',()=>{void post('/api/budget/acknowledge',{}).then(()=>{status.textContent='Unknown cost acknowledged. Review the session budget before starting another run.';void refreshBudget();}).catch(()=>{status.textContent='Cost acknowledgement failed.';});});
  window.addEventListener('pagehide',()=>{clearTimeout(saveTimer);clearTimeout(pollTimer);},{once:true});
  status.textContent=config.enabled?'Ready · local key configured. No provider request has started.':'Live execution disabled. Restart policydesk serve --enable-live and enter the key in the terminal.';availability();updatePreview();
}
