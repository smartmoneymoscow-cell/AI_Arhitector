# Architect v10.2 🏗️

AI-архитектор — генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Быстрый старт

1. Откройте сайт
2. Нажмите **⚙️ Настройки** → введите OpenRouter API ключ (`sk-or-v1-...`) от [openrouter.ai/keys](https://openrouter.ai/keys)
3. Опишите здание: *двухэтажный кирпичный дом 10×12*, *офис 5 этажей стекло*, *коттедж с террасой*

> Бесплатные модели работают без баланса, но ключ обязателен.

## Деплой

### GitHub Pages (только фронтенд)
Сервис работает в браузере. Three.js рендерит 3D локально, OpenRouter API вызывается напрямую. Blender-рендеринг недоступен.

### Локальный сервер (полный функционал)
```bash
pip install flask flask-cors httpx
export OPENROUTER_API_KEY="sk-or-v1-..."
python server.py
# → http://localhost:8080
```

Для Blender-рендеринга GLB-моделей:
```bash
export BLENDER_PATH="/path/to/blender"
```

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (index.html)                     │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ Chat UI  │  │ 3D View  │  │ 2D Plan  │  │ Settings (⚙️)    │ │
│  │ (sidebar)│  │ (Three.js│  │ (Canvas) │  │ API Key + Backend│ │
│  │          │  │  + WebGL) │  │          │  │ URL (localStorage)│ │
│  └────┬─────┘  └─────┬────┘  └──────────┘  └──────────────────┘ │
│       │              │                                            │
│  ┌────┴──────────────┴────────────────────────────────────────┐  │
│  │                    JS Engine Layer                          │  │
│  │  • parseLocal()    — regex-парсинг русского текста         │  │
│  │  • callClaude()    — прокси → OpenRouter fallback          │  │
│  │  • analyzeImage()  — Claude Vision / OpenRouter VL          │  │
│  │  • startGen()      — Three.js процедурная генерация        │  │
│  │  • generateViaBlenderServer() — GLB с сервера              │  │
│  └───────────┬─────────────────────┬──────────────────────────┘  │
│              │                     │                              │
└──────────────┼─────────────────────┼──────────────────────────────┘
               │                     │
       ┌───────▼───────┐    ┌───────▼───────────┐
       │  OpenRouter    │    │  Backend Server    │
       │  API (free)    │    │  (server.py)       │
       │                │    │                     │
       │ • nemotron-nano│    │ ┌─────────────────┐│
       │   -9b-v2:free  │    │ │ /api/v1/health  ││
       │ • gemma-4-31b  │    │ │ /proxy/claude   ││
       │   -it:free     │    │ │ /generate/build ││
       └────────────────┘    │ │ /render/interior││
                              │ └────────┬────────┘│
                              │          │         │
                              │ ┌────────▼────────┐│
                              │ │ OpenRouter API  ││
                              │ │ (server-side    ││
                              │ │  key in env)    ││
                              │ └─────────────────┘│
                              │ ┌─────────────────┐│
                              │ │ Blender CLI     ││
                              │ │ (subprocess)    ││
                              │ │ → GLB / PNG     ││
                              │ └─────────────────┘│
                              └─────────────────────┘

       ┌─────────────────────────────────┐
       │  Blender/ (scripts)              │
       │                                  │
       │  blenderllm_bridge.py            │
       │   └─ BlenderLLM (Qwen2.5-7B)    │
       │   └─ Claude fallback             │
       │                                  │
       │  generate_building.py            │
       │   └─ Параметры → bpy → GLB      │
       │                                  │
       │  render_interior.py              │
       │   └─ Стиль → сцена → PNG        │
       │                                  │
       │  server.py (blender/)            │
       │   └─ Flask API для Blender GUI   │
       └─────────────────────────────────┘
```

---

## UML-диаграмма классов

```mermaid
classDiagram
    class Frontend {
        +index.html
        +send() void
        +callClaude(msg, sys, maxTok) string
        +analyzeImage(b64, mediaType, userText) JSON
        +parseLocal(text) Params
        +applyParams(text, params) Building
        +startGen(bld) void
        +generateViaBlenderServer(prompt) bool
        +openSettings() void
        +saveSettings() void
    }

    class Settings {
        +openRouterKey: string [localStorage]
        +backendUrl: string [localStorage]
        +getOpenRouterKey() string
        +getBackendUrl() string
    }

    class ThreeRenderer {
        +scene: THREE.Scene
        +camera: THREE.PerspectiveCamera
        +renderer: THREE.WebGLRenderer
        +initThree() void
        +createBuilding(params) void
        +enterInterior() void
        +resetCam() void
        +togWire() void
        +togAnn() void
    }

    class Server_Main {
        +server.py (root)
        +Flask app
        +proxy_claude() JSON
        +generate_building() GLB
        +render_interior() PNG
        +parse_building_params(text) dict
        +generate_bpy_script(params) string
        +generate_interior_script(params) string
    }

    class BlenderServer {
        +blender/server.py
        +Flask app
        +BlenderLLMBridge bridge
        +generate_building() GLB
        +render_interior() PNG
        +generate_script() string
    }

    class BlenderLLMBridge {
        +blenderllm_bridge.py
        +model: Qwen2.5-Coder-7B
        +generate(prompt) string
        +run_in_blender(script, output) bool
        +fallback_claude(prompt) string
    }

    class BuildingGenerator {
        +blender/generate_building.py
        +params: dict
        +create_walls() void
        +create_roof() void
        +create_windows() void
        +create_door() void
        +export_glb(path) void
    }

    class InteriorRenderer {
        +blender/render_interior.py
        +style_presets: dict
        +create_room() void
        +place_furniture() void
        +setup_lighting() void
        +render_png(path) void
    }

    class OpenRouterAPI {
        +/chat/completions
        +model: nemotron-nano-9b-v2:free
        +model: gemma-4-31b-it:free
        +model: nemotron-nano-12b-v2-vl:free
    }

    Frontend --> Settings : reads key/url
    Frontend --> ThreeRenderer : 3D rendering
    Frontend --> Server_Main : HTTP API
    Frontend --> OpenRouterAPI : direct fallback
    Server_Main --> OpenRouterAPI : proxy
    Server_Main --> BuildingGenerator : subprocess
    BlenderServer --> BlenderLLMBridge : AI generation
    BlenderServer --> BuildingGenerator : subprocess
    BlenderServer --> InteriorRenderer : subprocess
    BlenderLLMBridge --> OpenRouterAPI : fallback
```

---

## Схема AI-агентов

```mermaid
graph TB
    subgraph "Уровень 1: Фронтенд (браузер)"
        A1["🧠 Парсер параметров<br/><code>parseLocal()</code><br/>Regex + словари<br/>RU текст → JSON"]
        A2["🤖 Claude Proxy Agent<br/><code>callClaude()</code><br/>OpenRouter → nemotron-9b<br/>Точное извлечение параметров"]
        A3["👁 Vision Agent<br/><code>analyzeImage()</code><br/>OpenRouter → nemotron-12b-vl<br/>Фото → параметры здания"]
        A4["🏗 3D Generator<br/><code>startGen()</code><br/>Three.js процедурный<br/>Params → 3D mesh"]
    end

    subgraph "Уровень 2: Backend сервер"
        B1["🔀 Proxy Agent<br/><code>proxy_claude()</code><br/>Anthropic format → OpenAI<br/>Перезапрос к OpenRouter"]
        B2["📐 Building Agent<br/><code>generate_building()</code><br/>Prompt → AI params → bpy<br/>→ Blender CLI → GLB"]
        B3["🎨 Interior Agent<br/><code>render_interior()</code><br/>Style → bpy сцена<br/>→ Blender CLI → PNG"]
    end

    subgraph "Уровень 3: Blender pipeline"
        C1["🤖 BlenderLLM<br/>Qwen2.5-Coder-7B-Instruct<br/>Текст → bpy скрипт"]
        C2["🏛 Building Generator<br/>Template-based bpy<br/>Params → стены/крыша/окна"]
        C3["🛋 Interior Renderer<br/>Style presets + bpy<br/>Мебель + освещение"]
    end

    subgraph "Уровень 4: Внешние API"
        D1["OpenRouter API<br/>Бесплатные модели"]
    end

    A1 -->|"fallback"| A2
    A2 -->|"backend down"| D1
    A3 -->|"backend down"| D1
    A4 -.->|"GLB load"| B2

    A2 -->|"proxy"| B1
    A3 -->|"proxy"| B1
    B1 --> D1

    B2 -->|"subprocess"| C2
    B2 -->|"AI parse"| C1
    B2 -->|"fallback"| D1
    B3 -->|"subprocess"| C3

    C1 -->|"fallback"| D1

    style A1 fill:#e0f2fe,stroke:#0284c7
    style A2 fill:#fef3c7,stroke:#d97706
    style A3 fill:#fce7f3,stroke:#db2777
    style A4 fill:#d1fae5,stroke:#059669
    style B1 fill:#fef3c7,stroke:#d97706
    style B2 fill:#e0e7ff,stroke:#4f46e5
    style B3 fill:#fae8ff,stroke:#a855f7
    style C1 fill:#fef3c7,stroke:#d97706
    style C2 fill:#e0e7ff,stroke:#4f46e5
    style C3 fill:#fae8ff,stroke:#a855f7
    style D1 fill:#fee2e2,stroke:#dc2626
```

### Описание агентов

| # | Агент | Уровень | Модель | Роль |
|---|-------|---------|--------|------|
| 1 | **Парсер параметров** | Браузер | — (regex) | Первичный парсинг RU текста → структурированные параметры |
| 2 | **Claude Proxy Agent** | Браузер → Backend | nemotron-nano-9b-v2:free | Точное извлечение параметров через LLM |
| 3 | **Vision Agent** | Браузер → Backend | nemotron-nano-12b-v2-vl:free | Анализ фото/чертежей → параметры здания |
| 4 | **3D Generator** | Браузер | — (Three.js) | Процедурная генерация 3D из параметров |
| 5 | **Proxy Agent** | Backend | — (прокси) | Конвертация форматов, маршрутизация к OpenRouter |
| 6 | **Building Agent** | Backend | nemotron-9b + Blender | Полный цикл: текст → AI → bpy → GLB |
| 7 | **Interior Agent** | Backend | Blender | Генерация интерьеров: стиль → bpy → PNG |
| 8 | **BlenderLLM** | Blender | Qwen2.5-Coder-7B-Instruct | Генерация bpy скриптов из текста (AI) |

**Итого: 8 агентов** (4 в браузере, 3 на сервере, 1 в Blender pipeline)

---

## Функции

- 🏠 **3D-генерация** зданий по тексту (Three.js + Blender GLB)
- 📐 **2D-планы** этажей
- 🪟 **Интерьер / экстерьер** с пресетами стилей
- 📷 **Анализ фото** (загрузка изображений → Vision AI)
- 🎤 **Голосовой ввод** (Web Speech API, RU)
- 🔄 Поворот, зум, навигация по этажам
- ⚙️ Настройки API ключа и backend URL

## Стек

| Компонент | Технология |
|-----------|-----------|
| Frontend | HTML/CSS/JS, Three.js r160 |
| Backend | Flask, httpx |
| AI (free) | OpenRouter: nemotron-nano-9b-v2, gemma-4-31b-it |
| AI (vision) | OpenRouter: nemotron-nano-12b-v2-vl |
| AI (Blender) | BlenderLLM (Qwen2.5-Coder-7B-Instruct) |
| 3D рендер | Three.js (браузер) + Blender CLI (сервер) |
| Хранение | localStorage (ключ, URL) |

## Структура проекта

```
AI_Arhitector/
├── index.html              # Фронтенд (SPA, ~2600 строк)
├── server.py               # Flask backend (proxy + Blender)
├── README.md
├── .nojekyll
├── blender/
│   ├── blenderllm_bridge.py   # BlenderLLM ↔ bpy bridge
│   ├── generate_building.py   # Параметры → bpy → GLB
│   ├── render_interior.py     # Стиль → bpy → PNG
│   └── server.py              # Blender-специфичный Flask API
├── colab/
│   └── ArchAI_Blender.ipynb   # Google Colab notebook
├── frontend/
│   └── index.html             # Копия фронтенда
└── output/                    # Сгенерированные модели
```

## Лицензия

Проект открытый. Автор: [smartmoneymoscow-cell](https://github.com/smartmoneymoscow-cell)
