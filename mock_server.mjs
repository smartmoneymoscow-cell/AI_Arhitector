import http from 'http';
import fs from 'fs';
import path from 'path';

const PORT = 8080;
const ROOT = '/home/work/.openclaw/workspace/AI_Arhitector';

const MIME_TYPES = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
  '.glb': 'model/gltf-binary',
};

function parsePrompt(text) {
  const t = text.toLowerCase();
  const result = { object_type: 'interior', style: '', area_m2: 0, rooms: [], features: [], materials: [], color_scheme: '', lighting: '' };
  if (t.includes('ванн') || t.includes('bathroom')) { result.rooms = ['bathroom']; }
  else if (t.includes('детск') || t.includes('children')) { result.rooms = ['children_room']; }
  else if (t.includes('гостин') || t.includes('камин') || t.includes('living')) { result.rooms = ['living_room']; }
  else if (t.includes('кабинет') || t.includes('офис') || t.includes('office')) { result.rooms = ['office']; }
  else if (t.includes('кухн') || t.includes('kitchen')) { result.rooms = ['kitchen']; }
  else if (t.includes('спальн') || t.includes('bedroom')) { result.rooms = ['bedroom']; }
  else if (t.includes('дом') || t.includes('house')) { result.object_type = 'house'; }
  else if (t.includes('коттедж') || t.includes('cottage')) { result.object_type = 'cottage'; }
  if (t.includes('хайтек') || t.includes('hi-tech')) result.style = 'hi-tech';
  else if (t.includes('скандинав') || t.includes('scandinavian')) result.style = 'scandinavian';
  else if (t.includes('классич') || t.includes('classic')) result.style = 'classic';
  else if (t.includes('минимализм') || t.includes('minimal')) result.style = 'minimalist';
  else if (t.includes('лофт') || t.includes('loft')) result.style = 'loft';
  const areaMatch = t.match(/(\d+)\s*(?:кв|м2|метров|метр)/);
  if (areaMatch) result.area_m2 = parseInt(areaMatch[1]);
  if (t.includes('джакуз')) result.features.push('jacuzzi');
  if (t.includes('душев')) result.features.push('shower_cabin');
  if (t.includes('камин')) result.features.push('fireplace');
  if (t.includes('книжн') && t.includes('шкаф')) result.features.push('bookshelf');
  if (t.includes('сейф')) result.features.push('safe');
  if (t.includes('телевизор') || t.includes('tv')) result.features.push('tv');
  if (t.includes('сан') && t.includes('узел')) result.features.push('bathroom_en_suite');
  if (t.includes('кроват')) result.features.push('bed');
  if (t.includes('нежн') || t.includes('пастел')) result.color_scheme = 'pastel';
  else if (t.includes('светл')) result.color_scheme = 'light';
  return result;
}

function buildThinking(prompt, parsed) {
  const steps = [];
  steps.push(`Анализирую ваш запрос: "${prompt.substring(0, 100)}..."`);
  const roomNames = { bathroom: 'ванная комната', children_room: 'детская комната', living_room: 'гостиная', office: 'рабочий кабинет', kitchen: 'кухня', bedroom: 'спальня' };
  if (parsed.rooms.length > 0) steps.push(`Определён тип помещения: ${roomNames[parsed.rooms[0]] || parsed.rooms[0]}`);
  if (parsed.style) steps.push(`Стиль дизайна: ${parsed.style}`);
  if (parsed.area_m2 > 0) steps.push(`Площадь: ${parsed.area_m2} м² — ${parsed.area_m2 > 30 ? 'просторное помещение' : 'оптимальное использование пространства'}`);
  if (parsed.features.length > 0) { const fn = { jacuzzi: 'джакузи', shower_cabin: 'душевая кабина', fireplace: 'камин', bookshelf: 'книжный шкаф', safe: 'сейф', tv: 'телевизор', bathroom_en_suite: 'санузел', bed: 'кровать' }; steps.push(`Запрошенные элементы: ${parsed.features.map(f => fn[f] || f).join(', ')}`); }
  if (parsed.color_scheme) { const cn = { pastel: 'пастельные нежные тона', light: 'светлые тона' }; steps.push(`Цветовая гамма: ${cn[parsed.color_scheme] || parsed.color_scheme}`); }
  steps.push('Подбираю оптимальную планировку и размещение элементов');
  steps.push('Рассчитываю нормативы и эргономику пространства');
  return steps;
}

function buildReferences(prompt, parsed) {
  const refs = [];
  if (parsed.rooms.includes('bathroom')) { refs.push('Изучаю референсы современных ванных комнат в стиле хайтек'); refs.push('Анализирую планировки с джакузи и душевыми кабинами'); refs.push('Подбираю оптимальные материалы: керамогранит, стекло, хром'); }
  else if (parsed.rooms.includes('children_room')) { refs.push('Изучаю референсы детских комнат в пастельных тонах'); refs.push('Анализирую эргономику детских помещений по СП и СанПиН'); refs.push('Подбираю безопасные материалы и мебель для детской'); }
  else if (parsed.rooms.includes('living_room')) { refs.push('Изучаю референсы гостиных в скандинавском стиле'); refs.push('Анализирую размещение каминов и зонирование'); refs.push('Подбираю натуральные материалы: дерево, шерсть, лён'); }
  else if (parsed.rooms.includes('office')) { refs.push('Изучаю референсы рабочих кабинетов 35 м²'); refs.push('Анализирую эргономику рабочего места и хранения'); refs.push('Подбираю мебель: стол, кресло, книжный шкаф, сейф'); }
  else if (parsed.rooms.includes('kitchen')) { refs.push('Изучаю референсы кухонь в стиле хайтек'); refs.push('Анализирую кухонные модули и технику'); refs.push('Подбираю современные решения: встроенная техника, LED-подсветка'); }
  else if (parsed.rooms.includes('bedroom')) { refs.push('Изучаю референсы спален в классическом стиле'); refs.push('Анализирую планировки с собственным санузлом'); refs.push('Подбираю мебель: кровать, ТВ-зона, гардероб'); }
  return refs;
}

function buildQuestions(parsed) {
  const q = [];
  if (parsed.rooms.includes('bathroom')) { q.push('Какой размер джакузи предпочитаете — на 1 или 2 человека?'); q.push('Нужна ли паровая зона или сауна?'); q.push('Какой тип отделки — мрамор, керамогранит или натуральный камень?'); }
  else if (parsed.rooms.includes('children_room')) { q.push('Возраст ребёнка? Это влияет на эргономику и безопасность'); q.push('Нужна ли зона для занятий и творчества?'); q.push('Какой размер кровати — односпальная или двуспальная?'); }
  else if (parsed.rooms.includes('living_room')) { q.push('Какой тип камина — дровяной, электрический или газовый?'); q.push('Нужна ли зона для ТВ и медиацентра?'); q.push('Какой размер дивана предпочитаете?'); }
  else if (parsed.rooms.includes('office')) { q.push('Какой размер рабочего стола — стандартный или угловой?'); q.push('Нужна ли зона для приёма гостей?'); q.push('Какой объём сейфа — для документов или для ценностей?'); }
  else if (parsed.rooms.includes('kitchen')) { q.push('Какой формат кухни — линейная, П-образная или остров?'); q.push('Нужна ли столовая зона или только рабочая?'); q.push('Какую технику планируете — встроенную или отдельностоящую?'); }
  else if (parsed.rooms.includes('bedroom')) { q.push('Какой размер кровати — king-size или queen-size?'); q.push('Нужна ли гардеробная или достаточно шкафа?'); q.push('Какой размер ТВ и где его разместить?'); }
  return q;
}

function buildTasks(parsed) {
  const tasks = [{ agent: 'planner', task: 'Создание планировки помещения', status: 'completed' }, { agent: 'norms', task: 'Проверка СП и СанПиН нормативов', status: 'completed' }];
  if (parsed.rooms.includes('bathroom')) { tasks.push({ agent: 'furniture', task: 'Подбор сантехники: джакузи, душевая кабина, раковина', status: 'completed' }); tasks.push({ agent: 'materials', task: 'Подбор материалов: керамогранит, стекло, хром', status: 'completed' }); }
  else if (parsed.rooms.includes('children_room')) { tasks.push({ agent: 'furniture', task: 'Подбор детской мебели: кровать, стол, шкаф', status: 'completed' }); tasks.push({ agent: 'materials', task: 'Подбор безопасных материалов и покрытий', status: 'completed' }); }
  else if (parsed.rooms.includes('living_room')) { tasks.push({ agent: 'furniture', task: 'Подбор мебели: диван, кресла, журнальный стол', status: 'completed' }); tasks.push({ agent: 'fireplace', task: 'Проектирование камина и дымохода', status: 'completed' }); }
  else if (parsed.rooms.includes('office')) { tasks.push({ agent: 'furniture', task: 'Подбор мебели: стол, кресло, книжный шкаф, сейф', status: 'completed' }); tasks.push({ agent: 'lighting', task: 'Проектирование освещения рабочей зоны', status: 'completed' }); }
  else if (parsed.rooms.includes('kitchen')) { tasks.push({ agent: 'furniture', task: 'Подбор кухонных модулей и техники', status: 'completed' }); tasks.push({ agent: 'lighting', task: 'Проектирование LED-подсветки', status: 'completed' }); }
  else if (parsed.rooms.includes('bedroom')) { tasks.push({ agent: 'furniture', task: 'Подбор мебели: кровать, ТВ-зона, гардероб', status: 'completed' }); tasks.push({ agent: 'bathroom', task: 'Проектирование встроенного санузла', status: 'completed' }); }
  tasks.push({ agent: '3d', task: 'Генерация 3D-модели', status: 'completed' }, { agent: 'renderer', task: 'Рендер фотореалистичных изображений 8K', status: 'completed' }, { agent: 'qa', task: 'Проверка качества и нормативов', status: 'completed' });
  return tasks;
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const p = url.pathname;
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-API-Key');
  if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return; }

  // API endpoints
  if (p === '/api/v1/health') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ status: 'ok', version: '8.0.0' })); return; }

  if (p === '/api/v1/parse' && req.method === 'POST') {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      try {
        const { text } = JSON.parse(body);
        const parsed = parsePrompt(text);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ...parsed, thinking: buildThinking(text, parsed), references: buildReferences(text, parsed), clarifying_questions: buildQuestions(parsed), width_m: parsed.area_m2 > 0 ? Math.round(Math.sqrt(parsed.area_m2) * 1.2) : 10, length_m: parsed.area_m2 > 0 ? Math.round(Math.sqrt(parsed.area_m2) * 0.8) : 12, height_m: 2.8, floors: 1 }));
      } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
    }); return;
  }

  if (p === '/api/v1/orchestrator/execute' && req.method === 'POST') {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      try {
        const { prompt } = JSON.parse(body);
        const parsed = parsePrompt(prompt);
        setTimeout(() => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ status: 'success', tasks: buildTasks(parsed), exports: { glb: '/api/v1/mock_model.glb', png: '/output/mock_render.png' }, quality_score: 92, norms_compliance: true })); }, 800);
      } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
    }); return;
  }

  if (p === '/api/v1/generate' && req.method === 'POST') {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      setTimeout(() => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ status: 'completed', model_url: '/output/mock_model.glb', render_url: '/output/mock_render.png', quality: { score: 95, resolution: '8K', textures: 'PBR', lighting: 'HDR' } })); }, 500);
    }); return;
  }

  if (p === '/api/v1/chat' && req.method === 'POST') {
    let body = ''; req.on('data', c => body += c); req.on('end', () => {
      try {
        const { message } = JSON.parse(body);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ response: `Обрабатываю: "${message}"`, status: 'ok' }));
      } catch (e) { res.writeHead(400); res.end(JSON.stringify({ error: e.message })); }
    }); return;
  }

  if (p === '/api/v1/compliance/check' && req.method === 'POST') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ compliant: true, issues: [], score: 95 })); return; }
  if (p === '/api/v1/vectordb/search_by_prompt') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ results: [] })); return; }

  // Serve GLB mock model
  if (p === '/api/v1/mock_model.glb') {
    try {
      const glbData = fs.readFileSync(path.join(ROOT, 'output/mock_model.glb'));
      res.writeHead(200, { 'Content-Type': 'model/gltf-binary', 'Content-Length': glbData.length });
      res.end(glbData);
    } catch (e) { res.writeHead(404); res.end('GLB not found'); }
    return;
  }

  // Static files
  let filePath = path.join(ROOT, p === '/' ? 'index.html' : p);
  if (!fs.existsSync(filePath)) { res.writeHead(404); res.end('Not found'); return; }
  const ext = path.extname(filePath);
  const mime = MIME_TYPES[ext] || 'application/octet-stream';
  try {
    const data = fs.readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': mime });
    res.end(data);
  } catch (e) { res.writeHead(500); res.end('Error'); }
});

server.listen(PORT, '0.0.0.0', () => console.log(`Mock server on http://0.0.0.0:${PORT}`));
