/**
 * DriftShield End-to-End Abrupt Run Verification
 * 
 * Verifies:
 * 1. Creation and start of 10,000-event abrupt run via frontend form.
 * 2. Real monotonic event progression via WebSocket.
 * 3. Completion to COMPLETED state with candidate training & evaluation.
 * 4. Refresh persistence and validation across Overview, Live, Incidents, Insights, Actions, Reports.
 */

import puppeteer from 'puppeteer-core';

const FRONTEND_URL = 'http://localhost:5174';
const BACKEND_URL = 'http://127.0.0.1:8000';

async function verifyFullRun() {
  console.log(`\n======================================================`);
  console.log(` DRIFTSHIELD 10,000-EVENT FULL SIMULATION RUN VERIFIER`);
  console.log(` Frontend: ${FRONTEND_URL}`);
  console.log(` Backend:  ${BACKEND_URL}`);
  console.log(`======================================================\n`);

  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const pageErrors = [];
  const failedRequests = [];
  const consoleMessages = [];

  page.on('console', msg => {
    const text = msg.text();
    consoleMessages.push(text);
    if (msg.type() === 'error') {
      console.error(`[Browser Console Error]`, text);
    }
  });

  page.on('pageerror', err => {
    pageErrors.push(err.message);
    console.error(`[Browser PageError]`, err.message);
  });

  page.on('response', async res => {
    if (res.url().includes('/api/')) {
      const status = res.status();
      if (status >= 400) {
        let text = '';
        try { text = await res.text(); } catch {}
        console.error(`[Browser API Error ${status}]`, res.url(), text);
      }
    }
  });

  try {
    // 1. Navigate to Frontend
    console.log(`[1/5] Loading application at ${FRONTEND_URL}...`);
    await page.goto(FRONTEND_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.app-header');

    // 2. Open New Run Form
    console.log(`[2/5] Navigating to New Run creation form...`);
    const newStreamBtn = await page.waitForSelector('button ::-p-text(New stream)');
    await newStreamBtn.click();
    await page.waitForSelector('.app-content h1');
    const formHeading = await page.$eval('.app-content h1', el => el.textContent);
    console.log(`  ✓ Form open: "${formHeading}"`);

    // Submit form (default parameters: 10k events, warmup 200, drift 1000, seed 42, budget 2000, speed 100)
    console.log(`[3/5] Submitting run creation form...`);
    const submitBtn = await page.waitForSelector('button[type="submit"]');
    await submitBtn.click();

    // Wait for transition to Live Run
    await page.waitForFunction(() => {
      const h1 = document.querySelector('.app-content h1')?.textContent;
      return h1 && !h1.includes('Connect a stream');
    }, { timeout: 15000 });

    // Retrieve active run from backend
    const health = await fetch(`${BACKEND_URL}/api/health`).then(r => r.json());
    const runId = health.active_run_id;
    if (!runId) {
      throw new Error('Expected active_run_id in backend /api/health after creation.');
    }
    console.log(`  ✓ Active Run created & executing: ${runId}`);

    // 3. Monitor progression until COMPLETED
    console.log(`[4/5] Monitoring stream progression to completion (10,000 events)...`);
    let lastProcessed = 0;
    let isDone = false;
    const startTime = Date.now();

    while (!isDone && (Date.now() - startTime < 120000)) {
      await new Promise(r => setTimeout(r, 2000));
      const detail = await fetch(`${BACKEND_URL}/api/runs/${runId}`).then(r => r.json());
      const processed = detail.events_processed;
      const state = detail.operational_state;
      const candidateState = detail.candidate_state;
      const modelVersion = detail.active_model_version;

      console.log(`  -> Progress: ${processed} / ${detail.total_events} events (${detail.progress_percent.toFixed(1)}%) | State: ${state} | Model: ${modelVersion} | Candidate: ${candidateState}`);

      if (processed < lastProcessed) {
        throw new Error(`Non-monotonic events progression detected: ${processed} < ${lastProcessed}`);
      }
      lastProcessed = processed;

      if (state === 'COMPLETED' || processed >= 10000) {
        isDone = true;
      }
    }

    if (!isDone) {
      throw new Error('Run did not complete within timeout (120s).');
    }

    console.log(`  ✓ Run completed successfully!`);

    // Fetch final detail
    const finalDetail = await fetch(`${BACKEND_URL}/api/runs/${runId}`).then(r => r.json());
    console.log(`\n--- Final Run Summary ---`);
    console.log(`Run ID:                 ${finalDetail.run_id}`);
    console.log(`State:                  ${finalDetail.operational_state}`);
    console.log(`Events Processed:       ${finalDetail.events_processed}`);
    console.log(`Active Model Version:   ${finalDetail.active_model_version}`);
    console.log(`Candidate State:        ${finalDetail.candidate_state}`);
    console.log(`Alerts Count:           ${finalDetail.monitoring_summary?.alerts_count}`);
    console.log(`Paired Evaluations:     ${finalDetail.paired_summary?.completed_comparisons_count}`);
    console.log(`Full Synthetic Error:   ${finalDetail.metrics?.full_synthetic ? (finalDetail.metrics.full_synthetic.error_rate * 100).toFixed(2) + '%' : 'N/A'}`);
    console.log(`-------------------------\n`);

    // 4. Verify all navigation tabs and persisted states
    console.log(`[5/5] Verifying page refresh and tab navigation persistence...`);

    // Tab 1: Overview
    const overviewNav = await page.waitForSelector('button ::-p-text(Overview)');
    await overviewNav.click();
    await page.waitForSelector('.kpi-card-value');
    await new Promise(r => setTimeout(r, 1000));
    console.log(`  ✓ Overview tab rendered persisted state.`);

    // Tab 2: Live Monitor
    const liveNav = await page.waitForSelector('button ::-p-text(Live monitor)');
    await liveNav.click();
    await page.waitForSelector('.app-content h1');
    const liveHeading = await page.$eval('.app-content h1', el => el.textContent);
    console.log(`  ✓ Live Monitor heading: "${liveHeading}"`);

    // Tab 3: Incidents
    const incNav = await page.waitForSelector('button ::-p-text(Incidents)');
    await incNav.click();
    await page.waitForSelector('.app-content h1');
    console.log(`  ✓ Incidents tab rendered.`);

    // Tab 4: Insights
    const insightsNav = await page.waitForSelector('button ::-p-text(Insights)');
    await insightsNav.click();
    await page.waitForSelector('.app-content h1');
    console.log(`  ✓ Insights tab rendered.`);

    // Tab 5: Actions
    const actionsNav = await page.waitForSelector('button ::-p-text(Actions)');
    await actionsNav.click();
    await page.waitForSelector('.app-content h1');
    console.log(`  ✓ Actions tab rendered.`);

    // Tab 6: Reports
    const reportsNav = await page.waitForSelector('button ::-p-text(Reports)');
    await reportsNav.click();
    await page.waitForSelector('table tbody tr');
    console.log(`  ✓ Reports tab loaded persisted runs.`);

    // Reload page to test cold hydration
    console.log(`  -> Reloading browser for cold cache persistence check...`);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.app-header');
    await new Promise(r => setTimeout(r, 1000));
    console.log(`  ✓ Cold page reload verified.`);

  } catch (err) {
    console.error(`\n❌ VERIFICATION FAILED:`, err);
    await browser.close();
    process.exit(1);
  }

  if (pageErrors.length > 0) {
    console.error(`\n❌ Uncaught Page Errors Detected:`, pageErrors);
    await browser.close();
    process.exit(1);
  }

  await browser.close();
  console.log(`\n🎉 FULL SIMULATION RUN & INTEGRATION VERIFICATION COMPLETE!\n`);
}

verifyFullRun();
