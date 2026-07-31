# Architect v5.0 🏗️

AI-архитектор — генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Архитектура

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Gateway    │────▶│  LLM Service │     │ Blender Service  │
│  :8080       │     │  :8081       │     │  :8082           │
│  (роутинг)   │────▶│  (парсинг)   │     │  (выполнение)    │
└──────┬───────┘     └─────────────┘     └────────┬────────┘
       │                                          │
       │         ┌─────────────────┐              │
       └────────▶│   Orchestrator   │─────────────┘
                 │  (pipeline)      │
                 │  parse→geom→     │
                 │  texture→render→ │
                 │  export          │
                 └─────────────────┘
```

### Микросервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| **Gateway** | 8080 | API Gateway, роутинг, SSE stream, статика |
| **LLM Service** | 8081 | Прокси к OpenRouter, парсинг промтов |
| **Blender Service** | 8082 | Выполнение bpy-скриптов, рендер, превью |

### Multi-Agent Pipeline

```
prompt → ParserAgent → GeometryAgent → TextureAgent → RenderAgent → ExportAgent
            │               │               │              │             │
         LLM/reg        bpy-скрипт     PBR-материалы   Blender CLI    GLB/IFC
```

## Что нового в v5.0

### 🔄 Оркестратор подключён к Blender
- **Агенты реально выполняют задачи** через blender-service `/api/v1/execute`
- RenderAgent, ExportAgent, TextureAgent вызывают Blender CLI
- Полный pipeline: парсинг → геометрия → текстуры → рендер → экспорт

### 🎨 16K Quality
| Пресет | Разрешение | Движок | Семплы |
|--------|-----------|--------|--------|
| preview | 1280×720 | EEVEE Next | 64 |
| standard | 3840×2160 | EEVEE Next | 128 |
| high | 7680×4320 | EEVEE Next | 256 |
| ultra | 15360×8640 | Cycles | 1024 |
| **16k** | **15360×8640** | **Cycles** | **2048** |

- Adaptive sampling, denoising (OpenImageDENOISE)
- PBR-материалы с procedural текстурами (noise, bump, color ramp)
- EEVEE Next заменяет deprecated EEVEE

### 👁️ Preview + Анализ
- `/api/v1/preview` — быстрое превью (1920×1080, ~30 сек)
- `shared/preview.py` — генерация превью + анализ через mimo-omni
- Скриншоты с аннотациями (размер, имя файла)

### 🏛️ BIM / IFC
- IfcOpenShell интеграция — генерация IFC-файлов
- Стены, окна, двери, перекрытия, крыши, помещения

### 📐 Floor Plans
- Shapely + SVG — 2D-планы этажей с мебелью и размерами

### 📊 Building Graph
- NetworkX — граф связей помещений
- SVG-визуализация

### 🔄 Async Tasks
- Celery + Redis — длинные задачи асинхронно
- Статус через REST API

### 🎤 Voice Input
- Whisper — голосовой ввод промтов (русский/английский)

## Быстрый старт

### Docker Compose (рекомендуется)

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
docker-compose up --build
# → http://localhost:8080
```

### Локально

```bash
pip install fastapi uvicorn httpx pydantic ifcopenshell shapely networkx celery redis Pillow

cp .env.example .env
python server.py
# → http://localhost:8080
```

## API

### Генерация (через оркестратор)

```bash
# Полный pipeline с 16K качеством
curl -X POST http://localhost:8080/api/v1/orchestrator/execute \
  -H "Content-Type: application/json" \
  -d '{"prompt": "двухэтажный кирпичный дом 10x12", "quality": "16k", "export_formats": ["glb", "ifc"]}'

# Быстрое превью
curl -X POST http://localhost:8080/api/v1/preview \
  -H "Content-Type: application/json" \
  -d '{"prompt": "современная спальня 6x8"}' --output preview.png

# SSE stream прогресса
curl http://localhost:8080/api/v1/orchestrator/jobs/{job_id}/stream
```

### Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/orchestrator/execute` | POST | Полный pipeline (parse→render→export) |
| `/api/v1/orchestrator/jobs/{id}` | GET | Статус задачи |
| `/api/v1/orchestrator/jobs/{id}/stream` | GET | SSE прогресс |
| `/api/v1/preview` | POST | Быстрое превью |
| `/api/v1/generate` | POST | Быстрая генерация (legacy) |
| `/api/v1/parse` | POST | Парсинг промта |
| `/api/v1/health` | GET | Health check |

### Качество рендера

```json
{
  "prompt": "...",
  "quality": "16k",
  "export_formats": ["glb", "ifc", "svg"]
}
```

Значения `quality`: `preview`, `standard`, `high`, `ultra`, `16k`

## Структура проекта

```
AI_Arhitector/
├── shared/                    # Единая библиотека
│   ├── config.py              # Настройки из env
│   ├── models.py              # Pydantic-модели
│   ├── validation.py          # Валидация параметров
│   ├── parser.py              # LLM + regex парсер
│   ├── blender.py             # bpy-скрипты (PBR, лестницы)
│   ├── ifc_generator.py       # IFC через IfcOpenShell
│   ├── floorplan.py           # SVG планы через Shapely
│   ├── graph.py               # Граф здания (NetworkX)
│   ├── preview.py             # 🆕 Превью + анализ
│   ├── streaming.py           # SSE прогресс
│   ├── clarification.py       # Уточняющие вопросы
│   ├── upscaler.py            # Real-ESRGAN апскейл
│   ├── voice.py               # Whisper голосовой ввод
│   └── agents/                # Multi-agent система
│       ├── orchestrator.py    # 🆕 Полный pipeline
│       ├── parser_agent.py    # Парсинг промтов
│       ├── geometry_agent.py  # Генерация геометрии
│       ├── texture_agent.py   # 🆕 PBR материалы
│       ├── render_agent.py    # 🆕 Рендер (до 16K)
│       └── export_agent.py    # 🆕 Экспорт (GLB/IFC/OBJ)
├── gateway/                   # API Gateway (:8080)
├── llm-service/               # LLM прокси (:8081)
├── blender-service/           # Blender CLI (:8082)
│   └── app.py                 # 🆕 /execute + /preview
├── server.py                  # Монолит (локальная разработка)
├── docker-compose.yml         # Docker Compose
└── Dockerfile                 # Единый Dockerfile
```

## Технологический стек

| Компонент | Технология | Статус |
|-----------|-----------|--------|
| API Gateway | FastAPI | ✅ |
| LLM | OpenRouter (Gemini Flash) | ✅ |
| 3D Rendering | Blender CLI (EEVEE Next / Cycles) | ✅ |
| BIM/IFC | IfcOpenShell | ✅ |
| Floor Plans | Shapely + SVG | ✅ |
| 3D Viewer | Three.js | ✅ |
| Async Queue | Celery + Redis | ✅ |
| Graph | NetworkX | ✅ |
| Upscaling | Real-ESRGAN / PIL | ✅ |
| Voice | Whisper | ✅ |
| Preview | mimo-omni | ✅ |

## Переменные окружения

| Переменная | Обязательна | Описание |
|-----------|-------------|----------|
| `OPENROUTER_API_KEY` | Да | Ключ от openrouter.ai |
| `LLM_MODEL` | Нет | Модель LLM (default: google/gemini-2.5-flash) |
| `REDIS_URL` | Нет | Redis для Celery (default: localhost:6379) |
| `BLENDER_PATH` | Нет | Путь к Blender (default: blender) |
| `OUTPUT_DIR` | Нет | Директория выходных файлов (default: /app/output) |

## Лицензия

MIT
