# 📖 AI_Arhitector v11.2.0 — Полная документация (Wiki)

> Обновлено: 2026-08-09 (v11.2.0 — Frontend/Backend Stitching + Critical Pipeline Fixes)

---

## Содержание

1. [Обзор проекта](#1-обзор-проекта)
2. [Архитектура системы](#2-архитектура-системы)
3. [Pipeline обработки](#3-pipeline-обработки)
4. [LLM-каскад](#4-llm-каскад)
5. [Руководство по настройке](#5-руководство-по-настройке)
6. [API Reference](#6-api-reference)
7. [Агенты системы (25+)](#7-агенты-системы)
8. [Качество рендера](#8-качество-рендера)
9. [PDF/DWG анализ](#9-pdfdwg-анализ)
10. [Устранение неполадок](#10-устранение-неполадок)

---

## 1. Обзор проекта

**AI_Arhitector** — это AI-платформа для генерации 3D-моделей зданий и интерьеров по текстовому описанию на русском языке. Система принимает текстовый промт (например, «построй двухэтажный коттедж в стиле лофт из кирпича»), парсит его через LLM, запускает цепочку из 25+ специализированных агентов и выдаёт:

- **3D-модель** в формате GLB/GLTF
- **Фотореалистичный рендер** (PNG, до 16K разрешения)
- **IFC-файл** (BIM-данные)
- **SVG-чертежи** (планы этажей, разрезы, фасады)
- **PDF/DWG анализ** загруженных архитектурных чертежей

### Ключевые особенности

| Возможность | Описание |
|------------|----------|
| **Бесплатный LLM** | Google Gemini API (4 ключа с ротацией) + OpenRouter free models |
| **25+ AI-агентов** | Парсинг, геометрия, текстуры, свет, конструктив, нормативы, рендер |
| **PDF/DWG анализ** | Загрузка архитектурных чертежей, извлечение помещений и размеров |
| **Микросервисная архитектура** | Gateway, LLM Service, Blender Service, Redis |
| **Crash-safe pipeline** | Каждый агент в отдельном subprocess, circuit breaker |
| **До 16K рендера** | 15360×8640 пикселей, tiled rendering, Kaggle GPU |
| **Мульти-профиль** | 12 pipeline профилей: quick, standard, premium, interior и др. |

---

## 2. Архитектура системы

### Диаграмма микросервисов

```
┌──────────────────────────────────────────────────────────────────┐
│                        Пользователь (браузер)                    │
│                     Three.js 3D Viewer + Chat UI                 │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP/SSE
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Nginx (reverse proxy)                        │
│                  Порты: 80 (HTTP), 443 (HTTPS)                   │
│                  SSL: Let's Encrypt (certbot)                    │
└────────┬──────────────────────────────────┬──────────────────────┘
         │                                  │
         ▼                                  ▼ (static files)
┌─────────────────────────────┐   ┌─────────────────────┐
│     Gateway (FastAPI)       │   │    Frontend          │
│     Порт: 8080              │   │    index.html        │
│                             │   │    Three.js 3D       │
│  ┌───────────────────────┐  │   │    PDF/DWG upload    │
│  │    Orchestrator       │  │   └─────────────────────┘
│  │    (25+ agents)       │  │
│  │    Pipeline profiles  │  │
│  │    Clarification      │  │
│  │    Circuit breaker    │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │  Blender Load Balancer│  │
│  │  Round-robin + CB     │  │
│  └───────────────────────┘  │
└─────┬───────────┬───────────┘
      │           │
      ▼           ▼
┌───────────┐ ┌────────────────────┐
│ LLM       │ │ Blender Service    │
│ Service   │ │ Порт: 8082         │
│ Порт:8081 │ │                    │
│           │ │ Cycles CPU/GPU     │
│ Gemini    │ │ bpy-скрипты        │
│ OpenRouter│ │ HDRI освещение     │
│ Ollama    │ │ Tiled rendering    │
└─────┬─────┘ │ Kaggle GPU fallback│
      │       └────────────────────┘
      ▼
┌───────────┐
│  Redis    │
│  Порт:    │
│  6379     │
│           │
│  Кеш LLM │
│  Jobs DB  │
│  Sessions │
└───────────┘
```

### Компоненты

| Сервис | Технология | Порт | Назначение |
|--------|-----------|------|------------|
| **Nginx** | nginx:1.27-alpine | 80, 443 | Reverse proxy, SSL, static files |
| **Gateway** | FastAPI (Python) | 8080 | API routing, orchestrator, auth |
| **LLM Service** | FastAPI + httpx | 8081 | LLM cascade, prompt parsing |
| **Blender Service** | FastAPI + Blender CLI | 8082 | 3D generation, rendering |
| **Redis** | Redis 7 Alpine | 6379 | Cache, job storage, sessions |
| **Certbot** | certbot | — | SSL auto-renewal |
| **Aedifex Bridge** | FastAPI | 8085 | 3D editor bridge (Phase 1) |
| **Aedifex Editor** | Next.js | 3002 | 3D architectural editor UI |

### Docker Compose — ресурсы

| Сервис | Memory Limit | Reservations |
|--------|-------------|-------------|
| Nginx | 256 MB | — |
| Gateway | 512 MB | — |
| LLM Service | 512 MB | — |
| Blender Service | 8 GB | 2 GB |
| Redis | 300 MB | — |
| Aedifex Bridge | 256 MB | — |
| Aedifex Editor | 1 GB | — |

---

## 3. Pipeline обработки

### Полный pipeline (профиль «premium»)

```
Промт пользователя
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 0: Dialog Agent (multi-turn context)                  │
│  ├── Загрузка контекста предыдущих запросов                 │
│  ├── Определение модификации ("добавь балкон")              │
│  └── Обогащение промта контекстом                           │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Parser Agent (CRITICAL)                            │
│  ├── LLM-парсинг промта → JSON параметры                   │
│  ├── Pipeline: Gemini → OpenRouter → Ollama → Regex         │
│  ├── Pydantic-валидация + auto-fix                          │
│  └── Определение pipeline_profile (interior/landscape/...)  │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1.5: Clarification Engine                             │
│  ├── Проверка confidence (< 0.6 → вопросы)                  │
│  ├── LLM-генерация контекстных вопросов                     │
│  ├── Visual options с pros/cons                             │
│  └── Resume через /api/v1/orchestrator/resume               │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Router                                             │
│  ├── Определение шагов генерации                            │
│  └── Building params extraction                             │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Pre-pipeline Agents (PARALLEL, non-critical)       │
│  ├── Research Agent — референсы                             │
│  ├── Market Agent — рыночный анализ                         │
│  ├── Concept Agent — концепция                              │
│  ├── Brand Agent — бренд-айдентика                          │
│  ├── Style Agent — стиль + палитра                          │
│  └── Masterplan Agent — мастер-план                         │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Geometry + Texture (PARALLEL)                      │
│  ├── Geometry Agent (CRITICAL) → bpy-скрипт                 │
│  │   ├── Здание: стены, окна, двери, крыша, лестница        │
│  │   └── Интерьер: стены, пол, потолок, мебель              │
│  └── Texture Agent → PBR-материалы                          │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 5: Mid-pipeline Agents (PARALLEL, non-critical)       │
│  ├── Landscape Agent — деревья, газон, дорожки              │
│  ├── Furniture Agent — расстановка мебели                   │
│  ├── Lighting Agent — настройка освещения                   │
│  ├── MEP Agent — инженерные системы                         │
│  └── Structural Agent — конструктивный расчёт               │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 6: Render Agent                                       │
│  ├── Blender Service → Cycles рендер                        │
│  ├── HDRI world (Nishita sky model)                         │
│  ├── Quality presets: preview/standard/high/ultra/16k        │
│  ├── Kaggle GPU fallback                                    │
│  └── Quality gate retry (16K: 4096 samples + tiled)         │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 7: Quality Agent                                      │
│  ├── Проверка разрешения                                    │
│  ├── Проверка file size                                     │
│  └── Опциональный AI-анализ                                 │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 8: Post-pipeline Agents                               │
│  ├── Compliance Agent — проверка нормативов (СП, ГОСТ)      │
│  ├── Financial Agent — смета материалов                     │
│  ├── Presentation Agent — презентация                       │
│  └── SVG Drawings — планы, разрезы, фасады                  │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 9: Export Agent                                       │
│  ├── GLB/GLTF (Three.js viewer)                             │
│  ├── IFC (BIM)                                              │
│  └── SVG drawings (floor plan, section, elevation)          │
└─────────────────────────────────────────────────────────────┘
```

### Pipeline профили

| Профиль | Агенты | Назначение |
|---------|--------|------------|
| `quick` | parser → geometry → texture → render → quality → compliance → export | Быстрая генерация |
| `standard` | parser → style → geometry → texture → lighting → structural → compliance → render → quality → export | Стандартный pipeline |
| `cad` | parser → style → cad → geometry → texture → lighting → render → quality → compliance → export | Из CAD-файлов |
| `interactive` | dialog → parser → style → geometry → texture → lighting → render → quality → export | С диалогом |
| `full` | parser → research → concept → style → masterplan → geometry → texture → furniture → lighting → render → quality → structural → compliance → export | Полный pipeline |
| `premium` | parser → research → market → concept → brand → style → masterplan → landscape → geometry → texture → furniture → lighting → mep → structural → render → quality → compliance → financial → export → presentation | Максимальный |
| `interior` | parser → concept → style → furniture → lighting → texture → render → quality → compliance → export | Интерьеры |
| `presentation` | parser → concept → style → geometry → texture → render → quality → export → presentation | Презентация |
| `electrical` | parser → el → compliance → export | Электрика |
| `landscape` | parser → research → landscape → masterplan → compliance → export | Ландшафт |
| `mep_documentation` | parser → mep → mep_bim → compliance → export | Инженерные системы |
| `interior_full` | parser → concept → style → furniture → lighting → mep → el → structural → texture → render → quality → export | Полный интерьер |

---

## 4. LLM-каскад

### Стратегия fallback

Система использует 4-уровневый каскад LLM для бесплатного парсинга промтов:

```
Уровень 1: Google Gemini API (БЕСПЛАТНО)
    ├── ВСЕ ключи равноправны (round-robin, нет "основных")
    ├── Rate limit: 15 RPM/ключ → 60+ RPM суммарно
    ├── Модель: gemini-2.0-flash-lite-001 (настраивается)
    ├── Прямой API (не через OpenRouter)
    └── Cooldown: RPM → 60 сек, quota → 24 часа

    ↓ если все ключи исчерпаны или ошибка

Уровень 2: OpenRouter Free Models
    ├── Auto-discovery: обновление каждый час (background loop)
    ├── Eager discovery: при старте сервиса
    ├── Discovery → Redis:共享 между воркерами, переживает рестарт
    ├── 8+ моделей в каскаде
    ├── Приоритеты: tier 1 → tier 2 → tier 3
    ├── ВСЕ ключи равноправны (round-robin + cooldown)
    └── Модели: Gemma, Nemotron, GPT-OSS, Llama, Qwen, DeepSeek

    ↓ если все модели недоступны

Уровень 3: Ollama (локальный)
    ├── OLLAMA_URL — URL локального Ollama-сервера
    ├── OLLAMA_MODEL — модель (по умолчанию llama3.1:8b)
    └── Полностью бесплатно, работает оффлайн

    ↓ если Ollama не настроен

Уровень 4: Regex Fallback
    ├── Базовый regex-парсинг промта
    ├── Извлечение: тип здания, этажность, размеры, стиль
    └── Confidence: 0.1 (низкий)
```

### Key Health Tracker (v11.1.0)

Единая система управления ключами для Gemini и OpenRouter:

| Ситуация | Код ответа | Cooldown | Действие |
|----------|-----------|----------|----------|
| RPM-лимит | 429 (без "quota") | 60 сек | Ключ помечается, переход к следующему |
| Дневная квота | 402, "quota", "RESOURCE_EXHAUSTED" | 24 часа | Ключ помечается, переход к следующему |
| Невалидный ключ | 400, 403 | 24 часа | Ключ помечается как невалидный |
| Модель удалена | 404 | — | invalidate discovery, следующая модель |

**Cooldown переживает рестарт** — дублируется в Redis (`keycd:<hash>`).

**Endpoint мониторинга**: `GET /api/v1/keys/status`
```json
{
  "openrouter": {"total": 3, "alive": 2, "keys": [...]},
  "gemini": {"total": 4, "alive": 4, "keys": [...]},
  "total_accounts": 7
}
```

### Auto-discovery бесплатных моделей

Система автоматически запрашивает OpenRouter API (`/api/v1/models`) для поиска доступных бесплатных моделей:

- **TTL**: 1 час (обновление каскада)
- **Background loop**: обновление каждые 3600 сек в фоне
- **Eager discovery**: обновление при старте сервиса
- **Redis persistence**:共享 между воркерами
- **Фильтры**: цена = 0, поддержка text generation
- **Blocklist**: исключены музыкальные, vision, safety модели
- **Preferred**: gemini-2.5-flash, llama-3.3-70b, qwen3-235b, deepseek-v3
- **Лимит**: top 15 моделей
- **Защита от пустого ответа**: если 0 моделей — не затираем предыдущий список

### Кеширование

| Уровень | Хранилище | TTL | Макс. записей |
|---------|-----------|-----|---------------|
| L1 | In-memory (thread-safe) | 5 мин | 1000 |
| L2 | Redis | 24 ч | без ограничений |

### Безопасность LLM

- **Prompt sanitization**: удаление control characters, ограничение 2000 символов
- **Injection prevention**: фильтрация «ignore previous instructions», «system:», special tokens
- **Pydantic validation**: валидация ответа LLM через схему
- **Auto-retry с fix prompt**: при невалидном JSON — повторный запрос с исправлениями

---

## 5. Руководство по настройке

### Живая конфигурация ключей (v11.1.0)

**Живой LLM Service:** `https://architect-llm-1s1j.onrender.com` (Render Account #4)

| # | Провайдер | Переменная | Кол-во ключей | Статус |
|---|-----------|-----------|---------------|--------|
| 1 | OpenRouter | `OPENROUTER_API_KEY` | 1 | ✅ alive |
| 2 | OpenRouter | `OPENROUTER_FALLBACK_KEYS` | 2 | ✅ alive |
| 3 | Gemini | `GOOGLE_API_KEY` | 1 | ✅ alive |
| 4 | Gemini | `GOOGLE_FALLBACK_KEYS` | 7 | ✅ alive |
| | | **Итого** | **11** | **все alive** |

**НЕ живой** (старый деплой): `ai-arch-llmproxy.onrender.com` — 1 OR ключ, 0 Gemini. Не использовать.

### Render Accounts

| # | Аккаунт | URL | Что работает | LLM-ключей |
|---|---------|-----|-------------|------------|
| 1 | Render #1 | `ai-arch-blender3d.onrender.com` | Blender CLI, EEVEE 4K | — |
| 4 | Render #4 | `architect-gateway.onrender.com` | Gateway (фронтенд + прокси) | — |
| 4 | Render #4 | `architect-llm-1s1j.onrender.com` | LLM Service (парсинг промтов) | 11 |
| 4 | Render #4 | `architect-blender.onrender.com` | Blender Service | — |

### Каскад перебора (11 аккаунтов)

```
Промт пользователя
    ↓
1. Google Gemini (8 ключей, round-robin)
   gem-key-1 → gem-key-2 → ... → gem-key-8
   При 429: cooldown 60 сек → следующий ключ
   При 402/quota: cooldown 24ч → следующий ключ
    ↓ если все 8 исчерпаны
2. OpenRouter Free Models (3 ключа, round-robin)
   or-key-1 → or-key-2 → or-key-3
   Auto-discovery: 8+ бесплатных моделей, обновление каждый час
   При 404 модели → invalidate discovery + следующая модель
    ↓ если все 3 ключа × N моделей исчерпаны
3. Ollama (локальный, если настроен)
    ↓ если не настроен
4. Regex fallback (крайний случай)
```

### Мониторинг

```bash
# Сколько ключей настроено и живых
curl https://architect-llm-1s1j.onrender.com/api/v1/keys/status

# Статистика discovery бесплатных моделей
curl https://architect-llm-1s1j.onrender.com/api/v1/cache/stats

# Ручное обновление списка моделей
curl -X POST https://architect-llm-1s1j.onrender.com/api/v1/models/refresh
```

### Переменные окружения (.env)

#### Основные

| Переменная | Обязательна | Описание | Пример |
|-----------|-------------|----------|--------|
| `GOOGLE_API_KEY` | Рекомендуется | Google Gemini API key (бесплатно, все ключи равноправны) | `AIzaSy-key1` |
| `GOOGLE_FALLBACK_KEYS` | Опционально | Доп. Gemini ключи (round-robin) | `key2,key3` |
| `GEMINI_MODEL` | Опционально | Модель Gemini | `gemini-2.0-flash-lite-001` |
| `OPENROUTER_API_KEY` | Опционально | OpenRouter API key (все ключи равноправны) | `sk-or-v1-aaaa` |
| `OPENROUTER_FALLBACK_KEYS` | Опционально | Доп. OpenRouter ключи (round-robin) | `bbbb,cccc` |
| `KEY_COOLDOWN_RATE_LIMIT_SEC` | Опционально | Cooldown при RPM-лимите (сек) | `60` |
| `KEY_COOLDOWN_QUOTA_SEC` | Опционально | Cooldown при quota/402 (сек) | `86400` |

#### Gateway

| Переменная | Описание | Значение по умолчанию |
|-----------|----------|----------------------|
| `ARCH_API_KEYS` | API ключи для авторизации (через запятую) | `""` (без авторизации) |
| `CORS_ORIGINS` | Разрешённые origins (через запятую) | `*` |
| `REDIS_URL` | URL Redis | `redis://redis:6379/0` |
| `PORT` | Порт Gateway | `8080` |
| `OUTPUT_DIR` | Директория для выходных файлов | `/app/output` |
| `LLM_SERVICE_URL` | URL LLM Service | `http://llm-service:8081` |
| `BLENDER_SERVICE_URL` | URL Blender Service | `http://blender-service:8082` |
| `KAGGLE_RENDERER_URL` | URL Kaggle GPU renderer | `""` |
| `KAGGLE_POLLING_ENABLED` | Включить Kaggle polling | `false` |

#### LLM Service

| Переменная | Описание | Значение по умолчанию |
|-----------|----------|----------------------|
| `OPENROUTER_BASE` | Базовый URL OpenRouter | `https://openrouter.ai/api/v1` |
| `REDIS_URL` | URL Redis для кеша | `redis://redis:6379/1` |
| `OLLAMA_URL` | URL локального Ollama | `""` |
| `OLLAMA_MODEL` | Модель Ollama | `llama3.1:8b` |

#### Blender Service

| Переменная | Описание | Значение по умолчанию |
|-----------|----------|----------------------|
| `BLENDER_PATH` | Путь к Blender CLI | `blender` |
| `BLENDER_TIMEOUT` | Таймаут Blender (сек) | `300` |
| `RENDER_INTERIOR_TIMEOUT` | Таймаут рендера интерьера (сек) | `600` |

#### Ollama (опционально)

| Переменная | Описание | Пример |
|-----------|----------|--------|
| `OLLAMA_URL` | URL Ollama сервера | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | Модель | `llama3.1:8b` |

### Быстрый старт

```bash
# 1. Клонировать
git clone https://github.com/smartmoneymoscow-cell/AI_Arhitector.git
cd AI_Arhitector

# 2. Создать .env
cp .env.example .env

# 3. Заполнить ключи (минимум один):
#    GOOGLE_API_KEY=AIzaSy-xxxx        ← бесплатно
#    OPENROUTER_API_KEY=sk-or-xxxx     ← бесплатные модели

# 4. Запуск
docker-compose up -d

# 5. Проверить здоровье
curl http://localhost/health
```

### Получение API ключей

| Провайдер | Ссылка | Стоимость |
|-----------|--------|-----------|
| Google Gemini | https://aistudio.google.com/apikey | Бесплатно (15 RPM) |
| OpenRouter | https://openrouter.ai | Бесплатные модели (`:free`) |
| Ollama | https://ollama.com | Бесплатно (локально) |

---

## 6. API Reference

Подробное описание всех endpoints — в [API_REFERENCE.md](./API_REFERENCE.md).

### Краткий обзор

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Проверка здоровья сервиса |
| `/api/v1/parse` | POST | LLM-парсинг промта |
| `/api/v1/orchestrator/execute` | POST | Полный pipeline генерации |
| `/api/v1/orchestrator/resume` | POST | Продолжение после clarification |
| `/api/v1/orchestrator/jobs/{id}` | GET | Статус задачи |
| `/api/v1/orchestrator/jobs/{id}/stream` | GET | SSE stream прогресса |
| `/api/v1/generate` | POST | Генерация через Blender Service |
| `/api/v1/preview` | POST | Быстрое превью (PNG) |
| `/api/v1/clarify` | POST | Уточняющие вопросы |
| `/api/v1/clarify/answer` | POST | Применить ответы |
| `/api/v1/compliance/check` | POST | Проверка нормативов |
| `/api/v1/analyze/pdf` | POST | Анализ PDF чертежа |
| `/api/v1/analyze/dwg` | POST | Анализ DWG/DXF файла |
| `/api/v1/variants` | POST | Варианты дизайна |
| `/api/v1/context/{session_id}` | GET/DELETE | Управление сессиями |
| `/api/v1/kaggle/enqueue` | POST | Kaggle GPU задача |
| `/api/v1/kaggle/pending` | GET | Kaggle polling |
| `/api/v1/stats` | GET | Статистика (кеш, стоимость) |

---

## 7. Агенты системы

### Полный список агентов (25+)

#### Критические (pipeline падает при ошибке)

| Агент | Файл | Описание |
|-------|------|----------|
| **Parser Agent** | `shared/parser.py` | LLM-парсинг промта → JSON параметры. Gemini → OpenRouter → Ollama → Regex |
| **Geometry Agent** | `shared/agents/geometry_agent.py` | Генерация bpy-скрипта для 3D-геометрии (стены, окна, двери, крыша) |

#### Интеллектуальные (pre-pipeline, параллельно)

| Агент | Описание |
|-------|----------|
| **Dialog Agent** | Multi-turn контекст, определение модификаций |
| **Research Agent** | Поиск референсов и аналогов |
| **Market Agent** | Рыночный анализ (цены, тренды) |
| **Concept Agent** | Создание концепции и moodboard |
| **Brand Agent** | Бренд-айдентика проекта |
| **Style Agent** | Определение стиля + цветовая палитра |
| **Masterplan Agent** | Генерация мастер-плана участка |

#### Генерационные (mid-pipeline, параллельно)

| Агент | Описание |
|-------|----------|
| **Texture Agent** | PBR-материалы (roughness, metallic, emission) |
| **Furniture Agent** | Эргономичная расстановка мебели |
| **Lighting Agent** | Настройка освещения под стиль |
| **Landscape Agent** | Генерация окружения (деревья, газон, дорожки) |
| **MEP Agent** | Инженерные системы (вентиляция, отопление, водоснабжение) |
| **Structural Agent** | Конструктивный расчёт (нагрузки, фундамент) |
| **EL Agent** | Электрические системы |

#### Рендеринг и качество

| Агент | Описание |
|-------|----------|
| **Render Agent** | Рендер через Blender Service (Cycles). Quality presets, HDRI world, tiled rendering |
| **Quality Agent** | Проверка разрешения, file size, AI-анализ |

#### Пост-pipeline

| Агент | Описание |
|-------|----------|
| **Compliance Agent** | Проверка соответствия нормативам (СП, ГОСТ) |
| **Financial Agent** | Смета материалов и стоимость |
| **Presentation Agent** | Генерация презентации проекта |
| **Export Agent** | Экспорт в GLB, IFC, SVG |

#### Анализ файлов

| Агент | Файл | Описание |
|-------|------|----------|
| **PDF Analysis Agent** | `shared/agents/pdf_analysis_agent.py` | Парсинг PDF чертежей: помещения, размеры, MEP |
| **DWG Analysis Agent** | `shared/agents/dwg_analysis_agent.py` | Парсинг DXF/DWG: слои, блоки, размерные линии |

#### Прочие

| Агент | Описание |
|-------|----------|
| **CAD Agent** | Обработка CAD-данных |
| **MEP BIM Agent** | BIM-модель инженерных систем |
| **Drawings SVG Agent** | Генерация SVG-чертежей (планы, разрезы, фасады) |

### Изоляция агентов

Каждый агент запускается в **отдельном subprocess** через `AgentRunner`:

- Краш агента → pipeline продолжает с fallback
- Circuit breaker: 5 ошибок → агент отключается на 60 сек
- Timeout по умолчанию: 120 сек (render: 300 сек для 16K)
- Только parser и geometry — CRITICAL (остальные non-critical)

---

## 8. Качество рендера

### Пресеты качества

| Пресет | Разрешение | Samples | Denoising | Adaptive | Особенности |
|--------|-----------|---------|-----------|----------|-------------|
| `preview` | 1280×720 | 64 | ✅ | — | Быстрый preview |
| `standard` | 3840×2160 (4K) | 256 | ✅ | ✅ (0.05) | Стандартный рендер |
| `high` | 7680×4320 (8K) | 512 | ✅ | ✅ (0.02) | Высокое качество |
| `ultra` | 15360×8640 (16K) | 1024 | ✅ | ✅ (0.01) | Максимальное качество |
| `16k` | 15360×8640 (16K) | 2048 | ✅ | ✅ (0.005) | 16K с motion blur |

### Quality gate retry

Если запрошен 16K рендер, но фактическое разрешение ниже:

1. Первый рендер с стандартными настройками
2. Quality Agent проверяет разрешение
3. Если не 16K → retry с:
   - `samples_override`: 4096 samples
   - `use_tiled_render`: true (16 тайлов)
   - Timeout: 600 сек
4. Повторная проверка качества

### HDRI освещение

- **Nishita sky model** — процедурный небесный купол
- **Sun elevation**: 45° (настраивается)
- **Contact shadows**: GTAO/SSAO для ambient occlusion
- **3-точечный свет**: Key (Sun) + Fill (Area) + Rim (Area)

### Kaggle GPU Auto-Submit

Для ускорения рендера можно использовать бесплатный T4 GPU на Kaggle:

1. Настройка `KAGGLE_RENDERER_URL` в `.env`
2. Render Agent автоматически отправляет задачи на Kaggle
3. Polling-режим с экспоненциальным backoff
4. Fallback на локальный CPU если Kaggle недоступен

---

## 9. PDF/DWG анализ

### PDF Analysis Agent

Загрузка архитектурных чертежей в формате PDF для автоматического извлечения данных.

**Возможности:**
- Извлечение помещений (название, площадь, размеры)
- Определение размеров здания (ширина, длина, высота, этажность)
- Распознавание MEP-систем (вентиляция, отопление, водоснабжение, канализация, электрика)
- Определение типа чертежа (план, разрез, фасад, спецификация)
- Извлечение материалов из спецификаций
- Аннотации и текстовые пометки

**Используемые библиотеки:**
- `PyMuPDF (fitz)` — извлечение текста и аннотаций из PDF

**API:**
```bash
curl -X POST http://localhost/api/v1/analyze/pdf \
  -H "X-API-Key: your-key" \
  -F "file=@blueprint.pdf"
```

**Пример ответа:**
```json
{
  "file_name": "blueprint.pdf",
  "page_count": 5,
  "rooms": [
    {"name": "Гостиная", "area_m2": 20.52, "width_m": 5.4, "length_m": 3.8, "floor": 1, "materials": []},
    {"name": "Кухня", "area_m2": 14.7, "width_m": 4.2, "length_m": 3.5, "floor": 1, "materials": []}
  ],
  "dimensions": {"width_m": 10, "length_m": 12, "total_area_m2": 120, "floors": 2},
  "mep_systems": [
    {"system_type": "ventilation", "description": "Ventilation system detected", "components": ["вытяжк", "приточн"]}
  ],
  "materials": ["brick", "concrete", "plaster"],
  "drawing_type": "floor_plan",
  "warnings": []
}
```

### DWG/DXF Analysis Agent

Парсинг CAD-файлов через библиотеку `ezdxf`.

**Возможности:**
- Извлечение слоёв с классификацией (wall, door, window, furniture, mep и т.д.)
- Блоки и их базовые точки
- Размерные линии (DIMENSION entities)
- Текстовые аннотации (TEXT, MTEXT)
- Entity summary (подсчёт по типам)
- Bounding box (габариты чертежа)
- Архитектурные элементы по именам слоёв

**Конвертация DWG → DXF:**
- ODA File Converter (первый вариант)
- LibreCAD (fallback)

**API:**
```bash
curl -X POST http://localhost/api/v1/analyze/dwg \
  -H "X-API-Key: your-key" \
  -F "file=@floor_plan.dxf"
```

**Пример ответа:**
```json
{
  "file_name": "floor_plan.dxf",
  "file_format": "dxf",
  "layers": [
    {"name": "A-WALL", "color": 1, "linetype": "Continuous", "entity_count": 45, "is_architectural": true, "element_type": "wall"},
    {"name": "A-DOOR", "color": 3, "linetype": "Continuous", "entity_count": 8, "is_architectural": true, "element_type": "door"}
  ],
  "blocks": [
    {"name": "DOOR_SINGLE", "base_point": [0, 0, 0], "entity_count": 5, "element_type": "door"}
  ],
  "dimensions": [
    {"value": 5400.0, "text": "5400", "start": [0, 0], "end": [5400, 0], "layer": "A-DIM"}
  ],
  "entity_summary": {"LINE": 120, "ARC": 30, "TEXT": 25, "INSERT": 15},
  "architectural_elements": {
    "wall": {"layers": ["A-WALL"], "total_entities": 45},
    "door": {"layers": ["A-DOOR"], "total_entities": 8}
  },
  "bounding_box": {"min_x": 0, "min_y": 0, "max_x": 12000, "max_y": 8000, "width": 12000, "height": 8000}
}
```

### Интеграция с генерацией

После анализа PDF/DWG пользователь может:
1. Просмотреть результаты анализа в UI
2. Нажать «Использовать для 3D генерации»
3. Система автоматически подставит параметры в pipeline

---

## 10. Устранение неполадок

### Проблема: LLM не отвечает / все модели failed

**Симптомы:** `AllModelsFailedError`, Gateway возвращает 503

**Решения:**
1. Проверить `GOOGLE_API_KEY` в `.env`:
   ```bash
   docker-compose logs llm-service | grep -i "google\|gemini"
   ```
2. Проверить rate limit Gemini (15 RPM/ключ):
   ```bash
   curl http://localhost/api/v1/stats
   ```
3. Добавить дополнительные ключи:
   ```
   GOOGLE_API_KEY=key1
   GOOGLE_FALLBACK_KEYS=key2,key3,key4
   ```
4. Настроить Ollama как fallback:
   ```
   OLLAMA_URL=http://host.docker.internal:11434
   OLLAMA_MODEL=llama3.1:8b
   ```

### Проблема: Blender timeout

**Симптомы:** `Blender timeout (300s)`, render failed

**Решения:**
1. Увеличить таймаут:
   ```
   BLENDER_TIMEOUT=600
   RENDER_INTERIOR_TIMEOUT=900
   ```
2. Использовать preview качество:
   ```json
   {"quality": "preview"}
   ```
3. Настроить Kaggle GPU:
   ```
   KAGGLE_RENDERER_URL=https://your-kaggle-notebook-url
   ```

### Проблема: Circuit breaker OPEN

**Симптомы:** `Service blender circuit breaker OPEN — try again later`

**Решения:**
1. Подождать 60 секунд (автоматическое восстановление)
2. Проверить здоровье сервиса:
   ```bash
   curl http://localhost/health
   ```
3. Проверить логи:
   ```bash
   docker-compose logs blender-service --tail=50
   ```

### Проблема: Redis недоступен

**Симптомы:** Jobs не сохраняются, кеш не работает

**Решения:**
1. Проверить Redis:
   ```bash
   docker-compose ps redis
   docker-compose logs redis --tail=20
   ```
2. Перезапустить:
   ```bash
   docker-compose restart redis
   ```
3. Gateway работает без Redis (in-memory fallback), но jobs не персистентны

### Проблема: Низкое качество рендера

**Симптомы:** Шумное изображение, артефакты

**Решения:**
1. Увеличить samples:
   ```json
   {"quality": "high"}
   ```
2. Для 16K — система автоматически retry с 4096 samples
3. Использовать Kaggle GPU для лучшего качества

### Проблема: PDF анализ не находит комнаты

**Симптомы:** `"warnings": ["No rooms detected in PDF text"]`

**Решения:**
1. Убедиться, что PDF содержит текстовый слой (не растровое изображение)
2. Проверить, что PyMuPDF установлен:
   ```bash
   pip install pymupdf
   ```
3. Для сканированных PDF — OCR не поддерживается (пока)

### Проблема: DWG конвертация не работает

**Симптомы:** `"Cannot convert DWG to DXF"`

**Решения:**
1. Установить ODA File Converter:
   ```bash
   # Ubuntu/Debian
   apt-get install odafc
   ```
2. Или использовать DXF напрямую (конвертировать в AutoCAD/BricsCAD)
3. Проверить, что ezdxf установлен:
   ```bash
   pip install ezdxf
   ```

### Проблема: CORS ошибки

**Симптомы:** `Access-Control-Allow-Origin` в браузере

**Решения:**
1. Настроить `CORS_ORIGINS`:
   ```
   CORS_ORIGINS=https://your-domain.com,https://another.com
   ```
2. Никогда не используйте `*` в продакшене

### Проблема: Frontend не обновляется

**Симптомы:** Старая версия UI

**Решения:**
1. Очистить кеш браузера (Ctrl+Shift+R)
2. Проверить, что используется правильный `index.html`:
   ```bash
   docker-compose exec gateway ls -la /app/frontend/
   ```
3. Синхронизировать фронтенды (если вручную):
   ```bash
   cp index.html gateway/frontend/index.html
   cp index.html frontend/index.html
   ```

---

## Приложение A: Архитектурные стили интерьеров

| Стиль | Стены | Пол | Акцент | Описание |
|-------|-------|-----|--------|----------|
| `modern` | #F5F5F5 | #C4A882 | #2B3D4F | Современный минимализм |
| `classic` | #F0E6D4 | #8C6914 | #8C0000 | Классический стиль |
| `scandinavian` | #FAFAFA | #D4B896 | #8FBD8F | Скандинавский уют |
| `loft` | #A1A1A1 | #6B6B6B | #FF6B36 | Индустриальный лофт |
| `minimalist` | #FFFFFF | #E0D9CC | #000000 | Чистый минимализм |
| `hitech` | #E6E6F2 | #4D4D59 | #0099CC | Высокие технологии |

## Приложение B: Мебель для интерьеров

### Доступные предметы мебели

| Категория | Предметы |
|-----------|----------|
| **Гостиная** | sofa, sofa_bed, table, tv, chandelier, bookshelf |
| **Спальня** | bed, double_bed, single_bed, wardrobe, nightstand |
| **Кухня** | kitchen_counter, kitchen_island, dining_table, stove, fridge, oven, microwave, sink |
| **Ванная** | bathtub, jacuzzi, shower, shower_cabin, toilet, bidet, mirror, faucet, towel_rack |
| **Кабинет** | desk, chair, bookshelf |
| **Общее** | cabinet, washing_machine, dryer |

### Русские названия (автоматическая конвертация)

| Русский | English |
|---------|---------|
| кровать | bed |
| диван | sofa |
| шкаф | wardrobe |
| стол | table |
| стул | chair |
| ванна | bathtub |
| джакузи | jacuzzi |
| унитаз | toilet |
| зеркало | mirror |
| холодильник | fridge |
| плита | stove |
| телевизор | tv |

## Приложение C: Типы зданий

| Тип | Описание | Стандартные размеры |
|-----|----------|-------------------|
| `house` | Жилой дом | 10×12×3 м |
| `office` | Офис | 15×20×3.2 м |
| `cottage` | Коттедж | 12×14×3 м |
| `hotel` | Гостиница | 24×36×3.2 м |
| `townhouse` | Таунхаус | 8×12×3 м |
| `villa` | Вилла | 16×20×3.5 м |
| `barn` | Сарай | 3×4×2.5 м |
| `garage` | Гараж | 6×3×3 м |
| `gazebo` | Беседка | 3×3×2.5 м |
| `greenhouse` | Теплица | 3×6×2.5 м |
| `bathhouse` | Баня | 5×6×2.5 м |

## Приложение D: Нормативные документы

Система проверяет соответствие следующим нормативам:

| Документ | Название | Область |
|----------|----------|---------|
| СП 1.13130 | Эвакуационные пути и выходы | Безопасность |
| СП 54.13330 | Жилые здания | Жилое строительство |
| ГОСТ 21.501 | Правила выполнения рабочей документации | Чертежи |
| IBC | International Building Code | Международные |

---

---

## 11. Визуальное тестирование — результаты 2026-08-09

### Методология тестирования

Тестирование проводилось через:
1. **agent-browser** (headless Chromium) — навигация по UI, ввод промтов, скриншоты
2. **mimo-omni** — компьютерный анализ скриншотов
3. **Прямое API-тестирование** — curl-запросы к gateway на Render
4. **Code review** — анализ bpy-скриптов и pipeline

### 11.1 Инфраструктурные проблемы

#### 🔴 GitHub Pages не развёрнут
- **URL**: `https://smartmoneymoscow-cell.github.io/AI_Arhitector/`
- **Результат**: «Site not found» — страница не существует
- **Влияние**: Невозможно провести E2E тесты через публичный URL
- **Исправление**: Настроить GitHub Pages из ветки `gh-pages` или из `/docs`

#### 🔴 Render Gateway требует API Key
- **URL**: `https://architect-gateway.onrender.com`
- **Все endpoints** (`/api/v1/parse`, `/api/v1/orchestrator/execute`, `/api/v1/clarify`) возвращают `401: Missing API key`
- **Влияние**: Невозможно протестировать реальный pipeline без ключа
- **Проблема**: Нет тестового режима или публичного demo-endpoint
- **Рекомендация**: Добавить `/api/v1/demo` endpoint без авторизации с rate limit

#### 🟡 Blender Service работает
- **URL**: `https://ai-arch-blender3d.onrender.com/health`
- **Результат**: `{"status":"ok","service":"blender-service","version":"6.0.0"}`
- **URL**: `https://architect-blender.onrender.com/health`
- **Результат**: `{"status":"ok"}` — два экземпляра доступны

### 11.2 Проблемы Frontend UI

#### 🔴 Поле ввода не принимает программный ввод
- **Элемент**: `textarea[placeholder="Опишите здание или интерьер…"]`
- **Проблема**: `agent-browser fill @e23` не работает — значение не устанавливается
- **Workaround**: Через `eval` — `document.querySelector('textarea').value = '...'`
- **Причина**: React/Vue-подобная фреймворк не обрабатывает нативные события `input`
- **Исправление**: Использовать `Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(inp, text)` + `inp.dispatchEvent(new Event('input', {bubbles: true}))`

#### 🔴 Кнопка отправки не срабатывает программно
- **Проблема**: `agent-browser click @e24` не вызывает отправку формы
- **Причина**: Кнопка может использовать `mousedown`/`pointerdown` вместо `click`
- **Влияние**: E2E тесты через Puppeteer/Playwright не работают без нативных событий
- **Исправление**: Добавить обработчик `click` на кнопку отправки (не только `mousedown`)

#### 🟡 Демо-проекты — хардкод
- Sidebar показывает 5 предустановленных проектов (Коттедж, Офис, Таунхаус, Ванная, Отель)
- Это **не сгенерированные** модели, а статические данные
- При клике на проект — не видно загрузки 3D-модели в viewer

### 11.3 Проблемы Pipeline (Code Review + API анализ)

#### 🔴 Lighting Agent — bpy_script не используется (ИСПРАВЛЕНО в v11.0.1)
- **Файл**: `shared/agents/orchestrator.py`
- **Проблема**: Lighting agent генерирует bpy_script с HDRI, IES, time-of-day, но он НЕ добавлялся в render script
- **Цепочка**: `geometry_script + texture_script` → lighting_script **отсутствовал**
- **Исправление**: v11.0.1 — mid-pipeline bpy_scripts теперь интегрируются

#### 🔴 Building samples=16, denoiser OFF (ИСПРАВЛЕНО в v11.0.1)
- **Файл**: `shared/blender.py` строка 424-425
- **Проблема**: `samples = 16`, `use_denoising = False` — рендер зданий шумный
- **Исправление**: v11.0.1 — samples=256, denoiser=OPENIMAGEDENOISE

#### 🟡 Мебель из примитивов (НЕ ИСПРАВЛЕНО)
- **Файл**: `shared/blender.py`, `generate_interior_script()`
- **Проблема**: Вся мебель (кровати, столы, диваны, стулья) — это `primitive_cube_add` с масштабированием
- **Визуальный эффект**: Интерьер выглядит как Minecraft, не как реальная комната
- **Исправление**: Нужна asset library с GLB/GLTF моделями мебели
- **Приоритет**: 🟡 Важно (v11.1.0)

#### 🟡 Нет Boolean operations для окон/дверей (НЕ ИСПРАВЛЕНО)
- **Проблема**: Окна — отдельные кубы поверх стен, а не вырезанные проёмы
- **Визуальный эффект**: Стены не имеют сквозных отверстий, окна «плавают»
- **Исправление**: Использовать `bpy.ops.mesh.primitive_cube_add` + `bpy.ops.object.modifier_add(type='BOOLEAN')`
- **Приоритет**: 🟡 Важно (v11.1.0)

#### 🟡 Нет UV mapping (НЕ ИСПРАВЛЕНО)
- **Проблема**: Текстуры применяются без UV-развёртки
- **Визуальный эффект**: PBR-материалы выглядят плоско, без детализации
- **Исправление**: `bpy.ops.object.mode_set(mode='EDIT')` → `bpy.ops.uv.smart_project()`
- **Приоритет**: 🟡 Важно (v11.1.0)

#### 🟡 IFC генератор — ограниченный (ЧАСТИЧНО ИСПРАВЛЕНО в v11.0.1)
- **Проблема**: IFC-файл содержит базовые IfcWall/IfcWindow/IfcDoor, но:
  - Нет параметрических связей между элементами
  - Нет инженерных параметров (U-value, fire rating)
  - Нет quantity takeoff (объёмы материалов)
- **Исправление v11.0.1**: Добавлены PropertySets, spatial containment, roof aggregation
- **Остаётся**: Parametric constraints, engineering parameters

#### 🟡 StructuralAgent — упрощённый (НЕ ИСПРАВЛЕНО)
- **Проблема**: Нет FEM-анализа, нет расчёта прогибов, нет подбора арматуры
- **Влияние**: BIM-модель содержит справочные данные, а не инженерный расчёт
- **Исправление**: Интеграция с OpenSees или аналогом
- **Приоритет**: 🟢 Улучшение (v12.0)

#### 🟡 ComplianceAgent — чек-лист (НЕ ИСПРАВЛЕНО)
- **Проблема**: Проверяет параметры по таблицам СП, но НЕ проверяет:
  - Геометрическую корректность модели
  - Пересечения конструкций
  - Соответствие чертежей 3D-модели
- **Исправление**: Добавить валидацию геометрии через Blender API
- **Приоритет**: 🟢 Улучшение (v12.0)

### 11.4 Проблемы LLM-каскада

#### 🟡 OpenRouter возвращает 402 (нет кредитов)
- **Проблема**: Бесплатные модели `:free` требуют ненулевой баланс
- **Влияние**: Если Gemini API недоступен, fallback на OpenRouter не работает
- **Статус**: Gemini API настроен как основной, OpenRouter — фолбэк
- **Рекомендация**: Проверять баланс OpenRouter при старте

#### 🟡 Regex fallback — низкое качество парсинга
- **Проблема**: При недоступности всех LLM, regex-парсёр извлекает только базовые параметры
- **Confidence**: 0.1 (очень низкий)
- **Влияние**: Неточный парсинг → неправильная генерация

### 11.5 Сводная таблица проблем

| # | Проблема | Серьёзность | Статус | Версия исправления |
|---|----------|-------------|--------|--------------------|
| 1 | GitHub Pages не развёрнут | 🔴 | ❌ | — |
| 2 | Gateway требует API Key для всех endpoints | 🔴 | ❌ | Нужен demo endpoint |
| 3 | Frontend: textarea не принимает программный ввод | 🔴 | ❌ | v11.1.0 |
| 4 | Frontend: кнопка отправки не срабатывает программно | 🔴 | ❌ | v11.1.0 |
| 5 | Lighting bpy_script не в рендере | 🔴 | ✅ | v11.0.1 |
| 6 | Building samples=16, no denoiser | 🔴 | ✅ | v11.0.1 |
| 7 | IFC spatial + property sets | 🟡 | ✅ | v11.0.1 |
| 8 | ifcopenshell в requirements | 🟡 | ✅ | v11.0.1 |
| 9 | Мебель из кубов | 🟡 | ❌ | v11.1.0 |
| 10 | Нет boolean для окон | 🟡 | ❌ | v11.1.0 |
| 11 | Нет UV mapping | 🟡 | ❌ | v11.1.0 |
| 12 | StructuralAgent без FEM | 🟡 | ❌ | v12.0 |
| 13 | ComplianceAgent — чек-лист | 🟡 | ❌ | v12.0 |
| 14 | OpenRouter 402 | 🟡 | ❌ | — |
| 15 | Regex fallback низкое качество | 🟡 | ❌ | — |

### 11.6 Рекомендации

1. **Deploy GitHub Pages** — чтобы E2E тесты работали через публичный URL
2. **Demo API endpoint** — `/api/v1/demo` без авторизации с rate limit для тестирования
3. **Fix frontend input events** — использовать `nativeInputValueSetter` для программного ввода
4. **Asset library** — загрузить GLB-модели мебели (100+ типов) для реалистичных интерьеров
5. **Boolean operations** — вырезать оконные/дверные проёмы в стенах
6. **UV unwrap** — автоматическая развёртка перед текстурированием
7. **Visual regression testing** — скриншоты после каждого коммита для отслеживания регрессий

---

*Документация обновлена для версии v11.0.0 (2026-08-09)*
