/**
 * E2E Browser Test v2 — Architect 3D Generation
 * Uses Puppeteer-style approach with Playwright
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SITE_URL = process.argv[2] || 'http://localhost:8080/';
const SCREENSHOTS_DIR = path.join(__dirname, '..', 'screenshots');

const TEST_CASES = [
  { prompt: 'двухэтажный кирпичный дом 10×12 с балконом', expect: { floors: 2 } },
  { prompt: 'офис 5 этажей стекло 20×24', expect: { floors: 5 } },
  { prompt: 'деревянный коттедж 2 этажа с террасой 12×15', expect: { floors: 2 } },
];

async function main() {
  const tc = TEST_CASES[Math.floor(Math.random() * TEST_CASES.length)];
  console.log(`\n🏗️  E2E: "${tc.prompt}"\n`);

  if (!fs.existsSync(SCREENSHOTS_DIR)) fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  const browser = await chromium.launch({
    executablePath: '/tmp/chrome-linux64/chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--disable-web-security']
  });

  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  try {
    // 1. Load
    console.log('1️⃣  Loading...');
    await page.goto(SITE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01_loaded.png') });
    console.log('   ✅ Page loaded');

    // 2. Force local Three.js — disable backend calls
    await page.evaluate(() => {
      window._backendOk = false;
      window.callAI = async function() { throw new Error('skip LLM'); };
      window.generateViaBlenderServer = async function() { return false; };
      window.renderInteriorViaServer = async function() { return false; };
    });

    // 3. Type prompt
    console.log('2️⃣  Typing...');
    await page.fill('#ci', tc.prompt);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02_typed.png') });

    // 4. Send
    console.log('3️⃣  Sending...');
    await page.click('button.sbtn:last-of-type'); // ➤ button
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03_sending.png') });

    // 5. Wait for gen overlay to appear then disappear
    console.log('4️⃣  Waiting for 3D model...');
    // Wait for genov to show (generation started)
    await page.waitForTimeout(1000);
    // Wait for genov to hide (generation complete) — max 60s
    for (let i = 0; i < 60; i++) {
      const genovHidden = await page.evaluate(() => {
        const el = document.getElementById('genov');
        return !el || getComputedStyle(el).display === 'none';
      });
      if (genovHidden) break;
      await page.waitForTimeout(1000);
      if (i % 10 === 9) console.log(`   ⏳ ${i+1}s...`);
    }
    await page.waitForTimeout(2000); // Extra settle time
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04_generated.png') });
    console.log('   ✅ Generation phase complete');

    // 6. Check results
    console.log('5️⃣  Analyzing...');
    const r = await page.evaluate(() => {
      const out = { chatMsgs: [], canvasOk: false, modelOk: false, meshes: 0, bld: null };
      document.querySelectorAll('.bub').forEach(b => out.chatMsgs.push(b.textContent.trim().substring(0, 150)));
      const c = document.getElementById('c3d');
      out.canvasOk = c && c.style.display !== 'none';
      if (typeof ST !== 'undefined' && ST.hasModel && ST.bld) {
        out.modelOk = true;
        out.bld = { label: ST.bld.label, floors: ST.bld.floors, W: ST.bld.W, L: ST.bld.L, mat: ST.bld.mat };
      }
      if (typeof bG !== 'undefined' && bG) {
        bG.traverse(o => { if (o.isMesh) out.meshes++; });
      }
      return out;
    });

    console.log(`   Canvas: ${r.canvasOk}`);
    console.log(`   Model: ${r.modelOk}`);
    console.log(`   Meshes: ${r.meshes}`);
    if (r.bld) console.log(`   Building: ${r.bld.label}, ${r.bld.floors}fl, ${r.bld.W}×${r.bld.L}m, ${r.bld.mat}`);
    console.log(`   Chat: ${r.chatMsgs.length} messages`);
    r.chatMsgs.forEach((m, i) => console.log(`     [${i}] ${m.substring(0, 100)}`));

    // 7. Zoom in
    await page.evaluate(() => { if (typeof radius !== 'undefined') { radius = 20; updCam(); } });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '05_closeup.png') });

    // 8. Interior
    await page.evaluate(() => { if (typeof enterInterior === 'function' && typeof ST !== 'undefined' && ST.hasModel) enterInterior(); });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '06_interior.png') });
    console.log('   📸 Screenshots saved');

    // 9. Verify
    console.log('\n🔍 Checks:');
    const checks = {
      'Page loads': true,
      'No critical JS errors': !errors.some(e => !e.includes('export') && !e.includes('ResizeObserver')),
      'Chat has messages': r.chatMsgs.length >= 2,
      'Canvas visible': r.canvasOk,
      '3D model loaded': r.modelOk,
      'Meshes > 5': r.meshes > 5,
    };
    if (tc.expect.floors && r.bld) checks[`Floors=${tc.expect.floors}`] = r.bld.floors === tc.expect.floors;

    let ok = true;
    for (const [k, v] of Object.entries(checks)) {
      console.log(`   ${v ? '✅' : '❌'} ${k}`);
      if (!v) ok = false;
    }

    // Save report
    fs.writeFileSync(path.join(SCREENSHOTS_DIR, 'report.json'), JSON.stringify({ prompt: tc.prompt, result: r, checks, ok }, null, 2));

    console.log(`\n${ok ? '✅ ALL CHECKS PASSED' : '❌ SOME CHECKS FAILED'}\n`);
    process.exit(ok ? 0 : 1);

  } catch (err) {
    console.error('❌ FAILED:', err.message);
    try { await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'error.png') }); } catch(e) {}
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
