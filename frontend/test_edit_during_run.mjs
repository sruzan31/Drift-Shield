import puppeteer from 'puppeteer';

async function testEditDuringRun() {
  console.log('=== STEP 1: Fetching initial backend PID and status ===');
  const backendRes = await fetch('http://127.0.0.1:8000/api/health').then(r => r.json());
  console.log('Backend health status:', backendRes);

  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();

  page.on('console', msg => {
    if (msg.type() === 'error') console.log('[Browser Error]', msg.text());
  });

  console.log('\n=== STEP 2: Creating and starting a fresh abrupt run via Frontend UI ===');
  await page.goto('http://localhost:5174', { waitUntil: 'load' });
  await page.waitForSelector('.app-shell');
  await new Promise(r => setTimeout(r, 1000));

  // Navigate to New Run form
  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Connect a stream') || b.innerText.includes('New stream'));
    if (btn) btn.click();
  });
  await new Promise(r => setTimeout(r, 1000));

  // Submit form for short verification run (1000 events)
  await page.evaluate(() => {
    const nEventsInput = document.querySelector('input[name="n_events"]') || Array.from(document.querySelectorAll('input')).find(i => i.value === '10000' || i.value === '2000');
    if (nEventsInput) {
      nEventsInput.value = '1000';
      nEventsInput.dispatchEvent(new Event('input', { bubbles: true }));
    }
    const submitBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Connect stream') || b.innerText.includes('Start stream'));
    if (submitBtn) submitBtn.click();
  });
  await new Promise(r => setTimeout(r, 2000));

  const pageText = await page.evaluate(() => document.body.innerText);
  console.log('Page state after submission:', pageText.slice(0, 400));

  await browser.close();
}

testEditDuringRun().catch(console.error);
