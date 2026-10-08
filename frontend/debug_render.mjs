import puppeteer from 'puppeteer';

async function verify() {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('[Console]', msg.type(), msg.text()));
  page.on('requestfailed', req => console.log('[ReqFailed]', req.url(), req.failure()?.errorText));
  page.on('response', res => {
    if (res.status() >= 400) {
      console.log('[HttpError]', res.status(), res.url());
    }
  });

  await page.goto('http://localhost:5174', { waitUntil: 'load' });
  await page.waitForSelector('.app-shell', { timeout: 5000 });
  await new Promise(r => setTimeout(r, 2000));

  await browser.close();
}

verify().catch(console.error);
