import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const DIR = 'screenshots/visual_test';
mkdirSync(DIR, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  executablePath: '/tmp/chrome-dir/chrome'
});
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, locale: 'ru-RU' });
const page = await ctx.newPage();

// Listen for network requests to understand API calls
const apiCalls = [];
page.on('request', req => {
  const url = req.url();
  if (url.includes('api') || url.includes('llm') || url.includes('chat') || url.includes('generate') || url.includes('gateway') || url.includes('localhost:8') || url.includes('127.0.0.1:8')) {
    apiCalls.push({ method: req.method(), url: url.substring(0, 200), postData: req.postData()?.substring(0, 300) || null });
  }
});
page.on('response', res => {
  const url = res.url();
  if (url.includes('api') || url.includes('llm') || url.includes('chat') || url.includes('generate')) {
    apiCalls.push({ type: 'response', url: url.substring(0, 200), status: res.status() });
  }
});

try {
  console.log('Opening page...');
  await page.goto('http://127.0.0.1:8090/index.html', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  
  // Take initial screenshot
  await page.screenshot({ path: `${DIR}/send_01_initial.png` });
  console.log('Initial page loaded');

  // Find the input and type a prompt
  const input = await page.$('#msgInput');
  if (!input) {
    console.log('ERROR: msgInput not found!');
    await browser.close();
    process.exit(1);
  }
  
  await input.click();
  await input.fill('Сделай ванную в стиле хайтек на 45 кВ метров с джакузи и душево кабинкой');
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${DIR}/send_02_typed.png` });
  console.log('Prompt typed');

  // Click the send button
  const sendBtn = await page.$('#sendBtn');
  if (sendBtn) {
    console.log('Found sendBtn, clicking...');
    await sendBtn.click();
  } else {
    console.log('sendBtn not found, trying other selectors...');
    // Try clicking any send-like button
    const btns = await page.$$('button');
    for (const btn of btns) {
      const id = await btn.evaluate(el => el.id);
      const cls = await btn.evaluate(el => el.className);
      if (cls.includes('send') || id.includes('send')) {
        console.log(`Found button with id=${id} class=${cls}, clicking...`);
        await btn.click();
        break;
      }
    }
  }
  
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${DIR}/send_03_after_send.png` });
  console.log('After send click');

  // Check if message appeared in chat
  const chatContent = await page.evaluate(() => {
    const msgs = document.querySelectorAll('.msg, .message, .chat-msg, [class*="msg-"], [class*="message-"]');
    return Array.from(msgs).map(m => ({ class: m.className.substring(0, 60), text: m.textContent.trim().substring(0, 200) }));
  });
  console.log('Chat messages after send:', JSON.stringify(chatContent, null, 2));

  // Wait for LLM response
  console.log('Waiting 15s for LLM response...');
  await page.waitForTimeout(15000);
  await page.screenshot({ path: `${DIR}/send_04_after_wait.png` });

  // Check chat content again
  const chatContent2 = await page.evaluate(() => {
    const msgs = document.querySelectorAll('.msg, .message, .chat-msg, [class*="msg-"], [class*="message-"]');
    return Array.from(msgs).map(m => ({ class: m.className.substring(0, 60), text: m.textContent.trim().substring(0, 300) }));
  });
  console.log('Chat messages after wait:', JSON.stringify(chatContent2, null, 2));

  // Check API calls
  console.log('\nAPI calls captured:', JSON.stringify(apiCalls, null, 2));

  // Check for any error messages in the UI
  const errors = await page.evaluate(() => {
    const body = document.body.innerText;
    const errorKeywords = ['ошибка', 'error', 'failed', 'не удалось', 'нет ответа', 'timeout'];
    return errorKeywords.filter(kw => body.toLowerCase().includes(kw));
  });
  console.log('Error keywords found:', errors);

  // Check the full page text for any LLM-related content
  const fullText = await page.evaluate(() => document.body.innerText);
  console.log('\nFull page text (first 2000 chars):\n', fullText.substring(0, 2000));

} catch (err) {
  console.error('ERROR:', err.message);
  await page.screenshot({ path: `${DIR}/send_error.png` });
} finally {
  await browser.close();
}
