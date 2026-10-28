import { expect, test } from '@playwright/test';

test('the human approval boundary is visible in the first desktop screen', async ({page}) => {
  await page.setViewportSize({width:1440,height:900});
  await page.goto('./');
  const bounds = await page.getByRole('button', {name:'Simulate approval', exact:true}).boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.y + bounds!.height).toBeLessThan(850);
});

test('editing money clears authorization and changes the displayed decision', async ({page}) => {
  await page.goto('./');
  await page.getByRole('button', {name:'Simulate approval', exact:true}).click();
  await expect(page.getByRole('button', {name:'Authorization recorded · simulated'})).toBeDisabled();
  await page.locator('summary').click();
  await page.getByLabel('Shipping fee', {exact:true}).fill('15.00');
  await page.getByLabel('Shipping fee', {exact:true}).press('Tab');
  await expect(page.getByText('Proposed refund · BRL 94.90', {exact:true})).toBeVisible();
  await expect(page.getByRole('button', {name:'Simulate approval', exact:true})).toBeEnabled();
  await expect(page.getByRole('region', {name:'Synthetic customer reply'}).getByText('Localized template', {exact:true})).toBeVisible();
  await expect(page.getByText('The original replay trace was cleared', {exact:false})).toBeVisible();
});

test('all selects have stable accessible labels and localized presets load', async ({page}) => {
  await page.goto('./');
  await page.getByLabel('Ticket language', {exact:true}).selectOption('es');
  await expect(page.getByText('D-ES-01 · fictional ticket', {exact:true})).toBeVisible();
  await expect(page.getByText('Proposed refund · MXN 989.00', {exact:true})).toBeVisible();
  await page.locator('summary').click();
  await page.getByLabel('Currency', {exact:true}).selectOption('USD');
  await expect(page.locator('#decision-region').getByText('Human review required', {exact:true})).toBeVisible();
});

for (const lang of ['pt','es','en']) {
  test(`all eight ${lang} synthetic presets work after network is disabled`, async ({page,context}) => {
    const errors: string[] = [];
    const external: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (!request.url().startsWith('http://127.0.0.1:4177/')) external.push(request.url());});
    await page.goto('./');
    await context.setOffline(true);
    await page.getByLabel('Ticket language', {exact:true}).selectOption(lang);
    const outcomes = ['Eligible · approval required','Denied by policy','Human review required','Human review required',
      'Eligible · approval required','Human review required','Eligible · approval required','Eligible · approval required'];
    for (let index=0;index<8;index++) {
      await page.getByRole('button', {name: new RegExp(`^0${index+1} `)}).click();
      await expect(page.locator('#case-id')).toHaveText(`D-${lang.toUpperCase()}-0${index+1} · fictional ticket`);
      await expect(page.locator('#decision-region').getByText(outcomes[index],{exact:true})).toBeVisible();
      await expect(page.locator('#reply-body')).toHaveAttribute('lang',lang);
      if ([1,2,3,5].includes(index)) await expect(page.getByRole('button',{name:'Simulate approval',exact:true})).toHaveCount(0);
      if (index===6) await expect(page.getByRole('button',{name:'Simulate approval',exact:true})).toHaveCount(2);
    }
    expect(errors).toEqual([]); expect(external).toEqual([]);
  });
}

test('invalid edited facts hide the previous decision and approval controls', async ({page}) => {
  await page.goto('./');
  await page.getByRole('button',{name:'Simulate approval',exact:true}).click();
  await page.locator('summary').click();
  await page.getByLabel('Delivery date',{exact:true}).fill('2026-11-03');
  await expect(page.locator('#decision-region').getByText('Check the fictional inputs',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Simulate approval',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Authorization recorded · simulated'})).toHaveCount(0);
  await expect(page.locator('#reply-body')).toHaveText('Correct the fictional inputs to preview a template reply.');
  await page.getByRole('button',{name:'Reset scenario',exact:true}).click();
  await expect(page.getByText('Proposed refund · BRL 94.80',{exact:true})).toBeVisible();
});

test('keyboard skip link and scenario controls work', async ({page}) => {
  await page.goto('./');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link',{name:'Skip to ticket'})).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#workbench')).toBeFocused();
  const language = page.getByLabel('Ticket language',{exact:true});
  await language.focus();
  await page.keyboard.press('e'); await page.keyboard.press('Enter');
  await page.getByRole('button',{name:/^03 Prompt injection/}).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#decision-region').getByText('Human review required',{exact:true})).toBeVisible();
});

test('edited shipping status displays the actual carrier fact without financial actions', async ({page}) => {
  await page.goto('./');
  await page.getByLabel('Ticket language',{exact:true}).selectOption('en');
  await page.locator('summary').click();
  await page.getByLabel('Request',{exact:true}).selectOption('shipping_status');
  await page.getByLabel('Claim',{exact:true}).selectOption('none');
  await expect(page.locator('#decision-region').getByText('Information only',{exact:true})).toBeVisible();
  await expect(page.locator('#reply-body')).toContainText('Carrier status: delivered.');
  await expect(page.getByRole('button',{name:'Simulate approval',exact:true})).toHaveCount(0);
});

for (const width of [390,768,1440]) {
  test(`responsive layout ${width}px and captured approval/refusal evidence`, async ({page},testInfo) => {
    await page.setViewportSize({width,height:900});
    await page.goto('./');
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    expect(overflow).toBe(false);
    await expect(page.getByText('Synthetic prototype.',{exact:true})).toBeVisible();
    await page.screenshot({path:testInfo.outputPath(`approval-${width}.png`),fullPage:true});
    await page.getByRole('button',{name:/^04 Another customer/}).click();
    await expect(page.locator('#decision-region').getByText('Human review required',{exact:true})).toBeVisible();
    await expect(page.locator('#reply-body')).not.toContainText('GN-1009');
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({path:testInfo.outputPath(`refusal-${width}.png`),fullPage:true});
  });
}
