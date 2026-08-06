import { chromium } from 'playwright';

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--enable-webgl','--use-gl=swiftshader','--enable-gpu-rasterization'],
  executablePath: '/home/work/.cache/puppeteer/chrome/linux-151.0.7922.47/chrome-linux64/chrome'
});

const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await ctx.newPage();

const consoleLogs = [];
page.on('console', msg => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));

await page.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });
await page.waitForTimeout(2000);

// Send prompt
await page.evaluate(async () => {
  const inp = document.getElementById('msgInput');
  inp.value = 'Сделай ванную в стиле хайтек на 45 кв. метров с джакузи и душевой кабинкой';
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  await sendMessage();
});

// Wait for full pipeline (parse + orchestrator + GLB load)
await page.waitForTimeout(8000);

// Check results
const result = await page.evaluate(() => {
  const canvas = document.getElementById('c3d');
  const emptyState = document.getElementById('emptyState');
  const msgs = document.querySelectorAll('.msg');
  const msgTexts = Array.from(msgs).map(m => m.textContent.trim().substring(0, 120));
  
  return {
    canvasVisible: canvas ? getComputedStyle(canvas).display !== 'none' : false,
    emptyStateHidden: emptyState ? getComputedStyle(emptyState).display === 'none' : true,
    canvasWidth: canvas ? canvas.width : 0,
    canvasHeight: canvas ? canvas.height : 0,
    msgCount: msgs.length,
    hasModelReady: document.body.innerText.includes('3D модель готова') || document.body.innerText.includes('3D model ready'),
    hasGenOverlayHidden: !document.querySelector('.gen-overlay:not([style*="display: none"])'),
    msgs: msgTexts.slice(-5),
  };
});

console.log('\n=== 3D MODEL CHECK ===');
console.log('Canvas visible:', result.canvasVisible ? '✅' : '❌');
console.log('Empty state hidden:', result.emptyStateHidden ? '✅' : '❌');
console.log('Canvas size:', result.canvasWidth + 'x' + result.canvasHeight);
console.log('Model ready message:', result.hasModelReady ? '✅' : '❌');
console.log('Messages:', result.msgCount);
console.log('Last 5 msgs:');
result.msgs.forEach(m => console.log('  -', m.substring(0, 100)));

console.log('\nConsole logs:');
consoleLogs.filter(l => l.includes('GLB') || l.includes('3D') || l.includes('model') || l.includes('error') || l.includes('Error')).forEach(l => console.log(' ', l));

await page.screenshot({ path: 'screenshots/cv_test2/verify_3d.png', fullPage: false });
console.log('\nScreenshot saved: verify_3d.png');

await browser.close();
