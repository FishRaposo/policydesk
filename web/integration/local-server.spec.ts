import {expect,test,type Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import bundle from '../src/generated/bundle.json' with {type:'json'};

// Real loopback HTTP -> production ASGI -> real SDK with an in-process mock transport.
// No Playwright route interception and no authentic provider response is used here.
const fixture=bundle.scenarios[0];
const observations=new WeakMap<Page,{errors:string[];external:string[]}>();
test.beforeEach(({page})=>{
  const seen={errors:[] as string[],external:[] as string[]};observations.set(page,seen);
  page.on('pageerror',error=>seen.errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')seen.errors.push(message.text());});
  page.on('request',request=>{if(new URL(request.url()).hostname!=='127.0.0.1')seen.external.push(request.url());});
});
test.afterEach(({page})=>{expect(observations.get(page)?.errors).toEqual([]);expect(observations.get(page)?.external).toEqual([]);});

async function ready(page:Page){
  await page.goto('./');
  await expect(page.getByRole('button',{name:'Run using my OpenAI key',exact:true})).toBeEnabled();
  await expect(page.locator('meta[name="policydesk-runtime"]')).toHaveAttribute('content','local');
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('sk-');
  await expect(page.locator('body')).not.toContainText('fake-local-sdk-key');
  expect(await page.evaluate(()=>({local:localStorage.length,session:sessionStorage.length}))).toEqual({local:0,session:0});
}
async function resetTicket(page:Page,scenario=fixture){
  await page.getByLabel('Fictional customer',{exact:true}).selectOption(scenario.ticket.customer_id);
  await page.getByLabel('Local ticket language',{exact:true}).selectOption('pt');
  await page.getByLabel('Order fixture',{exact:true}).selectOption(scenario.order.order_id);
  await page.getByLabel('Editable fictional order JSON',{exact:true}).fill(JSON.stringify(scenario.order));
  await page.getByLabel('Local ticket message',{exact:true}).fill(scenario.ticket.message);
}
async function runTicket(page:Page){
  const result=page.waitForResponse(response=>response.url().endsWith('/api/runs')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Run using my OpenAI key',exact:true}).click();
  const response=await result;expect(response.status()).toBe(202);const job=await response.json();
  await expect(page.locator('#local-status')).toHaveText('Job completed');return String(job.id);
}

test('startup is inert; actual local run authorizes only and edited facts become stale',async ({page})=>{
  const posts:string[]=[];page.on('request',request=>{if(request.method()==='POST')posts.push(request.url());});
  await ready(page);
  const config=await (await page.request.get('/api/config')).json();
  expect(config.session_budget.spent_usd).toMatch(/^0(?:\.0+)?$/);
  expect(config.session_budget.reserved_usd).toMatch(/^0(?:\.0+)?$/);
  expect(posts).toEqual([]);
  const id=await runTicket(page);
  await expect(page.locator('#local-result')).toContainText('mock_openai_transport');
  await expect(page.locator('#local-result')).toContainText('94.80');
  const approvalResponse=page.waitForResponse(r=>r.url().includes('/api/approvals/')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Record local authorization',exact:true}).click();
  const approved=await (await approvalResponse).json();expect(approved.executed).toBe(false);
  await expect(page.locator('#local-authorization')).toContainText('false');
  await page.getByLabel('Local ticket message',{exact:true}).fill(`${fixture.ticket.message} Fictional edit.`);
  await expect(page.locator('#local-status')).toContainText('stale');
  await expect(page.getByRole('button',{name:'Record local authorization',exact:true})).toHaveCount(0);
  await expect.poll(async()=>(await (await page.request.get(`/api/runs/${id}`)).json()).stale).toBe(true);
});

test('malformed edits revoke actual server approval without replacing valid workspace facts',async({page})=>{
  await ready(page);await resetTicket(page);const id=await runTicket(page);
  const before=await (await page.request.get('/api/config')).json();
  const job=await (await page.request.get(`/api/runs/${id}`)).json();
  await page.getByLabel('Editable fictional order JSON',{exact:true}).fill('{');
  await expect.poll(async()=>(await (await page.request.get(`/api/runs/${id}`)).json()).stale,{timeout:5000}).toBe(true);
  await expect(page.locator('#local-status')).toContainText('not saved');
  const rejected=await page.request.post(`/api/approvals/${job.result.pending_actions[0].id}`,{data:{revision:job.revision,run_id:id},headers:{Origin:'http://127.0.0.1:8765','X-PolicyDesk-CSRF':before.csrf_token}});
  expect(rejected.status()).toBe(409);
  const after=await (await page.request.get('/api/config')).json();expect(after.workspace).toEqual(before.workspace);
  await expect(page.getByRole('button',{name:'Record local authorization',exact:true})).toHaveCount(0);
});

test('actual compound cancellation and refund each retain their authorization control',async({page})=>{
  await ready(page);await resetTicket(page,bundle.scenarios.find(s=>s.id==='D-PT-07')!);
  const id=await runTicket(page);
  const result=await (await page.request.get(`/api/runs/${id}`)).json();
  expect(result.result.provenance).toBe('mock_openai_transport');
  expect(result.result.pending_actions.map((a:{action:string})=>JSON.parse(a.action).kind).sort()).toEqual(['cancel_subscription','refund']);
  const controls=page.getByRole('button',{name:'Record local authorization',exact:true});await expect(controls).toHaveCount(2);
  const authorizationIds:string[]=[];
  for(let remaining=2;remaining>0;remaining--){
    const response=page.waitForResponse(r=>r.url().includes('/api/approvals/')&&r.request().method()==='POST');
    await controls.first().click();const authorization=await response;
    expect(authorization.ok()).toBe(true);expect((await authorization.json()).executed).toBe(false);
    authorizationIds.push(authorization.url());await expect(controls).toHaveCount(remaining-1);
  }
  expect(new Set(authorizationIds).size).toBe(2);await expect(page.locator('#local-authorization pre')).toHaveCount(2);
});

test('recorded run retains mock transport provenance in the real downloadable report',async ({page})=>{
  await ready(page);await resetTicket(page);await page.getByLabel('Save local recording',{exact:true}).check();
  const id=await runTicket(page);
  const downloaded=page.waitForEvent('download');
  await page.getByRole('link',{name:'Download JSON report',exact:true}).click();
  const download=await downloaded;expect(download.suggestedFilename()).toBe(`policydesk-${id}.json`);
  const report=JSON.parse(await readFile((await download.path())!,'utf8'));expect(report.result.provenance).toBe('mock_openai_transport');
  expect(report.result.run_id).toMatch(/^[a-zA-Z0-9_-]+$/);
  const recording=JSON.parse(await readFile(resolve(import.meta.dirname,'..','..','.runtime/browser-http/recordings',`${report.result.run_id}.json`),'utf8'));
  expect(recording.provenance).toBe('mock_openai_transport');expect(recording.result.run_id).toBe(report.result.run_id);
  expect(recording.kind).toBe('openai_responses_recording');expect(recording.exchanges.length).toBeGreaterThan(0);
  expect(JSON.stringify(recording)).not.toContain('fake-local-sdk-key');
  expect(report.result.metrics.estimated_cost_usd).not.toBeNull();
  expect(report.result.metrics.ttft_ms).toBeNull();
  await expect(page.getByRole('link',{name:'Download MD report',exact:true})).toHaveAttribute('href',`/api/runs/${id}/report?format=md`);
});

test('actual paired development comparison completes 27 mock pairs without empirical claims',async ({page})=>{
  await ready(page);await resetTicket(page);
  await page.getByLabel('Maximum comparison cost (USD)',{exact:true}).fill('2.00');
  await page.getByLabel('Session spending limit (USD)',{exact:true}).fill('5.00');
  const started=page.waitForResponse(r=>r.url().endsWith('/api/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Run paired comparison',exact:true}).click();
  const id=String((await (await started).json()).id);
  await expect(page.locator('#local-status')).toHaveText('Job completed');
  const report=await (await page.request.get(`/api/runs/${id}/report?format=json`)).json();
  expect(report.result.planned_pairs).toBe(27);expect(report.result.complete_pairs).toBe(27);
  expect(report.result.provenance).toEqual(['mock_openai_transport']);
  expect(report.result.human_review_performed).toBe(false);expect(report.result.independent_benchmark).toBe(false);
  expect(report.result.pairs.every((pair:{baseline:{result:{pending_actions:unknown[]}}})=>pair.baseline.result.pending_actions.length===0)).toBe(true);
  await expect(page.locator('#local-result')).toContainText('mock_openai_transport');
  await expect(page.getByRole('button',{name:'Record local authorization',exact:true})).toHaveCount(0);
});

test('actual comparison cancellation retains an analysis-only report and no approvals',async({page})=>{
  await ready(page);await resetTicket(page);
  await page.getByLabel('Maximum comparison cost (USD)',{exact:true}).fill('2.00');
  await page.getByLabel('Session spending limit (USD)',{exact:true}).fill('5.00');
  const started=page.waitForResponse(r=>r.url().endsWith('/api/runs')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Run paired comparison',exact:true}).click();
  const id=String((await (await started).json()).id);
  const cancel=page.getByRole('button',{name:'Cancel local job',exact:true});
  await expect(cancel).toBeEnabled();await cancel.click();
  await expect(page.locator('#local-status')).toHaveText('Job cancelled');
  const report=await (await page.request.get(`/api/runs/${id}/report?format=json`)).json();
  expect(report.result.independent_benchmark).toBe(false);
  expect(report.result.human_review_performed).toBe(false);
  expect(report.result.complete_pairs).toBeLessThan(report.result.planned_pairs);
  await expect(page.getByRole('button',{name:'Record local authorization',exact:true})).toHaveCount(0);
});

for(const width of [390,768,1440])test(`actual local runtime keyboard and layout ${width}px`,async({page},info)=>{
  await page.setViewportSize({width,height:900});await ready(page);await resetTicket(page);
  const run=page.getByRole('button',{name:'Run using my OpenAI key',exact:true});await run.focus();await expect(run).toBeFocused();await page.keyboard.press('Enter');
  await expect(page.locator('#local-status')).toHaveText('Job completed');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.screenshot({path:info.outputPath(`actual-local-${width}.png`),fullPage:true});
});
