# CHANGELOG — AI_Arhitector

## v11.3.2 — Gemini Direct Integration + Proactive Health Check

### Дата: 2026-08-12

### Проблема

- Модель `gemini-2.0-flash-lite-001` удалена из Google API (404)
- 7 из 8 Gemini ключей (`AQ.Ab8...`) нерабочие из-за известного бага Google ([ACCESS_TOKEN_TYPE_UNSUPPORTED](https://discuss.ai.google.dev/t/account-restricted-to-aq-keys-all-return-401-access-token-type-unsupported-on-generativelanguage-googleapis-com-requesting-fix-aiza-restoration/175424))
- Не было проактивной проверки ключей — мёртвый ключ обнаруживался только при реальном запросе

### Что исправлено

| # | Файл | Что | Исправление |
|---|------|-----|-------------|
| 1 | `shared/parser.py` | Модель Gemini удалена из API | `gemini-2.0-flash-lite-001` → `gemini-3.1-flash-lite` |
| 2 | `shared/parser.py` | Нет проактивной проверки ключей | Добавлен `proactive_health_loop()` — каждые 30 мин проверяет все ключи |
| 3 | `llm-service/app.py` | Health check не запускался | Добавлен `proactive_health_loop()` в startup/shutdown |
| 4 | `.env.example` | Устаревшие имена моделей | Обновлены на `gemini-3.1-flash-lite` и `gemini-2.5-flash` |
| 5 | Render env vars | `GOOGLE_API_KEY` = мёртвый key 1 | Заменён на key 8 (рабочий) |

### Статус ключей

| Провайдер | Рабочие | Итого | Примечание |
|-----------|---------|-------|------------|
| OpenRouter | ✅ 5/5 | 5 | Все free tier |
| Gemini | ✅ 1/8 | 8 | Key 8 работает, 1-7 — Google AQ bug |
| Render | ✅ 8/8 | 8 | |

### Known Issues

- Ключи Gemini 1-7 нерабочие (Google AQ bug). Обход: OpenRouter для Gemini моделей
- Redis не настроен в Gateway (`redis: not_configured`)

## v11.3.1 — Gateway Fix: GEOS libs + Frontend Cleanup

### Дата: 2026-08-11

### Проблема
Gateway не деплоился на Render (update_failed) из-за отсутствия GEOS C-библиотек, необходимых для `shapely`. Frontend содержал кнопки быстрого старта, которые были удалены ранее.

### Что исправлено

| # | Файл | Что | Исправление |
|---|------|-----|-------------|
| 1 | `gateway.Dockerfile` | `shashely` не мог импортироваться — нет `libgeos` | Добавлен `libgeos-dev` (builder) и `libgeos3 libgeos-c1v5` (runtime) |
| 2 | `index.html` | Кнопки быстрого старта (Дом, Офис, Коттедж, Интерьер) | Удалены из welcome screen и empty state |
| 3 | `index.html` | CSS `.quick-actions`, `.qa-btn`, `.qa-icon` | Удалены |
| 4 | `index.html` | i18n ключи `qaHouse`, `qaOffice`, `qaCottage`, `qaInterior` | Удалены из RU и EN |

### Визуальное тестирование (LIVE скриншоты)

| Скриншот | Результат |
|----------|-----------|
| fresh_01_main.png | ✅ Интерфейс рабочий, чистый |
| fresh_02_input.png | ✅ Ввод текста работает |
| fresh_03_sending.png | ⚠️ HTTP 401 — Gateway старый код требует API key |
| fresh_04_response.png | ⚠️ 3D не сгенерировался (та же причина) |

### Анализ PDF воздуховодов

DuctAnalysisAgent успешно проанализировал чертёж МРЭ-РД-ОВ4 (18MB, 56 листов):
- Извлечено 9 систем вентиляции
- 20+ типов воздуховодов (круглые Ø100-630, прямоугольные 100×200 — 800×500)
- 11 противодымных систем (ПД1-ПД10)
- 12 типов клапанов (OKL-2-90, ПРОК, KPU-1N и др.)
- Полная спецификация по ГОСТ 21.1101
- Нормативная база: СП 60.13330, СП 7.13130, СП 253.1325800

---

## v11.3.0 — Duct Analysis Agent + 8-Account Architecture

### Дата: 2026-08-11

### Новые возможности
- DuctAnalysisAgent (800+ строк) — анализ чертежей воздуховодов
- 31 агент в реестре (было 30)
- Pipeline profiles: `duct_analysis`, `document_analysis`
- Репозиторий публичный (Render auto-deploy)
- Python 3.12 Dockerfiles

### Инфраструктура
- Account #2: 8 сервисов LIVE
- Account #4: 3 сервиса (Gateway, LLM, Blender)
- LLM обновлён до нового кода
- Kaggle T4 GPU для рендера

### Известные проблемы
- Gateway update_failed → исправлено в v11.3.1 (GEOS libs)
- Blender build_failed → не нужен, Kaggle T4 отрабатывает
