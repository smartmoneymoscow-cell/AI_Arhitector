# 📚 Architect AI — Документация

## Архитектура системы (v11.2.1)

```
Пользователь (браузер)
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  Nginx (routing, rate limiting, SSL)                 │
└───┬──────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Gateway (:8080)                                     │
│  ├── FastAPI Backend (routing only)                  │
│  ├── Оркестратор пайплайна                           │
│  └── Load Balancer (Blender instances)               │
└───┬──────────┬──────────┬────────────────────────────┘
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────────────┐
│ Agent  │ │ LLM    │ │ Blender        │
│ Pool   │ │Service │ │ Service        │
│ :8083  │ │:8081   │ │ :8082          │
│30 agents│ │Gemini  │ │ Cycles CPU/GPU │
│isolated│ │Flash   │ │                │
└────────┘ └────────┘ └────────────────┘
    │
    ▼
┌────────┐
│ Redis  │
│ :6379  │
│ state  │
└────────┘
```

### Agent Pool (v11.2.1+)

Все 30 агентов выполняются в отдельном сервисе `agent-pool` через HTTP:
- `POST /api/v1/agents/{name}/run` — запуск агента в изолированном thread
- Timeout по умолчанию 120с
- Gateway вызывает agent-pool вместо `importlib.import_module()`

## Pipeline обработки промта

```
1. Пользователь вводит промт
2. Frontend → POST /api/v1/parse (LLM парсинг)
3. LLM возвращает: object_type, room_type, style, features, furniture
4. Frontend показывает:
   ├── 🧠 Reasoning (анализ запроса)
   ├── 📋 Декомпозиция (5 шагов с агентами)
   ├── 💬 Уточняющие вопросы (кнопки-ответы)
   └── 🖼 Референсы (иконки релевантные промту)
5. Frontend → POST /api/v1/orchestrator/execute
6. Оркестратор:
   ├── LLM Agent → парсинг параметров
   ├── Geometry Agent → генерация геометрии (bpy-скрипт)
   ├── Texture Agent → применение материалов
   ├── Lighting Agent → настройка освещения
   ├── Blender → рендер (Cycles CPU)
   └── Quality Agent → проверка качества
7. Результат → GLB модель + PNG рендер
8. Frontend загружает GLB в Three.js viewer
```

## API Endpoints

### Gateway (architect-gateway.onrender.com)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Статус сервиса |
| `/api/v1/parse` | POST | LLM парсинг промта |
| `/api/v1/generate` | POST | Генерация 3D модели |
| `/api/v1/orchestrator/execute` | POST | Полный pipeline через оркестратор |
| `/api/v1/preview` | POST | Быстрое превью |

### LLM Service (architect-llm-1s1j.onrender.com)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Статус сервиса |
| `/api/v1/parse` | POST | Парсинг промта через Gemini |

### Blender Service (ai-arch-blender3d.onrender.com)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Статус сервиса |
| `/api/v1/execute` | POST | Выполнение bpy-скрипта |
| `/api/v1/generate` | POST | Генерация из промта |
| `/api/v1/preview` | POST | Быстрое превью PNG |

## Типы генерации

### Интерьеры (object_type: "interior")

| room_type | Название | Стандартная мебель |
|-----------|----------|-------------------|
| bathroom | Ванная комната | ванна, раковина, унитаз |
| children | Детская | кровать, шкаф, стол |
| kitchen | Кухня | стол, стулья, техника |
| bedroom | Спальня | кровать, шкаф, тумбочка |
| living | Гостиная | диван, стол, телевизор |
| office | Кабинет | стол, стул, книжный шкаф |

### Здания (object_type: "building")

| building_type | Название | Особенности |
|---------------|----------|-------------|
| house | Жилой дом | этажи, кровля, фасад |
| office | Офис | стекло, много этажей |
| cottage | Коттедж | дерево, камин |
| hotel | Гостиница | бассейн, парковка |

## Рендер

### Cycles CPU (текущий)

- **Движок:** Cycles
- **Устройство:** CPU
- **Samples:** 16-32
- **Denoising:** Отключён (нет OpenImageDenoiser)
- **Разрешение:** 1920×1080 (preview), 3840×2160 (standard)
- **Время:** ~60 сек на сцену

### 16K Tiled (опционально)

- **Разрешение:** 15360×8640 (132 мегапикселя)
- **Тайлы:** 4×3 = 12 тайлов
- **Каждый тайл:** 3840×2880
- **Samples:** 512-2048
- **Время:** ~10 мин на тайл

## Стили интерьеров

| Стиль | Цвет стен | Цвет пола | Акцент |
|-------|-----------|-----------|--------|
| modern | #F5F5F5 | #C4A882 | #2B3D4F |
| classic | #F0E6D4 | #8C6914 | #8C0000 |
| scandinavian | #FAFAFA | #D4B896 | #8FBD8F |
| loft | #A1A1A1 | #6B6B6B | #FF6B36 |
| minimalist | #FFFFFF | #E0D9CC | #000000 |
| hitech | #E6E6F2 | #4D4D59 | #0099CC |

## Агенты системы

| Агент | Роль | Вход | Выход |
|-------|------|------|-------|
| LLM Agent | Парсинг промта | текст | параметры (JSON) |
| Style Agent | Определение стиля | параметры | стиль, палитра |
| Concept Agent | Создание концепции | стиль | описание, moodboard |
| Geometry Agent | Генерация геометрии | параметры | bpy-скрипт |
| Texture Agent | Применение текстур | материалы | PBR материалы |
| Lighting Agent | Настройка освещения | время суток | bpy-скрипт света |
| Furniture Agent | Расстановка мебели | комната, мебель | координаты |
| Render Agent | Рендер | сцена | PNG/GLB |
| Quality Agent | Проверка качества | рендер | оценка, рекомендации |
| Compliance Agent | Проверка нормативов | параметры | отчёт |

## Environment Variables

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `ARCH_API_KEYS` | API ключи (через запятую) | `arch-prod-key-2024` |
| `LLM_SERVICE_URL` | URL LLM сервиса | `https://architect-llm-1s1j.onrender.com` |
| `BLENDER_SERVICE_URL` | URL Blender сервиса | `https://ai-arch-blender3d.onrender.com` |
| `BLENDER_SERVICE_URL_2` | Blender failover | `https://architect-blender.onrender.com` |
| `CORS_ORIGINS` | Разрешённые origins | `https://smartmoneymoscow-cell.github.io` |
| `REDIS_URL` | URL Redis | `redis://redis:6379/0` |
| `PORT` | Порт сервиса | `8080` |

## Известные ограничения

1. **Render Free Tier** — сервисы засыпают через 15 мин без активности
2. **Cycles CPU** — медленнее чем GPU (~60 сек vs ~10 сек)
3. **Нет OpenImageDenoiser** — шум при низком количестве samples
4. **LLM квоты** — Gemini free tier имеет лимиты на запросы
