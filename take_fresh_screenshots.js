const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({headless:'new',args:['--no-sandbox','--disable-setuid-sandbox']});
  const page = await browser.newPage();
  await page.setViewport({width:1440,height:900});
  
  console.log('Opening site...');
  await page.goto('https://architect-gateway.onrender.com/', {waitUntil:'networkidle2',timeout:60000});
  await new Promise(r => setTimeout(r, 3000));
  await page.screenshot({path:'screenshots/fresh_01_main.png'});
  console.log('1: main page');
  
  // Type in input
  const input = await page.$('#msgInput');
  if (input) {
    await input.type('дом 2 этажа кирпич 10x12');
    await page.screenshot({path:'screenshots/fresh_02_input.png'});
    console.log('2: input filled');
    
    // Click send
    const sendBtn = await page.$('#sendBtn');
    if (sendBtn) {
      await sendBtn.click();
      await new Promise(r => setTimeout(r, 5000));
      await page.screenshot({path:'screenshots/fresh_03_sending.png'});
      console.log('3: sending');
      
      await new Promise(r => setTimeout(r, 30000));
      await page.screenshot({path:'screenshots/fresh_04_response.png'});
      console.log('4: response');
    }
  }
  
  await browser.close();
  console.log('Done');
})().catch(e => { console.error(e.message); process.exit(1); });
