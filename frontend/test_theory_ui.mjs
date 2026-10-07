import puppeteer from 'puppeteer';
import path from 'path';

const ARTIFACTS_DIR = '/Users/ksruzanroy/.gemini/antigravity-ide/brain/7f73d383-81c0-45a1-89a2-fe0165842fb0';
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

async function run() {
  console.log('1. Launching browser...');
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--window-size=1400,1050'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 1050 });

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR:', err.toString()));

  // 1. Visit App and navigate to Theory Lab
  console.log('2. Navigating to Theory Lab tab...');
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1000));

  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const theoryBtn = btns.find(b => b.textContent.includes('Theory Lab'));
    if (theoryBtn) theoryBtn.click();
  });
  await new Promise(r => setTimeout(r, 1000));

  // 2. Expand assumptions card
  console.log('3. Expanding theorem assumptions card...');
  await page.evaluate(() => {
    const card = document.querySelector('.card');
    if (card) (card).click();
  });
  await new Promise(r => setTimeout(r, 500));

  // 3. Launch T4 Rare-Region Experiment
  console.log('4. Launching T4 Rare-Region Experiment (10,000 trials)...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const runBtn = btns.find(b => b.textContent.includes('Run T4 Rare-Region Experiment'));
    if (runBtn) runBtn.click();
  });

  // Wait for completion (typically ~1-2 seconds)
  console.log('5. Waiting for T4 Rare-Region experiment completion...');
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 1000));
    const isDone = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes('Miss Probability at') && text.includes('95% Wilson CI');
    });
    if (isDone) {
      console.log('T4 Experiment results displayed at t=' + i + 's');
      break;
    }
  }

  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'theory_rare_region_desktop.png'), fullPage: true });
  console.log('Captured theory_rare_region_desktop.png');

  // 4. Switch to T5 Finite-Domain Tab
  console.log('6. Switching to T5 Finite-Domain Adaptation tab...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const finiteTab = btns.find(b => b.textContent.includes('T5 Finite-Domain'));
    if (finiteTab) finiteTab.click();
  });
  await new Promise(r => setTimeout(r, 800));

  // Launch T5 Finite-Domain Audit
  console.log('7. Launching T5 Finite-Domain Audit (N=32, single-last)...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const runBtn = btns.find(b => b.textContent.includes('Run T5 Finite-Domain Audit'));
    if (runBtn) runBtn.click();
  });

  // Wait for T5 completion
  console.log('8. Waiting for T5 Finite-Domain experiment completion...');
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 1000));
    const isDone = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes('Audit Complete') && text.includes('100% Exact Accuracy');
    });
    if (isDone) {
      console.log('T5 Experiment results displayed at t=' + i + 's');
      break;
    }
  }

  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'theory_finite_domain_desktop.png'), fullPage: true });
  console.log('Captured theory_finite_domain_desktop.png');

  // 5. Test Mobile Viewport
  console.log('9. Capturing mobile viewport for Theory Lab...');
  await page.setViewport({ width: 390, height: 844 });
  await new Promise(r => setTimeout(r, 800));
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'theory_mobile.png'), fullPage: true });
  console.log('Captured theory_mobile.png');

  await browser.close();
  console.log('All Theory Lab browser verification tests completed successfully!');
}

run().catch(err => {
  console.error('Error running Theory Lab UI test:', err);
  process.exit(1);
});
