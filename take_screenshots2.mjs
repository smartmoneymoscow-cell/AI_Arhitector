import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const DIR = 'screenshots/cv_test';
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

  await page.waitForTimeout(5000);
  
  // Scroll chat to top to show reasoning
  await page.evaluate(() => {
    const chat = document.getElementById('chatMessages');
    if (chat) chat.scrollTop = 0;
  });
  await page.waitForTimeout(500);
  
  // Full page screenshot
  await page.screenshot({ path: DIR + '/' + pr.id + '_full.png', fullPage: true });
  
  // Viewport screenshot (what user sees)
  await page.screenshot({ path: DIR + '/' + pr.id + '.png', fullPage: false });
  
  console.log('Saved: ' + pr.id);
  await ctx.close();
}

await browser.close();
console.log('All done!');
