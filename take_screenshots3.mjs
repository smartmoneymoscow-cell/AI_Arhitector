import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const DIR = 'screenshots/cv_test2';
mkdirSync(DIR, { recursive: true });

const PROMPTS = [
  {id:'bathroom',text:'Сделай ванную в стиле хайтек на 45 кв. метров с джакузи и душевой кабинкой'},
  {id:'children',text:'Сделай красивую детскую в нежных тонах'},
  {id:'living',text:'Сделай гостиную с камином в скандинавском стиле'},
  {id:'office',text:'Сделай рабочий кабинет в комнате 35 метров с книжным шкафом и сейфом'},
  {id:'kitchen',text:'Сделай просторную светлую кухню в стиле хайтек'},
  {id:'bedroom',text:'Сделай большую спальню в классическом стиле с большим телевизором и кроватью, в спальне должен быть свой санузел'},
];

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage'],
  executablePath: '/home/work/.cache/puppeteer/chrome/linux-151.0.7922.47/chrome-linux64/chrome'
});

for (const pr of PROMPTS) {
  console.log('Processing: ' + pr.id);
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();
  await page.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // Send message
  await page.evaluate(async (text) => {
    const inp = document.getElementById('msgInput');
    inp.value = text;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    await sendMessage();
  }, pr.text);

  await page.waitForTimeout(6000);
  
  // Take viewport screenshot
  await page.screenshot({ path: DIR + '/' + pr.id + '.png', fullPage: false });
  
  // Scroll chat to bottom and take screenshot
  await page.evaluate(() => {
    const chat = document.getElementById('chatMessages');
    if (chat) chat.scrollTo({top: chat.scrollHeight, behavior: 'instant'});
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: DIR + '/' + pr.id + '_scrolled.png', fullPage: false });
  
  console.log('Saved: ' + pr.id);
  await ctx.close();
}

// Mobile with chat open
const mCtx = await browser.newContext({ viewport: { width: 375, height: 812 } });
const mp = await mCtx.newPage();
await mp.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });
await mp.waitForTimeout(2000);
// Open mobile chat
await mp.evaluate(() => { if(typeof openMobile === 'function') openMobile(); });
await mp.waitForTimeout(500);
await mp.screenshot({ path: DIR + '/mobile_chat_open.png' });
// Type and send
await mp.evaluate(async () => {
  const inp = document.getElementById('msgInput');
  inp.value = 'Сделай ванную в стиле хайтек';
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  await sendMessage();
});
await mp.waitForTimeout(4000);
await mp.screenshot({ path: DIR + '/mobile_result.png' });
console.log('Saved: mobile');
await mCtx.close();

// Tablet
const tCtx = await browser.newContext({ viewport: { width: 768, height: 1024 } });
const tp = await tCtx.newPage();
await tp.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });
await tp.waitForTimeout(2000);
await tp.evaluate(async () => {
  const inp = document.getElementById('msgInput');
  inp.value = 'Сделай ванную в стиле хайтек';
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  await sendMessage();
});
await tp.waitForTimeout(4000);
await tp.screenshot({ path: DIR + '/tablet_result.png' });
console.log('Saved: tablet');
await tCtx.close();

await browser.close();
console.log('All done!');
