# Architect v11.0.0 — AI Architecture Generator

Генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone https://github.com/smartmoneymoscow-cell/AI_Arhitector.git
cd AI_Arhitector

# 2. Создать .env из примера
cp .env.example .env

# 3. Заполнить ключи в .env (минимум один):
#    GOOGLE_API_KEY=AIzaSy-xxxx        ← бесплатно, https://aistudio.google.com/apikey
#    OPENROUTER_API_KEY=sk-or-xxxx     ← бесплатные модели, https://openrouter.ai

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

### LLM-цепочка (бесплатно)

```
1. Google Gemini API  ← основной, 4 ключа с ротацией
2. OpenRouter :free   ← фолбэк, 8 моделей
3. Ollama (local)     ← опционально
4. Regex fallback     ← крайний случай
```

### Pipeline агентов

```
Промт → Parser → Clarification → Style → Geometry → Texture
     → Lighting → Structural → Compliance → Render → Quality → Export
```

20+ специализированных агентов: парсер, геометрия, текстуры, свет,
конструктив, нормативы, рендер, качество, экспорт.

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
