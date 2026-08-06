import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const DIR = 'screenshots/real_api_test';
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
  args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--enable-webgl','--use-gl=swiftshader'],
  executablePath: '/home/work/.cache/puppeteer/chrome/linux-151.0.7922.47/chrome-linux64/chrome'
});

for (const pr of PROMPTS) {
  console.log('Processing: ' + pr.id);
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();
  
  // Set API key and backend URL BEFORE page load
  await page.addInitScript(() => {
    localStorage.setItem('arch_api_key', 'arch-prod-key-2024');
    localStorage.setItem('archai_backend_url', 'https://architect-gateway.onrender.com');
  });
  
  // Use the mock server but it will proxy to real gateway
  await page.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  
  // Verify API_BASE is set to real gateway
  const apiBase = await page.evaluate(() => typeof API_BASE !== 'undefined' ? API_BASE : 'undef');
  console.log('API_BASE:', apiBase);

  // Send message via real click
  await page.evaluate(async (text) => {
    const inp = document.getElementById('msgInput');
    inp.value = text;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    await sendMessage();
  }, pr.text);

  // Wait for real API response (longer timeout)
  await page.waitForTimeout(15000);
  
  // Scroll to top of chat
  await page.evaluate(() => {
    const chat = document.getElementById('chatMessages');
    if (chat) chat.scrollTo({ top: 0, behavior: 'instant' });
  });
  await page.waitForTimeout(500);
  
  await page.screenshot({ path: DIR + '/' + pr.id + '.png', fullPage: false });
  
  // Scroll to bottom
  await page.evaluate(() => {
    const chat = document.getElementById('chatMessages');
    if (chat) chat.scrollTo({ top: chat.scrollHeight, behavior: 'instant' });
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: DIR + '/' + pr.id + '_bottom.png', fullPage: false });
  
  console.log('Saved: ' + pr.id);
  await ctx.close();
}

await browser.close();
console.log('All done!');
