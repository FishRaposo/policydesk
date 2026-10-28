import {expect, test, type Page} from '@playwright/test';
import bundle from '../src/generated/bundle.json' with {type:'json'};

const fixture = bundle.scenarios[0];
const observations=new WeakMap<Page,{errors:string[];external:string[]}>();
test.beforeEach(async ({page})=>{
  const seen={errors:[] as string[],external:[] as string[]};observations.set(page,seen);
  page.on('pageerror',error=>seen.errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error'&&!message.text().includes('409'))seen.errors.push(message.text());});
  await page.route('**/*',route=>{
    if(new URL(route.request().url()).hostname==='127.0.0.1')return route.fallback();
    seen.external.push(route.request().url());return route.abort();
  });
});
test.afterEach(async ({page})=>{expect(observations.get(page)?.errors).toEqual([]);expect(observations.get(page)?.external).toEqual([]);});
async function localPage(page: Page, running = false, enabled = true, pendingActions=1) {
  const requests: {path: string; body: Record<string, unknown>; csrf: string | undefined}[] = [];
  let revision = 1;
  await page.route('**/policydesk/', async route => {
    const response = await route.fetch();
    await route.fulfill({response, body: (await response.text()).replace('<head>', '<head><meta name="policydesk-runtime" content="local">')});
  });
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    if (request.method() === 'POST') requests.push({path, body: request.postDataJSON(), csrf: request.headers()['x-policydesk-csrf']});
    let data: unknown = {};
    if (path === '/api/config') data = {csrf_token:'mock-csrf',enabled,models:[{id:'gpt-6-luna',label:'Luna',pricing_version:'mock-prices-v1',effective_date:'2026-10-28'}],limits:{max_tool_calls:3},session_budget:{},workspace_revision:1,fictional_customers:[{customer_id:fixture.ticket.customer_id,label:'Fictional customer'}],orders:[fixture.order],workspace:{ticket:fixture.ticket,order:fixture.order},verification_status:'mock transport; live verification not performed'};
    if (path === '/api/workspace') data = {revision:++revision};
    if (path === '/api/workspace/invalidate') data = {revision:++revision};
    if (path === '/api/runs') data = {id:'mock-job',status:'queued'};
    if (path === '/api/runs/mock-job') data = {id:'mock-job',status:running?'running':'completed',revision,stale:false,progress:[{step:'mock transport'}],result:running?null:{provenance:'mock_openai_transport',reply:{body:'<img src=x onerror=alert(1)>'},pending_actions:[{id:'action-1',kind:'refund'},...(pendingActions===2?[{id:'action-2',kind:'cancel_subscription'}]:[])],metrics:{estimated_cost_usd:'0.001',ttft_ms:null}}};
    if (path.endsWith('/cancel')) {running=false; data={status:'cancelled'};}
    if (path.startsWith('/api/approvals/')) data={authorized:true,executed:false};
    if (path.endsWith('/report')) return route.fulfill({contentType:'application/json',body:'{"provenance":"mock_openai_transport"}'});
    await route.fulfill({json:data});
  });
  await page.goto('./'); return requests;
}

test('public setup stays static without local API probing', async ({page}) => {
  const calls: string[]=[]; page.on('request', r => {if(r.url().includes('/api/')) calls.push(r.url());});
  await page.goto('./');
  await expect(page.getByRole('heading',{name:'Run OpenAI locally',exact:true})).toBeVisible();
  await expect(page.getByText('policydesk serve --enable-live',{exact:true})).toBeVisible();
  expect(calls).toEqual([]);
  await expect(page.getByRole('button',{name:'Run using my OpenAI key',exact:true})).toHaveCount(0);
});

test('local explicit run binds workspace, renders safe output and revokes approvals on edit', async ({page}) => {
  const requests = await localPage(page);
  const run = page.getByRole('button',{name:'Run using my OpenAI key',exact:true});
  await expect(run).toBeVisible(); expect(requests).toEqual([]);
  await page.getByLabel('Local ticket message',{exact:true}).fill('Please refund fictional order GN-1007.');
  await run.click();
  await expect(page.locator('#local-status')).toContainText('completed');
  expect(requests.slice(0,3).map(r=>r.path)).toEqual(['/api/workspace/invalidate','/api/workspace','/api/runs']);
  expect(requests[1].body.ticket).toMatchObject({message:'Please refund fictional order GN-1007.'});
  expect(requests[2].body).toMatchObject({kind:'ticket',revision:3,confirm_spend:true,record:false,model:'gpt-6-luna'});
  expect(requests.every(r => r.csrf==='mock-csrf')).toBe(true);
  await expect(page.locator('#local-result')).toContainText('mock_openai_transport');
  await expect(page.locator('#local-result blockquote')).toHaveText('<img src=x onerror=alert(1)>');
  await expect(page.locator('#local-result blockquote')).toBeVisible();
  await expect(page.getByRole('link',{name:'Download JSON report',exact:true})).toHaveAttribute('href','/api/runs/mock-job/report?format=json');
  await expect(page.locator('#local-result img')).toHaveCount(0);
  await page.getByRole('button',{name:'Record local authorization',exact:true}).click();
  expect(requests.at(-1)?.body).toEqual({revision:3,run_id:'mock-job'});
  await expect(page.locator('#local-authorization')).toContainText('executed');
  await page.getByLabel('Local ticket message',{exact:true}).fill('An edited ticket');
  await expect(page.locator('#local-status')).toContainText('stale');
  await expect(page.getByRole('button',{name:'Record local authorization',exact:true})).toHaveCount(0);
});

test('malformed fictional order edits invalidate the server before parsing or saving',async({page})=>{
  const requests=await localPage(page);
  await page.getByRole('button',{name:'Run using my OpenAI key',exact:true}).click();
  await expect(page.locator('#local-status')).toHaveText('Job completed');
  await page.getByRole('button',{name:'Record local authorization',exact:true}).click();
  const before=requests.length;
  await page.getByLabel('Editable fictional order JSON',{exact:true}).fill('{');
  await expect.poll(()=>requests.slice(before).map(r=>r.path),{timeout:3000}).toEqual(['/api/workspace/invalidate']);
  await expect(page.locator('#local-status')).toContainText('not saved');
  await expect(page.locator('#local-authorization')).toBeEmpty();
});

test('compound proposals remain individually reviewable after the first authorization',async({page})=>{
  const requests=await localPage(page,false,true,2);
  await page.getByRole('button',{name:'Run using my OpenAI key',exact:true}).click();
  await expect(page.locator('#local-status')).toHaveText('Job completed');
  const approvals=page.getByRole('button',{name:'Record local authorization',exact:true});
  await expect(approvals).toHaveCount(2);await approvals.first().click();
  await expect(approvals).toHaveCount(1);await expect(approvals).toBeEnabled();
  await expect(page.locator('#local-authorization')).toContainText('executed');
  await approvals.click();await expect(approvals).toHaveCount(0);
  expect(requests.filter(r=>r.path.startsWith('/api/approvals/')).map(r=>r.path)).toEqual(['/api/approvals/action-1','/api/approvals/action-2']);
  await expect(page.locator('#local-authorization pre')).toHaveCount(2);
});

test('comparison uses the explicit spend contract and can be cancelled', async ({page}) => {
  const requests = await localPage(page,true);
  await expect(page.getByLabel('Maximum comparison cost (USD)',{exact:true})).toHaveValue('1.00');
  await expect(page.getByLabel('Maximum job cost (USD)',{exact:true})).toHaveValue('0.05');
  await expect(page.getByLabel('Session spending limit (USD)',{exact:true})).toHaveValue('1.00');
  await expect(page.getByLabel('Local ticket message',{exact:true})).toHaveAttribute('maxlength','8000');
  await page.getByText('Data preview and execution limits',{exact:true}).click();
  const preview=JSON.parse(await page.locator('#local-workspace details').first().locator('pre').innerText());
  expect(preview).toMatchObject({ticket_max_cost_usd:'0.05',comparison_max_cost_usd:'1.00',pricing:{id:'gpt-6-luna',pricing_version:'mock-prices-v1',effective_date:'2026-10-28'}});
  await page.getByLabel('Save local recording').check();
  await page.getByRole('button',{name:'Run paired comparison',exact:true}).click();
  await expect(page.locator('#local-status')).toContainText('running');
  expect(requests[1].body).toMatchObject({kind:'comparison',record:true,confirm_spend:true,max_cost_usd:'1.00'});
  await expect(page.getByText(/9 development cases.*3 repeats/)).toBeVisible();
  await page.getByRole('button',{name:'Cancel local job',exact:true}).click();
  expect(requests.at(-1)?.path).toBe('/api/runs/mock-job/cancel');
});

test('disabled local runtime exposes status without spend controls', async ({page}) => {
  const requests=await localPage(page,false,false);
  await expect(page.getByRole('button',{name:'Run using my OpenAI key',exact:true})).toBeDisabled();
  expect(requests).toEqual([]);
});

test('invalid allowances cannot initiate a provider job',async ({page})=>{
  const requests=await localPage(page);
  for(const invalid of ['0','-1','NaN','1e3']){
    await page.getByLabel('Maximum job cost (USD)',{exact:true}).fill(invalid);
    await page.getByRole('button',{name:'Run using my OpenAI key',exact:true}).click();
    await expect(page.locator('#local-status')).toContainText('positive plain decimal');
  }
  expect(requests).toEqual([]);
});

test('job startup rejection is visible and cannot leave approval controls',async ({page})=>{
  await localPage(page);
  await page.route('**/api/runs',route=>route.fulfill({status:409,json:{detail:'Another run is active'}}));
  await page.getByRole('button',{name:'Run using my OpenAI key',exact:true}).click();
  await expect(page.locator('#local-status')).toContainText('Run not started');
  await expect(page.getByRole('button',{name:'Record local authorization',exact:true})).toHaveCount(0);
});

for (const width of [390,768,1440]) test(`local workspace keyboard and layout ${width}px`,async ({page},info)=>{
  await page.setViewportSize({width,height:900}); await localPage(page);
  const run=page.getByRole('button',{name:'Run using my OpenAI key',exact:true});
  await run.focus(); await expect(run).toBeFocused(); await page.keyboard.press('Enter');
  await expect(page.locator('#local-status')).toContainText('completed');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.screenshot({path:info.outputPath(`local-${width}.png`),fullPage:true});
});
