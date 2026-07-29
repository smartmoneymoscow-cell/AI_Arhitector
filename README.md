# Architect v12.0 🏗️

AI-архитектор — генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Что нового в v12.0

### 🆕 BIM / IFC
- **IfcOpenShell интеграция** — генерация настоящих IFC-файлов с BIM-объектами (IfcWall, IfcWindow, IfcDoor, IfcSlab, IfcRoof, IfcSpace)
- Параметры стен, площади помещений, свойства BIM

### 🆕 Floor Plans
- **Shapely + SVG** — генерация 2D-планов этажей с помещениями, мебелью, размерными линиями
- Компас, масштабная лейка, легенда

### 🆕 Async Task Queue
- **Celery + Redis** — длинные задачи (Blender, IFC, апскейл) выполняются асинхронно
- Статус задач через REST API (`/api/v1/tasks/{id}`)
- Progress tracking

### 🆕 Building Graph
- **NetworkX** — граф связей помещений (смежность, маршруты)
- Статистика по этажам и типам помещений
- SVG-визуализация графа

### 🆕 Image Upscaling
- **Real-ESRGAN** — апскейл рендеров интерьеров (640×480 → 1920×1080+)
- PIL fallback если GPU недоступен

### 🆕 Voice Input
- **Whisper** — голосовой ввод промтов (русский/английский)
- OpenAI API + локальный fallback

### Архитектурные изменения (v11.0)
- Единый `shared/` пакет — ноль дублирования кода
- Улучшенные bpy-скрипты (PBR, окна с рамами, лестницы, водостоки)
- Исправленный фронтенд (Three.js error handling, таймауты)

## Структура проекта

```
AI_Arhitector/
├── shared/                    # Единая библиотека
│   ├── config.py              # Настройки из env
│   ├── models.py              # Pydantic-модели
│   ├── validation.py          # Валидация параметров
│   ├── parser.py              # LLM + regex парсер
│   ├── blender.py             # bpy-скрипты (PBR, лестницы)
│   ├── ifc_generator.py       # 🆕 IFC через IfcOpenShell
│   ├── floorplan.py           # 🆕 SVG планы через Shapely
│   ├── celery_app.py          # 🆕 Async очередь (Celery)
│   ├── upscaler.py            # 🆕 Real-ESRGAN апскейл
│   ├── graph.py               # 🆕 Граф здания (NetworkX)
│   └── voice.py               # 🆕 Whisper голосовой ввод
├── gateway/                   # API Gateway
├── llm-service/               # LLM прокси
├── blender-service/           # Blender CLI
├── server.py                  # Монолит (локальная разработка)
├── docker-compose.yml         # Docker Compose + Redis
└── .env.example               # Шаблон переменных
```

## Быстрый старт

### Локально

```bash
# Установить зависимости
pip install fastapi uvicorn httpx pydantic ifcopenshell shapely networkx celery redis Pillow

# Запустить Redis (для Celery)
docker run -d -p 6379:6379 redis:alpine

# Скопировать .env
cp .env.example .env

# Запустить сервер
python server.py
# → http://localhost:8080

# Запустить Celery worker (в отдельном терминале)
celery -A shared.celery_app worker --loglevel=info
```

### Docker Compose

```bash
export OPENROUTER_API_KEY="***"
docker-compose up --build
# → http://localhost:8080 (включает Redis + Celery worker)
```

## API Endpoints

### Генерация

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/generate` | POST | Текст → GLB/PNG (синхронно) |
| `/api/v1/tasks/generate` | POST | Текст → GLB (async через Celery) |
| `/api/v1/tasks/{id}` | GET | Статус async задачи |
| `/api/v1/ifc/generate-local` | POST | Текст → IFC-файл |
| `/api/v1/floorplan/svg-local` | POST | Параметры → SVG план |
| `/api/v1/graph/building-local` | POST | Параметры → граф здания |
| `/api/v1/graph/building-local/svg` | POST | Параметры → SVG графа |

### Анализ

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/parse` | POST | Текст → параметры |
| `/api/v1/health` | GET | Health check всех сервисов |

## Технологический стек

| Компонент | Технология | Статус |
|-----------|-----------|--------|
| BIM/IFC | IfcOpenShell | ✅ |
| Floor Plans | Shapely + SVG | ✅ |
| 3D Viewer | Three.js | ✅ |
| Rendering | Blender CLI | ✅ |
| Async Queue | Celery + Redis | ✅ |
| Graph | NetworkX | ✅ |
| Upscaling | Real-ESRGAN / PIL | ✅ |
| Voice | Whisper | ✅ |
| API | FastAPI | ✅ |
| LLM | OpenRouter | ✅ |

## Переменные окружения

См. [`.env.example`](.env.example).

| Переменная | Обязательна | Описание |
|-----------|-------------|----------|
| `OPENROUTER_API_KEY` | Да | Ключ от openrouter.ai |
| `REDIS_URL` | Нет | Redis для Celery (default: localhost:6379) |
| `OPENAI_API_KEY` | Нет | Для Whisper (fallback на локальный) |
| `LLM_MODEL` | Нет | Модель LLM |
| `BLENDER_PATH` | Нет | Путь к Blender |

## Лицензия

MIT
