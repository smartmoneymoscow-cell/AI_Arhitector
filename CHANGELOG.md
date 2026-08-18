# CHANGELOG — AI_Arhitector

## v12.0.0 — Blender via Kaggle GPU Only (2026-08-18)

### КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ
- **Blender рендеринг теперь работает ТОЛЬКО через Kaggle GPU (T4/P100).**
- Render blender-service оставлен как emergency fallback, но не используется по умолчанию.
- Все запросы на рендер направляются сначала на Kaggle, затем на Render.

### Что изменено
| # | Файл | Что | Исправление |
|---|------|-----|-------------|
| 1 | `gateway/app.py` | `_get_blender_urls()` — Kaggle был последним | Kaggle теперь **PRIMARY** (первый в списке) |
| 2 | `gateway/app.py` | `blender_request_with_fallback()` — только HTTP | Добавлен fallback на Kaggle polling queue |
| 3 | `gateway/app.py` | `_kaggle_polling_render()` — не существовала | Новая функция: enqueue + wait for result |
| 4 | `gateway/app.py` | Версия gateway | 8.2.0 → **9.0.0** |
| 5 | `.env.example` | KAGGLE_RENDERER_URL не было | Добавлен как обязательная переменная |
| 6 | `.env.example` | KAGGLE_POLLING_ENABLED не было | Добавлен (true по умолчанию) |
| 7 | `README.md` | Архитектура не показывала Kaggle | Обновлена диаграмма: Kaggle = primary renderer |

### Архитектура (новая)
```
Пользователь → Nginx → Gateway → LLM Service → Kaggle GPU (Blender)
                  │         │          │              │
                  │         │    Google Gemini    bpy-скрипты
                  │         │    OpenRouter       T4/P100 GPU
                  │         │    DeepSeek/Groq    ngrok/polling
                  │         │
                  │    Orchestrator (v9.0)
                  │    Kaggle = PRIMARY renderer
                  │
              Frontend
              (Three.js 3D)
```

### Как запустить Kaggle
1. Открыть `kaggle/blender_gpu_renderer.ipynb` на kaggle.com
2. Включить GPU: Settings → Accelerator → GPU T4
3. Запустить все ячейки
4. Режим ngrok: вставить токен → получить URL → прописать `KAGGLE_RENDERER_URL`
5. Режим polling: ноутбук опрашивает Gateway автоматически

---

## v11.6.0 — Dynamic LLM Cascade (2026-08-16)

### Исправлено
- **Динамический каскад моделей** — `get_active_cascade()` теперь возвращает ОБНАРУЖЕННЫЕ бесплатные модели вместо захардкоженного списка. Fallback на хардкод только если discovery не сработал.
- **Сортировка по мощности** — `_estimate_power()` оценивает размер модели по ID (параметры, MoE activated params, семейство). Самые мощные модели первыми в каскаде.
- **Актуальный список _PREFERRED** — обновлён текущими рабочими бесплатными моделями OpenRouter: gemma-4-26b, gemma-4-31b, nemotron-3-ultra-550b, nemotron-3-super-120b, north-mini-code, nemotron-3-nano-30b, laguna-s, gpt-oss-20b.
- **Blocklist обновлён** — добавлен dots-studio/dots-3-note-preview:free (неконсистентный JSON).
- **Кеш инвалидирован** — SYSTEM_PROMPT_VERSION bumped to v10.0.

### Архитектурные изменения
- Discovery (`discover_free_models()`) теперь вызывается при старте + каждые 3600с в фоне
- Результат discovery автоматически используется через `get_active_cascade()`
- Каскад строится динамически: 10+ бесплатных моделей OpenRouter × 8 аккаунтов = 80+ комбинаций
- При 404 от модели → `invalidate_discovery()` + следующая модель
- При 429/402 от ключа → cooldown + следующий аккаунт

### Тестирование
- ✅ Groq (llama-3.3-70b-versatile): работает, 0.2s
- ✅ Cohere (command-r-08-2024): работает, 26s
- ✅ Gemini Key #1 (gemini-flash-lite-latest): работает
- ✅ OpenRouter: 16 бесплатных моделей обнаружено
- ❌ DeepSeek: все 8 ключей — 402 Insufficient Balance (нет бесплатного тира)
- ❌ Cerebras: 402 Payment required
- ❌ SambaNova: 402 balance_units=0
- ⚠️ OpenRouter: все 8 ключей исчерпали дневной лимит (50 req/сутки), reset 2026-08-17 08:00 UTC

---

## v11.5.0 — Pipeline Timeouts Fix + GLB URL + Deploy Fix

### Дата: 2026-08-14

### Что исправлено

| # | Файл | Что | Исправление |
|---|------|-----|-------------|
| 1 | `shared/parser.py` | OpenRouter discovery зависает на Render | `httpx.get()` → `httpx.stream()` с 2MB body limit |
| 2 | `shared/parser.py` | Cascade timeout 30s на модель | 30s → **3s** |
| 3 | `shared/parser.py` | GEMINI_MODEL default неверный | `gemini-3.1-flash-lite` → `gemini-2.0-flash-lite-001` |
| 4 | `shared/parser.py` | Gemini/Ollama timeout 60s | → **3s** |
| 5 | `gateway/app.py` | Parse proxy timeout 120s | → **15s** |
| 6 | `llm-service/app.py` | Chat completions timeout 60s | → **10s** |
| 7 | `blender-service/app.py` | LLM parse timeout 60s | → **15s** |
| 8 | `frontend/index.html` | GLB URL с двойным слешем | `cleanPath = glbPath.replace(/^\/+/, '')` |
| 9 | `gateway/app.py` | Auth middleware блокирует запросы | Исправлена проверка |
| 10 | `shared/agents/orchestrator.py` | Blender fallback не работает | Добавлена fallback логика |
| 11 | `shared/auth.py` | Auth пропускает/блокирует неверно | Исправлены условия |
| 12 | `.github/workflows/deploy.yml` | Exit code 127 | Добавлен `shell: bash`, переименован `PATH` → `HEALTH_PATH` |

### Коммиты

- `e3801af` — fix: streaming discovery for OpenRouter /models
- `b61503d` — fix: 3s cascade timeouts, correct GEMINI_MODEL default
- `41b53bd` — fix: pipeline timeouts + auth + GLB URL + blender fallback

---

## v11.4.0 — 8-Account OpenRouter Cascade + Full Infrastructure Update

### Дата: 2026-08-12

### Что сделано

| # | Задача | Детали |
|---|--------|--------|
| 1 | OpenRouter: 5 → 8 ключей | Добавлены 3 новых ключа (…4437, …00ab, …43a9) во все 8 LLM-сервисов |
| 2 | Каскад между аккаунтами | Каждый сервис: 1 unique primary + 7 fallback = все 8 ключей |
| 3 | Деплой всех сервисов | 8/8 LLM-сервисов задеплоены и healthy |
| 4 | RENDER_ACCOUNTS.md | Полностью переписан: 8 аккаунтов, все URL, все ключи |
| 5 | INFRASTRUCTURE_REPORT.md | Обновлён: 18 живых сервисов на 8 аккаунтах |
| 6 | .env.example | Обновлён: примеры 8 OpenRouter + 8 Google ключей |

### Архитектура ключей

```
Каждый LLM-сервис (8 штук):
  OPENROUTER_API_KEY        = уникальный primary (Acc1→…88f4, Acc2→…09d3, ...)
  OPENROUTER_FALLBACK_KEYS  = 7 остальных ключей через запятую

Каскад при исчерпании:
  429 (rate limit) → cooldown 60с → следующий ключ
  402 (quota)      → cooldown 24ч → следующий ключ
  Redis-дублирование → переживает рестарт контейнера
```

### Статус инфраструктуры

| Провайдер | Ключей | Статус |
|-----------|:------:|:------:|
| OpenRouter | 8/8 | ✅ все alive |
| Google Gemini | 8/8 | ✅ все настроены |
| Render | 8/8 | ✅ все сервисы live |

**Итого: 8 × 50 = 400 запросов/сутки через OpenRouter**

### Сервисы по аккаунтам

| # | Сервисы | URL LLM |
|---|---------|---------|
| 1 | llm | architect-llm-s5q7.onrender.com |
| 2 | llmproxy + blender + 6 data/DB + 3 legacy | ai-arch-llmproxy.onrender.com |
| 3 | llm | architect-llm-zczl.onrender.com |
| 4 | gateway + llm + blender | architect-llm-1s1j.onrender.com |
| 5 | llm | architect-llm-2pmo.onrender.com |
| 6 | llm | architect-llm-5mdk.onrender.com |
| 7 | llm + chat-monitor-bot | architect-llm-sdrh.onrender.com |
| 8 | llm | architect-llm-qarj.onrender.com |

---

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
