import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';

const ARTIFACTS_DIR = '/Users/ksruzanroy/.gemini/antigravity-ide/brain/7f73d383-81c0-45a1-89a2-fe0165842fb0';

async function run() {
  console.log('1. Launching browser for Phase 7A UI verification...');
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.error('PAGE ERROR:', err.message));

  console.log('2. Navigating to DriftShield UI...');
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0' });

  // Click "New Run" tab
  console.log('Navigating to New Run tab...');
  const navButtons = await page.$$('header nav button');
  // Second button is New Run
  await navButtons[1].click();
  await page.waitForSelector('select#scenario');

  // 1. Verify scenario select has all 6 options
  const options = await page.$$eval('select#scenario option', opts => opts.map(o => o.value));
  console.log('Available scenario options:', options);
  const expectedScenarios = ['stationary', 'abrupt', 'gradual', 'recurring', 'rare_region', 'adversary'];
  for (const exp of expectedScenarios) {
    if (!options.includes(exp)) {
      throw new Error(`Missing scenario option: ${exp}`);
    }
  }

  // 2. Test scenario-specific parameter inputs
  console.log('3. Testing gradual scenario inputs...');
  await page.select('select#scenario', 'gradual');
  await page.waitForSelector('input#gradual_window');
  await page.$eval('input#gradual_window', el => el.value = '350');

  console.log('4. Testing recurring scenario inputs...');
  await page.select('select#scenario', 'recurring');
  await page.waitForSelector('input#recurrence_interval');
  await page.$eval('input#recurrence_interval', el => el.value = '450');

  console.log('5. Testing rare_region scenario inputs...');
  await page.select('select#scenario', 'rare_region');
  await page.waitForSelector('input#rare_region_p');
  await page.$eval('input#rare_region_p', el => el.value = '0.04');

  console.log('6. Testing adversary scenario inputs...');
  await page.select('select#scenario', 'adversary');
  await page.waitForSelector('input#adversary_dwell');
  await page.$eval('input#adversary_dwell', el => el.value = '250');

  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'new_run_scenarios_verified.png') });
  console.log('Captured new_run_scenarios_verified.png');

  // 7. Submit a new abrupt run
  console.log('7. Creating and starting a practical run end-to-end...');
  await page.select('select#scenario', 'abrupt');

  await page.evaluate(() => {
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) {
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeSetter.call(el, val);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    };
    setVal('n_events', '600');
    setVal('drift_start_sequence', '250');
    setVal('warmup_size', '100');
    setVal('label_budget', '400');
  });

  console.log('Checking form validity and submitting...');
  const validity = await page.evaluate(() => {
    const form = document.querySelector('form');
    if (!form) return { hasForm: false };
    const isValid = form.checkValidity();
    const invalidInputs = Array.from(form.querySelectorAll(':invalid')).map(el => ({
      id: el.id,
      name: el.name,
      validationMessage: el.validationMessage,
    }));
    return { hasForm: true, isValid, invalidInputs };
  });
  console.log('Form validity status:', validity);

  await page.evaluate(() => {
    const form = document.querySelector('form');
    if (form) form.requestSubmit();
  });

  try {
    console.log('Submitted run form, waiting for Live Run view...');
    await page.waitForSelector('button#btn-start-stream', { timeout: 10000 });
  } catch (err) {
    const errorText = await page.evaluate(() => document.body.innerText);
    console.log('DOM text on failure:\n', errorText);
    await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'failure_debug.png') });
    throw err;
  }

  // 8. Start the run
  await page.click('button#btn-start-stream');
  console.log('Started run execution.');

  // 9. Wait for run completion via WebSocket
  console.log('Waiting for run completion...');
  await page.waitForFunction(
    () => {
      const badges = Array.from(document.querySelectorAll('.badge, .badge-status'));
      return badges.some(b => b.textContent?.includes('COMPLETED'));
    },
    { timeout: 30000 }
  );
  console.log('Run reached COMPLETED state!');

  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'live_run_scenario_completed.png') });
  console.log('Captured live_run_scenario_completed.png');

  // 10. Check Run History
  console.log('10. Navigating to Run History...');
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('header nav button'));
    if (btns[0]) btns[0].click();
  });
  await page.waitForSelector('table');
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, 'run_history_scenario_completed.png') });
  console.log('Captured run_history_scenario_completed.png');

  console.log('All Phase 7A browser tests passed successfully!');
  await browser.close();
}

run().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
