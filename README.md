# Architect v11.1.0 — AI Architecture Generator

Генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

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
Пользователь → Nginx → Gateway → LLM Service → Blender Service
                  │         │          │              │
                  │         │    Google Gemini    Blender CLI
                  │         │    OpenRouter       (bpy-скрипты)
                  │         │    Ollama (local)
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
1. Google Gemini API (8 ключей, round-robin)
   ↓ если все 8 исчерпаны
2. OpenRouter Free Models (3 ключа, round-robin)
   ├── auto-discovery каждый час
   ├── 8+ бесплатных моделей в каскаде
   └── при 404 → invalidate discovery + следующая модель
   ↓ если все модели/ключи недоступны
3. Ollama (локальный, если настроен)
   ↓ если не настроен
4. Regex fallback (крайний случай)
```

### Key Rotation

- Все ключи Gemini и OpenRouter равноправны (нет "основных" и "фолбэков")
- При 429 (RPM) → ключ помечается на 60 сек, переход к следующему
- При 402/quota → ключ помечается на 24 часа
- Cooldown дублируется в Redis — переживает рестарт контейнера
- `GET /api/v1/keys/status` — мониторинг: сколько ключей настроено / живых

### Render Accounts

| # | Аккаунт | URL | Что работает | LLM-ключей |
|---|---------|-----|-------------|------------|
| 1 | Render #1 | `ai-arch-blender3d.onrender.com` | Blender | — |
| 4 | Render #4 | `architect-gateway.onrender.com` | Gateway | — |
| 4 | Render #4 | `architect-llm-1s1j.onrender.com` | LLM Service | 11 |

### Pipeline агентов

```
Промт → Parser → Clarification → Style → Geometry → Texture
     → Lighting → Structural → Compliance → Render → Quality → Export
```

20+ специализированных агентов: парсер, геометрия, текстуры, свет,
конструктив, нормативы, рендер, качество, экспорт.

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
