import puppeteer from 'puppeteer';

async function verifyAllTabs() {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(err.toString()));

  console.log('1. Loading Overview page...');
  await page.goto('http://localhost:5174', { waitUntil: 'load' });
  await page.waitForSelector('.app-shell');
  await new Promise(r => setTimeout(r, 2500));

  let overviewText = await page.evaluate(() => document.body.innerText);
  console.log('Overview preview:\n', overviewText.slice(0, 500));

  // Switch to Streams tab
  console.log('\n2. Navigating to Streams...');
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Streams'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));
  let streamsText = await page.evaluate(() => document.body.innerText);
  console.log('Streams preview:\n', streamsText.slice(0, 400));

  // Click on the latest run in streams list to select it
  await page.evaluate(() => {
    const runRow = Array.from(document.querySelectorAll('tr, button, div')).find(el => el.innerText && el.innerText.includes('run-abrupt-42-replay-6844fd'));
    if (runRow) runRow.click();
  });
  await new Promise(r => setTimeout(r, 1500));

  // Check Live Monitor
  console.log('\n3. Live Monitor tab:');
  let liveText = await page.evaluate(() => document.body.innerText);
  console.log(liveText.slice(0, 400));

  // Check Incidents
  console.log('\n4. Navigating to Incidents...');
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Incidents'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));
  let incidentsText = await page.evaluate(() => document.body.innerText);
  console.log(incidentsText.slice(0, 400));

  // Check Insights
  console.log('\n5. Navigating to Insights...');
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Insights'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));
  let insightsText = await page.evaluate(() => document.body.innerText);
  console.log(insightsText.slice(0, 400));

  // Check Actions
  console.log('\n6. Navigating to Actions...');
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Actions'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));
  let actionsText = await page.evaluate(() => document.body.innerText);
  console.log(actionsText.slice(0, 400));

  // Check Reports
  console.log('\n7. Navigating to Reports...');
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Reports'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1500));
  let reportsText = await page.evaluate(() => document.body.innerText);
  console.log(reportsText.slice(0, 400));

  console.log('\nConsole errors (excluding favicon):', consoleErrors.filter(e => !e.includes('favicon')));

  await browser.close();
}

verifyAllTabs().catch(console.error);
