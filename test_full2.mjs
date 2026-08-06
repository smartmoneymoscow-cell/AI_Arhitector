import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const DIR = 'screenshots/full_test';
mkdirSync(DIR, { recursive: true });

const PROMPTS = [
  { id: 'bathroom', text: 'Сделай ванную в стиле хайтек на 45 кв. метров с джакузи и душевой кабинкой' },
  { id: 'children', text: 'Детская комната для мальчика 7 лет, 20 кв.м, нежные пастельные тона' },
  { id: 'living', text: 'Гостиная в скандинавском стиле 50 кв.м с камином и большой ТВ-зоной' },
  { id: 'office', text: 'Кабинет для руководителя 35 кв.м с книжными шкафами, сейфом, зоной приёма гостей' },
  { id: 'kitchen', text: 'Кухня в стиле хайтек 25 кв.м с островом и встроенной техникой' },
  { id: 'bedroom', text: 'Спальня 30 кв.м в классическом стиле с собственным санузлом и ТВ-зоной' },
];

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  executablePath: '/tmp/chrome-dir/chrome'
});

const results = [];

for (const prompt of PROMPTS) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Testing: ${prompt.id}`);
  console.log('='.repeat(60));

  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, locale: 'ru-RU' });
  const page = await ctx.newPage();

  const apiCalls = [];
  page.on('request', req => {
    const url = req.url();
    if (url.includes('/api/')) {
      apiCalls.push({ method: req.method(), url: url.split('?')[0] });
    }
  });
  
  const consoleLogs = [];
  page.on('console', msg => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => consoleLogs.push(`[pageerror] ${err.message}`));

  try {
    await page.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    // Debug: check what functions exist
    const fnCheck = await page.evaluate(() => ({
      hasSendMessage: typeof sendMessage === 'function',
      hasMsgInput: !!document.getElementById('msgInput'),
      hasSendBtn: !!document.getElementById('sendBtn'),
      apiBase: typeof API_BASE !== 'undefined' ? API_BASE : 'undefined',
      backendOk: typeof _backendOk !== 'undefined' ? _backendOk : 'undefined',
    }));
    console.log('Function check:', JSON.stringify(fnCheck));

    // Set the input value and call sendMessage directly via evaluate
    const result = await page.evaluate(async (text) => {
      const inp = document.getElementById('msgInput');
      if (!inp) return { error: 'no input' };
      
      inp.value = text;
      // Trigger input event for any listeners
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      
      try {
        await sendMessage();
        return { success: true };
      } catch(e) {
        return { error: e.message };
      }
    }, prompt.text);

    console.log('sendMessage result:', JSON.stringify(result));
    await page.waitForTimeout(3000);

    // Check what happened
    const state = await page.evaluate(() => {
      const allMsgs = document.querySelectorAll('.msg, .message, .chat-msg, [class*="msg-"]');
      const welcome = document.querySelector('.welcome, .welcome-screen, [class*="welcome"]');
      const typing = document.querySelector('.typing, .typing-indicator, [class*="typing"]');
      const errors = document.querySelectorAll('.error, [class*="error"]');
      
      return {
        msgCount: allMsgs.length,
        msgs: Array.from(allMsgs).map(m => m.textContent.trim().substring(0, 150)),
        welcomeVisible: welcome ? getComputedStyle(welcome).display !== 'none' : 'no welcome element',
        typingVisible: typing ? getComputedStyle(typing).display !== 'none' : 'no typing element',
        errors: Array.from(errors).map(e => e.textContent.trim().substring(0, 100)),
        bodyText: document.body.innerText.substring(0, 1000)
      };
    });

    console.log('State after sendMessage:');
    console.log('  Messages:', state.msgCount);
    console.log('  Welcome visible:', state.welcomeVisible);
    console.log('  Typing visible:', state.typingVisible);
    console.log('  Errors:', state.errors);
    console.log('  API calls:', apiCalls.length);
    if (state.msgs.length > 0) console.log('  First msgs:', state.msgs.slice(0, 3));
    
    // Check for specific features in body text
    const features = await page.evaluate(() => {
      const t = document.body.innerText;
      return {
        hasReasoning: /🧠|Анализ|анализ|reasoning|thinking/i.test(t),
        hasQuestions: /Какой|Нужна|Какую|Возраст|Какой размер|Какой тип/i.test(t),
        hasTasks: /Агент|Agent|Шаг|Оркестратор|Создание|Проверка|Подбор|Генерация/i.test(t),
        hasReferences: /Изучаю|референс|Анализирую|Подбираю/i.test(t),
      };
    });
    console.log('Features:', JSON.stringify(features));

    await page.screenshot({ path: `${DIR}/${prompt.id}_result.png`, fullPage: true });

    results.push({
      id: prompt.id,
      apiCalls: apiCalls.length,
      msgs: state.msgCount,
      ...features,
      consoleErrors: consoleLogs.filter(l => l.includes('[error]') || l.includes('[pageerror]')).slice(0, 3)
    });

  } catch (err) {
    console.error(`ERROR:`, err.message);
    results.push({ id: prompt.id, error: err.message });
  } finally {
    await ctx.close();
  }
}

await browser.close();

console.log('\n\n' + '='.repeat(60));
console.log('SUMMARY');
console.log('='.repeat(60));
for (const r of results) {
  if (r.error) { console.log(`❌ ${r.id}: ${r.error}`); continue; }
  console.log(`${r.hasReasoning && r.hasQuestions && r.hasTasks && r.hasReferences ? '✅' : '⚠️'} ${r.id}: api=${r.apiCalls} msgs=${r.msgs} R=${r.hasReasoning} Q=${r.hasQuestions} T=${r.hasTasks} Ref=${r.hasReferences}`);
  if (r.consoleErrors.length) console.log(`  Errors: ${r.consoleErrors.join(' | ')}`);
}
