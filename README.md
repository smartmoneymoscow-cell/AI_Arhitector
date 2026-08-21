# Architect v13.1.0 — AI Architecture Generator

Генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

**Blender рендеринг через Kaggle GPU (T4/P100) + Render fallback.**

**LLM каскад: Groq → Gemini → DeepSeek → OpenRouter (Groq первый для скорости).**

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone https://github.com/smartmoneymoscow-cell/AI_Arhitector.git
cd AI_Arhitector

# 2. Создать .env из примера
cp .env.example .env

# 3. Заполнить ключи в .env (минимум один):
#    GOOGLE_API_KEY=AIzaSy-key1        ← бесплатно, https://aistudio.google.com/apikey
#    GOOGLE_FALLBACK_KEYS=AIzaSy-key2,AIzaSy-key3  ← ротация
#    OPENROUTER_API_KEY=sk-or-v1-aaaa   ← бесплатные модели, https://openrouter.ai
#    OPENROUTER_FALLBACK_KEYS=sk-or-v1-bbbb,sk-or-v1-cccc  ← ротация

# 4. Запуск
docker-compose up -d
```

## Архитектура

```
Пользователь → Nginx → Gateway → LLM Service → Kaggle GPU (Blender)
                  │         │          │              │
                  │         │    Google Gemini    bpy-скрипты
                  │         │    OpenRouter       T4/P100 GPU
                  │         │    DeepSeek/Groq    ngrok/polling
                  │         │
                  │    Orchestrator
                  │    (20+ AI-агентов)
                  │
              Frontend
              (Three.js 3D)
```

### 🔑 Ключи LLM — живая конфигурация

**Живой LLM Service:** `https://architect-llm-1s1j.onrender.com`

| # | Провайдер | Переменная | Кол-во | Статус |
|---|-----------|-----------|--------|--------|
| 1 | OpenRouter | `OPENROUTER_API_KEY` | 1 | ✅ alive |
| 2 | OpenRouter | `OPENROUTER_FALLBACK_KEYS` | 2 | ✅ alive |
| 3 | Gemini | `GOOGLE_API_KEY` | 1 | ✅ alive |
| 4 | Gemini | `GOOGLE_FALLBACK_KEYS` | 7 | ✅ alive |
| | | **Итого** | **11** | **все alive** |

**НЕ живой** (старый деплой, не трогать): `ai-arch-llmproxy.onrender.com` — 1 OR ключ, 0 Gemini

### LLM-цепочка (бесплатно)

```
1. Groq (free tier, быстрый inference, qwen3.6-27b)
   ↓ если все ключи исчерпаны
2. Google Gemini API (8 ключей, round-robin)
   ↓ если все 8 исчерпаны
3. DeepSeek (прямой API)
   ↓ если все ключи исчерпаны
4. OpenRouter Free Models (auto-discovery, 15+ моделей)
   ↓ если все модели/ключи недоступны
5. Ollama (локальный, если настроен)
   ↓ если не настроен
6. Last resort: retry Groq + Gemini
```

### Key Rotation

- Все ключи Groq, Gemini, DeepSeek и OpenRouter равноправны
- При 429 (RPM) → ключ помечается на 60 сек, переход к следующему
- При 402/quota → ключ помечается на 24 часа
- Cooldown дублируется в Redis — переживает рестарт контейнера
- `GET /api/v1/keys/status` — мониторинг: сколько ключей настроено / живых

### Render Accounts (v12.0)

| # | Аккаунт | URL | Что работает | LLM-ключей |
|---|---------|-----|-------------|------------|
| 4 | Render #4 | `architect-gateway.onrender.com` | Gateway + Redis | — |
| 1 | Render #1 | `architect-llm-s5q7.onrender.com` | LLM #1 | 16 |
| 2 | Render #2 | `ai-arch-llmproxy.onrender.com` | Agent Pool + microservices | — |
| 3 | Render #3 | `architect-llm-zczl.onrender.com` | LLM #3 | 16 |
| 4 | Render #4 | `architect-llm-1s1j.onrender.com` | LLM #4 | 16 |
| 5 | Render #5 | `architect-llm-2pmo.onrender.com` | LLM #5 | 16 |
| 6 | Render #6 | `architect-llm-5mdk.onrender.com` | LLM #6 | 16 |
| 7 | Render #7 | `architect-llm-sdrh.onrender.com` | LLM #7 | 16 |
| 8 | Render #8 | `architect-llm-qarj.onrender.com` | LLM #8 | 16 |
| — | Kaggle | GPU T4/P100 | **Blender (GPU рендер)** | — |

### Pipeline агентов

```
Промт → Parser → Clarification → Style → Geometry → Texture
     → Lighting → Structural → Compliance → Render → Quality → Export
```

20+ специализированных агентов: парсер, геометрия, текстуры, свет,
конструктив, нормативы, рендер, качество, экспорт.

## Что нового в v11.5.0

- **Agent Pool микросервис** — 30 агентов выполняются в отдельном сервисе через HTTP (не in-process)
  - `AGENT_POOL_URL` env var → gateway вызывает agent-pool вместо importlib
  - 3-tier fallback: agent-pool HTTP → subprocess → in-process
- **Quality agent** — все 5 уровней работают (было 2/5): mimo-omni заменён на Gemini Vision
  - Levels 3-5 (visual bugs, prompt match, geometry sanity) fail-safe при недоступности vision
- **Threading timeout** — зависший агент не блокирует gateway
- **CORS fix** — wildcard `*` удалён из LLM и Blender сервисов
- **30+ bare `except:`** заменены на конкретные типы (KeyError, AttributeError, Exception)
- **Post-pipeline agents** (compliance, financial, presentation) работают параллельно
- **sys.path.insert** удалён из сервисов, PYTHONPATH в Dockerfiles
- **Structured logging** — print() → logger в production коде
- **Зависимости обновлены** — Python 3.13, fastapi 0.141, httpx 0.28, pydantic 2.13, redis 8.1
- **Aedifex** — IFC/CAD routes, auth anonymous access, nginx bridge fix

## Что нового в v11.2.0

- **Frontend/Backend stitching** — исправлены все критические баги сшивки: 3D-модель теперь загружается в viewer, clarification flow работает корректно
- **Единый source HTML** — 3 копии index.html → 1 (`frontend/index.html`), gateway и GitHub Pages используют единый файл
- **File proxy** — `GET /api/v1/files/{path}` в gateway для отдачи GLB/PNG с blender-service
- **Публичные эндпоинты** — chat-эндпоинты больше не требуют `ARCH_API_KEYS`
- **ifc-service + cad-service** — добавлены в docker-compose, hostnames теперь резолвятся
- **Nginx** — отдельные location-блоки для `/api/v1/files/` и `/api/v1/analyze/`

## Что нового в v11.1.0

- **Key Health Tracker** — единая система cooldown для Gemini и OpenRouter, дублирование в Redis
- **Все ключи равноправны** — round-robin вместо "основной + фолбэк"
- **Background discovery** — список бесплатных моделей OpenRouter обновляется каждый час
- **Eager discovery** — обновление при старте сервиса, не при первом запросе
- **Discovery → Redis** — список моделей共享 между воркерами и переживает рестарт
- **chat_completions перебор** — все ключи пробуются автоматически при 429/402
- **404 handling** — если модель удалена из OpenRouter → invalidate discovery + следующая модель
- **GET /api/v1/keys/status** — endpoint мониторинга ключей
- **KEY_COOLDOWN_RATE_LIMIT_SEC / KEY_COOLDOWN_QUOTA_SEC** — настраиваемые cooldown

## Что нового в v11.0.0

- **PDF/DWG анализ** — загрузка архитектурных чертежей, автоматическое извлечение помещений, размеров, MEP-систем
- **Kaggle GPU Auto-Submit** — автоматическая отправка рендер-задач на бесплатный T4 GPU
- **HDRI освещение** — процедурный небесный купол для реалистичного света
- **Улучшенный интерьер** — дверь с коробкой, встроенные потолочные светильники, стиль-зависимые материалы пола
- **LLM-уточнения** — генерация контекстных вопросов через LLM вместо хардкода
- **Pipeline profile от LLM** — парсер сам определяет профиль (interior/landscape/standard)
- **16K retry** — при неудаче рендера 16K: 4096 samples + tiled render
- **25+ AI-агентов** — парсер, геометрия, текстуры, свет, конструктив, нормативы, рендер, качество, экспорт, анализ PDF/DWG

## Что нового в v10.6.0

- **Google Gemini прямой API** — бесплатный LLM без зависимости от OpenRouter
- **4 ключа Gemini с ротацией** — обход rate limit (15 RPM/ключ)
- **Docker: проброс GOOGLE_API_KEY** — ключи теперь доходят до LLM-сервиса
- **Kaggle GPU Renderer** — polling-режим для бесплатного T4 GPU рендеринга

## Что нового в v10.5.0

- **Render pipeline fix** — исправлен критический баг: render_agent получал неправильные параметры
- **Denoising fix** — отключён OpenImageDenoiser (недоступен на Render free tier)
- **Bathroom furniture** — добавлены: jacuzzi, shower, shower_cabin, toilet и др.
- **Russian→English mapping** — автоматическая конвертация русских названий мебели
- **File download endpoint** — `/api/v1/files/{path}` для скачивания рендеров
- **Kaggle GPU Renderer** — документация по настройке Kaggle T4 GPU

## CV-тест результаты

| Проверка | Статус |
|----------|--------|
| LLM парсит промты | ✅ Все 6 промтов корректно |
| Reasoning в чате | ✅ Пошаговый процесс |
| Декомпозиция задач | ✅ 5 этапов |
| Уточняющие вопросы | ✅ Качество (Премиум/Стандарт/Быстрый) |
| Чипсины подсказки | ✅ Дом, Офис, Коттедж |
| Адаптивность | ✅ Поле ввода не обрезается |
| 3D модель генерируется | ✅ Через Three.js + Blender pipeline |
| Текстуры | ⚠️ Базовые, нужен Kaggle GPU |
| Качество рендера | ⚠️ 4/10 (CPU), улучшится с Kaggle T4 GPU |

## Документация

| Документ | Описание |
|----------|----------|
| [CHANGELOG.md](CHANGELOG.md) | Журнал изменений и планы доработок |
| [PLAN.md](PLAN.md) | Комплексный план исправлений |
| [ROADMAP.md](ROADMAP.md) | Дорожная карта на будущее |
| [AUDIT.md](AUDIT.md) | Аудит безопасности |
| [docs/KAGGLE_SETUP.md](docs/KAGGLE_SETUP.md) | Настройка Kaggle GPU рендера |
# Deploy trigger Tue Aug 11 09:35:50 CST 2026
