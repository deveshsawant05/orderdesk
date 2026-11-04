import {test, expect, Page, BrowserContext} from '@playwright/test';
import fs from 'node:fs';

const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8010';
const headers = {'X-OrderDesk':'1','X-OrderDesk-Experience':'staff'};

async function signIn(context: BrowserContext, email: string) {
  const result = await context.request.post(api+'/auth/login', {
    headers, data:{email,password:process.env.DEMO_PASSWORD},
  });
  expect(result.status()).toBe(200);
}

async function chooseLocation(page: Page, area = 'kondapur') {
  await page.getByRole('button',{name:/Where shall we bring your food|Choose delivery point/}).click();
  await page.getByLabel('Try a demo delivery point').selectOption(area);
  await page.getByRole('button',{name:'Confirm location'}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
}

async function addChicken(page: Page) {
  await page.getByRole('button',{name:'Customize Chicken dum biryani',exact:true}).click();
  await page.getByRole('radio',{name:/Family pack/}).check();
  await page.getByRole('checkbox',{name:/Extra raita/}).check();
  await page.getByRole('button',{name:/Add to bag/}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
}

async function openPayment(page: Page, phone = '6000000000') {
  await page.getByLabel('Your name').fill('Synthetic Guest');
  await page.getByLabel('Indian mobile number').fill(phone);
  await page.getByRole('button',{name:'Continue to test payment'}).click();
  await expect(page.getByRole('dialog',{name:'Test payment'})).toBeVisible();
}

test('guest test payment routes to manager, kitchen and secure SSE tracker',async ({browser,page}) => {
  const managerContext = await browser.newContext();
  const kitchenContext = await browser.newContext({viewport:{width:1024,height:768}});
  const otherContext = await browser.newContext();
  await signIn(managerContext,'manager.kondapur@orderdesk.demo');
  await signIn(kitchenContext,'kitchen.kondapur@orderdesk.demo');
  await signIn(otherContext,'manager.kukatpally@orderdesk.demo');
  const manager = await managerContext.newPage();
  const kitchen = await kitchenContext.newPage();
  const other = await otherContext.newPage();
  await Promise.all([manager.goto('/ops/orders'), kitchen.goto('/ops/kitchen'), other.goto('/ops/orders')]);
  for (const view of [manager,kitchen,other]) await expect(view.getByText('Live connection',{exact:true})).toBeVisible();

  await page.goto('/');
  await expect(page.locator('.food-card')).toHaveCount(6);
  await page.screenshot({path:'../artifacts/menu-desktop.png'});
  await addChicken(page);
  await expect(page.locator('.bag-button b')).toHaveText('1');
  await page.goto('/checkout');
  await chooseLocation(page);
  await expect(page.getByText('₹940',{exact:true}).first()).toBeVisible();
  await openPayment(page);
  await page.getByRole('button',{name:'Simulate successful payment'}).click();
  await expect(page.getByRole('heading',{name:'Your order is awaiting acceptance.'})).toBeVisible();
  const ref = (await page.locator('.tracking-hero .eyebrow').innerText()).split(' · ')[0];
  const token = page.url().split('/').pop()!;
  expect(token).not.toContain(ref);
  const ticket = kitchen.locator(`[data-order-id="${ref}"]`);
  await expect(ticket.getByText('Manager acceptance required')).toBeVisible();
  await expect(other.getByText(ref,{exact:true})).toHaveCount(0);
  const forbidden = await otherContext.request.get(api+'/orders/'+ref,{headers});
  expect(forbidden.status()).toBe(403);
  expect((await page.request.get(api+'/tracking/'+ref+'/events')).status()).toBe(404);
  await manager.getByRole('button',{name:new RegExp(ref)}).click();
  await manager.screenshot({path:'../artifacts/control-room-desktop.png'});
  await manager.getByRole('button',{name:'Accept & Start Preparing'}).click();
  await expect(page.getByRole('heading',{name:'A little magic in the kitchen.'})).toBeVisible();
  await manager.getByRole('button',{name:'Add five minutes'}).click();
  await manager.getByLabel('Reason for the customer').fill('Fresh dum finishing needs more time.');
  await manager.getByRole('button',{name:'Save revised ready time'}).click();
  await expect(page.getByText(/Kitchen revision:/)).toBeVisible();
  await kitchen.screenshot({path:'../artifacts/kitchen-tablet.png'});
  await ticket.getByRole('button',{name:'Mark ready'}).click();
  await expect(page.getByRole('heading',{name:'Packed with care. Ready to go.'})).toBeVisible();
  await page.screenshot({path:'../artifacts/tracking-desktop.png'});
  const ready = await (await page.request.get(api+'/tracking/'+token)).json();
  const cursor = ready.events.at(-1).id;
  await ticket.getByRole('button',{name:'Confirm handoff'}).click();
  const replay = await fetch(api+'/tracking/'+token+'/events',{
    headers:{'Last-Event-ID':String(cursor)},signal:AbortSignal.timeout(6000),
  });
  expect(replay.ok).toBeTruthy();
  const stream = replay.body!.getReader();
  let received = '';
  try {
    while (!received.includes('order.handed_off')) {
      const chunk = await stream.read();
      if (chunk.done) break;
      received += new TextDecoder().decode(chunk.value);
    }
    expect(received).toContain('order.handed_off');
    expect(received).toContain(ref);
    expect(received).not.toContain('order.ready');
  } finally {
    await stream.cancel();
  }
  await expect(page.getByRole('heading',{name:'Handed to the delivery partner.'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading',{name:'Handed to the delivery partner.'})).toBeVisible();
  fs.writeFileSync('../artifacts/verified-order.json',JSON.stringify({ref}));
  await Promise.all([managerContext.close(),kitchenContext.close(),otherContext.close()]);
});

test('outlet stock SSE flags a customer bag and CMS edits propagate',async ({browser,page,context}) => {
  await signIn(context,'admin@orderdesk.demo');
  await page.goto('/ops/menu');
  await page.getByLabel('Availability at').selectOption('kondapur');
  const customer = await browser.newContext();
  const menu = await customer.newPage();
  await menu.goto('/');
  await chooseLocation(menu);
  await addChicken(menu);
  const chicken = page.locator('.cms-row').filter({hasText:'Chicken dum biryani'});
  const restore = chicken.getByRole('button',{name:'Sold out',exact:true});
  try {
    await chicken.getByRole('button',{name:'In stock',exact:true}).click();
    await expect(menu.getByRole('button',{name:'Customize Chicken dum biryani'})).toBeDisabled({timeout:6000});
    await expect(menu.locator('.bag-preview')).toContainText('currently unavailable');
    await expect(menu.locator('.bag-button b')).toHaveText('1');
    await page.reload();
    await expect(restore).toBeVisible();
    await page.screenshot({path:'../artifacts/cms-desktop.png'});
  } finally {
    if (await restore.isVisible()) await restore.click();
  }

  const dessert = page.locator('.cms-row').filter({hasText:'Double ka meetha'});
  await dessert.getByRole('button',{name:'Edit Double ka meetha'}).click();
  const input = page.getByRole('textbox',{name:'Description',exact:true});
  const original = await input.inputValue();
  const updated = original+' Prepared with care.';
  try {
    await input.fill(updated);
    await page.getByRole('button',{name:'Save central menu changes'}).click();
    await expect(menu.getByText(updated,{exact:true})).toBeVisible({timeout:6000});
  } finally {
    await dessert.getByRole('button',{name:'Edit Double ka meetha'}).click();
    await page.getByRole('textbox',{name:'Description',exact:true}).fill(original);
    await page.getByRole('button',{name:'Save central menu changes'}).click();
  }
  await customer.close();
});

test('phone viewport, Card failure, retry and persisted bag',async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.locator('.food-card')).toHaveCount(6);
  await page.screenshot({path:'../artifacts/menu-mobile.png'});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await chooseLocation(page);
  await addChicken(page);
  await page.getByRole('link',{name:/View bag/}).click();
  await page.getByRole('button',{name:/Card/}).click();
  await openPayment(page,'6000000001');
  await page.getByRole('button',{name:'Simulate payment failure'}).click();
  await expect(page.getByText(/Payment failed/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading',{name:'Chicken dum biryani',exact:true})).toBeVisible();
  await page.getByRole('button',{name:/Card/}).click();
  await openPayment(page,'6000000001');
  await page.getByRole('button',{name:'Simulate successful payment'}).click();
  await expect(page.getByRole('heading',{name:'Your order is awaiting acceptance.'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'../artifacts/tracking-mobile.png',fullPage:true});
});

test('unreachable menu API has a recoverable error state',async ({page}) => {
  await page.route(api+'/menu**',route => route.abort());
  await page.goto('/');
  await expect(page.locator('.error[role=alert]')).toContainText('Cannot reach OrderDesk');
  await expect(page.getByRole('button',{name:'Customize Chicken dum biryani'})).toBeVisible();
});


test('party form and manager confirmation update the customer and kitchen',async ({browser,page}) => {
  const managerContext = await browser.newContext();
  const kitchenContext = await browser.newContext();
  await signIn(managerContext,'manager.kondapur@orderdesk.demo');
  await signIn(kitchenContext,'kitchen.kondapur@orderdesk.demo');
  const manager = await managerContext.newPage();
  const kitchen = await kitchenContext.newPage();
  await manager.goto('/ops/orders');
  await manager.getByRole('button',{name:'Party requests'}).click();
  await kitchen.goto('/ops/kitchen');
  await expect(kitchen.getByText('Live connection',{exact:true})).toBeVisible();

  await page.goto('/party');
  const contact = 'Synthetic Party '+Date.now();
  await page.getByLabel('Your name').fill(contact);
  await page.getByLabel('Indian mobile number').fill('6000000002');
  const desired = new Date(Date.now()+4*86400000+19800000).toISOString().slice(0,16);
  await page.getByLabel(/Requested date and time/).fill(desired);
  await chooseLocation(page);
  await page.getByLabel('Chicken dum biryani quantity').fill('14');
  await page.getByRole('button',{name:'Request confirmation'}).click();
  await expect(page.getByRole('heading',{name:'Awaiting confirmation.'})).toBeVisible();
  const record = manager.locator('.party-record').filter({hasText:contact});
  await expect(record).toBeVisible();
  const previous = await kitchenContext.request.get(api+'/staff/party?outlet_id=kondapur',{headers});
  const matches = (await previous.json()).filter((entry:{items:{quantity:number;name:string}[]}) => entry.items.some(line => line.quantity===14 && line.name==='Chicken dum biryani')).length;
  const ticket = kitchen.getByText('14 × Chicken dum biryani',{exact:true});
  await expect(ticket).toHaveCount(matches);
  await record.getByLabel('Message to customer').fill('Capacity confirmed for your gathering.');
  await record.getByRole('button',{name:'Record decision'}).click();
  await expect(page.getByRole('heading',{name:'Your request is confirmed.'})).toBeVisible();
  await expect(ticket).toHaveCount(matches+1);
  await manager.getByRole('button',{name:'Reporting'}).click();
  await expect(manager.getByText('Median prep · acceptance to ready')).toBeVisible();
  await Promise.all([managerContext.close(),kitchenContext.close()]);
});
