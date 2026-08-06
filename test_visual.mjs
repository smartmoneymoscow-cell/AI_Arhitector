import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const SCREENSHOTS_DIR = 'screenshots/visual_test';
mkdirSync(SCREENSHOTS_DIR, { recursive: true });

const PROMPTS = [
  "Сделай ванную в стиле хайтек на 45 кВ метров с джакузи и душево кабинкой",
  "Сделай красивую детскую в нежный тонах",
  "Сделай гостиную с камином в скандинавском стиле",
  "Сделай рабочий кабинет в комнате 35 метров с книжным шкафом и сейфом",
  "Сделай просторную светлую кухню в стиле хайтек",
  "Сделай большую спальню в классическом стиле с большим телевизором и кроватью, в спальне должен быть свой сан узел"
];

const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
  executablePath: '/tmp/chrome-dir/chrome'
});

const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  locale: 'ru-RU'
});

const page = await context.newPage();

// Helper to take named screenshot
async function snap(name) {
  const path = `${SCREENSHOTS_DIR}/${name}.png`;
  await page.screenshot({ path, fullPage: false });
  console.log(`📸 Screenshot: ${path}`);
  return path;
}

// Helper to wait and log
async function waitAndLog(ms, msg) {
  console.log(`⏳ ${msg} (waiting ${ms}ms)`);
  await page.waitForTimeout(ms);
}

try {
  // ═══════════════ STEP 1: Open main page ═══════════════
  console.log('\n══════════════ STEP 1: Opening main page ═══════════════');
  await page.goto('http://127.0.0.1:8090/index.html', { waitUntil: 'networkidle', timeout: 30000 });
  await waitAndLog(3000, 'Page loaded, waiting for render');
  await snap('01_initial_page');

  // ═══════════════ STEP 2: Check adaptivity - input not cut off ═══════════════
  console.log('\n══════════════ STEP 2: Checking adaptivity ═══════════════');
  
  // Find chat input area
  const inputInfo = await page.evaluate(() => {
    const inputs = document.querySelectorAll('textarea, input[type="text"], [contenteditable="true"]');
    const results = [];
    for (const el of inputs) {
      const rect = el.getBoundingClientRect();
      results.push({
        tag: el.tagName,
        id: el.id,
        class: el.className,
        placeholder: el.placeholder || '',
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        visible: rect.width > 0 && rect.height > 0,
        inViewport: rect.y >= 0 && rect.y + rect.height <= window.innerHeight
      });
    }
    return results;
  });
  console.log('Input elements found:', JSON.stringify(inputInfo, null, 2));

  // Also check buttons
  const buttonInfo = await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    const results = [];
    for (const btn of btns) {
      const rect = btn.getBoundingClientRect();
      if (rect.width > 0) {
        results.push({
          text: btn.textContent.trim().substring(0, 50),
          id: btn.id,
          class: btn.className.substring(0, 60),
          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          inViewport: rect.y >= 0 && rect.y + rect.height <= window.innerHeight
        });
      }
    }
    return results;
  });
  console.log('Buttons found:', JSON.stringify(buttonInfo, null, 2));

  // Test at different viewport sizes for adaptivity
  for (const vp of [{w:1920,h:1080,name:'desktop'}, {w:768,h:1024,name:'tablet'}, {w:375,h:812,name:'mobile'}]) {
    await page.setViewportSize({ width: vp.w, height: vp.h });
    await waitAndLog(1000, `Viewport: ${vp.name} (${vp.w}x${vp.h})`);
    await snap(`02_adaptivity_${vp.name}`);
    
    const inputVisible = await page.evaluate(() => {
      const el = document.querySelector('textarea, input[type="text"], [contenteditable="true"]');
      if (!el) return { found: false };
      const rect = el.getBoundingClientRect();
      return {
        found: true,
        inViewport: rect.y >= 0 && rect.y + rect.height <= window.innerHeight && rect.x >= 0 && rect.x + rect.width <= window.innerWidth,
        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
      };
    });
    console.log(`  Input visibility at ${vp.name}:`, JSON.stringify(inputVisible));
  }

  // Reset to desktop
  await page.setViewportSize({ width: 1920, height: 1080 });
  await waitAndLog(1000, 'Reset to desktop viewport');

  // ═══════════════ STEP 3-8: Test each prompt ═══════════════
  for (let i = 0; i < PROMPTS.length; i++) {
    const prompt = PROMPTS[i];
    console.log(`\n══════════════ PROMPT ${i + 1}: "${prompt}" ═══════════════`);
    
    // Find and clear input
    const inputSelector = 'textarea, input[type="text"], [contenteditable="true"]';
    await page.waitForSelector(inputSelector, { timeout: 5000 });
    
    // Clear existing text and type new prompt
    const input = await page.$(inputSelector);
    if (input) {
      await input.click();
      await input.fill('');
      await input.fill(prompt);
      await waitAndLog(500, 'Typed prompt');
      await snap(`prompt${i + 1}_01_typed`);
      
      // Find and click send button
      const sendBtn = await page.evaluate(() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
          const text = btn.textContent.trim().toLowerCase();
          const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
          if (text.includes('отправить') || text.includes('send') || text.includes('➤') || 
              ariaLabel.includes('send') || ariaLabel.includes('отправить') ||
              btn.querySelector('svg') || btn.innerHTML.includes('→')) {
            return { found: true, text: btn.textContent.trim().substring(0, 30) };
          }
        }
        // Try finding by position (usually last button near input)
        return { found: false };
      });
      console.log('Send button:', JSON.stringify(sendBtn));
      
      // Try pressing Enter instead
      await input.press('Enter');
      await waitAndLog(2000, 'Pressed Enter to send');
      await snap(`prompt${i + 1}_02_sent`);
      
      // Wait for LLM response to start appearing
      console.log('Waiting for LLM response...');
      await waitAndLog(8000, 'Waiting for thinking/reasoning to appear');
      await snap(`prompt${i + 1}_03_thinking`);
      
      // Check for thinking/reasoning content
      const thinkingContent = await page.evaluate(() => {
        const body = document.body.innerText;
        const thinkingKeywords = ['анализ', 'размышлен', 'анализирую', 'рассуждаю', 'думаю', '思考', 'thinking', 'рассматриваю', 'изучаю', 'задача'];
        const found = thinkingKeywords.filter(kw => body.toLowerCase().includes(kw));
        return { keywordsFound: found, bodyLength: body.length };
      });
      console.log('Thinking content check:', JSON.stringify(thinkingContent));
      
      // Wait more for references search
      await waitAndLog(8000, 'Waiting for references/research');
      await snap(`prompt${i + 1}_04_references`);
      
      // Check for reference search indicators
      const refContent = await page.evaluate(() => {
        const body = document.body.innerText;
        const refKeywords = ['референс', 'reference', 'поиск', 'search', 'изучаю', 'стиль', 'пример', 'найден', 'источник'];
        const found = refKeywords.filter(kw => body.toLowerCase().includes(kw));
        return { keywordsFound: found };
      });
      console.log('Reference search check:', JSON.stringify(refContent));
      
      // Wait for clarifying questions
      await waitAndLog(8000, 'Waiting for clarifying questions');
      await snap(`prompt${i + 1}_05_questions`);
      
      // Check for question marks (clarifying questions)
      const questionContent = await page.evaluate(() => {
        const body = document.body.innerText;
        const questionMarks = (body.match(/\?/g) || []).length;
        const questionKeywords = ['уточн', 'вопрос', 'question', 'какой', 'какая', 'какие', 'нужно', 'предпочитаете', 'хотите'];
        const found = questionKeywords.filter(kw => body.toLowerCase().includes(kw));
        return { questionMarks, keywordsFound: found };
      });
      console.log('Clarifying questions check:', JSON.stringify(questionContent));
      
      // Check hint chips
      const chips = await page.evaluate(() => {
        const chipSelectors = ['.chip', '.hint', '.suggestion', '.quick-reply', '[class*="chip"]', '[class*="hint"]', '[class*="suggest"]', '[class*="quick"]'];
        const results = [];
        for (const sel of chipSelectors) {
          const els = document.querySelectorAll(sel);
          for (const el of els) {
            if (el.textContent.trim().length > 0) {
              results.push({ selector: sel, text: el.textContent.trim().substring(0, 60) });
            }
          }
        }
        return results;
      });
      console.log('Hint chips:', JSON.stringify(chips));
      
      // Wait for orchestrator task distribution
      await waitAndLog(8000, 'Waiting for orchestrator/agent tasks');
      await snap(`prompt${i + 1}_06_orchestrator`);
      
      // Check for agent/task indicators
      const agentContent = await page.evaluate(() => {
        const body = document.body.innerText;
        const agentKeywords = ['агент', 'agent', 'оркестратор', 'orchestrator', 'задача', 'task', 'распределяю', 'назначаю', 'выполняю'];
        const found = agentKeywords.filter(kw => body.toLowerCase().includes(kw));
        return { keywordsFound: found };
      });
      console.log('Agent/orchestrator check:', JSON.stringify(agentContent));
      
      // Wait for preview/3D generation
      await waitAndLog(10000, 'Waiting for 3D preview generation');
      await snap(`prompt${i + 1}_07_preview`);
      
      // Check preview area
      const previewInfo = await page.evaluate(() => {
        const canvas = document.querySelector('canvas');
        const iframe = document.querySelector('iframe');
        const preview3d = document.querySelector('[class*="preview"], [class*="3d"], [class*="canvas"], [id*="preview"], [id*="canvas"]');
        return {
          hasCanvas: !!canvas,
          canvasSize: canvas ? { w: canvas.width, h: canvas.height } : null,
          hasIframe: !!iframe,
          hasPreview3d: !!preview3d,
          preview3dRect: preview3d ? preview3d.getBoundingClientRect() : null
        };
      });
      console.log('Preview info:', JSON.stringify(previewInfo));
      
      // Wait more and take final screenshot
      await waitAndLog(10000, 'Final wait for complete generation');
      await snap(`prompt${i + 1}_08_final`);
      
      // Get full chat content for analysis
      const chatContent = await page.evaluate(() => {
        const messages = document.querySelectorAll('.message, .chat-message, [class*="message"], [class*="bubble"], [class*="chat"]');
        const results = [];
        for (const msg of messages) {
          results.push({
            class: msg.className.substring(0, 60),
            text: msg.textContent.trim().substring(0, 200)
          });
        }
        return results;
      });
      console.log('Chat messages:', JSON.stringify(chatContent, null, 2));
      
      console.log(`\n✅ Prompt ${i + 1} test complete\n`);
    }
  }

  console.log('\n══════════════ ALL TESTS COMPLETE ═══════════════');

} catch (err) {
  console.error('ERROR:', err.message);
  await snap('error_state');
} finally {
  await browser.close();
}
