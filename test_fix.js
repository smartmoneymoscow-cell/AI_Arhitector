const puppeteer = require('puppeteer');
const http = require('http');
const fs = require('fs');
const path = require('path');

// Simple static file server
const server = http.createServer((req, res) => {
  const filePath = path.join(__dirname, req.url === '/' ? 'frontend/index.html' : req.url);
  const ext = path.extname(filePath);
  const types = {'.html':'text/html','.js':'application/javascript','.css':'text/css','.png':'image/png'};
  try {
    const data = fs.readFileSync(filePath);
    res.writeHead(200, {'Content-Type': types[ext] || 'application/octet-stream'});
    res.end(data);
  } catch(e) {
    res.writeHead(404); res.end('Not found');
  }
});

server.listen(9876, async () => {
  console.log('Server on :9876');
  try {
    const browser = await puppeteer.launch({ 
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
    });
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 900 });
    
    console.log('Loading page...');
    await page.goto('http://localhost:9876/', { waitUntil: 'networkidle2', timeout: 30000 });
    await new Promise(r => setTimeout(r, 3000));
    
    // Check for JS errors
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if(m.type()==='error') errors.push(m.text()); });
    
    // Check placeholder
    const ph = await page.evaluate(() => document.getElementById('ci')?.placeholder);
    console.log('1. Placeholder:', ph);
    
    // Check if send function exists
    const sendExists = await page.evaluate(() => typeof window.send);
    console.log('   send() type:', sendExists);
    const sendExists2 = await page.evaluate(() => typeof send);
    console.log('   send (global):', sendExists2);
    
    // Send house
    console.log('2. Sending: жилой дом 2 этажа кирпич 10x12');
    await page.evaluate(() => { document.getElementById('ci').value = 'жилой дом 2 этажа кирпич 10x12'; });
    await page.evaluate(() => { document.querySelector('.sbtn:last-of-type').click(); });
    await new Promise(r => setTimeout(r, 12000));
    
    const msgs = await page.evaluate(() => Array.from(document.querySelectorAll('.bub')).map(m => m.textContent.slice(0,100)));
    console.log('   Messages:', JSON.stringify(msgs));
    const hasModel = await page.evaluate(() => typeof ST !== 'undefined' && ST.hasModel);
    console.log('   Has model:', hasModel);
    const canvasVis = await page.evaluate(() => { const c = document.getElementById('c3d'); return c && c.style.display !== 'none'; });
    console.log('   Canvas visible:', canvasVis);
    
    // Send bathroom
    console.log('3. Sending: ванная с джакузи');
    await page.evaluate(() => { document.getElementById('ci').value = 'ванная с джакузи'; });
    await page.evaluate(() => { document.querySelector('.sbtn:last-of-type').click(); });
    await new Promise(r => setTimeout(r, 8000));
    
    const msgs2 = await page.evaluate(() => Array.from(document.querySelectorAll('.bub')).map(m => m.textContent.slice(0,100)));
    console.log('   Messages:', JSON.stringify(msgs2));
    
    // Check context prompts
    const qpbar = await page.evaluate(() => document.getElementById('qpbar')?.textContent?.trim()?.slice(0,200));
    console.log('4. Context prompts:', qpbar);
    
    // Report errors
    if(errors.length) console.log('JS Errors:', JSON.stringify(errors));
    
    await browser.close();
    console.log('DONE');
  } catch(e) {
    console.error('Error:', e.message);
  }
  server.close();
});
