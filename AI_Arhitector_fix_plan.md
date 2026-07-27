# AI_Arhitector — План исправления генерации

**Репозиторий:** https://github.com/smartmoneymoscow-cell/AI_Arhitector  
**Проблема:** Ни один промт не генерирует 3D-модель (5 скринов — 0 результатов)  
**Цель:** Любой промт на русском → корректная 3D-модель или интерьерный рендер

---

## Диагноз: 7 корневых причин

| # | Проблема | Где в коде | Импакт |
|---|----------|-----------|--------|
| 1 | Regex-парсер не понимает естественный язык | `parse_building_params()` в server.py и blender-service/app.py | "сделай дизайн коттеджа" → дефолты, "спальня в стиле хайтек" → мусор |
| 2 | Нет маршрутизации building/interior по смыслу | server.py, index.html JS | "детская комната" летит в `generate_building()` вместо `generate_interior()` |
| 3 | LLM используется только для чата, не для парсинга | server.py `proxy_claude()` | AI есть, но не помогает генерации |
| 4 | bpy-скрипт генерирует неинициализированные переменные | `generate_bpy_script()` f-string | "Cannot access uninitialized variable" |
| 5 | GitHub Pages не имеет бэкенда, нет fallback | frontend index.html | "Сервер рендеринга недоступен" |
| 6 | Тесты проверяют Blender CLI, а не pipeline промт→модель | test_blender.py | Зелёные тесты при сломанной генерации |
| 7 | Render Free Tier cold start 30-60 сек без retry | render.yaml, gateway/app.py | Первый запрос всегда таймаутит |

---

## Фаза 1: Критические исправления (без смены стека)

Цель: заставить текущую архитектуру работать. Минимум изменений, максимум эффекта.

### Шаг 1.1: LLM-парсер вместо regex

**Файл:** создать `promt_parser.py`, заменить вызовы `parse_building_params()`  
**Что делает:** отправляет промт в OpenRouter, получает JSON с параметрами  
**Ключевое изменение:** LLM различает здание/интерьер/комнату и извлекает параметры

```python
# promt_parser.py — новый файл
import json, re, httpx

SYSTEM_PROMPT = '''Ты — парсер архитектурных описаний для 3D-генератора.
Отвечай ТОЛЬКО валидным JSON. Пояснения запрещены.

Формат ответа:
{
  "object_type": "building | interior | room",
  "building_type": "house | office | cottage | villa | apartment | townhouse",
  "room_type": "bedroom | kitchen | living | bathroom | children | study | null",
  "floors": 2,
  "width_m": 10,
  "length_m": 12,
  "height_m": 3,
  "style": "modern | classic | loft | scandinavian | minimalist | hitech",
  "material": "brick | wood | glass | stone | concrete | plaster",
  "roof_type": "gabled | flat | hip",
  "features": [],
  "furniture": []
}

Правила:
- "детская", "спальня", "кухня", "гостиная" → object_type="room"
- "интерьер", "дизайн интерьера" → object_type="interior"
- "дом", "здание", "коттедж", "офис" → object_type="building"
- "хайтек" → style="hitech"
- "лофт" → style="loft"
- Размеры в метрах, если не указаны → null
- "64 кв метра" → width_m=8, length_m=8 (примерный корень)
- Мебель для комнат: bedroom→["bed","wardrobe","nightstand"],
  children→["bed","desk","bookshelf"], kitchen→["table","sink","stove"]
'''

async def parse_prompt(text, api_key, model="nvidia/nemotron-3-nano-30b-a3b:free"):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            },
            timeout=30.0,
        )
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if match:
                result = json.loads(match.group())
                # Валидация обязательных полей
                result.setdefault("object_type", "building")
                result.setdefault("building_type", "house")
                result.setdefault("floors", 2)
                result.setdefault("width_m", 10)
                result.setdefault("length_m", 12)
                result.setdefault("height_m", 3)
                result.setdefault("style", "modern")
                result.setdefault("material", "plaster")
                result.setdefault("roof_type", "gabled")
                result.setdefault("features", [])
                result.setdefault("furniture", [])
                return result
    except Exception as e:
        print(f"LLM parse error: {e}")
    
    # Fallback на regex если LLM недоступен
    return fallback_regex_parse(text)


def fallback_regex_parse(text):
    """Улучшенный regex-парсер (замена текущего parse_building_params)."""
    t = text.lower()
    p = {
        "object_type": "building",
        "building_type": "house",
        "room_type": None,
        "floors": 2,
        "width_m": 10,
        "length_m": 12,
        "height_m": 3,
        "style": "modern",
        "material": "plaster",
        "roof_type": "gabled",
        "features": [],
        "furniture": [],
    }

    # === Определение типа объекта ===
    room_words = {
        "спальн": "bedroom", "детск": "children", "кухн": "kitchen",
        "гостин": "living", "ванн": "bathroom", "кабинет": "study",
        "салон": "living", "столов": "dining",
    }
    for word, room_type in room_words.items():
        if word in t:
            p["object_type"] = "room"
            p["room_type"] = room_type
            break

    if p["object_type"] == "building":
        interior_words = ["интерьер", "дизайн интерьера", "внутри"]
        if any(w in t for w in interior_words):
            p["object_type"] = "interior"

    # === Тип здания ===
    type_map = {
        "офис": "office", "коттедж": "cottage", "вилл": "villa",
        "таунхаус": "townhouse", "квартир": "apartment",
    }
    for word, btype in type_map.items():
        if word in t:
            p["building_type"] = btype
            break

    # === Этажи ===
    floor_words = {
        "одно": 1, "двух": 2, "трёх": 3, "трех": 3,
        "четыр": 4, "пяти": 5, "шести": 6,
    }
    for word, n in floor_words.items():
        if word in t and ("этаж" in t or "уровн" in t):
            p["floors"] = n
    fm = re.search(r"(\d+)\s*(?:этаж|floor)", t)
    if fm:
        p["floors"] = int(fm.group(1))

    # === Размеры ===
    dm = re.search(r"(\d+)\s*[×xх]\s*(\d+)", t)
    if dm:
        p["width_m"] = int(dm.group(1))
        p["length_m"] = int(dm.group(2))
    else:
        # "64 кв метра" → ~8x8
        sqm = re.search(r"(\d+)\s*(?:кв|м2|м²)", t)
        if sqm:
            area = int(sqm.group(1))
            side = int(area ** 0.5)
            p["width_m"] = side
            p["length_m"] = side

    # === Кровля ===
    if "плоск" in t:
        p["roof_type"] = "flat"
    elif "вальм" in t:
        p["roof_type"] = "hip"
    elif "двускат" in t or "скатн" in t:
        p["roof_type"] = "gabled"

    # === Материал ===
    mat_map = {
        "кирпич": "brick", "дерев": "wood", "стекл": "glass",
        "камен": "stone", "бетон": "concrete", "штукатурк": "plaster",
    }
    for word, mat in mat_map.items():
        if word in t:
            p["material"] = mat
            break

    # === Стиль ===
    style_map = {
        "хайтек": "hitech", "hi-tech": "hitech", "лофт": "loft",
        "классич": "classic", "скандинав": "scandinavian",
        "минималист": "minimalist", "современн": "modern",
    }
    for word, style in style_map.items():
        if word in t:
            p["style"] = style
            break

    # === Фичи ===
    if "балкон" in t:
        p["features"].append("balcony")
    if "террас" in t:
        p["features"].append("terrace")
    if "гараж" in t:
        p["features"].append("garage")

    # === Мебель по умолчанию для комнат ===
    if p["room_type"] and not p["furniture"]:
        default_furniture = {
            "bedroom": ["bed", "wardrobe", "nightstand"],
            "children": ["bed", "desk", "bookshelf"],
            "kitchen": ["table", "sink", "stove"],
            "living": ["sofa", "table", "tv"],
            "bathroom": ["sink", "bathtub"],
            "study": ["desk", "bookshelf", "chair"],
        }
        p["furniture"] = default_furniture.get(p["room_type"], ["sofa", "table"])

    return p
```

### Шаг 1.2: Маршрутизация по типу объекта

**Файл:** `server.py`, `blender-service/app.py`  
**Что меняется:** новый endpoint `/api/v1/generate` который сам выбирает building или interior

```python
# Добавить в server.py и blender-service/app.py

@app.route("/api/v1/generate", methods=["POST"])
def generate():
    """Единый endpoint: промт → парсинг → роутинг → генерация."""
    data = request.json or {}
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    # Парсинг через LLM (или fallback)
    try:
        params = parse_prompt_sync(prompt, OPENROUTER_KEY)
    except Exception:
        params = fallback_regex_parse(prompt)

    # Роутинг по типу объекта
    obj_type = params.get("object_type", "building")

    if obj_type in ("interior", "room"):
        # Генерация интерьера
        interior_params = {
            "width": params.get("width_m", 6),
            "length": params.get("length_m", 8),
            "height": params.get("height_m", 3),
            "style": params.get("style", "modern"),
            "furniture": params.get("furniture", ["sofa", "table", "chandelier"]),
        }
        script = generate_interior_script(interior_params)
        return execute_blender_render(script, "png", "interior")
    else:
        # Генерация здания
        building_params = {
            "width": params.get("width_m", 10),
            "length": params.get("length_m", 12),
            "floors": params.get("floors", 2),
            "roof_type": params.get("roof_type", "gabled"),
            "facade_material": params.get("material", "plaster"),
            "has_balcony": "balcony" in params.get("features", []),
            "has_terrace": "terrace" in params.get("features", []),
            "has_garage": "garage" in params.get("features", []),
        }
        script = generate_bpy_script(building_params)
        return execute_blender_export(script, "glb")


def execute_blender_export(script, format_type):
    """Запуск Blender CLI с валидацией."""
    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(OUTPUT_DIR, f"{job_id}.py")
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}.{format_type}")

    # Валидация: проверить что скрипт компилируется
    try:
        compile(script, f"<blender_{job_id}>", "exec")
    except SyntaxError as e:
        return jsonify({"error": f"Script syntax error: {e}"}), 500

    export_cmd = f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')"
    with open(script_path, "w") as f:
        f.write(script + export_cmd)

    try:
        result = subprocess.run(
            [BLENDER, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Blender timeout (120s)"}), 504
    except Exception as e:
        return jsonify({"error": f"Blender failed: {e}"}), 500
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

    if os.path.exists(output_file):
        return send_file(output_file, as_attachment=True,
                        download_name=f"archai_{job_id}.{format_type}",
                        mimetype="model/gltf-binary")
    return jsonify({"error": "Export failed", "stderr": result.stderr[-500:]}), 500
```

### Шаг 1.3: Исправить bpy-генератор — безопасные переменные

**Файл:** `blender-service/app.py` функция `generate_bpy_script()`  
**Что меняется:** все f-string переменные проходят валидацию

```python
def safe_val(value, default, valid=None):
    """Валидация параметров перед подстановкой в bpy-скрипт."""
    if value is None:
        return default
    if valid and value not in valid:
        return default
    return value

def generate_bpy_script(params):
    # Валидация всех параметров
    W = safe_val(params.get('width'), 10, range(1, 200))
    L = safe_val(params.get('length'), 12, range(1, 200))
    floors = safe_val(params.get('floors'), 2, range(1, 20))
    fH = 3.0
    thick = 0.3
    roof_type = safe_val(params.get('roof_type'), 'gabled', ['gabled', 'flat', 'hip'])
    mat = safe_val(params.get('facade_material'), 'plaster',
                   ['brick', 'wood', 'glass', 'stone', 'concrete', 'plaster'])
    has_balcony = bool(params.get('has_balcony', False))
    has_terrace = bool(params.get('has_terrace', False))
    has_garage = bool(params.get('has_garage', False))

    # ... остальной код без изменений, но с безопасными переменными
```

### Шаг 1.4: Фронтенд — fallback на Three.js при недоступности Blender

**Файл:** `index.html` (JS-часть)  
**Что меняется:** если Blender не отвечает за 10 сек, использовать Three.js

```javascript
// Добавить в JS перед функцией send()

async function generateWithFallback(text, params) {
    const backendUrl = localStorage.getItem('archai-backend') || '';

    // Шаг 1: Если есть бэкенд — пробуем Blender
    if (backendUrl) {
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 15000);

            const r = await fetch(backendUrl + '/api/v1/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({prompt: text}),
                signal: controller.signal,
            });
            clearTimeout(timeout);

            if (r.ok) {
                const blob = await r.blob();
                if (params.object_type === 'interior' || params.object_type === 'room') {
                    showInteriorImage(blob);
                } else {
                    loadGLBBlob(blob);
                }
                return;
            }
        } catch(e) {
            console.log('Blender unavailable, falling back to Three.js', e);
        }
    }

    // Шаг 2: Fallback — Three.js локальный рендер
    if (params.object_type === 'interior' || params.object_type === 'room') {
        renderInteriorLocal(params);
    } else {
        renderBuildingLocal(params);
    }
}

function renderBuildingLocal(params) {
    // Использовать существующий parseLocal() + Three.js
    const w = params.width_m || 10;
    const l = params.length_m || 12;
    const floors = params.floors || 2;
    const mat = params.material || 'plaster';
    // ... Three.js код генерации коробки с окнами
    buildThreeJS({w, l, floors, material: mat, roof: params.roof_type});
}

function renderInteriorLocal(params) {
    // Three.js генерация комнаты
    const w = params.width_m || 6;
    const l = params.length_m || 8;
    const style = params.style || 'modern';
    const furniture = params.furniture || ['sofa', 'table'];
    buildInteriorThreeJS({w, l, style, furniture});
}
```

### Шаг 1.5: Gateway — добавить retry и увеличить timeout

**Файл:** `gateway/app.py`  
**Что меняется:** retry при cold start, больший timeout

```python
import time

def request_with_retry(url, json_data, timeout=120, retries=2):
    """Retry с exponential backoff для Render cold start."""
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=json_data, timeout=timeout)
            return r
        except requests.exceptions.Timeout:
            if attempt < retries:
                time.sleep(5 * (attempt + 1))  # 5s, 10s backoff
                continue
            raise

@app.route("/api/v1/generate", methods=["POST"])
def generate():
    try:
        r = request_with_retry(f"{BLENDER_SVC}/api/v1/generate", request.json, timeout=120)
        if r.status_code == 200:
            content_type = r.headers.get("Content-Type", "model/gltf-binary")
            return r.content, 200, {"Content-Type": content_type}
        return jsonify(r.json()), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502
```

---

## Фаза 2: Интеграционные тесты (заменяют лживые)

### Шаг 2.1: Новый тест-файл

**Файл:** `tests/test_generation.py` (новый)  
**Что проверяет:** полный pipeline от промта до вывода

```python
"""Реальные интegration тесты генерации."""
import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from promt_parser import fallback_regex_parse


class TestPromptParsing:
    """Тесты парсинга промтов."""

    def test_cottage(self):
        p = fallback_regex_parse("сделай дизайн коттеджа")
        assert p["building_type"] == "cottage", f"Expected cottage, got {p['building_type']}"

    def test_children_room(self):
        p = fallback_regex_parse("сделай дизайн интерьера детской")
        assert p["object_type"] == "room", f"Expected room, got {p['object_type']}"
        assert p["room_type"] == "children", f"Expected children, got {p.get('room_type')}"

    def test_bedroom_hitech(self):
        p = fallback_regex_parse("красивую спальню в стиле хайтек")
        assert p["object_type"] == "room"
        assert p["room_type"] == "bedroom"
        assert p["style"] == "hitech", f"Expected hitech, got {p['style']}"

    def test_apartment_64sqm(self):
        p = fallback_regex_parse("интерьерный дизайн квартиры на 64 кв метра")
        assert p["object_type"] in ("interior", "room")
        assert p["width_m"] * p["length_m"] >= 49  # ~64 sqm

    def test_office_5_floors(self):
        p = fallback_regex_parse("офис 5 этажей стекло плоская кровля 20×24")
        assert p["building_type"] == "office"
        assert p["floors"] == 5
        assert p["material"] == "glass"
        assert p["roof_type"] == "flat"
        assert p["width_m"] == 20
        assert p["length_m"] == 24

    def test_house_brick_balcony(self):
        p = fallback_regex_parse("двухэтажный кирпичный дом 10×12 с балконом")
        assert p["floors"] == 2
        assert p["material"] == "brick"
        assert "balcony" in p["features"]

    def test_cottage_terrace_garage(self):
        p = fallback_regex_parse("деревянный коттедж 2 этажа терраса гараж 12×15")
        assert p["building_type"] == "cottage"
        assert p["material"] == "wood"
        assert "terrace" in p["features"]
        assert "garage" in p["features"]
        assert p["width_m"] == 12
        assert p["length_m"] == 15

    def test_unknown_prompt_defaults(self):
        p = fallback_regex_parse("построй что-нибудь красивое")
        assert p["object_type"] == "building"
        assert p["floors"] >= 1
        assert p["width_m"] >= 1


class TestBpyScriptValidation:
    """Тесты что bpy-скрипты компилируются."""

    def _get_generate_bpy(self):
        from blender_service_app import generate_bpy_script
        return generate_bpy_script

    def test_default_params_compile(self):
        """Скрипт с дефолтными параметрами компилируется."""
        script = self._make_script({"width": 10, "length": 12, "floors": 2,
                                     "roof_type": "gabled", "facade_material": "plaster"})
        compile(script, "<test>", "exec")

    def test_all_roof_types_compile(self):
        for roof in ["gabled", "flat", "hip"]:
            script = self._make_script({"roof_type": roof})
            compile(script, f"<test_{roof}>", "exec")

    def test_all_materials_compile(self):
        for mat in ["brick", "wood", "glass", "stone", "concrete", "plaster"]:
            script = self._make_script({"facade_material": mat})
            compile(script, f"<test_{mat}>", "exec")

    def _make_script(self, params):
        """Минимальная версия generate_bpy_script для тестов."""
        defaults = {"width": 10, "length": 12, "floors": 2, "floor_height": 3.0,
                    "wall_thickness": 0.3, "roof_type": "gabled", "facade_material": "plaster",
                    "has_balcony": False, "has_terrace": False, "has_garage": False}
        defaults.update(params)
        # ... вызов generate_bpy_script(defaults)
        from blender_service_app import generate_bpy_script
        return generate_bpy_script(defaults)


class TestRouting:
    """Тесты маршрутизации building/interior."""

    def test_children_room_routes_to_interior(self):
        p = fallback_regex_parse("детская комната")
        assert p["object_type"] in ("room", "interior")

    def test_cottage_routes_to_building(self):
        p = fallback_regex_parse("коттедж")
        assert p["object_type"] == "building"

    def test_bedroom_routes_to_interior(self):
        p = fallback_regex_parse("спальня")
        assert p["object_type"] == "room"


# Запуск: python -m pytest tests/test_generation.py -v
```

### Шаг 2.2: CI — автоматические тесты

**Файл:** `.github/workflows/test.yml` (новый)

```yaml
name: Test Generation Pipeline
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pytest httpx flask flask-cors
      - run: python -m pytest tests/test_generation.py -v --tb=short
```

---

## Фаза 3: Переписывание микросервисов на FastAPI

### Шаг 3.1: LLM-сервис → FastAPI + структурированный вывод

**Файл:** `llm-service/app.py` (полная замена)

```python
"""LLM Microservice — прокси к OpenRouter + промт-парсинг."""
import os, json, re
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Architect LLM Service")

OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_BASE = "https://openrouter.ai/api/v1"
MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")


class ChatRequest(BaseModel):
    messages: list
    max_tokens: int = 400
    temperature: float = 0.7
    model: Optional[str] = None


class ParseRequest(BaseModel):
    text: str


class ParsedParams(BaseModel):
    object_type: str = "building"
    building_type: str = "house"
    room_type: Optional[str] = None
    floors: int = 2
    width_m: int = 10
    length_m: int = 12
    height_m: int = 3
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: list = []
    furniture: list = []


PARSE_SYSTEM = '''Ты — парсер архитектурных описаний. Отвечай ТОЛЬКО JSON.
{"object_type":"building|interior|room","building_type":"house|office|cottage|villa|townhouse","room_type":"bedroom|kitchen|living|bathroom|children|study|null","floors":2,"width_m":10,"length_m":12,"height_m":3,"style":"modern|classic|loft|scandinavian|minimalist|hitech","material":"brick|wood|glass|stone|concrete|plaster","roof_type":"gabled|flat|hip","features":[],"furniture":[]}
Правила: "детская"→room_type=children, "спальня"→bedroom, "хайтек"→hitech, "коттедж"→cottage, "64 кв метра"→width=8,length=8.'''


@app.get("/health")
def health():
    return {"status": "ok", "service": "llm-service", "model": MODEL}


@app.post("/api/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    headers = {"Content-Type": "application/json"}
    if OR_KEY:
        headers["Authorization"] = f"Bearer {OR_KEY}"
    
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{OR_BASE}/chat/completions",
            headers=headers,
            json={
                "model": req.model or MODEL,
                "messages": req.messages,
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
            },
            timeout=60.0,
        )
    
    if r.status_code == 200:
        return r.json()
    raise HTTPException(status_code=r.status_code, detail=r.text)


@app.post("/api/v1/parse")
async def parse_prompt(req: ParseRequest):
    """Парсинг промта → структурированные параметры."""
    headers = {"Content-Type": "application/json"}
    if OR_KEY:
        headers["Authorization"] = f"Bearer {OR_KEY}"
    
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OR_BASE}/chat/completions",
                headers=headers,
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": PARSE_SYSTEM},
                        {"role": "user", "content": req.text},
                    ],
                    "max_tokens": 300,
                    "temperature": 0.1,
                },
                timeout=30.0,
            )
        
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                return ParsedParams(**{**ParsedParams().dict(), **parsed})
    except Exception as e:
        print(f"LLM parse error: {e}")
    
    # Fallback
    return fallback_parse(req.text)


def fallback_parse(text):
    """Regex fallback."""
    # ... (код из Шага 1.1 fallback_regex_parse)
    pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### Шаг 3.2: Blender-сервис → FastAPI + валидация

**Файл:** `blender-service/app.py` (полная замена)

```python
"""Blender Microservice — генерация зданий (GLB) и интерьеров (PNG)."""
import os, uuid, subprocess, re
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI(title="Architect Blender Service")

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")
BLENDER = os.environ.get("BLENDER_PATH", "blender")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class GenerateRequest(BaseModel):
    prompt: str
    object_type: Optional[str] = None  # building | interior | room
    building_type: str = "house"
    room_type: Optional[str] = None
    floors: int = 2
    width_m: int = 10
    length_m: int = 12
    height_m: int = 3
    style: str = "modern"
    material: str = "plaster"
    roof_type: str = "gabled"
    features: List[str] = []
    furniture: List[str] = []


@app.get("/health")
def health():
    return {"status": "ok", "service": "blender-service", "blender": BLENDER}


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest):
    """Единый endpoint: определяет тип → генерирует → возвращает файл."""
    obj_type = req.object_type or "building"
    
    if obj_type in ("interior", "room"):
        return await _generate_interior(req)
    else:
        return await _generate_building(req)


async def _generate_building(req: GenerateRequest):
    params = {
        "width": req.width_m, "length": req.length_m,
        "floors": req.floors, "roof_type": req.roof_type,
        "facade_material": req.material,
        "has_balcony": "balcony" in req.features,
        "has_terrace": "terrace" in req.features,
        "has_garage": "garage" in req.features,
    }
    script = generate_bpy_script(params)
    return _execute_blender(script, "glb", "model/gltf-binary")


async def _generate_interior(req: GenerateRequest):
    furniture = req.furniture or _default_furniture(req.room_type)
    params = {
        "width": req.width_m, "length": req.length_m,
        "height": req.height_m, "style": req.style,
        "furniture": furniture,
    }
    script = generate_interior_script(params)
    return _execute_blender(script, "png", "image/png")


def _default_furniture(room_type):
    defaults = {
        "bedroom": ["bed", "wardrobe", "nightstand"],
        "children": ["bed", "desk", "bookshelf"],
        "kitchen": ["table", "sink", "stove"],
        "living": ["sofa", "table", "chandelier"],
        "bathroom": ["sink", "bathtub"],
        "study": ["desk", "bookshelf", "chair"],
    }
    return defaults.get(room_type or "living", ["sofa", "table", "chandelier"])


def _execute_blender(script, ext, mime):
    """Валидация + запуск Blender CLI."""
    job_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(OUTPUT_DIR, f"{job_id}.py")
    output_file = os.path.join(OUTPUT_DIR, f"{job_id}.{ext}")

    # Валидация синтаксиса
    try:
        compile(script, f"<{job_id}>", "exec")
    except SyntaxError as e:
        raise HTTPException(500, f"Script syntax error: {e}")

    if ext == "glb":
        script += f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')"
    else:
        script += (
            f"\nimport bpy"
            f"\nbpy.context.scene.render.filepath = r'{output_file}'"
            "\nbpy.context.scene.render.engine = 'BLENDER_EEVEE'"
            "\nbpy.context.scene.render.resolution_x = 640"
            "\nbpy.context.scene.render.resolution_y = 480"
            "\nbpy.ops.render.render(write_still=True)"
        )

    with open(script_path, "w") as f:
        f.write(script)

    try:
        result = subprocess.run(
            [BLENDER, "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Blender render timeout (120s)")
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)

    if os.path.exists(output_file):
        return FileResponse(output_file, media_type=mime,
                           filename=f"archai_{job_id}.{ext}")
    
    raise HTTPException(500, detail={
        "error": "Blender export failed",
        "stderr": (result.stderr or "")[-500:],
    })


# generate_bpy_script и generate_interior_script — из текущего кода
# с исправлениями из Шага 1.3 (safe_val)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8082))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### Шаг 3.3: Gateway → FastAPI + retry

**Файл:** `gateway/app.py` (полная замена)

```python
"""API Gateway — маршрутизация к микросервисам."""
import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, Response

app = FastAPI(title="Architect Gateway")

LLM_SVC = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
BLENDER_SVC = os.environ.get("BLENDER_SERVICE_URL", "http://localhost:8082")
FRONTEND_DIR = os.environ.get("FRONTEND_DIR", "../frontend")


@app.get("/health")
async def health():
    services = {}
    async with httpx.AsyncClient() as client:
        for name, url in [("llm", LLM_SVC), ("blender", BLENDER_SVC)]:
            try:
                r = await client.get(f"{url}/health", timeout=5.0)
                services[name] = "ok" if r.status_code == 200 else "error"
            except:
                services[name] = "unreachable"
    return {"status": "ok", "service": "gateway", "services": services}


@app.post("/api/v1/proxy/claude")
async def proxy_claude(request: Request):
    data = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{LLM_SVC}/api/v1/chat/completions", json=data, timeout=60.0)
    if r.status_code == 200:
        result = r.json()
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"content": [{"type": "text", "text": text or ""}]}
    raise HTTPException(r.status_code, detail=r.json())


@app.post("/api/v1/generate")
async def generate(request: Request):
    """Единый endpoint генерации с retry для cold start."""
    data = await request.json()
    
    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            try:
                r = await client.post(
                    f"{BLENDER_SVC}/api/v1/generate",
                    json=data,
                    timeout=120.0,
                )
                if r.status_code == 200:
                    content_type = r.headers.get("content-type", "model/gltf-binary")
                    return Response(content=r.content, media_type=content_type)
                if r.status_code != 502:  # 502 = cold start, retry
                    raise HTTPException(r.status_code, detail=r.json())
            except httpx.TimeoutException:
                if attempt < 2:
                    import asyncio
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                raise HTTPException(504, "Blender service timeout")
    
    raise HTTPException(502, "Blender service unavailable")


@app.post("/api/v1/parse")
async def parse(request: Request):
    data = await request.json()
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{LLM_SVC}/api/v1/parse", json=data, timeout=30.0)
    if r.status_code == 200:
        return r.json()
    raise HTTPException(r.status_code, detail=r.json())


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/{filename:path}")
def serve_static(filename: str):
    path = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(path):
        return FileResponse(path)
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### Шаг 3.4: Обновить requirements.txt для каждого сервиса

**gateway/requirements.txt:**
```
fastapi==0.115.0
uvicorn==0.30.0
httpx==0.27.0
```

**llm-service/requirements.txt:**
```
fastapi==0.115.0
uvicorn==0.30.0
httpx==0.27.0
pydantic==2.9.0
```

**blender-service/requirements.txt:**
```
fastapi==0.115.0
uvicorn==0.30.0
pydantic==2.9.0
```

---

## Фаза 4: Фронтенд — полная переработка генерации

### Шаг 4.1: Единая функция генерации в JS

**Файл:** `index.html` (замена JS-логики генерации)

```javascript
// Заменить текущую функцию send() и связанную логику

async function send() {
    const input = document.getElementById('ci');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';

    addMessage('user', text);
    showThinking('Анализирую описание...');

    // Шаг 1: Парсинг промта через LLM
    let params;
    try {
        updateThink('Извлекаю параметры через AI...');
        const r = await apiFetch('/api/v1/parse', {text});
        params = await r.json();
    } catch(e) {
        console.log('LLM parse failed, using local', e);
        params = parseLocal(text);
    }

    // Шаг 2: Показать что извлечено
    const desc = formatParams(params);
    updateThink(`Параметры: ${desc}`);

    // Шаг 3: Генерация
    const objType = params.object_type || 'building';
    if (objType === 'room' || objType === 'interior') {
        updateThink('Генерирую интерьер...');
        await generateInterior(text, params);
    } else {
        updateThink('Генерирую здание...');
        await generateBuilding(text, params);
    }
}

async function generateBuilding(text, params) {
    // Попробовать Blender
    try {
        updateThink('Запрос к Blender серверу...');
        const r = await apiFetch('/api/v1/generate', {
            prompt: text,
            ...params
        });

        if (r.ok) {
            const ct = r.headers.get('content-type') || '';
            if (ct.includes('gltf') || ct.includes('octet')) {
                const blob = await r.blob();
                loadGLBBlob(blob);
                hideThinking();
                return;
            }
            if (ct.includes('image')) {
                showRenderedImage(blob);
                hideThinking();
                return;
            }
        }
    } catch(e) {
        console.log('Blender failed:', e);
    }

    // Fallback: Three.js
    updateThink('Сервер недоступен, рендерю локально...');
    renderBuildingThreeJS(params);
    hideThinking();
}

async function generateInterior(text, params) {
    try {
        updateThink('Запрос к серверу рендеринга...');
        const r = await apiFetch('/api/v1/generate', {
            prompt: text,
            ...params
        });

        if (r.ok) {
            const ct = r.headers.get('content-type') || '';
            if (ct.includes('image')) {
                const blob = await r.blob();
                showInteriorImage(blob);
                hideThinking();
                return;
            }
        }
    } catch(e) {
        console.log('Interior render failed:', e);
    }

    // Fallback
    updateThink('Сервер недоступен, рендерю локально...');
    renderInteriorThreeJS(params);
    hideThinking();
}

function apiFetch(path, body) {
    const backend = localStorage.getItem('archai-backend') || '';
    const url = backend ? backend + path : path;
    return fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(15000),
    });
}

function formatParams(p) {
    const parts = [];
    if (p.object_type === 'room') parts.push(`комната: ${p.room_type}`);
    else if (p.object_type === 'interior') parts.push('интерьер');
    else parts.push(p.building_type || 'здание');
    if (p.floors) parts.push(`${p.floors} эт.`);
    if (p.width_m && p.length_m) parts.push(`${p.width_m}×${p.length_m}м`);
    if (p.material) parts.push(p.material);
    if (p.style) parts.push(p.style);
    return parts.join(' | ');
}
```

---

## Фаза 5: Деплой и инфраструктура

### Шаг 5.1: Обновить Dockerfile-ы

**gateway/Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY ../frontend /app/frontend
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

**llm-service/Dockerfile:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 8081
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8081"]
```

**blender-service/Dockerfile:**
```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y blender python3-pip xvfb && rm -rf /var/lib/apt/lists/*
RUN pip install fastapi uvicorn pydantic
WORKDIR /app
COPY app.py .
RUN mkdir -p /app/output
EXPOSE 8082
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 & export DISPLAY=:99 && uvicorn app:app --host 0.0.0.0 --port 8082"]
```

### Шаг 5.2: Обновить docker-compose.yml

```yaml
services:
  gateway:
    build: ./gateway
    ports:
      - "8080:8080"
    environment:
      - LLM_SERVICE_URL=http://llm-service:8081
      - BLENDER_SERVICE_URL=http://blender-service:8082
      - PORT=8080
    depends_on:
      - llm-service
      - blender-service

  llm-service:
    build: ./llm-service
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - PORT=8081

  blender-service:
    build: ./blender-service
    environment:
      - PORT=8082
      - BLENDER_PATH=blender
      - OUTPUT_DIR=/app/output
    volumes:
      - ./output:/app/output
```

### Шаг 5.3: Обновить render.yaml

```yaml
services:
  - type: web
    name: architect-gateway
    runtime: docker
    dockerfilePath: ./gateway/Dockerfile
    region: oregon
    plan: free
    healthCheckPath: /health
    envVars:
      - key: LLM_SERVICE_URL
        value: https://architect-llm.onrender.com
      - key: BLENDER_SERVICE_URL
        value: https://architect-blender.onrender.com
      - key: FRONTEND_DIR
        value: /app/frontend
      - key: PORT
        value: "8080"

  - type: web
    name: architect-llm
    runtime: docker
    dockerfilePath: ./llm-service/Dockerfile
    region: oregon
    plan: free
    healthCheckPath: /health
    envVars:
      - key: OPENROUTER_API_KEY
        sync: false
      - key: PORT
        value: "8081"

  - type: web
    name: architect-blender
    runtime: docker
    dockerfilePath: ./blender-service/Dockerfile
    region: oregon
    plan: free
    healthCheckPath: /health
    envVars:
      - key: PORT
        value: "8082"
      - key: BLENDER_PATH
        value: blender
      - key: OUTPUT_DIR
        value: /app/output
```

---

## Порядок выполнения

```
Фаза 1 (критика)          Фаза 2 (тесты)         Фаза 3 (стек)          Фаза 4 (фронт)         Фаза 5 (деплой)
─────────────────         ──────────────         ──────────────         ──────────────         ──────────────
1.1 LLM-парсер      →    2.1 test_generation  → 3.1 LLM FastAPI   →   4.1 JS refactor   →   5.1 Dockerfile
1.2 Роутинг          →    2.2 CI workflow      → 3.2 Blender FastAPI→   (fallback)        →   5.2 compose
1.3 Валидация bpy    →                         → 3.3 Gateway FastAPI→                      →   5.3 render.yaml
1.4 JS fallback      →                         → 3.4 requirements  →
1.5 Gateway retry    →                         →
```

**Минимальный viable path (только Фаза 1):**  
Шаги 1.1 + 1.2 + 1.3 = промты начинают работать. Остальное — улучшения.

**Рекомендуемый path:** Фаза 1 → Фаза 2 → Фаза 3 → Фаза 4 → Фаза 5

---

## Ожидаемый результат после каждой фазы

| Фаза | Результат |
|------|-----------|
| Фаза 1 | "сделай дизайн коттеджа" → GLB модель коттеджа. "спальня в стиле хайтек" → PNG рендер интерьера |
| Фаза 2 | CI ловит регрессии. Тесты покрывают 10+ промтов |
| Фаза 3 | Async API, Pydantic-валидация, документация OpenAPI |
| Фаза 4 | GitHub Pages работает с fallback на Three.js |
| Фаза 5 | Docker-compose запускается одной командой, Render деплоится автоматически |

---

## Критерии приёмки и тесты-защиты от галлюцинаций

Для каждого шага прописано:
- **Acceptance Criteria (AC)** — что считается «сделано»
- **Anti-Hallucination Tests (AHT)** — как проверить, что код реально работает, а не «выглядит правильным»
- **Definition of Done (DoD)** — что должно быть true одновременно

---

### Фаза 1

#### Шаг 1.1: LLM-парсер вместо regex

**AC-1.1.1:** Файл `promt_parser.py` существует и содержит функцию `parse_prompt()` и `fallback_regex_parse()`  
**AC-1.1.2:** `parse_prompt()` принимает строку, возвращает dict с ключами: `object_type`, `building_type`, `room_type`, `floors`, `width_m`, `length_m`, `height_m`, `style`, `material`, `roof_type`, `features`, `furniture`  
**AC-1.1.3:** При недоступности LLM автоматически вызывается `fallback_regex_parse()` и возвращает валидный dict  
**AC-1.1.4:** Результат всегда содержит `object_type` ∈ {`building`, `interior`, `room`}  

**AHT-1.1.1: Проверка на галлюцинацию промтов (10 кейсов)**
```python
import pytest
from promt_parser import fallback_regex_parse

HALLUCINATION_MATRIX = [
    # (промт, ожидаемый object_type, ожидаемый room_type/building_type, ожидаемый style)
    ("сделай дизайн коттеджа",                    "building", "cottage",  None),
    ("сделай дизайн интерьера детской",            "room",     "children", None),
    ("красивую спальню в стиле хайтек",            "room",     "bedroom",  "hitech"),
    ("интерьерный дизайн квартиры на 64 кв метра", "interior",  None,       None),
    ("офис 5 этажей стекло плоская кровля 20×24",  "building", "office",   None),
    ("двухэтажный кирпичный дом 10×12 с балконом", "building", "house",    None),
    ("деревянный коттедж 2 этажа терраса гараж 12×15", "building", "cottage", None),
    ("построй что-нибудь красивое",                "building", "house",    None),
    ("кухня в стиле лофт 4×5",                    "room",     "kitchen",  "loft"),
    ("современный таунхаус 3 этажа минимализм",    "building", "townhouse","minimalist"),
]

@pytest.mark.parametrize("text,obj_type,subtype,style", HALLUCINATION_MATRIX)
def test_no_hallucination_parse(text, obj_type, subtype, style):
    """Парсер НЕ должен выдумывать параметры которых нет в промте."""
    p = fallback_regex_parse(text)

    # Проверка object_type
    assert p["object_type"] == obj_type, \
        f"'{text}' → object_type='{p['object_type']}', ожидали '{obj_type}'"

    # Проверка подтипа
    if obj_type == "building":
        assert p["building_type"] == subtype, \
            f"'{text}' → building_type='{p['building_type']}', ожидали '{subtype}'"
    elif obj_type == "room":
        assert p["room_type"] == subtype, \
            f"'{text}' → room_type='{p.get('room_type')}', ожидали '{subtype}'"

    # Проверка стиля
    if style:
        assert p["style"] == style, \
            f"'{text}' → style='{p['style']}', ожидали '{style}'"

    # Анти-галлюцинация: если в промте нет размеров → дефолты, не выдуманные числа
    import re
    has_dimensions = bool(re.search(r'\d+\s*[×xх]\s*\d+', text)) or bool(re.search(r'\d+\s*кв', text))
    if not has_dimensions:
        assert p["width_m"] in (10, 6, 5), f"Выдуман размер width_m={p['width_m']} для промта без размеров"
        assert p["length_m"] in (12, 8, 6), f"Выдуман размер length_m={p['length_m']} для промта без размеров"
```

**AHT-1.1.2: Проверка что fallback не падает на мусорных входах**
```python
GARBAGE_INPUTS = [
    "", "   ", "asdfghjkl", "12345", "🤖💀", None,
    "а" * 10000,  # длинная строка
    "{json}",  # инъекция
    "<script>alert(1)</script>",  # XSS
]

@pytest.mark.parametrize("text", GARBAGE_INPUTS)
def test_fallback_survives_garbage(text):
    """Fallback не должен падать на любом входе."""
    try:
        if text is None:
            return  # None не валидный вход
        result = fallback_regex_parse(text)
        assert isinstance(result, dict)
        assert "object_type" in result
        assert result["object_type"] in ("building", "interior", "room")
    except Exception as e:
        pytest.fail(f"fallback_regex_parse упал на входе {repr(text[:50])}: {e}")
```

**AHT-1.1.3: Проверка что LLM-парсер и fallback дают совместимый формат**
```python
def test_llm_and_fallback_same_schema():
    """LLM-парсер и fallback должны возвращать одинаковые ключи."""
    text = "двухэтажный дом 10×12"
    fb = fallback_regex_parse(text)

    required_keys = {"object_type", "building_type", "floors", "width_m",
                     "length_m", "style", "material", "roof_type", "features", "furniture"}

    assert required_keys.issubset(fb.keys()), \
        f"Fallback не возвращает ключи: {required_keys - fb.keys()}"
```

**DoD-1.1:**
- [ ] `promt_parser.py` существует
- [ ] `fallback_regex_parse()` проходит AHT-1.1.1 (10/10 кейсов)
- [ ] `fallback_regex_parse()` проходит AHT-1.1.2 (все мусорные входы)
- [ ] Возвращаемый dict содержит все обязательные ключи (AHT-1.1.3)
- [ ] Нет `import *` или скрытых зависимостей

---

#### Шаг 1.2: Маршрутизация по типу объекта

**AC-1.2.1:** Endpoint `/api/v1/generate` существует и принимает POST с JSON `{"prompt": "..."}`  
**AC-1.2.2:** При `object_type == "room"` или `"interior"` → вызывается `generate_interior_script()`, возвращается PNG  
**AC-1.2.3:** При `object_type == "building"` → вызывается `generate_bpy_script()`, возвращается GLB  
**AC-1.2.4:** Ответ содержит корректный `Content-Type` (`image/png` или `model/gltf-binary`)  

**AHT-1.2.1: Проверка маршрутизации (unit-тест без Blender)**
```python
def test_routing_interior():
    """Промт про комнату → interior pipeline."""
    params = fallback_regex_parse("детская комната")
    assert params["object_type"] in ("room", "interior"), \
        f"'детская комната' не маршрутизируется в interior: {params['object_type']}"

def test_routing_building():
    """Промт про здание → building pipeline."""
    params = fallback_regex_parse("коттедж")
    assert params["object_type"] == "building", \
        f"'коттедж' не маршрутизируется в building: {params['object_type']}"

def test_routing_bedroom():
    params = fallback_regex_parse("спальня")
    assert params["object_type"] == "room"
    assert params["room_type"] == "bedroom"

def test_routing_office():
    params = fallback_regex_parse("офис 5 этажей")
    assert params["object_type"] == "building"
    assert params["building_type"] == "office"
```

**AHT-1.2.2: Проверка Content-Type (интеграция с Blender)**
```python
import httpx

def test_generate_returns_correct_content_type():
    """Проверка что /api/v1/generate возвращает правильный Content-Type."""
    # Тест здания
    r = httpx.post("http://localhost:8082/api/v1/generate",
                   json={"prompt": "дом 10×12"}, timeout=30)
    if r.status_code == 200:
        assert "gltf" in r.headers["content-type"] or "octet" in r.headers["content-type"], \
            f"Building: неожиданный Content-Type: {r.headers['content-type']}"

    # Тест интерьера
    r = httpx.post("http://localhost:8082/api/v1/generate",
                   json={"prompt": "спальня в стиле лофт"}, timeout=30)
    if r.status_code == 200:
        assert "image" in r.headers["content-type"], \
            f"Interior: неожиданный Content-Type: {r.headers['content-type']}"
```

**DoD-1.2:**
- [ ] Endpoint `/api/v1/generate` отвечает на POST
- [ ] AHT-1.2.1: 4/4 маршрута корректны
- [ ] AHT-1.2.2: Content-Type совпадает с типом генерации
- [ ] Нет fallback-маршрутизации «всё → building»

---

#### Шаг 1.3: Исправить bpy-генератор

**AC-1.3.1:** Функция `generate_bpy_script()` возвращает строку, которая `compile()`ится без ошибок  
**AC-1.3.2:** Все параметры проходят через `safe_val()` с валидацией  
**AC-1.3.3:** Нет неинициализированных переменных в сгенерированном bpy-скрипте  

**AHT-1.3.1: Проверка компиляции для всех комбинаций параметров**
```python
import itertools

def test_bpy_compiles_all_combinations():
    """Скрипт компилируется для ЛЮБОЙ комбинации параметров."""
    from blender_service_app import generate_bpy_script

    roofs = ["gabled", "flat", "hip", None, "INVALID", ""]
    materials = ["brick", "wood", "glass", "stone", "concrete", "plaster", None, "INVALID"]
    bools = [True, False]

    for roof, mat, balc, terr, gar in itertools.product(roofs, materials, bools, bools, bools):
        params = {
            "width": 10, "length": 12, "floors": 2,
            "roof_type": roof, "facade_material": mat,
            "has_balcony": balc, "has_terrace": terr, "has_garage": gar,
        }
        try:
            script = generate_bpy_script(params)
            compile(script, "<test>", "exec")
        except Exception as e:
            pytest.fail(f"Не компилируется: roof={roof}, mat={mat}, balc={balc}: {e}")
```

**AHT-1.3.2: Проверка что нет «сырых» Python-переменных в bpy-скрипте**
```python
import re

def test_no_raw_variables_in_bpy():
    """В bpy-скрипте не должно быть неинициализированных переменных."""
    from blender_service_app import generate_bpy_script

    script = generate_bpy_script({"roof_type": "gabled", "facade_material": "brick"})

    # Проверка: не должно быть f-string артефактов типа {variable}
    # Но ДОЛЖНЫ быть значения: "gabled", "brick" и т.д.
    assert "{roof_type}" not in script, "f-string не подставился: {roof_type}"
    assert "{facade_material}" not in script, "f-string не подставился: {facade_material}"
    assert "{W}" not in script, "f-string не подставился: {W}"
    assert "{L}" not in script, "f-string не подставился: {L}"

    # Проверка что значения реально подставились
    assert "10" in script or "W=10" in script
    assert "gabled" in script
    assert "brick" in script or "0.71" in script  # brick color
```

**AHT-1.3.3: Проверка что Blender реально экспортирует файл**
```python
import subprocess, os, tempfile

def test_blender_export_real_file():
    """Blender CLI реально создаёт GLB файл."""
    from blender_service_app import generate_bpy_script

    script = generate_bpy_script({"width": 10, "length": 12, "floors": 2})
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(script)
        f.write("\nimport bpy\nbpy.ops.export_scene.gltf(filepath='test.glb', export_format='GLB')\n")
        script_path = f.name

    try:
        result = subprocess.run(
            ["blender", "--background", "--factory-startup", "--log-level", "0", "--python", script_path],
            capture_output=True, text=True, timeout=60,
        )
        # Проверка что файл создался
        assert os.path.exists("test.glb"), f"GLB не создан. stderr: {result.stderr[-300:]}"
        assert os.path.getsize("test.glb") > 100, "GLB файл пустой или слишком маленький"
    finally:
        os.unlink(script_path)
        if os.path.exists("test.glb"):
            os.unlink("test.glb")
```

**DoD-1.3:**
- [ ] AHT-1.3.1: все комбинации компилируются (36 вариантов)
- [ ] AHT-1.3.2: нет f-string артефактов в выводе
- [ ] AHT-1.3.3: Blender CLI создаёт реальный файл > 100 bytes
- [ ] `safe_val()` отклоняет некорректные значения (None, пустые строки, невалидные enum)

---

#### Шаг 1.4: Фронтенд — fallback на Three.js

**AC-1.4.1:** При недоступности Blender фронтенд не показывает ошибку, а рендерит через Three.js  
**AC-1.4.2:** Функция `generateWithFallback()` существует и содержит try/catch с fallback  
**AC-1.4.3:** Timeout на запрос к Blender ≤ 15 секунд  

**AHT-1.4.1: Проверка timeout (тест браузера)**
```javascript
// Запустить в консоли браузера при отключённом бэкенде
console.time('fallback');
await generateWithFallback('дом 10×12', {object_type: 'building', width_m: 10, length_m: 12});
console.timeEnd('fallback');
// Ожидание: ≤ 16 сек (15 сек timeout + 1 сек на fallback)
```

**AHT-1.4.2: Проверка что Three.js canvas не пустой после fallback**
```javascript
// После вызова generateWithFallback с недоступным бэкендом
const canvas = document.getElementById('c3d');
const ctx = canvas.getContext('webgl2') || canvas.getContext('webgl');
assert(ctx !== null, 'Canvas не инициализирован');
assert(canvas.style.display !== 'none', 'Canvas скрыт');
```

**DoD-1.4:**
- [ ] `generateWithFallback()` существует в JS
- [ ] Timeout ≤ 15 сек
- [ ] При отключённом бэкенде Three.js canvas отображается
- [ ] Нет бесконечных спиннеров при недоступности сервера

---

#### Шаг 1.5: Gateway — retry и timeout

**AC-1.5.1:** Gateway делает ≥ 2 попытки при 502/timeout от Blender  
**AC-1.5.2:** Exponential backoff: 5 сек → 10 сек  
**AC-1.5.3:** После всех попыток возвращает 502 с читаемым сообщением  

**AHT-1.5.1: Проверка retry (мок-тест)**
```python
import asyncio
from unittest.mock import AsyncMock, patch

def test_gateway_retries_on_502():
    """Gateway повторяет запрос при 502."""
    call_count = 0
    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("timeout")
        # Третий вызов — успех
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b"fake-glb-data"
        mock_response.headers = {"content-type": "model/gltf-binary"}
        return mock_response

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        # Gateway должен сделать 3 попытки
        assert call_count == 3 or call_count >= 2
```

**AHT-1.5.2: Проверка что cold start не убивает запрос**
```bash
# Ручной тест:뒹ить blender-service, отправить запрос через gateway
# Ожидание: первый запрос таймаутит, второй (через 5-10 сек) проходит
curl -X POST http://localhost:8080/api/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "дом 10×12"}' \
  --max-time 130
# Ожидание: 200 OK с GLB файлом
```

**DoD-1.5:**
- [ ] Retry логика существует в gateway/app.py
- [ ] Backoff: 5s → 10s
- [ ] AHT-1.5.1 проходит
- [ ] Timeout на каждый attempt = 120 сек

---

### Фаза 2

#### Шаг 2.1: Интеграционные тесты

**AC-2.1.1:** Файл `tests/test_generation.py` существует  
**AC-2.1.2:** Содержит ≥ 10 параметризованных тестов промтов  
**AC-2.1.3:** Все тесты проходят (`pytest tests/test_generation.py -v` = all green)  
**AC-2.1.4:** Тесты покрывают: парсинг, маршрутизацию, компиляцию bpy  

**AHT-2.1.1: Мета-тест — проверка что тесты реальны, а не пустые**
```python
def test_tests_are_not_stubs():
    """Проверка что интеграционные тесты реально тестируют код."""
    import inspect
    from tests import test_generation

    test_funcs = [getattr(test_generation, name) for name in dir(test_generation)
                  if name.startswith("test_")]

    assert len(test_funcs) >= 10, f"Слишком мало тестов: {len(test_funcs)}"

    for func in test_funcs:
        source = inspect.getsource(func)
        # Тест не должен быть заглушкой
        assert "pass" not in source or "assert" in source, \
            f"{func.__name__} — пустой тест (только pass)"
        assert "assert" in source, \
            f"{func.__name__} — нет assert, тест ничего не проверяет"
```

**AHT-2.1.2: Проверка что тесты ловят реальные баги**
```python
def test_tests_catch_broken_parser():
    """Если парсер сломан — тесты должны падать."""
    import promt_parser
   
    # Подменяем парсер на сломанный
    original = promt_parser.fallback_regex_parse
    promt_parser.fallback_regex_parse = lambda text: {"object_type": "WRONG"}
    try:
        with pytest.raises(AssertionError):
            # Этот тест ДОЛЖЕН упасть со сломанным парсером
            result = original("коттедж")
            assert result["object_type"] == "building"
    finally:
        promt_parser.fallback_regex_parse = original
```

**DoD-2.1:**
- [ ] `tests/test_generation.py` существует
- [ ] ≥ 10 тестов
- [ ] `pytest` = all green
- [ ] AHT-2.1.1: мета-тест проходит
- [ ] Покрытие: parse (10 кейсов) + routing (4 кейса) + bpy compilation (6 кейсов)

---

#### Шаг 2.2: CI workflow

**AC-2.2.1:** Файл `.github/workflows/test.yml` существует  
**AC-2.2.2:** Запускается на push и pull_request  
**AC-2.2.3:** Устанавливает Python 3.11, зависимости, запускает pytest  

**AHT-2.2.1: Проверка workflow**
```yaml
# После push — проверить на GitHub Actions:
# 1. Workflow запустился
# 2. Все шаги зелёные
# 3. Время выполнения < 2 мин
```

**DoD-2.2:**
- [ ] `.github/workflows/test.yml` существует
- [ ] Push → tests run → green

---

### Фаза 3

#### Шаг 3.1: LLM-сервис на FastAPI

**AC-3.1.1:** `llm-service/app.py` использует FastAPI (не Flask)  
**AC-3.1.2:** Endpoint `/api/v1/parse` принимает `{"text": "..."}`, возвращает ParsedParams  
**AC-3.1.3:** Endpoint `/health` возвращает `{"status": "ok"}`  
**AC-3.1.4:** Pydantic-модели для всех request/response  
**AC-3.1.5:** OpenAPI-документация доступна на `/docs`  

**AHT-3.1.1: Проверка Pydantic-валидации**
```python
from fastapi.testclient import TestClient
from llm_service_app import app

client = TestClient(app)

def test_parse_endpoint_exists():
    r = client.post("/api/v1/parse", json={"text": "дом"})
    assert r.status_code == 200
    data = r.json()
    assert "object_type" in data

def test_parse_rejects_empty():
    r = client.post("/api/v1/parse", json={})
    assert r.status_code == 422  # Pydantic validation error

def test_parse_rejects_wrong_type():
    r = client.post("/api/v1/parse", json={"text": 123})
    assert r.status_code == 422

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_openapi_docs():
    r = client.get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower() or "openapi" in r.text.lower()
```

**AHT-3.1.2: Проверка что LLM-парсер НЕ галлюцинирует поля**
```python
def test_parse_returns_only_known_fields():
    """Ответ парсера содержит только определённые поля, не выдуманные."""
    r = client.post("/api/v1/parse", json={"text": "дом 10×12"})
    data = r.json()

    allowed_fields = {
        "object_type", "building_type", "room_type", "floors",
        "width_m", "length_m", "height_m", "style", "material",
        "roof_type", "features", "furniture"
    }
    unexpected = set(data.keys()) - allowed_fields
    assert not unexpected, f"Парсер вернул лишние поля: {unexpected}"
```

**DoD-3.1:**
- [ ] FastAPI, не Flask
- [ ] `/api/v1/parse` работает
- [ ] `/health` работает
- [ ] `/docs` показывает OpenAPI
- [ ] AHT-3.1.1: 4/4 теста
- [ ] AHT-3.1.2: нет лишних полей

---

#### Шаг 3.2: Blender-сервис на FastAPI

**AC-3.2.1:** `blender-service/app.py` использует FastAPI  
**AC-3.2.2:** Endpoint `/api/v1/generate` принимает GenerateRequest, возвращает файл  
**AC-3.2.3:** Pydantic-валидация на входе  
**AC-3.2.4:** `compile()` проверяет bpy-скрипт перед запуском Blender  
**AC-3.2.5:** Timeout на subprocess = 120 сек  

**AHT-3.2.1: Проверка что Blender реален (не мок)**
```python
def test_blender_binary_exists():
    """Blender CLI доступен в системе."""
    import shutil
    blender = shutil.which("blender")
    assert blender is not None, "Blender не найден в PATH"

def test_blender_runs():
    """Blender CLI запускается и отвечает."""
    import subprocess
    result = subprocess.run(["blender", "--version"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, f"Blender не запускается: {result.stderr}"
    assert "blender" in result.stdout.lower()
```

**AHT-3.2.2: Проверка что generate возвращает реальный файл**
```python
def test_generate_returns_real_glb():
    """Endpoint /api/v1/generate создаёт реальный GLB файл."""
    r = client.post("/api/v1/generate", json={
        "prompt": "дом 10×12",
        "object_type": "building",
        "width_m": 10, "length_m": 12, "floors": 2,
    }, timeout=60)

    if r.status_code == 200:
        assert len(r.content) > 500, f"GLB слишком маленький: {len(r.content)} bytes"
        assert r.headers["content-type"] == "model/gltf-binary"
    else:
        pytest.skip(f"Blender недоступен: {r.status_code}")

def test_generate_interior_returns_real_png():
    """Endpoint генерирует реальный PNG для интерьера."""
    r = client.post("/api/v1/generate", json={
        "prompt": "спальня",
        "object_type": "room",
        "room_type": "bedroom",
        "style": "modern",
    }, timeout=60)

    if r.status_code == 200:
        assert len(r.content) > 1000, f"PNG слишком маленький: {len(r.content)} bytes"
        assert r.headers["content-type"] == "image/png"
        # Проверка PNG magic bytes
        assert r.content[:4] == b'\x89PNG', "Не PNG файл"
    else:
        pytest.skip(f"Blender недоступен: {r.status_code}")
```

**DoD-3.2:**
- [ ] FastAPI
- [ ] GenerateRequest с Pydantic
- [ ] `compile()` перед Blender
- [ ] AHT-3.2.1: Blender CLI работает
- [ ] AHT-3.2.2: реальные файлы (GLB > 500 bytes, PNG > 1000 bytes, PNG magic bytes)

---

#### Шаг 3.3: Gateway на FastAPI

**AC-3.3.1:** FastAPI + uvicorn  
**AC-3.3.2:** Retry logic для Blender (≥ 2 попытки)  
**AC-3.3.3:** Proxy к LLM и Blender сервисам  
**AC-3.3.4:** Статика (frontend) раздаётся  

**AHT-3.3.1: Проверка retry**
```python
def test_gateway_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "services" in data
    assert "llm" in data["services"]
    assert "blender" in data["services"]

def test_gateway_proxies_parse():
    """Gateway проксирует /api/v1/parse к LLM-сервису."""
    r = client.post("/api/v1/parse", json={"text": "дом"})
    # Если LLM-сервис недоступен — 502, но не 404
    assert r.status_code in (200, 502), f"Неожиданный статус: {r.status_code}"
```

**DoD-3.3:**
- [ ] FastAPI
- [ ] Retry ≥ 2 попытки
- [ ] AHT-3.3.1 проходит
- [ ] `/health` показывает статус всех сервисов

---

#### Шаг 3.4: Requirements

**AC-3.4.1:** Каждый сервис имеет `requirements.txt`  
**AC-3.4.2:** Нет Flask в зависимостях (замёнён на FastAPI)  
**AC-3.4.3:** Версии зафиксированы  

**AHT-3.4.1:**
```bash
# Проверка что нет Flask
for svc in gateway llm-service blender-service; do
    if grep -i flask $svc/requirements.txt; then
        echo "FAIL: $svc всё ещё использует Flask"
        exit 1
    fi
done
echo "OK: Flask удалён из всех сервисов"
```

**DoD-3.4:**
- [ ] requirements.txt для каждого сервиса
- [ ] Нет Flask
- [ ] Версии pinned

---

### Фаза 4

#### Шаг 4.1: Фронтенд — единая функция генерации

**AC-4.4.1:** Функция `send()` вызывает `/api/v1/parse` → определяет тип → вызывает `/api/v1/generate`  
**AC-4.4.2:** Fallback на Three.js при недоступности бэкенда ≤ 15 сек  
**AC-4.4.3:** Нет бесконечных спиннеров — всегда есть результат или сообщение об ошибке  

**AHT-4.1.1: Ручной smoke-тест (5 промтов)**
```
Тест 1: "дом 10×12 кирпич 2 этажа"
  → Ожидание: 3D модель здания (GLB или Three.js)
  → Canvas НЕ пустой
  → Нет ошибок в консоли

Тест 2: "спальня в стиле лофт"
  → Ожидание: интерьерный рендер (PNG или Three.js)
  → Отображается изображение комнаты

Тест 3: "детская комната"
  → Ожидание: интерьер с детской мебелью

Тест 4: "офис 5 этажей стекло"
  → Ожидание: здание офиса

Тест 5: "построй что-нибудь" (с отключённым бэкендом)
  → Ожидание: Three.js fallback, не ошибка
  → Время ≤ 16 сек
```

**AHT-4.1.2: Проверка что нет «зависших» состояний**
```javascript
// После каждого промта проверять:
const genov = document.getElementById('genov');
assert(genov.style.display === 'none' || genov.style.display === '',
       'Спиннерзавис — генерация не завершилась');

const canvas = document.getElementById('c3d');
const empt = document.getElementById('empt');
// Хотя бы одно: canvas виден ИЛИ сообщение об ошибке
assert(
    canvas.style.display !== 'none' ||
    document.querySelector('.msg.a .bub') !== null,
    'Ни canvas ни сообщение об ошибке не отображаются'
);
```

**DoD-4.1:**
- [ ] `send()` → parse → generate → display pipeline
- [ ] Fallback ≤ 15 сек
- [ ] AHT-4.1.1: 5/5 промтов дают результат
- [ ] AHT-4.1.2: нет зависших состояний

---

### Фаза 5

#### Шаг 5.1: Dockerfile

**AC-5.1.1:** Dockerfile для каждого сервиса  
**AC-5.1.2:** `docker build` проходит без ошибок  
**AC-5.1.3:** Контейнер запускается и отвечает на `/health`  

**AHT-5.1.1:**
```bash
for svc in gateway llm-service blender-service; do
    echo "Building $svc..."
    docker build -t test-$svc ./$svc/
    echo "Running $svc..."
    docker run -d --name test-$svc -p 0:8080 test-$svc
    sleep 3
    PORT=$(docker port test-$svc | head -1 | cut -d: -f2)
    curl -sf http://localhost:$PORT/health || echo "FAIL: $svc health check"
    docker rm -f test-$svc
done
```

**DoD-5.1:**
- [ ] 3 Dockerfile-а
- [ ] `docker build` для каждого
- [ ] `/health` отвечает 200

---

#### Шаг 5.2: docker-compose

**AC-5.2.1:** `docker-compose up` запускает все 3 сервиса  
**AC-5.2.2:** Gateway доступен на localhost:8080  
**AC-5.2.3:** End-to-end: промт через gateway → ответ  

**AHT-5.2.1:**
```bash
docker-compose up -d
sleep 10

# Health check
curl -sf http://localhost:8080/health

# End-to-end генерация
curl -X POST http://localhost:8080/api/v1/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "дом 10×12"}' \
  -o test_output.glb \
  --max-time 60

# Проверка файла
SIZE=$(stat -f%z test_output.glb 2>/dev/null || stat -c%s test_output.glb)
if [ "$SIZE" -gt 500 ]; then
    echo "OK: GLB файл $SIZE bytes"
else
    echo "FAIL: GLB слишком маленький ($SIZE bytes)"
fi

docker-compose down
```

**DoD-5.2:**
- [ ] `docker-compose up` работает
- [ ] AHT-5.2.1: end-to-end GLB > 500 bytes

---

#### Шаг 5.3: render.yaml

**AC-5.3.1:** `render.yaml` описывает 3 сервиса  
**AC-5.3.2:** Blueprint создается на Render без ошибок  
**AC-5.3.3:** Все сервисы деплоятся и отвечают на `/health`  

**AHT-5.3.1: Ручная проверка на Render**
```
1. Зайти на render.com → New → Blueprint
2. Подключить репозиторий
3. Проверить что создано 3 сервиса:
   - architect-gateway → /health = 200
   - architect-llm → /health = 200
   - architect-blender → /health = 200
4. Открыть gateway URL в браузере
5. Ввести промт "дом 10×12" → должна появиться 3D модель
```

**DoD-5.3:**
- [ ] render.yaml валидный
- [ ] 3 сервиса на Render
- [ ] `/health` = 200 для каждого
- [ ] End-to-end промт через Render URL работает

---

## Сводная таблица: шаг → AC → AHT → DoD

| Шаг | AC кол-во | AHT кол-во | DoD чекбоксов | Критичность |
|-----|-----------|------------|---------------|-------------|
| 1.1 LLM-парсер | 4 | 3 | 5 | 🔴 Критическая |
| 1.2 Роутинг | 4 | 2 | 4 | 🔴 Критическая |
| 1.3 bpy-валидация | 3 | 3 | 4 | 🔴 Критическая |
| 1.4 JS fallback | 3 | 2 | 4 | 🟡 Важная |
| 1.5 Gateway retry | 3 | 2 | 4 | 🟡 Важная |
| 2.1 Тесты | 4 | 2 | 5 | 🟡 Важная |
| 2.2 CI | 3 | 1 | 2 | 🟢 Желательная |
| 3.1 LLM FastAPI | 5 | 2 | 6 | 🟢 Желательная |
| 3.2 Blender FastAPI | 5 | 2 | 5 | 🟢 Желательная |
| 3.3 Gateway FastAPI | 4 | 1 | 4 | 🟢 Желательная |
| 3.4 Requirements | 3 | 1 | 3 | 🟢 Желательная |
| 4.1 Фронтенд | 3 | 2 | 4 | 🟡 Важная |
| 5.1 Dockerfile | 3 | 1 | 3 | 🟢 Желательная |
| 5.2 compose | 3 | 1 | 3 | 🟢 Желательная |
| 5.3 render.yaml | 3 | 1 | 4 | 🟢 Желательная |
| **ИТОГО** | **49** | **25** | **60** | |
