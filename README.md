# Architect v6.0 🏗️

AI-архитектор — генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Архитектура

```
Client → Nginx (:80) → Gateway (:8080) → LLM Service (:8081)
                                           → Blender Service (:8082)
         Redis (:6379) — LLM cache + Celery broker
```

### Микросервисы

| Сервис | Образ | Порт | Описание |
|--------|-------|------|----------|
| **Nginx** | nginx:1.27-alpine | 80 | Rate limiting, gzip, cache, SSL, security headers |
| **Gateway** | ~200 MB | 8080 | API Gateway, оркестрация, frontend |
| **LLM Service** | ~200 MB | 8081 | LLM-only парсинг (каскад 7 моделей + Redis кеш) |
| **Blender Service** | ~3 GB | 8082 | 3D генерация, рендер (до 16K tiled), экспорт |
| **Redis** | redis:7-alpine | 6379 | LLM кеш (24h TTL) + Celery broker |

### Multi-Agent Pipeline

```
prompt → ParserAgent → GeometryAgent → TextureAgent → RenderAgent → QualityAgent → ExportAgent
            │               │               │              │              │             │
         LLM каскад     bpy-скрипт     PBR материалы   Blender CLI   Проверка      GLB/IFC
```

## Что нового в v6.0

### 🤖 LLM-only парсинг (regex УДАЛЁН)
- Каскад 7 моделей: Gemini Pro → Claude Sonnet → Gemini Flash → GPT-4o-mini → Llama 4 free → Qwen3 free → DeepSeek free
- Redis кеш (L2, 24h TTL) + in-memory (L1, 5min TTL)
- `AllModelsFailedError` при недоступности всех моделей

### 🌐 Nginx Gateway
- Rate limiting: `/parse` 20rpm, `/generate` 5rpm, `/health` 60rpm
- SSE proxy buffering off для streaming
- Gzip сжатие, static caching (7 дней), API response caching (1h)
- Security headers (X-Frame-Options, X-Content-Type-Options, CSP)

### 🐳 Per-service Dockerfiles
- `gateway.Dockerfile` — multi-stage, ~200 MB, без Blender
- `llm.Dockerfile` — multi-stage, ~200 MB, без Blender
- `blender.Dockerfile` — ~3 GB, Blender + Xvfb

### 🖼️ 16K Tiled Rendering
- Разбивает 15360×8640 на 12 тайлов (4×3 по 3840×2880)
- Рендерит каждый тайл через Blender Cycles (2048 samples)
- Собирает финальное изображение через PIL

### ✅ QualityAgent
- Проверка разрешения (≥ target resolution)
- Проверка file size (sanity check)
- Опциональный AI-анализ через mimo-omni

### 🔐 Auth
- API key через `X-API-Key` header
- Rate limiting (30 rpm / 200 rph per client)

### 🎨 Качество рендера

| Пресет | Разрешение | Движок | Семплы |
|--------|-----------|--------|--------|
| preview | 1280×720 | EEVEE Next | 64 |
| standard | 3840×2160 | EEVEE Next | 128 |
| high | 7680×4320 | EEVEE Next | 256 |
| ultra | 15360×8640 | Cycles | 1024 |
| **16k** | **15360×8640** | **Cycles** | **2048** |

## Быстрый старт

### Docker Compose (рекомендуется)

```bash
export OPENROUTER_API_KEY="***"
docker-compose up --build
# → http://localhost:80
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
curl -X POST http://localhost/api/v1/orchestrator/execute \
  -H "Content-Type: application/json" \
  -d '{"prompt": "двухэтажный кирпичный дом 10x12", "quality": "16k", "export_formats": ["glb", "ifc"]}'

# Быстрое превью
curl -X POST http://localhost/api/v1/preview \
  -H "Content-Type: application/json" \
  -d '{"prompt": "современная спальня 6x8"}' --output preview.png

# SSE stream прогресса
curl http://localhost/api/v1/orchestrator/jobs/{job_id}/stream
```

### Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/orchestrator/execute` | POST | Полный pipeline (parse→render→export) |
| `/api/v1/orchestrator/jobs/{id}` | GET | Статус задачи |
| `/api/v1/orchestrator/jobs/{id}/stream` | GET | SSE прогресс |
| `/api/v1/preview` | POST | Быстрое превью |
| `/api/v1/generate` | POST | Быстрая генерация (legacy) |
| `/api/v1/parse` | POST | Парсинг промта (LLM-only) |
| `/api/v1/render/16k` | POST | 16K tiled rendering |
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

## Тесты

```bash
# Unit-тесты (137 тестов)
PYTHONPATH=. python3 -m pytest tests/ -v

# E2E тесты (22 теста)
PYTHONPATH=. python3 tests/test_e2e_automated.py

# Все тесты (169 тестов)
PYTHONPATH=. python3 -m pytest tests/test_generation.py tests/test_server.py tests/test_orchestrator.py -v && \
PYTHONPATH=. python3 tests/test_e2e.py && \
PYTHONPATH=. python3 tests/test_e2e_automated.py
```

## Структура проекта

```
AI_Arhitector/
├── shared/                    # Единая библиотека
│   ├── config.py              # Настройки из env
│   ├── models.py              # Pydantic-модели
│   ├── validation.py          # Валидация параметров
│   ├── parser.py              # LLM-only парсинг (каскад 7 моделей)
│   ├── auth.py                # API key + rate limiting
│   ├── tiled_render.py        # 16K tiled rendering
│   ├── blender.py             # bpy-скрипты (PBR, лестницы)
│   ├── ifc_generator.py       # IFC через IfcOpenShell
│   ├── floorplan.py           # SVG планы через Shapely
│   ├── preview.py             # Превью + анализ
│   ├── streaming.py           # SSE прогресс
│   ├── clarification.py       # Уточняющие вопросы
│   └── agents/                # Multi-agent система
│       ├── orchestrator.py    # Полный pipeline
│       ├── parser_agent.py    # LLM-only парсинг
│       ├── geometry_agent.py  # Генерация геометрии
│       ├── texture_agent.py   # PBR материалы
│       ├── render_agent.py    # Рендер (до 16K)
│       ├── quality_agent.py   # Проверка качества
│       └── export_agent.py    # Экспорт (GLB/IFC/OBJ)
├── gateway/                   # API Gateway (:8080)
├── llm-service/               # LLM прокси (:8081)
├── blender-service/           # Blender CLI (:8082)
├── nginx.conf                 # Nginx конфиг
├── gateway.Dockerfile         # Gateway образ (~200MB)
├── llm.Dockerfile             # LLM Service образ (~200MB)
├── blender.Dockerfile         # Blender Service образ (~3GB)
├── docker-compose.yml         # Production compose
├── AUDIT.md                   # Ответы на 12 вопросов аудита
├── ROADMAP.md                 # 6-фазный план улучшений
├── tests/                     # Тесты (169 total)
│   ├── test_generation.py     # Unit-тесты парсера
│   ├── test_server.py         # Unit-тесты сервера
│   ├── test_orchestrator.py   # Unit-тесты оркестратора
│   ├── test_e2e.py            # E2E тесты (моки)
│   └── test_e2e_automated.py  # Автоматизированные E2E
└── server.py                  # Монолит (локальная разработка)
```

## Технологический стек

| Компонент | Технология | Статус |
|-----------|-----------|--------|
| API Gateway | FastAPI + Nginx | ✅ |
| LLM | OpenRouter (7-model cascade) | ✅ |
| Cache | Redis (24h) + in-memory (5min) | ✅ |
| 3D Rendering | Blender CLI (EEVEE Next / Cycles) | ✅ |
| BIM/IFC | IfcOpenShell | ✅ |
| Floor Plans | Shapely + SVG | ✅ |
| 3D Viewer | Three.js | ✅ |
| Async Queue | Celery + Redis | ✅ |
| Quality Check | QualityAgent + mimo-omni | ✅ |
| Auth | API key + rate limiting | ✅ |

## Переменные окружения

| Переменная | Обязательна | Описание |
|-----------|-------------|----------|
| `OPENROUTER_API_KEY` | Да | Ключ от openrouter.ai |
| `LLM_MODEL` | Нет | Модель LLM (default: google/gemini-2.5-flash) |
| `REDIS_URL` | Нет | Redis (default: redis://localhost:6379/0) |
| `BLENDER_PATH` | Нет | Путь к Blender (default: blender) |
| `OUTPUT_DIR` | Нет | Директория выходных файлов (default: /app/output) |
| `ARCH_API_KEYS` | Нет | API ключи (через запятую) |
| `CORS_ORIGINS` | Нет | Разрешённые origins (через запятую, default: *) |

## Лицензия

MIT
