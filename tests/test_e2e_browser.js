/**
 * E2E Browser Test v3 — Architect 3D Generation
 * Uses Playwright. Runs against local server or file://.
 *
 * Run:
 *   node tests/test_e2e_browser.js [URL]
 *   node tests/test_e2e_browser.js http://localhost:8080
 *   node tests/test_e2e_browser.js file://$(pwd)/index.html
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = process.env.CI ? require('path') : require('path');

const SITE_URL = process.argv[2] || process.env.SITE_URL || 'http://localhost:8080/';
const SCREENSHOTS_DIR = process.env.SCREENSHOTS_DIR || path.join(__dirname, '..', '.openclaw', 'tmp', 'test_screenshots');

const TEST_CASES = [
  { name: 'building', prompt: 'двухэтажный кирпичный дом 10×12 с балконом', expect: { floors: 2, type: 'building' } },
  { name: 'office', prompt: 'офис 5 этажей стекло 20×24', expect: { floors: 5, type: 'building' } },
  { name: 'cottage', prompt: 'деревянный коттедж 2 этажа с террасой 12×15', expect: { floors: 2, type: 'building' } },
  { name: 'interior_children', prompt: 'детская комната в классическом стиле', expect: { type: 'interior' } },
  { name: 'interior_bedroom', prompt: 'современная спальня 6x8 в стиле хайтек', expect: { type: 'interior' } },
];

async function runTest(tc, browser) {
  console.log(`\n${'─'.repeat(60)}`);
  console.log(`  🏗️  [${tc.name}] "${tc.prompt}"`);
  console.log('─'.repeat(60));

  if (!fs.existsSync(SCREENSHOTS_DIR)) fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  try {
    // 1. Load
    console.log('  1️⃣  Loading...');
    await page.goto(SITE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `${tc.name}_01_loaded.png`) });
    console.log('     ✅ Page loaded');

    // 2. Force local mode — disable backend calls
    await page.evaluate(() => {
      window._backendOk = false;
      window.callAI = async function() { throw new Error('skip LLM'); };
      window.generateViaBlenderServer = async function() { return false; };
      window.renderInteriorViaServer = async function() { return false; };
    });

    // 3. Type prompt
    console.log('  2️⃣  Typing...');
    await page.fill('#ci', tc.prompt);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `${tc.name}_02_typed.png`) });

    // 4. Send
    console.log('  3️⃣  Sending...');
    await page.click('button.sbtn:last-of-type');
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `${tc.name}_03_sending.png`) });

    // 5. Wait for generation
    console.log('  4️⃣  Waiting for 3D model...');
    await page.waitForTimeout(1000);
    for (let i = 0; i < 30; i++) {
      const genovHidden = await page.evaluate(() => {
        const el = document.getElementById('genov');
        return !el || getComputedStyle(el).display === 'none';
      });
      if (genovHidden) break;
      await page.waitForTimeout(1000);
      if (i % 10 === 9) console.log(`     ⏳ ${i+1}s...`);
    }
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `${tc.name}_04_generated.png`) });
    console.log('     ✅ Generation complete');

    // 6. Analyze results
    console.log('  5️⃣  Analyzing...');
    const r = await page.evaluate(() => {
      const out = { chatMsgs: [], thinkMsgs: [], canvasOk: false, modelOk: false, meshes: 0, bld: null, isInterior: false };
      // Chat messages
      document.querySelectorAll('.bub').forEach(b => out.chatMsgs.push(b.textContent.trim().substring(0, 200)));
      // Think blocks (reasoning)
      document.querySelectorAll('.think').forEach(t => out.thinkMsgs.push(t.textContent.trim().substring(0, 300)));
      // Canvas
      const c = document.getElementById('c3d');
      out.canvasOk = c && c.style.display !== 'none';
      // Model
      if (typeof ST !== 'undefined' && ST.hasModel && ST.bld) {
        out.modelOk = true;
        out.bld = {
          label: ST.bld.label, floors: ST.bld.floors,
          W: ST.bld.W, L: ST.bld.L, mat: ST.bld.mat,
          isInterior: ST.bld.isInterior, room_type: ST.bld.room_type,
        };
        out.isInterior = !!ST.bld.isInterior;
      }
      // Mesh count
      if (typeof bG !== 'undefined' && bG) {
        bG.traverse(o => { if (o.isMesh) out.meshes++; });
      }
      return out;
    });

    console.log(`     Canvas: ${r.canvasOk}`);
    console.log(`     Model: ${r.modelOk}`);
    console.log(`     Meshes: ${r.meshes}`);
    console.log(`     Interior: ${r.isInterior}`);
    if (r.bld) console.log(`     Building: ${r.bld.label}, ${r.bld.floors}fl, ${r.bld.W}×${r.bld.L}m, ${r.bld.mat}`);
    console.log(`     Chat msgs: ${r.chatMsgs.length}`);
    console.log(`     Think msgs: ${r.thinkMsgs.length}`);

    // 7. Check reasoning (think blocks should exist)
    console.log('  6️⃣  Checking reasoning...');
    const hasReasoning = r.thinkMsgs.length > 0;
    console.log(`     ${hasReasoning ? '✅' : '❌'} Reasoning blocks present (${r.thinkMsgs.length})`);
    if (hasReasoning) {
      r.thinkMsgs.forEach((m, i) => console.log(`       [${i}] ${m.substring(0, 120)}`));
    }

    // 8. Verify
    console.log('\n  🔍 Checks:');
    const checks = {
      'Page loads': true,
      'No critical JS errors': !errors.some(e => !e.includes('export') && !e.includes('ResizeObserver') && !e.includes('skip LLM')),
      'Chat has messages': r.chatMsgs.length >= 2,
      'Reasoning visible': hasReasoning,
      'Canvas visible': r.canvasOk,
      '3D model loaded': r.modelOk,
      'Meshes > 3': r.meshes > 3,
    };

    // Type-specific checks
    if (tc.expect.type === 'interior') {
      checks['Is interior'] = r.isInterior;
    }
    if (tc.expect.floors && r.bld) {
      checks[`Floors=${tc.expect.floors}`] = r.bld.floors === tc.expect.floors;
    }

    let allOk = true;
    for (const [k, v] of Object.entries(checks)) {
      console.log(`     ${v ? '✅' : '❌'} ${k}`);
      if (!v) allOk = false;
    }

    // Save report
    const report = { prompt: tc.prompt, name: tc.name, result: r, checks, passed: allOk, timestamp: new Date().toISOString() };
    fs.writeFileSync(
      path.join(SCREENSHOTS_DIR, `${tc.name}_report.json`),
      JSON.stringify(report, null, 2)
    );

    console.log(`\n  ${allOk ? '✅ PASSED' : '❌ FAILED'}\n`);
    await page.close();
    return { name: tc.name, passed: allOk, report };

  } catch (err) {
    console.error(`  ❌ FAILED: ${err.message}`);
    try { await page.screenshot({ path: path.join(SCREENSHOTS_DIR, `${tc.name}_error.png`) }); } catch(e) {}
    await page.close();
    return { name: tc.name, passed: false, error: err.message };
  }
}

async function main() {
  console.log('\n🏗️  Architect — E2E Browser Test Suite v3\n');
  console.log(`URL: ${SITE_URL}`);
  console.log(`Screenshots: ${SCREENSHOTS_DIR}`);

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--disable-web-security'],
  });

  const results = [];
  for (const tc of TEST_CASES) {
    const r = await runTest(tc, browser);
    results.push(r);
  }

  await browser.close();

  // Summary
  console.log(`\n${'═'.repeat(60)}`);
  console.log('  SUMMARY');
  console.log('═'.repeat(60));
  const passed = results.filter(r => r.passed).length;
  const total = results.length;
  for (const r of results) {
    console.log(`  ${r.passed ? '✅' : '❌'} ${r.name}${r.error ? ' — ' + r.error : ''}`);
  }
  console.log(`\n  ${passed}/${total} passed\n`);

  // Save combined report
  fs.writeFileSync(
    path.join(SCREENSHOTS_DIR, 'summary.json'),
    JSON.stringify({ passed, total, results: results.map(r => ({ name: r.name, passed: r.passed })), timestamp: new Date().toISOString() }, null, 2)
  );

  process.exit(passed === total ? 0 : 1);
}

main().catch(e => {
  console.error('Fatal:', e);
  process.exit(1);
});
