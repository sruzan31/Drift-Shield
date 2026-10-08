import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';

const SCREENSHOT_DIR = path.resolve(process.cwd(), '../docs/screenshots/frontend_reference_match');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function run() {
  console.log('Starting DriftShield Working Run Demonstration...');
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  // Listen for created run_id
  let createdRunId = null;
  page.on('response', async (res) => {
    if (res.url().includes('/api/runs') && res.request().method() === 'POST' && !res.url().includes('/control')) {
      try {
        const data = await res.json();
        if (data.run_id) {
          createdRunId = data.run_id;
          console.log('Intercepted newly created Run ID:', createdRunId);
        }
      } catch {}
    }
  });

  // 1. Navigate to DriftShield
  console.log('[1/8] Navigating to DriftShield Overview...');
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0' });

  // 2. Click "Connect a stream" to open New Run
  console.log('[2/8] Opening New Run wizard...');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const connectBtn = buttons.find(b => b.textContent.includes('Connect a stream') || b.textContent.includes('New Stream'));
    if (connectBtn) connectBtn.click();
  });
  await new Promise(r => setTimeout(r, 500));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02_new_run_desktop.png'), fullPage: true });

  // 3. Fill in exact specification configuration
  console.log('[3/8] Filling configuration form: abrupt, 10000 events, warmup 200, drift 1000, seed 42, rate 0.15, budget 2000, delay 0, train 200, eval 500, pacing 100...');
  await page.evaluate(() => {
    // Select scenario: abrupt
    const select = document.querySelector('select.form-select');
    if (select) {
      select.value = 'abrupt';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    const formGroups = Array.from(document.querySelectorAll('.form-group'));
    for (const group of formGroups) {
      const label = group.querySelector('.form-label')?.textContent?.toLowerCase() || '';
      const input = group.querySelector('input');
      if (!input) continue;

      if (label.includes('total events')) input.value = '10000';
      else if (label.includes('random seed')) input.value = '42';
      else if (label.includes('events / sec')) input.value = '100';
      else if (label.includes('drift start sequence')) input.value = '1000';
      else if (label.includes('random monitoring')) input.value = '15';
      else if (label.includes('training quota')) input.value = '200';
      else if (label.includes('total label budget')) input.value = '2000';
      else if (label.includes('label delay')) input.value = '0';

      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });

  // 4. Submit and start run
  console.log('[4/8] Submitting form and launching run...');
  await page.evaluate(() => {
    const submitBtn = document.querySelector('button[type="submit"]');
    if (submitBtn) submitBtn.click();
  });

  // Wait for transition to Live Run tab
  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03_live_run_created_desktop.png'), fullPage: true });

  if (!createdRunId) {
    const healthRes = await (await fetch('http://127.0.0.1:8000/api/health')).json();
    createdRunId = healthRes.active_run_id;
  }
  console.log('Active Run ID being monitored:', createdRunId);

  // 5. Monitor run progress
  console.log('[5/8] Monitoring execution across drift onset, alert, training, and evaluation...');
  let completed = false;
  let finalDetail = null;

  for (let i = 0; i < 200; i++) {
    await new Promise(r => setTimeout(r, 1000));
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/runs/${createdRunId}`);
      if (res.ok) {
        const detail = await res.json();
        finalDetail = detail;
        const processed = detail.events_processed;
        const candidateState = detail.candidate_state;
        const modelVer = detail.active_model_version;
        const err = detail.metrics?.full_synthetic?.error_rate ?? detail.metrics?.monitor_channel?.error_rate;
        const errStr = err != null ? (err * 100).toFixed(1) + '%' : 'N/A';
        const debits = detail.label_accounting?.budget_debits ?? 0;
        const alerts = detail.monitoring_summary?.alerts_count ?? 0;

        console.log(`[t=${i}s] Events: ${processed}/10000 | Alerts: ${alerts} | Candidate: ${candidateState} | Model: ${modelVer} | Error: ${errStr} | Debits: ${debits}`);

        if (processed >= 1500 && processed < 4000) {
          await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04_live_run_streaming_desktop.png'), fullPage: true });
        }

        if (detail.operational_state === 'COMPLETED' || processed >= 10000) {
          completed = true;
          console.log('Run execution reached completion!');
          break;
        }
      }
    } catch (err) {
      console.error('Poll error:', err.message);
    }
  }

  // Reload page to verify state hydration after completion
  console.log('Reloading page to verify completed state persistence...');
  await page.reload({ waitUntil: 'networkidle0' });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'live_run_completed.png'), fullPage: true });

  // 6. Verify and screenshot Overview
  console.log('[6/8] Capturing Overview page...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Overview'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01_overview_desktop.png'), fullPage: true });

  // 7. Verify and screenshot Incidents
  console.log('[7/8] Capturing Incidents & Evidence...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Incidents'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08_incidents_desktop.png'), fullPage: true });

  // Click Evidence tab
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const evBtn = buttons.find(b => b.textContent.includes('Evidence') || b.textContent.includes('Raw evidence'));
    if (evBtn) evBtn.click();
  });
  await new Promise(r => setTimeout(r, 500));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08b_incidents_evidence_desktop.png'), fullPage: true });

  // Insights
  console.log('Capturing Insights...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Insights'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09_insights_desktop.png'), fullPage: true });

  // Actions
  console.log('Capturing Actions...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Actions'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '10_actions_desktop.png'), fullPage: true });

  // Streams / History
  console.log('Capturing Run History...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Streams'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07_run_history_desktop.png'), fullPage: true });

  // Reports
  console.log('Capturing Reports...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Reports'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '11_reports_desktop.png'), fullPage: true });

  // Theory Lab
  console.log('Capturing Theory Lab...');
  await page.evaluate(() => {
    const navs = Array.from(document.querySelectorAll('.sidebar-nav-item'));
    const item = navs.find(n => n.textContent.includes('Theory Lab'));
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06_theory_lab_desktop.png'), fullPage: true });

  console.log('\n================ DEMONSTRATION SUMMARY ================');
  console.log('Run ID:', createdRunId);
  console.log('Operational State:', finalDetail?.operational_state);
  console.log('Events Processed:', finalDetail?.events_processed);
  console.log('Active Model Version:', finalDetail?.active_model_version);
  console.log('Candidate State:', finalDetail?.candidate_state);
  console.log('Unique Labels Acquired:', finalDetail?.label_accounting?.total_unique_acquisitions);
  console.log('Budget Debits:', finalDetail?.label_accounting?.budget_debits);
  console.log('Full Synthetic Error:', finalDetail?.metrics?.full_synthetic?.error_rate);
  console.log('Monitor Channel Error:', finalDetail?.metrics?.monitor_channel?.error_rate);
  console.log('Candidate Summary:', JSON.stringify(finalDetail?.candidate_summary));
  console.log('Paired Summary:', JSON.stringify(finalDetail?.paired_summary));
  console.log('=======================================================');

  await browser.close();
}

run().catch((err) => {
  console.error('Fatal error during demonstration:', err);
  process.exit(1);
});
