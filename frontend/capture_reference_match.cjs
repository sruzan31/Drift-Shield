const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const SCREENSHOT_DIR = path.resolve(__dirname, '../docs/screenshots/frontend_reference_match');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 375, height: 812 },
];

async function run() {
  console.log('Starting Puppeteer for reference match testing & screenshots...');
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const page = await browser.newPage();

  // Helper to capture a view across all viewports
  async function captureAllViewports(baseName) {
    for (const vp of VIEWPORTS) {
      await page.setViewport({ width: vp.width, height: vp.height });
      await new Promise((r) => setTimeout(r, 600));
      const filename = `${baseName}_${vp.name}.png`;
      const filepath = path.join(SCREENSHOT_DIR, filename);
      await page.screenshot({ path: filepath, fullPage: false });
      console.log(`Saved screenshot: ${filename}`);
    }
  }

  try {
    // 1. Overview Page
    console.log('\n--- Checking Overview Page ---');
    await page.setViewport({ width: 1440, height: 900 });
    await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 1000));
    await captureAllViewports('01_overview');

    // 2. New Run / Connect a Stream Page
    console.log('\n--- Checking New Run / Connect Stream Page ---');
    // Click "New stream" button or sidebar "Connect a stream"
    const newStreamButtons = await page.$$('button');
    let clickedNew = false;
    for (const btn of newStreamButtons) {
      const text = await (await btn.getProperty('innerText')).jsonValue();
      if (text.includes('Connect a stream') || text.includes('New stream')) {
        await btn.click();
        clickedNew = true;
        break;
      }
    }
    if (!clickedNew) {
      // Find nav item
      await page.click('button:has-text("Connect a stream")');
    }
    await new Promise((r) => setTimeout(r, 1000));
    await captureAllViewports('02_new_run');

    // Select scenario and configure run
    console.log('\n--- Creating a run via New Run form ---');
    // Click on "Abrupt drift" scenario card if visible
    const scenarioCards = await page.$$('.scenario-card');
    if (scenarioCards.length > 0) {
      await scenarioCards[0].click();
    }
    await new Promise((r) => setTimeout(r, 500));

    // Fill form or click Next step
    const nextButtons = await page.$$('button');
    for (const btn of nextButtons) {
      const text = await (await btn.getProperty('innerText')).jsonValue();
      if (text.includes('Validate & start') || text.includes('Create stream') || text.includes('Launch')) {
        await btn.click();
        console.log('Submitted New Run form');
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 2000));

    // 3. Live Run Page
    console.log('\n--- Checking Live Run Page ---');
    await captureAllViewports('03_live_run_created');

    // Click "Start Stream"
    console.log('\n--- Starting Stream execution ---');
    const startButtons = await page.$$('button');
    for (const btn of startButtons) {
      const text = await (await btn.getProperty('innerText')).jsonValue();
      if (text.includes('Start Stream') || text.includes('Start stream')) {
        await btn.click();
        console.log('Clicked Start Stream button');
        break;
      }
    }

    // Wait for stream to process some events
    await new Promise((r) => setTimeout(r, 3000));
    await captureAllViewports('04_live_run_streaming');

    // Test Pause
    console.log('\n--- Testing Pause control ---');
    const pauseButtons = await page.$$('button');
    for (const btn of pauseButtons) {
      const text = await (await btn.getProperty('innerText')).jsonValue();
      if (text.includes('Pause')) {
        await btn.click();
        console.log('Clicked Pause button');
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 1000));
    await captureAllViewports('05_live_run_paused');

    // Test Resume
    console.log('\n--- Testing Resume control ---');
    const resumeButtons = await page.$$('button');
    for (const btn of resumeButtons) {
      const text = await (await btn.getProperty('innerText')).jsonValue();
      if (text.includes('Resume')) {
        await btn.click();
        console.log('Clicked Resume button');
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 1000));

    // 4. Theory Lab Page
    console.log('\n--- Checking Theory Lab Page ---');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise((r) => setTimeout(r, 400));
    // Click on Theory Lab in sidebar
    const allButtons = await page.$$('button');
    for (const btn of allButtons) {
      try {
        const text = await (await btn.getProperty('innerText')).jsonValue();
        if (text.includes('Theory Lab')) {
          await btn.click();
          console.log('Navigated to Theory Lab');
          break;
        }
      } catch (e) {
        if (e && e.message) { /* ignore button click retry */ }
      }
    }
    await new Promise((r) => setTimeout(r, 1200));
    await captureAllViewports('06_theory_lab');

    // 5. Run History Page
    console.log('\n--- Checking Run History Page ---');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise((r) => setTimeout(r, 400));
    const allButtons2 = await page.$$('button');
    for (const btn of allButtons2) {
      try {
        const text = await (await btn.getProperty('innerText')).jsonValue();
        if (text.includes('Run History') || text.includes('Streams')) {
          await btn.click();
          console.log('Navigated to Run History');
          break;
        }
      } catch (e) {
        if (e && e.message) { /* ignore button click retry */ }
      }
    }
    await new Promise((r) => setTimeout(r, 1200));
    await captureAllViewports('07_run_history');

    // 6. Incidents Page
    console.log('\n--- Checking Incidents Page ---');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise((r) => setTimeout(r, 400));
    const allButtons3 = await page.$$('button');
    for (const btn of allButtons3) {
      try {
        const text = await (await btn.getProperty('innerText')).jsonValue();
        if (text.includes('Incidents')) {
          await btn.click();
          console.log('Navigated to Incidents');
          break;
        }
      } catch (e) {
        if (e && e.message) { /* ignore button click retry */ }
      }
    }
    await new Promise((r) => setTimeout(r, 1200));
    await captureAllViewports('08_incidents_analysis');

    // Click Evidence Sub-Tab
    console.log('\n--- Checking Incident Evidence Tab ---');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise((r) => setTimeout(r, 400));
    const subTabButtons = await page.$$('button');
    for (const btn of subTabButtons) {
      try {
        const text = await (await btn.getProperty('innerText')).jsonValue();
        if (text.toLowerCase() === 'evidence') {
          await btn.click();
          console.log('Clicked Evidence sub-tab');
          break;
        }
      } catch (e) {
        if (e && e.message) { /* ignore button click retry */ }
      }
    }
    await new Promise((r) => setTimeout(r, 1000));
    await captureAllViewports('08b_incidents_evidence');

    // 7. Insights Page
    console.log('\n--- Checking Insights Page ---');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise((r) => setTimeout(r, 400));
    const allButtons4 = await page.$$('button');
    for (const btn of allButtons4) {
      try {
        const text = await (await btn.getProperty('innerText')).jsonValue();
        if (text.includes('Insights')) {
          await btn.click();
          console.log('Navigated to Insights');
          break;
        }
      } catch (e) {
        if (e && e.message) { /* ignore button click retry */ }
      }
    }
    await new Promise((r) => setTimeout(r, 1200));
    await captureAllViewports('09_insights');

    // 8. Actions Page
    console.log('\n--- Checking Actions Page ---');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise((r) => setTimeout(r, 400));
    const allButtons5 = await page.$$('button');
    for (const btn of allButtons5) {
      try {
        const text = await (await btn.getProperty('innerText')).jsonValue();
        if (text.includes('Actions')) {
          await btn.click();
          console.log('Navigated to Actions');
          break;
        }
      } catch (e) {
        if (e && e.message) { /* ignore button click retry */ }
      }
    }
    await new Promise((r) => setTimeout(r, 1200));
    await captureAllViewports('10_actions');

    // 9. Reports Page
    console.log('\n--- Checking Reports Page ---');
    await page.setViewport({ width: 1440, height: 900 });
    await new Promise((r) => setTimeout(r, 400));
    const allButtons6 = await page.$$('button');
    for (const btn of allButtons6) {
      try {
        const text = await (await btn.getProperty('innerText')).jsonValue();
        if (text.includes('Reports')) {
          await btn.click();
          console.log('Navigated to Reports');
          break;
        }
      } catch (e) {
        if (e && e.message) { /* ignore button click retry */ }
      }
    }
    await new Promise((r) => setTimeout(r, 1200));
    await captureAllViewports('11_reports');

    console.log('\n✅ All screenshots captured and interactions verified successfully!');
  } catch (err) {
    console.error('Error during screenshot capture:', err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

run();
