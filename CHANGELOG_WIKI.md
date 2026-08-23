# CHANGELOG WIKI — AI_Arhitector

> Полный журнал изменений проекта AI_Arhitector — генератор 3D-моделей зданий и интерьеров по текстовому описанию.

---

## Версия 13.5.0 — Orchestrator Fix + Auto-Discovery
**Дата:** 2026-08-23

### Добавлено
1. LLM auto-discovery — Gateway автоматически пробует 7 LLM-сервисов на Render и кеширует первый рабочий
2. Blender auto-discovery — Gateway автоматически находит `ai-arch-blender3d.onrender.com`
3. Wiki-документация проекта (`docs/WIKI_v13.5.0.md`, `docs/WIKI_CHANGELOG_v13.5.0.md`)

### Исправлено
4. Orchestrator fix — оркестратор теперь использует discovered URLs вместо `settings.LLM_SERVICE_URL` (который был `localhost:8081`)
5. Оркестратор теперь корректно работает на Render (LLM_SERVICE_URL был指向 localhost)

### Изменено
6. `gateway/app.py` — добавлены `_discover_llm_url()`, `_get_blender_urls()` auto-discovery

### Тестирование (2026-08-23)
- ✅ Groq LLM — обработка и уточнение промтов (5/5 промтов пройдены)
- ✅ Оркестратор — декомпозиция промтов (5 pipeline-профилей: quick, standard, interior, landscape, full)
- ✅ Агенты → Blender (генерация, текстуры, рендер, экспорт GLB)
- ✅ Blender на Kaggle (T4/P100 GPU, polling queue)
- ✅ Модуль оценки качества (4K/16K, quality gate с retry)
- ✅ Интерфейс — Projects Panel исправлен (закрыт по умолчанию)
- ⚠️ Компьютерное зрение — ограничено (Chromium lacks execute permissions)

---

## Версия 13.4.0 — Frontend Resilience + Fast GLB Generation
**Дата:** 2026-08-23

### Добавлено
1. Frontend multi-backend fallback — `checkBackend()` пробует несколько backend URL автоматически
2. Backend URL configuration — пользователь может указать свой backend URL в настройках аккаунта
3. Backend status indicator — зелёный/красный индикатор в top bar рядом с логотипом
4. Fast GLB endpoint — `POST /api/v1/generate/fast` — быстрая генерация через trimesh (без Blender)
5. Orchestrator trimesh fallback — когда Blender недоступен, оркестратор генерирует GLB через trimesh
6. Frontend fast fallback — при ошибке 502/503 оркестратора фронтенд пробует `/api/v1/generate/fast`
7. Auto-detect backend — `simple.html` определяет backend URL автоматически
8. Gateway fast endpoint — проксирует `/api/v1/generate/fast` в blender-service

### Изменено
9. `frontend/index.html` — multi-backend fallback, backend URL config, status indicator, fast fallback
10. `simple.html` — auto-detect backend URL
11. `gateway/app.py` — `/api/v1/generate/fast` proxy
12. `blender-service/app.py` — `/api/v1/generate/fast` endpoint
13. `shared/agents/orchestrator.py` — trimesh fallback when Blender unavailable

---

## Версия 13.3.0 — Version Sync + Trimesh Fallback Consolidation
**Дата:** 2026-08-23

### Изменено
1. Gateway version sync — обновлён с v13.1.0 до v13.3.0
2. Blender Service version sync — обновлён до v13.3.0
3. Trimesh GLB fallback — консолидирован в релизе
4. scipy dependency — добавлен для trimesh GLB export
5. Kaggle notebook URL fix — обновлён Gateway URL

### Документация
6. Финальный отчёт тестирования v13.2.0

---

## Версия 13.2.0 — Full LLM Cascade for All Endpoints
**Дата:** 2026-08-21

### Добавлено
1. Chat endpoint полный каскад — `/api/v1/chat/completions` теперь использует Groq → Gemini → DeepSeek → OpenRouter → Ollama (раньше только OpenRouter)
2. Health endpoint показывает статус всех 4 провайдеров
3. Keys/status endpoint показывает Groq и DeepSeek ключи
4. docker-compose: добавлены `GROQ_API_KEY`, `GROQ_FALLBACK_KEYS`
5. `.env.example`: добавлены секции Groq и DeepSeek

### Исправлено
6. Chat endpoint при rate limit OpenRouter больше не падает с 429 — теперь используется полный cascade

### Каскад (приоритет)
1. Groq (free tier, qwen3.6-27b, ~300 tok/s) — ПЕРВЫЙ
2. Google Gemini (8 ключей, round-robin)
3. DeepSeek (прямой API)
4. OpenRouter (8 ключей, auto-discovery бесплатных моделей)
5. Ollama (локальный)

### Тестирование (2026-08-21)
- ✅ Gateway alive (200)
- ✅ LLM #1, #2, #4 alive (200)
- ⚠️ LLM #3 slow
- ✅ Blender alive (200)
- ✅ LLM Parse — корректный JSON с параметрами
- ✅ Blender Generate — GLB файл (28KB)
- ✅ Orchestrator Execute — status=done
- ❌ Orchestrator exports={} (пусто) — выявлена проблема
- ❌ Generate endpoint требует API key — выявлена проблема
- ⚠️ CORS блокирует прямые вызовы с localhost

---

## Версия 12.1.0 — Infrastructure Recovery + URL Migration
**Дата:** 2026-08-19

### Изменено
1. Все URL обновлены: `architect-gateway.onrender.com` → `architect-gateway-3guo.onrender.com`
2. Все сервисы перездеплоены через Render API с полными LLM ключами
3. LLM cascade: Groq → DeepSeek → Gemini → OpenRouter → Cohere → Cerebras → SambaNova

### Исправлено
4. Frontend → Gateway → LLM → Orchestrator → Blender pipeline работает end-to-end

### Тестирование
- ✅ LLM parse (интерьер) — object_type=interior, room_type=living_room, style=loft (~15s)
- ✅ LLM parse (здание) — object_type=building, building_type=cottage, floors=2 (~20s)
- ✅ Orchestrator (полный) — 7 шагов: parse→route→geometry→texture→render→quality→export (53s)
- ✅ GLB экспорт — 207KB файл доступен через /api/v1/files/
- ✅ Groq API — qwen/qwen3.6-27b отвечает (~2s)
- ✅ Frontend UI — Chat + 3D viewer + AI thinking display

### Инфраструктура
| Сервис | URL | Статус |
|--------|-----|--------|
| Gateway | architect-gateway-3guo.onrender.com | ✅ v9.0.0 |
| LLM | architect-llm-s5q7.onrender.com | ✅ v8.0.0 |
| Blender | ai-arch-blender3d.onrender.com | ✅ v6.0.0 |
| GitHub Pages | smartmoneymoscow-cell.github.io/AI_Arhitector | ✅ |

---

## Версия 12.0.0 — LLM Cascade Fix + Infrastructure Recovery
**Дата:** 2026-08-18

### Критические изменения
1. **Blender рендеринг теперь работает ТОЛЬКО через Kaggle GPU (T4/P100).** Render blender-service — emergency fallback.

### Исправлено
2. Groq модель `llama-3.3-70b-versatile` удалена из API → заменена на `openai/gpt-oss-20b`
3. Gemini fallback модели не существовали (`gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.1-flash-lite`) → заменены на рабочие: `gemini-flash-latest`, `gemini-2.5-flash-preview-05-20`, `gemini-2.0-flash`
4. Frontend Gateway URL указывал на Acc4 (suspended) → обновлён на Acc1

### Инфраструктурные исправления
5. Acc4 (Gateway) — suspended for billing → Gateway перенесён на Acc1
6. Acc1 LLM + Gateway — задеплоены с полными env vars (8 OpenRouter + Gemini + Groq ключи)
7. Acc3,5,6,7,8 LLM — задеплоены с обновлёнными env vars
8. Groq API ключ — добавлен в LLM cascade как прямой провайдер

### Статус провайдеров
| Провайдер | Ключей | Статус | Примечание |
|-----------|:------:|:------:|------------|
| OpenRouter | 8/8 | ✅ alive | Free модели: 429 daily limit |
| Gemini | 1/8 | ⚠️ degraded | Key#1 работает, но 503 under load |
| Groq | 1/1 | ✅ alive | gpt-oss-20b, fast inference |
| Cohere | 1/1 | ✅ alive | command-r-08-2024 |
| DeepSeek | 0/8 | ❌ | 402 Insufficient Balance |
| SambaNova | 0/1 | ❌ | 402 no balance |
| Cerebras | 0/1 | ❌ | Model not found |

---

## Версия 11.6.0 — Dynamic LLM Cascade
**Дата:** 2026-08-16

### Добавлено
1. Динамический каскад моделей — `get_active_cascade()` возвращает обнаруженные бесплатные модели вместо захардкоженного списка
2. Сортировка по мощности — `_estimate_power()` оценивает размер модели по ID
3. Актуальный список `_PREFERRED` — обновлён рабочими бесплатными моделями OpenRouter
4. Blocklist обновлён — добавлен `dots-studio/dots-3-note-preview:free` (неконсистентный JSON)
5. Кеш инвалидирован — `SYSTEM_PROMPT_VERSION` bumped to v10.0

### Архитектурные изменения
6. Discovery (`discover_free_models()`) вызывается при старте + каждые 3600с в фоне
7. Результат discovery автоматически используется через `get_active_cascade()`
8. Каскад строится динамически: 10+ бесплатных моделей OpenRouter × 8 аккаунтов = 80+ комбинаций
9. При 404 от модели → `invalidate_discovery()` + следующая модель
10. При 429/402 от ключа → cooldown + следующий аккаунт

### Тестирование
- ✅ Groq (llama-3.3-70b-versatile): работает, 0.2s
- ✅ Cohere (command-r-08-2024): работает, 26s
- ✅ Gemini Key #1 (gemini-flash-lite-latest): работает
- ✅ OpenRouter: 16 бесплатных моделей обнаружено
- ❌ DeepSeek: все 8 ключей — 402 Insufficient Balance
- ❌ Cerebras: 402 Payment required
- ❌ SambaNova: 402 balance_units=0
- ⚠️ OpenRouter: все 8 ключей исчерпали дневной лимит (50 req/сутки)

---

## Версия 11.5.0 — Pipeline Timeouts Fix + GLB URL + Deploy Fix
**Дата:** 2026-08-14

### Исправлено
1. OpenRouter discovery зависает на Render — `httpx.get()` → `httpx.stream()` с 2MB body limit
2. Cascade timeout 30s на модель → **3s**
3. GEMINI_MODEL default неверный — `gemini-3.1-flash-lite` → `gemini-2.0-flash-lite-001`
4. Gemini/Ollama timeout 60s → **3s**
5. Gateway Parse proxy timeout 120s → **15s**
6. LLM Chat completions timeout 60s → **10s**
7. Blender LLM parse timeout 60s → **15s**
8. Frontend GLB URL с двойным слешем — `cleanPath = glbPath.replace(/^\/+/, '')`
9. Gateway Auth middleware блокирует запросы — исправлена проверка
10. Orchestrator Blender fallback не работает — добавлена fallback логика
11. Auth пропускает/блокирует неверно — исправлены условия
12. GitHub Actions deploy workflow exit code 127 — добавлен `shell: bash`, переименован `PATH` → `HEALTH_PATH`

---

## Версия 11.4.0 — 8-Account OpenRouter Cascade + Full Infrastructure Update
**Дата:** 2026-08-12

### Добавлено
1. OpenRouter: 5 → 8 ключей — добавлены 3 новых ключа во все 8 LLM-сервисов
2. Каскад между аккаунтами — каждый сервис: 1 unique primary + 7 fallback = все 8 ключей
3. Деплой всех сервисов — 8/8 LLM-сервисов задеплоены и healthy
4. RENDER_ACCOUNTS.md — полностью переписан: 8 аккаунтов, все URL, все ключи
5. INFRASTRUCTURE_REPORT.md — обновлён: 18 живых сервисов на 8 аккаунтах
6. `.env.example` — обновлён: примеры 8 OpenRouter + 8 Google ключей

### Архитектура ключей
- Каждый LLM-сервис (8 штук): уникальный primary + 7 fallback
- Каскад при исчерпании: 429 → cooldown 60с → следующий ключ; 402 → cooldown 24ч → следующий ключ
- Redis-дублирование → переживает рестарт контейнера
- **Итого: 8 × 50 = 400 запросов/сутки через OpenRouter**

---

## Версия 11.3.2 — Gemini Direct Integration + Proactive Health Check
**Дата:** 2026-08-12

### Исправлено
1. Модель `gemini-2.0-flash-lite-001` удалена из Google API (404) → заменена на `gemini-3.1-flash-lite`
2. 7 из 8 Gemini ключей нерабочие (Google AQ bug `ACCESS_TOKEN_TYPE_UNSUPPORTED`) — обход через OpenRouter
3. Добавлен `proactive_health_loop()` — каждые 30 мин проверяет все ключи
4. Health check не запускался в LLM-сервисе — добавлен в startup/shutdown
5. `.env.example` — обновлены имена моделей
6. Render env vars — `GOOGLE_API_KEY` заменён с мёртвого key 1 на рабочий key 8

### Статус ключей
| Провайдер | Рабочие | Итого | Примечание |
|-----------|---------|-------|------------|
| OpenRouter | ✅ 5/5 | 5 | Все free tier |
| Gemini | ✅ 1/8 | 8 | Key 8 работает, 1-7 — Google AQ bug |

---

## Версия 11.3.1 — Gateway Fix: GEOS libs + Frontend Cleanup
**Дата:** 2026-08-11

### Исправлено
1. Gateway не деплоился на Render (update_failed) — отсутствовали GEOS C-библиотеки для `shapely` → добавлены `libgeos-dev` (builder) и `libgeos3 libgeos-c1v5` (runtime)
2. Удалены кнопки быстрого старта (Дом, Офис, Коттедж, Интерьер) из welcome screen и empty state
3. Удалены CSS `.quick-actions`, `.qa-btn`, `.qa-icon`
4. Удалены i18n ключи `qaHouse`, `qaOffice`, `qaCottage`, `qaInterior` из RU и EN

### Тестирование (визуальное)
- ✅ Интерфейс рабочий, чистый
- ✅ Ввод текста работает
- ⚠️ HTTP 401 — Gateway старый код требует API key

### Анализ PDF воздуховодов
- DuctAnalysisAgent успешно проанализировал чертёж МРЭ-РД-ОВ4 (18MB, 56 листов)
- Извлечено 9 систем вентиляции, 20+ типов воздуховодов, 11 противодымных систем, 12 типов клапанов
- Полная спецификация по ГОСТ 21.1101

---

## Версия 11.3.0 — Duct Analysis Agent + 8-Account Architecture
**Дата:** 2026-08-11

### Добавлено
1. DuctAnalysisAgent (800+ строк) — анализ чертежей воздуховодов
2. 31 агент в реестре (было 30)
3. Pipeline profiles: `duct_analysis`, `document_analysis`
4. Репозиторий публичный (Render auto-deploy)
5. Python 3.12 Dockerfiles

### Инфраструктура
6. Account #2: 8 сервисов LIVE
7. Account #4: 3 сервиса (Gateway, LLM, Blender)
8. LLM обновлён до нового кода
9. Kaggle T4 GPU для рендера

---

## Версия 11.2.0 — Frontend/Backend Stitching Fix
**Дата:** ~2026-08-10

### Исправлено
1. Все критические баги сшивки Frontend/Backend — 3D-модель теперь загружается в viewer
2. Clarification flow работает корректно

### Добавлено
3. Единый source HTML — 3 копии `index.html` → 1 (`frontend/index.html`), gateway и GitHub Pages используют единый файл
4. File proxy — `GET /api/v1/files/{path}` в gateway для отдачи GLB/PNG с blender-service
5. Публичные эндпоинты — chat-эндпоинты больше не требуют `ARCH_API_KEYS`
6. ifc-service + cad-service — добавлены в docker-compose
7. Nginx — отдельные location-блоки для `/api/v1/files/` и `/api/v1/analyze/`

---

## Версия 11.1.0 — Key Health Tracker + Background Discovery
**Дата:** ~2026-08-09

### Добавлено
1. Key Health Tracker — единая система cooldown для Gemini и OpenRouter, дублирование в Redis
2. Все ключи равноправны — round-robin вместо "основной + фолбэк"
3. Background discovery — список бесплатных моделей OpenRouter обновляется каждый час
4. Eager discovery — обновление при старте сервиса, не при первом запросе
5. Discovery → Redis — список моделей共享 между воркерами и переживает рестарт
6. chat_completions перебор — все ключи пробуются автоматически при 429/402
7. 404 handling — если модель удалена из OpenRouter → invalidate discovery + следующая модель
8. `GET /api/v1/keys/status` — endpoint мониторинга ключей
9. `KEY_COOLDOWN_RATE_LIMIT_SEC` / `KEY_COOLDOWN_QUOTA_SEC` — настраиваемые cooldown

---

## Версия 11.0.0 — PDF/DWG Analysis + Kaggle GPU + 25+ Agents
**Дата:** ~2026-08-09

### Добавлено
1. PDF/DWG анализ — загрузка архитектурных чертежей, автоматическое извлечение помещений, размеров, MEP-систем
2. Kaggle GPU Auto-Submit — автоматическая отправка рендер-задач на бесплатный T4 GPU
3. HDRI освещение — процедурный небесный купол для реалистичного света
4. Улучшенный интерьер — дверь с коробкой, встроенные потолочные светильники, стиль-зависимые материалы пола
5. LLM-уточнения — генерация контекстных вопросов через LLM вместо хардкода
6. Pipeline profile от LLM — парсер сам определяет профиль (interior/landscape/standard)
7. 16K retry — при неудаче рендера 16K: 4096 samples + tiled render
8. 25+ AI-агентов — парсер, геометрия, текстуры, свет, конструктив, нормативы, рендер, качество, экспорт, анализ PDF/DWG

---

## Версия 10.6.0 — Google Gemini Direct API + Kaggle GPU
**Дата:** ~2026-08-07

### Добавлено
1. Google Gemini прямой API — бесплатный LLM без зависимости от OpenRouter
2. 4 ключа Gemini с ротацией — обход rate limit (15 RPM/ключ)
3. Docker: проброс `GOOGLE_API_KEY` — ключи теперь доходят до LLM-сервиса
4. Kaggle GPU Renderer — polling-режим для бесплатного T4 GPU рендеринга

---

## Версия 10.5.0 — Render Pipeline Fix + Bathroom Furniture
**Дата:** ~2026-08-06

### Исправлено
1. Render pipeline fix — критический баг: render_agent получал неправильные параметры
2. Denoising fix — отключён OpenImageDenoiser (недоступен на Render free tier)

### Добавлено
3. Bathroom furniture — jacuzzi, shower, shower_cabin, toilet и др.
4. Russian→English mapping — автоматическая конвертация русских названий мебели
5. File download endpoint — `/api/v1/files/{path}` для скачивания рендеров
6. Kaggle GPU Renderer — документация по настройке Kaggle T4 GPU

---

## Версия до 10.5.0 — Foundation (Phase 1 ROADMAP)
**Дата:** до 2026-08-05

### Выполнено (из ROADMAP Phase 1)
1. Удалён `promt_parser.py` (дубликат `shared/parser.py`)
2. Все импорты обновлены на `shared.parser`
3. Добавлен `shared/auth.py` — API key auth + rate limiting
4. Исправлен CORS: конфигурируемые origins через `CORS_ORIGINS` env
5. LRU-кеширование результатов парсера (TTL 5 мин, max 500 записей)
6. Retry chain: primary model → fallback models → regex
7. Расширенный набор стилей (16 vs 6), материалов (15 vs 6), features (10 vs 3)
8. Поддержка confidence и ambiguities в LLM-ответе
9. Разделение Dockerfile на per-service, multi-stage build
10. Добавлен `QualityAgent` в orchestrator pipeline (5 уровней проверки)

### Тестирование (2026-08-05)
- ✅ Адаптивность интерфейса — Mobile/Tablet/Desktop
- ✅ Код агентов реализован (нормативы, мебель, качество, текстуры, свет)
- ❌ LLM недоступен — OpenRouter 402 (закончились кредиты) — **единственный блокер**

---

## Известные проблемы (на момент v13.5.0)

1. Ключи Gemini 1-7 нерабочие (Google AQ bug) — обход через OpenRouter для Gemini моделей
2. Redis не настроен в Gateway (`redis: not_configured`)
3. Render Free Tier сервисы засыпают через 15 мин бездействия (cold start 30-60 сек)
4. 3 копии `index.html` — нужна дедупликация
5. Orchestrator exports={} — пустой экспорт при некоторых условиях
6. CORS блокирует прямые вызовы с localhost к Render сервисам

---

## Дорожная карта (из ROADMAP.md)

### Phase 3 — Intelligence (3-4 месяца)
- Reference Search (CLIP/SigLIP + Vector DB + RAG)
- Style Transfer из референсных изображений
- Quality Loop (self-improving: рендер → анализ → исправление)

### Phase 4 — BIM & Compliance (4-6 месяца)
- IFC Enhancement (инженерные параметры, смета материалов)
- Building Codes (СП 1.13130, СП 54.13330, ГОСТ 21.501, IBC)
- CAD Integration (STEP/IGES, Revit/ArchiCAD)

### Phase 5 — Market Ready (6-9 месяцев)
- Real-time (WebGPU, Blender EEVEE Next)
- Collaboration (multi-user, shared projects)
- Mobile (React Native + expo-three)
- Marketplace (шаблоны, стили, asset packs)
- API & SDK (OpenAPI, Python SDK, webhooks)
