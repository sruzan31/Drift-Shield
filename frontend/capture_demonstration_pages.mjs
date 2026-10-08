import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';

const SCREENSHOT_DIR = path.resolve(process.cwd(), '../docs/screenshots/frontend_reference_match');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const RUN_ID = 'run-abrupt-42-replay-a0116c';

async function run() {
  console.log(`Starting page verification & screenshot capture for completed run ${RUN_ID}...`);
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  // 1. Overview Page
  console.log('[1/8] Verifying Overview...');
  await page.goto(`http://localhost:5173/overview?runId=${RUN_ID}`, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Model reliability, live'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01_overview_desktop.png'), fullPage: true });

  // 2. Connect a stream / New Run
  console.log('[2/8] Verifying New Run...');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const connectBtn = buttons.find(b => b.textContent.includes('Connect a stream') || b.textContent.includes('New Stream') || b.textContent.includes('New stream'));
    if (connectBtn) connectBtn.click();
  });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Connect a stream'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02_new_run_desktop.png'), fullPage: true });

  // 3. Live Monitor Page (Completed)
  console.log('[3/8] Verifying Live Monitor...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Live monitor'));
    if (item) item.click();
  });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Stream'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03_live_run_created_desktop.png'), fullPage: true });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'live_run_completed.png'), fullPage: true });

  // 4. Incidents Page
  console.log('[4/8] Verifying Incidents...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Incidents'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08_incidents_desktop.png'), fullPage: true });

  // Click Evidence Tab in Incidents
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const evBtn = buttons.find(b => b.textContent.includes('Evidence') || b.textContent.includes('Raw evidence'));
    if (evBtn) evBtn.click();
  });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08b_incidents_evidence_desktop.png'), fullPage: true });

  // 5. Insights Page
  console.log('[5/8] Verifying Insights...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Insights'));
    if (item) item.click();
  });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Prediction risk & stream health'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09_insights_desktop.png'), fullPage: true });

  // 6. Actions Page
  console.log('[6/8] Verifying Actions...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Actions'));
    if (item) item.click();
  });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Review model promotion'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '10_actions_desktop.png'), fullPage: true });

  // 7. Streams / Run History Page
  console.log('[7/8] Verifying Streams Ledger...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.trim().startsWith('Streams'));
    if (item) item.click();
  });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Streams & simulation runs'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07_run_history_desktop.png'), fullPage: true });

  // 8. Reports Page
  console.log('[8/8] Verifying Reports...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.trim().startsWith('Reports'));
    if (item) item.click();
  });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Runs, incidents & reports'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '11_reports_desktop.png'), fullPage: true });

  // 9. Theory Lab Page
  console.log('Verifying Theory Lab...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Theory Lab'));
    if (item) item.click();
  });
  await page.waitForFunction(() => document.querySelector('h1')?.textContent?.includes('Theory Lab'));
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06_theory_lab_desktop.png'), fullPage: true });

  console.log('All verification screenshots captured successfully.');
  await browser.close();
}

run().catch((err) => {
  console.error('Fatal error during capture:', err);
  process.exit(1);
});
