import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  executablePath: '/opt/ms-playwright/chromium-1228/chrome-linux64/chrome'
});

const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080 });

console.log('Opening page...');
await page.goto('http://localhost:8090/index.html', { waitUntil: 'networkidle2', timeout: 30000 });
console.log('Page loaded, title:', await page.title());

// Take initial screenshot
await page.screenshot({ path: 'screenshots/test_01_initial.png', fullPage: false });
console.log('Screenshot 1: initial page saved');

// Check if chat input is visible and not cut off
const chatInput = await page.$('textarea, input[type="text"], [contenteditable], .chat-input, #chat-input, [placeholder]');
if (chatInput) {
  const box = await chatInput.boundingBox();
  console.log('Chat input found at:', JSON.stringify(box));
  const isFullyVisible = box && box.y >= 0 && box.y + box.height <= 1080 && box.x >= 0 && box.x + box.width <= 1920;
  console.log('Chat input fully visible:', isFullyVisible);
} else {
  console.log('WARNING: No chat input found!');
}

// Look for the chat area
const elements = await page.evaluate(() => {
  const all = document.querySelectorAll('*');
  const interesting = [];
  for (const el of all) {
    const tag = el.tagName;
    const id = el.id;
    const cls = el.className;
    if (id || (typeof cls === 'string' && cls.length > 0)) {
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON' || 
          (typeof cls === 'string' && (cls.includes('chat') || cls.includes('input') || cls.includes('prompt') || cls.includes('send')))) {
        interesting.push({ tag, id, class: typeof cls === 'string' ? cls.substring(0, 80) : '' });
      }
    }
  }
  return interesting.slice(0, 30);
});
console.log('Interesting elements:', JSON.stringify(elements, null, 2));

await browser.close();
console.log('Done');
