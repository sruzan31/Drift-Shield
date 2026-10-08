import puppeteer from 'puppeteer';

async function testFetch() {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.goto('http://localhost:5174', { waitUntil: 'load' });
  const result = await page.evaluate(async () => {
    try {
      const res = await fetch('/health');
      const data = await res.json();
      return { status: res.status, ok: res.ok, data };
    } catch (e) {
      return { error: e.toString() };
    }
  });
  console.log('In-browser fetch(/health):', JSON.stringify(result));
  
  const runsRes = await page.evaluate(async () => {
    try {
      const res = await fetch('/api/runs?page=1&page_size=5');
      const data = await res.json();
      return { status: res.status, ok: res.ok, data };
    } catch (e) {
      return { error: e.toString() };
    }
  });
  console.log('In-browser fetch(/api/runs):', JSON.stringify(runsRes));

  await browser.close();
}
testFetch().catch(console.error);
