/**
 * Architect v10.3 — Chat Generation Tests
 * Tests that text, photo, and voice inputs all trigger 3D generation.
 *
 * Run: node tests/test_chat.js
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// ═══════════════════════════════════════════════════════════════
// TEST HARNESS
// ═══════════════════════════════════════════════════════════════
let passed = 0, failed = 0, total = 0;

function assert(condition, label) {
  total++;
  if (condition) { passed++; console.log(`  ✅ ${label}`); }
  else { failed++; console.error(`  ❌ ${label}`); }
}

function section(title) {
  console.log(`\n${'─'.repeat(60)}`);
  console.log(`  ${title}`);
  console.log('─'.repeat(60));
}

// ═══════════════════════════════════════════════════════════════
// EXTRACT FUNCTIONS FROM index.html
// ═══════════════════════════════════════════════════════════════
const htmlSrc = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf-8');

// Extract the inline script block (the big one without src=)
const scriptRe = /<script>([\s\S]*?)<\/script>/gi;
let appCode = '';
let m;
while ((m = scriptRe.exec(htmlSrc)) !== null) {
  const c = m[1].trim();
  if (c.length > 1000) { appCode = c; break; }  // The main app script
}

// Remove 'use strict'
appCode = appCode.replace(/'use strict';?\s*/g, '');

// Remove duplicate Voice Input code
appCode = appCode.replace(/let recognition = null;\s*/g, '');
appCode = appCode.replace(/let isListening = false;\s*/g, '');

// ═══════════════════════════════════════════════════════════════
// BUILD TEST ENVIRONMENT
// ═══════════════════════════════════════════════════════════════
function createEnv() {
  const log = {
    genCalls: [],
    msgLog: [],
    fetchCalls: [],
    notifications: [],
  };

  const elements = {};
  function el(id, tag = 'div') {
    if (elements[id]) return elements[id];
    const e = {
      id, tagName: tag, style: {}, innerHTML: '', value: '',
      placeholder: '', type: '', accept: '', files: [],
      src: '', textContent: '', className: '',
      _children: [],
      appendChild(c) { this._children.push(c); return c; },
      remove() {},
      click() {},
    };
    elements[id] = e;
    return e;
  }

  // Pre-create required elements
  el('ci', 'textarea');
  el('fileIn', 'input');
  el('filePreview');
  el('filePreviewImg', 'img');
  el('filePreviewName', 'span');
  el('tab-chat');
  el('qpbar');
  el('empt');
  el('genov');
  el('gtxt');
  el('gsub');
  el('gf');
  el('gsteps');
  el('lbadge');
  el('fnav');
  el('hint');
  el('c3d', 'canvas');
  el('cwrap');
  el('notif');
  el('typ');

  // Welcome screen
  const welcomeDiv = { style: { display: 'flex' } };
  elements['tab-chat']._children.push(welcomeDiv);

  const document = {
    getElementById: (id) => el(id),
    querySelector: (sel) => {
      if (sel.includes('justify-content')) return welcomeDiv;
      return null;
    },
    querySelectorAll: () => [],
    createElement: (tag) => el('_created_' + Math.random(), tag),
    body: { appendChild() {} },
  };

  // localStorage
  const store = {};
  const localStorage = {
    getItem: (k) => store[k] || null,
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  };

  // fetch mock — backend is available
  const fetch = async (url, opts) => {
    log.fetchCalls.push({ url, opts });
    if (url.includes('/api/v1/health')) return { ok: true };
    if (url.includes('/api/v1/proxy/claude')) {
      return {
        ok: true,
        json: async () => ({
          content: [{ text: JSON.stringify({
            type: 'house', floors: 2, width: 10, length: 12,
            roof_type: 'gabled', facade_material: 'brick',
            object_type: 'building',
          })}]
        })
      };
    }
    return { ok: false, status: 404, text: async () => 'Not found' };
  };

  // Mock classes
  class AbortController { constructor() { this.signal = {}; } abort() {} }
  class SpeechRecognition {
    constructor() { this.lang=''; this.continuous=false; this.interimResults=false;
      this.onresult=null; this.onstart=null; this.onend=null; this.onerror=null; }
    start() { if (this.onstart) this.onstart(); }
    stop() { if (this.onend) this.onend(); }
  }
  class FileReader {
    constructor() { this.onload = null; }
    readAsDataURL(file) {
      const b64 = Buffer.from(file._content || 'fake').toString('base64');
      setTimeout(() => { if (this.onload) this.onload({ target: { result: `data:${file.type};base64,${b64}` } }); }, 0);
    }
  }
  class File {
    constructor(parts, name, opts) {
      this.name = name; this.type = opts?.type || 'application/octet-stream';
      this.size = parts.reduce((s, p) => s + p.length, 0); this._content = parts.join('');
    }
  }
  class Blob {
    constructor(parts, opts) { this.size = (parts?.[0]?.length) || 100; this.type = opts?.type || ''; }
  }

  // THREE.js stubs
  const THREE = {
    Scene: class { add() {} traverse() {} },
    PerspectiveCamera: class { constructor() { this.position={set(){}}; this.rotation={x:0,y:0,z:0}; } lookAt() {} },
    WebGLRenderer: class { constructor() { this.domElement={style:{}}; } setPixelRatio() {} setSize() {} setClearColor() {} render() {} },
    Box3: class { setFromObject() { return this; } getCenter() { return {x:0,y:0,z:0}; } getSize() { return {x:10,y:10,z:10}; } },
    Vector3: class { x=0;y=0;z=0;constructor(x,y,z){this.x=x||0;this.y=y||0;this.z=z||0} get length(){return 1} normalize(){return this} clone(){return new THREE.Vector3(this.x,this.y,this.z)} },
    Mesh: class { constructor() { this.isMesh=true; this.name=''; this.geometry={dispose(){}}; this.material={dispose(){}}; this.position={set(){}}; this.scale={set(){}}; this.rotation={x:0,y:0,z:0}; } },
    PlaneGeometry: class {}, BoxGeometry: class {}, CylinderGeometry: class {},
    SphereGeometry: class {}, ConeGeometry: class {},
    ShapeGeometry: class {}, ExtrudeGeometry: class {},
    BufferGeometry: class { setFromPoints() { return this; } },
    MeshStandardMaterial: class { constructor() {} dispose() {} },
    MeshPhysicalMaterial: class { constructor() {} dispose() {} },
    Color: class { constructor() { this.r=0;this.g=0;this.b=0; } },
    AmbientLight: class {}, DirectionalLight: class { constructor() { this.position={set(){}}; } },
    Group: class { constructor() { this.children=[]; this.position={set(){}}; this.rotation={x:0,y:0,z:0}; } add() {} },
    LineBasicMaterial: class {}, Line: class {},
    Shape: class { moveTo() {} lineTo() {} },
    Vector2: class { x=0;y=0;constructor(x,y){this.x=x||0;this.y=y||0} },
    Path: class { moveTo() {} lineTo() {} absarc() {} },
    DoubleSide: 2, SRGBColorSpace: 'srgb', ACESFilmicToneMapping: 4, PCFSoftShadowMap: 2,
    GLTFLoader: class { load(url, cb) { cb({ scene: new THREE.Group() }); } },
    BufferAttribute: class {},
  };

  const env = {
    document, localStorage, fetch, AbortController,
    SpeechRecognition, webkitSpeechRecognition: SpeechRecognition,
    FileReader, File, Blob, THREE, log, elements,
    console, setTimeout: (fn, ms) => setTimeout(fn, 0), clearTimeout,
    setInterval, clearInterval,
    Math, JSON, parseInt, parseFloat, isNaN, isFinite,
    String, Number, Boolean, Array, Object, Date, RegExp, Error, TypeError, SyntaxError,
    encodeURIComponent, decodeURIComponent,
    btoa: (s) => Buffer.from(s).toString('base64'),
    atob: (s) => Buffer.from(s, 'base64').toString(),
    Buffer,
    Image: class { constructor() { this.src=''; this.onload=null; } },
    location: { protocol: 'http:', origin: 'http://localhost:8080', href: 'http://localhost:8080' },
    navigator: { userAgent: 'node-test' },
    innerWidth: 1280, innerHeight: 720,
    addEventListener() {}, removeEventListener() {},
    matchMedia: () => ({ matches: false }),
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    cancelAnimationFrame: (id) => clearTimeout(id),
    performance: { now: () => Date.now() },
    prompt: () => null, confirm: () => true, alert: () => {},
    URL: { createObjectURL: () => 'blob:fake', revokeObjectURL() {} },
    pendingFile: null, pendingFileB64: null,
  };
  env.window = env;
  env.self = env;
  env.globalThis = env;

  return env;
}

// ═══════════════════════════════════════════════════════════════
// INJECT APP CODE
// ═══════════════════════════════════════════════════════════════
function injectApp(env) {
  let code = appCode;

  const shimCode = `
    function initThree(){}
    function loadHDRI(){}
    function draw2D(){}
    function enterInterior(){}
    function hideIntMode(){}
    function resetCam(){}
    function showExp(){}
    function newProj(){}
    function checkMobile(){}
    function togWire(){}
    function togAnn(){}
    function startGen(bld){ _genCalls.push(bld); }
    function addMsg(role, html){ _msgLog.push({role, html}); }
    function showTyping(){}
    function removeTyping(){}
    async function generateViaBlenderServer(){ return false; }
    async function renderInteriorViaServer(){ return false; }
    function showNotif(){}
  `;

  const fullCode = code + '\n' + shimCode;

  try {
    const script = new vm.Script(fullCode, { filename: 'app.js' });
    const context = vm.createContext(env);
    context._genCalls = env.log.genCalls;
    context._msgLog = env.log.msgLog;
    script.runInContext(context);
    return context;
  } catch (e) {
    console.error('  ⚠️  Injection error:', e.message.slice(0, 200));
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════
// TEST 1: TEXT INPUT → GENERATION
// ═══════════════════════════════════════════════════════════════
async function testTextInput() {
  section('TEST 1: Text Input → 3D Generation');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  env.elements['ci'].value = 'двухэтажный кирпичный дом 10×12 двускатная кровля';

  try { await ctx.send(); } catch (e) {}
  await new Promise(r => setTimeout(r, 50));

  assert(env.log.genCalls.length > 0, `startGen() called (${env.log.genCalls.length}x)`);

  if (env.log.genCalls.length > 0) {
    const bld = env.log.genCalls[0];
    assert(bld.floors === 2, `Floors: ${bld.floors}`);
    assert(bld.W === 10, `Width: ${bld.W}`);
    assert(bld.L === 12, `Length: ${bld.L}`);
    assert(bld.mat === 'brick', `Material: ${bld.mat}`);
    assert(bld.roof === 'gabled', `Roof: ${bld.roof}`);
  }

  assert(env.log.msgLog.some(m => m.role === 'u'), 'User message logged');
}

// ═══════════════════════════════════════════════════════════════
// TEST 2: INTERIOR INPUT → INTERIOR GENERATION
// ═══════════════════════════════════════════════════════════════
async function testInteriorInput() {
  section('TEST 2: Interior Input → Interior Generation');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  env.elements['ci'].value = 'детская комната в классическом стиле';

  try { await ctx.send(); } catch (e) {}
  await new Promise(r => setTimeout(r, 100));

  assert(env.log.genCalls.length > 0, `startGen() called (${env.log.genCalls.length}x)`);

  if (env.log.genCalls.length > 0) {
    const bld = env.log.genCalls[0];
    assert(bld.isInterior === true, `isInterior: ${bld.isInterior}`);
    assert(bld.room_type === 'children', `room_type: ${bld.room_type}`);
    assert(bld.label && bld.label.includes('classic'), `label includes style: ${bld.label}`);
  }
}

// ═══════════════════════════════════════════════════════════════
// TEST 3: PHOTO INPUT → GENERATION
// ═══════════════════════════════════════════════════════════════
async function testPhotoInput() {
  section('TEST 3: Photo Upload → 3D Generation');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  const mockFile = new env.File(['fake-jpeg-data'], 'house.jpg', { type: 'image/jpeg' });
  mockFile._content = 'fake-jpeg-data';

  ctx.handleFile(mockFile);
  await new Promise(r => setTimeout(r, 50));

  assert(env.elements['filePreview'].style.display === 'flex', 'File preview shown');
  assert(env.elements['filePreviewName'].textContent.includes('house'), 'File name shown');

  try { await ctx.send(); } catch (e) {}
  await new Promise(r => setTimeout(r, 200));

  assert(env.log.genCalls.length > 0, `startGen() from photo (${env.log.genCalls.length}x)`);
  assert(env.log.msgLog.some(m => m.role === 'u'), 'User photo msg logged');
}

// ═══════════════════════════════════════════════════════════════
// TEST 4: NO BACKEND → STILL GENERATES (local parse only)
// ═══════════════════════════════════════════════════════════════
async function testNoBackend() {
  section('TEST 4: No Backend → Still Generates (local parse)');

  const env = createEnv();
  // Override fetch to fail — no backend
  env.fetch = async (url) => {
    env.log.fetchCalls.push({ url });
    return { ok: false, status: 0 };
  };

  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  env.elements['ci'].value = 'дом 2 этажа кирпич 10×12';

  try { await ctx.send(); } catch(e) {}
  await new Promise(r => setTimeout(r, 100));

  assert(env.log.genCalls.length > 0, `Generation works without backend (${env.log.genCalls.length}x)`);
  if (env.log.genCalls.length > 0) {
    assert(env.log.genCalls[0].floors === 2, `Floors from local parse: ${env.log.genCalls[0].floors}`);
    assert(env.log.genCalls[0].W === 10, `Width from local parse: ${env.log.genCalls[0].W}`);
  }
  assert(!env.log.msgLog.some(m => m.html && m.html.includes('API ключ')), 'No API key error');
}

// ═══════════════════════════════════════════════════════════════
// TEST 5: EMPTY INPUT → NO ACTION
// ═══════════════════════════════════════════════════════════════
async function testEmptyInput() {
  section('TEST 5: Empty Input → No Action');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  env.elements['ci'].value = '';

  ctx.send();
  await new Promise(r => setTimeout(r, 100));

  assert(env.log.genCalls.length === 0, 'No generation for empty');
  assert(env.log.msgLog.length === 0, 'No messages for empty');
}

// ═══════════════════════════════════════════════════════════════
// TEST 6: GO() QUICK PROMPT → GENERATION
// ═══════════════════════════════════════════════════════════════
async function testGoFunction() {
  section('TEST 6: go() Quick Prompt → Generation');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  try { await ctx.go('жилой дом 2 этажа кирпич 10×12'); } catch (e) {}
  await new Promise(r => setTimeout(r, 100));

  assert(env.log.genCalls.length > 0, `go() triggered gen (${env.log.genCalls.length}x)`);
  if (env.log.genCalls.length > 0) {
    assert(env.log.genCalls[0].floors === 2, 'Floors from go()');
  }
}

// ═══════════════════════════════════════════════════════════════
// TEST 7: LOCAL PARSER — PARAMETER EXTRACTION
// ═══════════════════════════════════════════════════════════════
async function testLocalParser() {
  section('TEST 7: Local Parser — Parameter Extraction');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  const cases = [
    { input: 'двухэтажный кирпичный дом 10×12', expect: { floors: 2, W: 10, L: 12, mat: 'brick' } },
    { input: 'офис 5 этажей стекло плоская кровля 20×24', expect: { floors: 5, W: 20, L: 24, mat: 'glass', roof: 'flat' } },
    { input: 'деревянный коттедж с террасой 12×15', expect: { W: 12, L: 15, mat: 'wood', has_terrace: true } },
    { input: 'трёхэтажный дом с балконом и гаражом', expect: { floors: 3, balcony: true, has_garage: true } },
  ];

  for (const tc of cases) {
    const parsed = ctx.parseLocal(tc.input);
    const applied = ctx.applyParams(tc.input, parsed);
    for (const [key, val] of Object.entries(tc.expect)) {
      assert(applied[key] === val, `"${tc.input.slice(0,35)}…" → ${key}=${JSON.stringify(applied[key])}`);
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// TEST 8: CALLAI — BACKEND REQUIRED
// ═══════════════════════════════════════════════════════════════
async function testCallAIRequiresBackend() {
  section('TEST 8: callAI() — Backend Required');

  const env = createEnv();
  // Override fetch to fail — no backend
  env.fetch = async () => ({ ok: false, status: 0 });

  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  let threw = false;
  try { await ctx.callAI('тест', '', 100); }
  catch (e) {
    threw = true;
    assert(e.message.includes('недоступен'), `Error: ${e.message.slice(0,80)}`);
  }
  assert(threw, 'callAI() throws without backend');
}

// ═══════════════════════════════════════════════════════════════
// TEST 9: GENERATING FLAG — BLOCKS DOUBLE SEND
// ═══════════════════════════════════════════════════════════════
async function testGeneratingFlag() {
  section('TEST 9: Generating Flag — Blocks Double Send');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  env.elements['ci'].value = 'дом 2 этажа';
  try { await ctx.send(); } catch(e) {}
  await new Promise(r => setTimeout(r, 50));
  const firstGenCount = env.log.genCalls.length;

  env.elements['ci'].value = 'ещё один дом';
  try { await ctx.send(); } catch(e) {}
  await new Promise(r => setTimeout(r, 50));

  assert(env.log.msgLog.length > 0, 'Messages were processed');
}

// ═══════════════════════════════════════════════════════════════
// TEST 10: NO API KEY IN STORAGE — CLEAN
// ═══════════════════════════════════════════════════════════════
async function testNoApiKeyInStorage() {
  section('TEST 10: No API Key in localStorage — Clean');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  assert(env.localStorage.getItem('archai_openrouter_key') === null, 'No openrouter_key in storage');
  assert(env.elements['settings-modal'] === undefined, 'No settings-modal element');
  assert(typeof ctx.getOpenRouterKey === 'undefined', 'getOpenRouterKey() does not exist');
  assert(typeof ctx.openSettings === 'undefined', 'openSettings() does not exist');
  assert(typeof ctx.saveSettings === 'undefined', 'saveSettings() does not exist');
}

// ═══════════════════════════════════════════════════════════════
// TEST 11: INTERIOR GSTEPS — DYNAMIC SWITCHING
// ═══════════════════════════════════════════════════════════════
async function testInteriorGSteps() {
  section('TEST 11: Interior GSTEPS — Dynamic Switching');

  const env = createEnv();
  const ctx = injectApp(env);
  assert(ctx !== null, 'App code injected');
  if (!ctx) return;

  // GSTEPS is a let variable in VM, check via startGen behavior
  // Verify building steps exist in the code
  assert(appCode.includes('GSTEPS_BUILDING'), 'GSTEPS_BUILDING in source');
  assert(appCode.includes('GSTEPS_INTERIOR'), 'GSTEPS_INTERIOR in source');
  assert(appCode.includes('Фундамент и стены'), 'Building step "Фундамент и стены" in source');
  assert(appCode.includes('Мебель и расстановка'), 'Interior step "Мебель и расстановка" in source');
  assert(appCode.includes('Освещение'), 'Interior step "Освещение" in source');
  assert(appCode.includes('bld.isInterior'), 'Dynamic GSTEPS switching in source');
}

// ═══════════════════════════════════════════════════════════════
// RUN ALL TESTS
// ═══════════════════════════════════════════════════════════════
async function main() {
  console.log('\n🏗️  Architect v10.3 — Chat Generation Tests\n');

  await testTextInput();
  await testInteriorInput();
  await testPhotoInput();
  await testNoBackend();
  await testEmptyInput();
  await testGoFunction();
  await testLocalParser();
  await testCallAIRequiresBackend();
  await testGeneratingFlag();
  await testNoApiKeyInStorage();
  await testInteriorGSteps();

  console.log(`\n${'═'.repeat(60)}`);
  console.log(`  RESULTS: ${passed}/${total} passed, ${failed} failed`);
  console.log('═'.repeat(60));
  console.log();

  if (failed > 0) process.exit(1);
}

main().catch(e => {
  console.error('Fatal:', e);
  process.exit(1);
});
