import puppeteer from 'puppeteer';
import path from 'path';

const ARTIFACTS_DIR = '/Users/ksruzanroy/.gemini/antigravity-ide/brain/7f73d383-81c0-45a1-89a2-fe0165842fb0';
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

async function run() {
  console.log('1. Launching browser...');
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--window-size=1400,1000'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 1000 });

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));

  // 1. Run History Page
  console.log('2. Navigating to Run History (http://127.0.0.1:5173)...');
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'history_desktop.png'), fullPage: true });
  console.log('Captured history_desktop.png');

  // 2. Open New Run Form
  console.log('3. Navigating to New Run page...');
  await page.evaluate(() => {
    const target = Array.from(document.querySelectorAll('button, a')).find(b => b.textContent.includes('New Simulation Run'));
    if (target) target.click();
  });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'new_run_desktop.png'), fullPage: true });
  console.log('Captured new_run_desktop.png');

  // Configure fast simulation for visual demonstration
  await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll('input'));
    const totalEventsInput = inputs.find(i => (i.previousElementSibling)?.textContent?.includes('Total Stream Events') || i.value === '2000');
    if (totalEventsInput) {
      totalEventsInput.value = '1000';
      totalEventsInput.dispatchEvent(new Event('input', { bubbles: true }));
      totalEventsInput.dispatchEvent(new Event('change', { bubbles: true }));
    }

    const pacingInput = inputs.find(i => (i.previousElementSibling)?.textContent?.includes('Clock Speed') || i.value === '100');
    if (pacingInput) {
      pacingInput.value = '250';
      pacingInput.dispatchEvent(new Event('input', { bubbles: true }));
      pacingInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });

  // 3. Submit Form
  console.log('4. Creating simulation run...');
  await page.evaluate(() => {
    const form = document.querySelector('form');
    if (form) form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
  await new Promise(r => setTimeout(r, 1200));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'live_run_created.png'), fullPage: true });
  console.log('Captured live_run_created.png');

  // 4. Click Start Stream
  console.log('5. Clicking Start Stream...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const startBtn = btns.find(b => b.textContent.includes('Start Stream'));
    if (startBtn) startBtn.click();
  });

  // Stream for 2 seconds
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'live_run_streaming.png'), fullPage: true });
  console.log('Captured live_run_streaming.png');

  // 5. Pause Stream
  console.log('6. Pausing stream...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const pauseBtn = btns.find(b => b.textContent.includes('Pause'));
    if (pauseBtn) pauseBtn.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'live_run_paused.png'), fullPage: true });
  console.log('Captured live_run_paused.png');

  // 6. Resume Stream
  console.log('7. Resuming stream...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const resumeBtn = btns.find(b => b.textContent.includes('Resume'));
    if (resumeBtn) resumeBtn.click();
  });

  // Wait for completion
  console.log('8. Waiting for stream completion...');
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 1000));
    const statusText = await page.evaluate(() => {
      const el = document.querySelector('.badge');
      return el ? el.textContent : '';
    });
    console.log('Live status at ' + i + 's:', statusText);
    if (statusText && (statusText.includes('COMPLETED') || statusText.includes('STOPPED'))) {
      break;
    }
  }

  await new Promise(r => setTimeout(r, 1500));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'live_run_completed.png'), fullPage: true });
  console.log('Captured live_run_completed.png');

  // 7. Test Incident Evidence Inspection Modal
  console.log('9. Opening Incident Evidence modal...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const evBtn = btns.find(b => b.textContent.includes('Evidence'));
    if (evBtn) evBtn.click();
  });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'live_run_evidence_modal.png'), fullPage: true });
  console.log('Captured live_run_evidence_modal.png');

  // 8. Mobile Viewport
  console.log('10. Capturing Mobile Viewport (390 x 844)...');
  await page.evaluate(() => {
    const closeBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Close'));
    if (closeBtn) closeBtn.click();
  });
  await new Promise(r => setTimeout(r, 500));
  await page.setViewport({ width: 390, height: 844 });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'live_run_mobile.png'), fullPage: true });
  console.log('Captured live_run_mobile.png');

  await browser.close();
  console.log('All E2E checks passed and screenshots generated!');
}

run().catch(err => {
  console.error('E2E runner error:', err);
  process.exit(1);
});
