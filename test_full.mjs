import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const DIR = 'screenshots/full_test';
mkdirSync(DIR, { recursive: true });

const PROMPTS = [
  { id: 'bathroom', text: 'Сделай ванную в стиле хайтек на 45 кв. метров с джакузи и душевой кабинкой', expect: ['ванн', 'хайтек', 'джакуз'] },
  { id: 'children', text: 'Детская комната для мальчика 7 лет, 20 кв.м, нежные пастельные тона', expect: ['детск', 'пастел'] },
  { id: 'living', text: 'Гостиная в скандинавском стиле 50 кв.м с камином и большой ТВ-зоной', expect: ['гостин', 'камин', 'скандинав'] },
  { id: 'office', text: 'Кабинет для руководителя 35 кв.м с книжными шкафами, сейфом, зоной приёма гостей', expect: ['кабинет', 'книжн', 'сейф'] },
  { id: 'kitchen', text: 'Кухня в стиле хайтек 25 кв.м с островом и встроенной техникой', expect: ['кухн', 'хайтек'] },
  { id: 'bedroom', text: 'Спальня 30 кв.м в классическом стиле с собственным санузлом и ТВ-зоной', expect: ['спальн', 'классич'] },
];

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  executablePath: '/tmp/chrome-dir/chrome'
});

const results = [];

for (const prompt of PROMPTS) {
  console.log(`\n${'='.repeat(60)}`);
  console.log(`Testing: ${prompt.id} — "${prompt.text}"`);
  console.log('='.repeat(60));

  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, locale: 'ru-RU' });
  const page = await ctx.newPage();

  const apiCalls = [];
  page.on('request', req => {
    const url = req.url();
    if (url.includes('/api/')) {
      apiCalls.push({ method: req.method(), url: url.split('?')[0], body: req.postData()?.substring(0, 200) });
    }
  });
  page.on('console', msg => {
    if (msg.type() === 'error') console.log('Console error:', msg.text().substring(0, 150));
  });

  try {
    // Set localStorage to point to mock server BEFORE navigating
    await page.addInitScript(() => {
      localStorage.setItem('archai_backend_url', 'http://127.0.0.1:8080');
    });

    await page.goto('http://127.0.0.1:8080/index.html', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    // Type prompt
    const input = await page.$('#msgInput');
    if (!input) { console.log('ERROR: msgInput not found'); continue; }
    await input.click();
    await input.fill(prompt.text);
    await page.waitForTimeout(300);

    // Click send button
    const sendBtn = await page.$('#sendBtn');
    if (sendBtn) await sendBtn.click();
    else { console.log('ERROR: sendBtn not found'); continue; }

    // Wait for LLM processing
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${DIR}/${prompt.id}_01_after_send.png` });

    // Check chat messages
    const msgs = await page.evaluate(() => {
      const elements = document.querySelectorAll('.msg, .message, .chat-msg, [class*="msg"], [class*="message"]');
      return Array.from(elements).map(el => ({
        class: el.className.substring(0, 80),
        text: el.textContent.trim().substring(0, 300)
      })).filter(m => m.text.length > 5);
    });

    // Check for reasoning card
    const hasReasoning = await page.evaluate(() => {
      return !!document.querySelector('.reasoning-card, .thinking-card, .think, [class*="reasoning"], [class*="thinking"]');
    });

    // Check for clarifying questions
    const hasQuestions = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes('?') && (text.includes('Какой') || text.includes('Нужна') || text.includes('Какую') || text.includes('prefer'));
    });

    // Check for task decomposition
    const hasTasks = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes('Агент') || text.includes('Agent') || text.includes('Оркестратор') || text.includes('orchestrat') || text.includes('Шаг') || text.includes('Step') || text.includes('Создание') || text.includes('Проверка');
    });

    // Check for reference research
    const hasReferences = await page.evaluate(() => {
      const text = document.body.innerText;
      return text.includes('Изучаю') || text.includes('референс') || text.includes('Анализирую') || text.includes('Подбираю');
    });

    const result = {
      prompt_id: prompt.id,
      prompt_text: prompt.text,
      messages_count: msgs.length,
      messages: msgs.slice(0, 5),
      has_reasoning: hasReasoning,
      has_questions: hasQuestions,
      has_tasks: hasTasks,
      has_references: hasReferences,
      api_calls: apiCalls.filter(c => !c.url.includes('health')),
      all_passed: hasReasoning && hasQuestions && hasTasks && hasReferences
    };
    results.push(result);

    console.log(`Messages: ${msgs.length}`);
    console.log(`Reasoning: ${hasReasoning ? '✅' : '❌'}`);
    console.log(`Questions: ${hasQuestions ? '✅' : '❌'}`);
    console.log(`Tasks: ${hasTasks ? '✅' : '❌'}`);
    console.log(`References: ${hasReferences ? '✅' : '❌'}`);
    console.log(`API calls: ${apiCalls.length}`);
    if (msgs.length > 0) console.log('First msg:', msgs[0].text.substring(0, 100));

    // Take final screenshot
    await page.screenshot({ path: `${DIR}/${prompt.id}_02_final.png`, fullPage: true });

  } catch (err) {
    console.error(`ERROR for ${prompt.id}:`, err.message);
    results.push({ prompt_id: prompt.id, error: err.message });
  } finally {
    await ctx.close();
  }
}

await browser.close();

console.log('\n\n' + '='.repeat(60));
console.log('SUMMARY');
console.log('='.repeat(60));
for (const r of results) {
  if (r.error) { console.log(`❌ ${r.prompt_id}: ERROR — ${r.error}`); continue; }
  console.log(`${r.all_passed ? '✅' : '⚠️'} ${r.prompt_id}: msgs=${r.messages_count} reasoning=${r.has_reasoning} questions=${r.has_questions} tasks=${r.has_tasks} refs=${r.has_references} apis=${r.api_calls.length}`);
}
