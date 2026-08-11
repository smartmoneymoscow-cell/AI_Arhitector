const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  try {
    await page.goto('https://architect-gateway.onrender.com/', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: '/home/work/.openclaw/workspace/.openclaw/tmp/AI_Arhitector/screenshot_landing.png', fullPage: false });
    console.log('Screenshot saved: screenshot_landing.png');
  } catch(e) {
    console.log('Error:', e.message);
  }
  await browser.close();
})();
