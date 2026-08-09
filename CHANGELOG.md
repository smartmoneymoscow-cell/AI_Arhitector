# CHANGELOG — AI_Arhitector

Все значимые изменения, планы доработок и итоги.

---

## v11.2.0 — Frontend/Backend Stitching + Critical Pipeline Fixes

### Дата: 2026-08-09

### Проблема
Система не работала end-to-end: фронтенд и бэкенд были рассшиты на нескольких уровнях.
Генерация 3D-моделей не запускалась, clarification flow ломался, файлы не загружались.

### Что исправлено

#### Критические исправления (pipeline)

| # | Файл | Баг | Исправление |
|---|------|-----|-------------|
| 1 | `index.html` | `ReferenceError: t is not defined` — regex pipeline profile падал до отправки запроса | Добавлен `const t = text.toLowerCase()` |
| 2 | `index.html` | `orchResult.exports.formats.glb` — такого поля нет, бэкенд возвращает `exports.output_path` | Исправлено на `exports.output_path` |
| 3 | `gateway/app.py` | Нет роута `GET /api/v1/files/{path}` — gateway отдавал index.html вместо GLB/PNG | Добавлен file proxy endpoint |
| 4 | `index.html` | `data-orch-q` атрибут не проставлялся → resume после 1-го вопроса вместо всех | Добавлен атрибут на каждый блок вопроса |
| 5 | `index.html` | `quality.score` не существует → quality строка не показывалась | Переписано под `{passed, checks, issues, severity}` |
| 6 | `index.html` | AbortController timeout 300s < nginx 600s → обрыв на холодном старте | Поднято до 620s |

#### Архитектурные исправления

| # | Файл | Что | Исправление |
|---|------|-----|-------------|
| 7 | `frontend/index.html`, `gateway/frontend/index.html` | 3 копии HTML рассинхронизированы | Единый source: `frontend/index.html`, остальные удалены |
| 8 | `gateway/app.py` | `ARCH_API_KEYS` блокировал публичный чат | Убран `Depends(get_api_key_required)` с 5 публичных эндпоинтов |
| 9 | `docker-compose.yml` | ifc-service и cad-service не объявлены → hostnames не резолвились | Добавлены оба сервиса с healthcheck |
| 10 | `docker-compose.yml` | IFC_SERVICE_URL порт 8083 вместо реального 8084 | Исправлено на 8084 |
| 11 | `nginx.conf` | `/api/v1/files/` и `/api/v1/analyze/` падали в catch-all с 30s timeout | Добавлены отдельные location-блоки |

#### Что НЕ вошло (осознанно)

- `shared/blender.py`, отдельные агенты (structural/compliance/furniture/…)
- `shared/celery_app.py`
- `tests/`
- Удаление regex pipeline profile из фронта (оставлен как fallback, LLM-детекция работает корректно)

### Сводная таблица

| # | Задача | Статус |
|---|--------|--------|
| 1 | ReferenceError `t` не определена | ✅ Done |
| 2 | 3D-модель не загружалась (exports.formats.glb) | ✅ Done |
| 3 | File proxy для GLB/PNG | ✅ Done |
| 4 | Clarification resume после всех вопросов | ✅ Done |
| 5 | Quality score отображение | ✅ Done |
| 6 | AbortController timeout | ✅ Done |
| 7 | Единый source HTML (3→1) | ✅ Done |
| 8 | Публичные эндпоинты без API key | ✅ Done |
| 9 | ifc-service + cad-service в compose | ✅ Done |
| 10 | IFC port 8083→8084 | ✅ Done |
| 11 | Nginx location для files/analyze | ✅ Done |

---

## v11.1.0 — Key Rotation + Free Model Discovery + Cooldown

### Дата: 2026-08-09

### Проблема
LLM-цепочка не использовала все доступные ключи:
1. Gemini: `max_retries=3` — при 4 ключах четвёртый никогда не пробовался
2. OpenRouter: при 429/402 ключ не помечался как исчерпанный — повторные запросы шли на тот же ключ
3. Discovery бесплатных моделей вызывался только по HTTP и только один раз за жизнь процесса
4. `chat_completions` endpoint использовал только один ключ
5. Cooldown не переживал рестарт контейнера (in-memory only)

### Что исправлено

#### Key Health Tracker (`shared/parser.py`)
- **Единая система cooldown** для Gemini и OpenRouter: `_KEY_COOLDOWN`, `_mark_key_dead()`, `_filter_alive()`, `_is_key_cooling()`
- RPM-лимит (429) → короткий cooldown (60 сек)
- Дневная квота / нет кредитов (402, quota) → длинный cooldown (24 часа)
- Cooldown дублируется в **Redis** — переживает рестарт/передеплой контейнера
- `_filter_alive()`: если ВСЕ ключи остывают — возвращает исходный список (лучше протухший, чем ничего)

#### Gemini — все ключи равноправны (`shared/parser.py`)
- Убран `max_retries=3` → `for attempt in range(len(keys))` — пробуем КАЖДЫЙ живой ключ
- Round-robin через `_GEMINI_KEY_IDX`
- На 429: `_mark_key_dead()` + мгновенный переход к следующему (вместо `asyncio.sleep`)
- На 400/403: `_mark_key_dead(key, QUOTA_EXHAUSTED)` — невалидный ключ

#### OpenRouter — ключ + статус ответа (`shared/parser.py`)
- `_call_openrouter()` теперь возвращает `(dict|None, http_status, body_snippet)` вместо `dict|None`
- 429/402 → `_mark_key_dead()` + `continue` (следующий ключ)
- 404 → модель удалена из каталога → `invalidate_discovery()` + следующая модель
- Re-filter `_filter_alive()` перед каждой моделью в каскаде

#### Discovery бесплатных моделей
- **Background loop** в `llm-service/app.py`: каждые 3600 сек ходит в OpenRouter `/models`
- **Eager discovery при старте**: обновляем список СРАЗУ, не ждём первого запроса
- **Redis persistence**: `_save_discovery_to_redis()` / `_load_discovery_from_redis()` —共享 между воркерами
- **`_maybe_trigger_discovery()`**: lazy refresh при каждом запросе если список устарел
- **Защита от пустого ответа**: если OpenRouter вернул 0 моделей — не затираем предыдущий список
- **`_cascade_is_stale()`**: точечная проверка свежести кэша

#### chat_completions — перебор всех ключей (`llm-service/app.py`)
- Цикл по `_filter_alive(all_keys)` с автоматическим переключением при 429/402
- Новый endpoint `GET /api/v1/keys/status` — мониторинг: сколько ключей настроено / живых

#### Конфигурация
- `.env.example`: добавлены `KEY_COOLDOWN_RATE_LIMIT_SEC`, `KEY_COOLDOWN_QUOTA_SEC`
- `docker-compose.yml`: проброс `KEY_COOLDOWN_*` в llm-service
- `render.yml`: добавлены `OPENROUTER_FALLBACK_KEYS`, `GOOGLE_FALLBACK_KEYS`, `KEY_COOLDOWN_*`

#### Тесты
- Все mock `_call_openrouter` обновлены: `return_value=dict` → `return_value=(dict, 200, "")`
- `return_value=None` → `return_value=(None, 500, "boom")`
- `_l1_get` / `_l2_get` моки остались `return_value=None` (не зависят от формата)

### Сводная таблица

| # | Задача | Статус |
|---|--------|--------|
| 1 | Gemini: все ключи вместо 3 попыток | ✅ Done |
| 2 | Key Health Tracker (cooldown + Redis) | ✅ Done |
| 3 | _call_openrouter → tuple (status, body) | ✅ Done |
| 4 | 404 → invalidate discovery | ✅ Done |
| 5 | Background discovery loop | ✅ Done |
| 6 | Eager discovery at startup | ✅ Done |
| 7 | Discovery → Redis persistence | ✅ Done |
| 8 | chat_completions — перебор ключей | ✅ Done |
| 9 | GET /api/v1/keys/status | ✅ Done |
| 10 | .env + docker-compose + render.yml | ✅ Done |
| 11 | Тесты обновлены | ✅ Done |

---

## v11.0.1 — Pipeline Integration + Quality Fixes

### Исправления pipeline

#### Mid-pipeline агенты теперь влияют на рендер
- **`shared/agents/orchestrator.py`**: bpy-скрипты от lighting, furniture, landscape, mep, structural агентов теперь **интегрируются** в render script
- Ранее агенты выполнялись, но их output **игнорировался** при рендеринге
- Исправлено в обоих методах: `execute()` и `resume_with_answers()`

#### Качество рендера зданий
- **`shared/blender.py`**: Building generator — samples 16→256, denoiser включён (OPENIMAGEDENOISE)
- Ранее building script содержал `samples=16, denoising=False` — теперь согласован с render_agent presets

#### IFC генератор (BIM)
- **`shared/ifc_generator.py`**: Исправлен и расширен:
  - Roof теперь агрегируется к Building через IfcRelAggregates
  - Все элементы содержатся в IfcRelContainedInSpatialStructure по этажам
  - Добавлен IfcSlab типа BASESLAB для пола
  - Добавлены PropertySets: Pset_WallCommon, Pset_WindowCommon, Pset_DoorCommon, Pset_SlabCommon
  - Отдельные материалы для стекла (окна) и дерева (двери)
  - Комнаты генерируются для всех этажей (не только 1-2)
- **`requirements.txt`**: ifcopenshell разблокирован (>=0.7.0 вместо ==0.8.0)

#### PDF/DWG агенты
- **Алиасы + реестр**: PdfAnalysisAgent/DwgAnalysisAgent зарегистрированы в AGENT_REGISTRY
- **Pipeline profile**: добавлен `document_analysis`

### Сводная таблица

| # | Задача | Статус |
|---|--------|--------|
| 1 | Lighting/furniture bpy → render script | ✅ Done |
| 2 | Building samples 16→256 + denoiser | ✅ Done |
| 3 | IFC generator: spatial structure + property sets | ✅ Done |
| 4 | ifcopenshell в requirements | ✅ Done |
| 5 | PDF/DWG agents в orchestrator registry | ✅ Done |

---

## v11.0.0 — PDF/DWG Analysis + 3D Quality + Pipeline Fixes

### Новые возможности

#### PDF/DWG анализ
- **PDF Analysis Agent** (`shared/agents/pdf_analysis_agent.py`) — парсинг архитектурных чертежей из PDF:
  - Извлечение помещений, размеров, материалов из спецификаций
  - Определение MEP-систем (вентиляция, отопление, водоснабжение, канализация)
  - Тип чертежа (план, разрез, фасад, спецификация)
- **DWG/DXF Analysis Agent** (`shared/agents/dwg_analysis_agent.py`) — парсинг DXF через ezdxf:
  - Слои, блоки, размерные линии, текстовые аннотации
  - Классификация архитектурных элементов по именам слоёв
- **API endpoints**: `POST /api/v1/analyze/pdf`, `POST /api/v1/analyze/dwg`
- **Frontend**: кнопка загрузки PDF/DWG в чате, отображение результатов анализа, кнопка «Использовать для 3D генерации»

#### Kaggle GPU Auto-Submit
- **`shared/kaggle_auto_submit.py`** — автоматическая отправка рендер-задач на Kaggle T4 GPU
- Экспоненциальный backoff при polling
- Интеграция в RenderAgent как fallback

### Улучшения качества 3D

#### Интерьер (`shared/blender.py`)
- **Дверь с коробкой** — панель, рама (лево/право/верх), ручка
- **Потолочные светильники** — 4 встроенных recessed lights с emit-материалом
- **Материал пола по стилю** — wood (classic), stone (loft), tile (hitech) и т.д.
- **Стекло окна**: Transmission=0.9, IOR=1.52 (физически корректное стекло)

#### Рендер (`shared/agents/render_agent.py`)
- **HDRI world** — процедурный небесный купол (Nishita sky model) вместо плоского цвета
- **Contact shadows** — SSAO (GTAO) для ambient occlusion
- **Tiled render** — композитинг для 16K рендеринга (разбиение на тайлы)
- **Samples override** — 4096 samples при retry 16K (вместо 2048)

### Исправления pipeline

#### ClarificationEngine (`shared/clarification.py`)
- **LLM-генерация вопросов** — новый метод `generate_llm_questions()`: вызывает LLM для генерации контекстных вопросов с visual_options (pros/cons)
- Fallback на хардкод вопросы если LLM недоступен

#### Orchestrator (`shared/agents/orchestrator.py`)
- **resume_with_answers**: сохраняет pre-agent результаты в job dict, переиспользует их вместо повторного запуска
- **Pipeline profile**: LLM-парсер определяет `pipeline_profile` в ответе; оркестратор использует его, regex только как fallback
- **Quality gate retry**: при неудаче 16K — 4096 samples + tiled render (16 тайлов) + уведомление пользователю

#### LLM Schema (`shared/llm_schemas.py`)
- Добавлено поле `pipeline_profile` в `ParsedParams`

#### Frontend (`index.html`)
- Pipeline profile: LLM-determined → regex fallback
- Загрузка PDF/DWG/DXF файлов через кнопку «Прикрепить файл»
- Анализ файлов и отображение результатов

### Архитектура (v11.0.0)
```
Пользователь → Nginx → Gateway → LLM Service → Blender Service
                  │         │          │              │
                  │    Orchestrator    Gemini     Blender CLI
                  │    (25+ agents)    OpenRouter   bpy-скрипты
                  │         │          Ollama       Kaggle GPU
                  │    Clarification
                  │    (LLM-driven)
                  │
              Frontend
              (Three.js 3D)
              + PDF/DWG upload
```

---

## 2026-08-09 — Полный фикс pipeline генерации 3D интерьера

### Проблема
Генерация 3D-моделей интерьера по промту не работала end-to-end:
1. Фронтенд обходил оркестратор — парсил промт сам, генерировал свои clarification-вопросы
2. Оркестратор возвращал `clarification_needed`, но не было endpoint'а для resume
3. Рендер: samples=16, denoiser выключен — качество 4/10
4. Интерьер: нет окна со стеклом, слабое освещение
5. Три копии HTML-фронта рассинхронизированы
6. Синтаксические ошибки в Python-файлах (celery_app.py, тесты)

### Что исправлено

#### Критические исправления (pipeline)
- **`shared/agents/orchestrator.py`**: добавлен `resume_with_answers()` — принимает ответы пользователя, мержит в параметры, продолжает pipeline
- **`gateway/app.py`**: добавлен `POST /api/v1/orchestrator/resume` — принимает `{job_id, answers}`
- **`index.html`**: переписана `sendMessage()`:
  - Промт → сразу в оркестратор (НЕ в parse напрямую)
  - Оркестратор парсит, проверяет confidence
  - Если `clarification_needed` → показывает вопросы от оркестратора (visual_options с pros/cons)
  - Пользователь отвечает → `/api/v1/orchestrator/resume`
  - Оркестратор продолжает → генерация → 3D модель

#### Качество рендера
- **`shared/agents/render_agent.py`**: samples 16→256 (standard), 512 (high), denoiser=OPENIMAGEDENOISE
- **`shared/blender.py`**: interior — окно со стеклом (transmission 0.9), 4 потолочных светильника, window area light, fill light
- **`blender-service/app.py`**: все hardcoded samples=16 заменены на 256+, denoiser включён, исправлены сломанные multiline строки
- **`shared/celery_app.py`**: исправлен синтаксис (broken multiline string)

#### Синхронизация фронтендов
- **`gateway/frontend/index.html`** и **`frontend/index.html`**: синхронизированы с `index.html`

#### Исправление тестов
- **`tests/test_ui_v2.py`**: JS regex `/pattern/` → Python `re.compile('pattern')`
- **`tests/visual_test_runner.py`**: исправлен indentation в `.replace()` цепочке

### Архитектура pipeline (после исправления)
```
Промт → /api/v1/orchestrator/execute
    ↓
1. ParserAgent (Gemini → OpenRouter → Ollama)
    ↓
2. ClarificationEngine (confidence < 0.6 → вопросы)
    ↓ если нужны уточнения
3. Frontend показывает вопросы → пользователь отвечает
    ↓
4. /api/v1/orchestrator/resume (с ответами)
    ↓
5. Route → Pre-agents (concept, style, furniture, lighting)
    ↓ параллельно
6. Geometry + Texture agents
    ↓ параллельно
7. Mid-agents (landscape, furniture, mep, structural)
    ↓
8. Render (Cycles, 256 samples, OIDN denoiser)
    ↓
9. Quality check (resolution, file size, visual)
    ↓
10. Export (GLB + IFC + SVG drawings)
```

### Сводная таблица

| # | Задача | Статус |
|---|--------|--------|
| 1 | Clarification → resume flow | ✅ Done |
| 2 | Orchestrator resume endpoint | ✅ Done |
| 3 | Frontend → orchestrator (не parse напрямую) | ✅ Done |
| 4 | Samples 16→256, denoiser включён | ✅ Done |
| 5 | Interior: окно + 4 светильника + fill | ✅ Done |
| 6 | 3 HTML-фронта синхронизированы | ✅ Done |
| 7 | Синтаксис Python файлов исправлен | ✅ Done |
| 8 | Тесты test_ui_v2.py исправлены | ✅ Done |

---

## 2026-08-08 — Исправление LLM-цепочки и бесплатного доступа

### Проблема
Генерация 3D-моделей не работала: OpenRouter возвращал ошибку 402 (нет кредитов), хотя в каскаде стояли бесплатные модели. Все модели `:free` на OpenRouter требуют ненулевой баланс аккаунта.

### Корневая причина
В `shared/parser.py` уже был реализован прямой вызов Google Gemini API (бесплатно), но:
1. Ключи `GOOGLE_API_KEY` и `GOOGLE_FALLBACK_KEYS` **не пробрасывались** в `docker-compose.yml` → LLM-сервис не видел ключи
2. В `llm-service` переменные `OPENROUTER_API_KEY` были обязательными (`:?`) → падал при запуске без ключей

### Что исправлено

#### `docker-compose.yml`
- **llm-service**: добавлены `GOOGLE_API_KEY`, `GOOGLE_FALLBACK_KEYS`, `GEMINI_MODEL`
- **llm-service**: `OPENROUTER_API_KEY` сделан необязательным (`:-`) — Gemini работает первым, OpenRouter — фолбэк
- **gateway**: добавлены `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `KAGGLE_RENDERER_URL`, `KAGGLE_POLLING_ENABLED`
- **blender-service**: добавлен `KAGGLE_RENDERER_URL` для GPU-рендера

### Архитектура LLM-цепочки (после исправления)
```
Промт пользователя
    ↓
1. Google Gemini API (прямой, бесплатно, 4 ключа с ротацией)
    ↓ если не ответил
2. OpenRouter каскад (8 бесплатных моделей :free)
    ↓ если не ответил
3. Ollama (локальный, если настроен)
    ↓ если не ответил
4. Regex fallback (базовый парсинг)
```

### Планы доработок (на 2026-08-08)

| # | Задача | Приоритет | Статус |
|---|--------|-----------|--------|
| 1 | Проброс GOOGLE_API_KEY в Docker | 🔴 Критично | ✅ Done |
| 2 | Frontend → orchestrator + clarification flow | 🟡 Важно | ✅ Done |
| 3 | Kaggle GPU polling endpoints | 🟡 Важно | ✅ Done (были реализованы) |
| 4 | answerClarification → resume orchestrator | 🟡 Важно | ✅ Done |
| 5 | _handleOrchestratorResult (clarif/success/fail) | 🟡 Важно | ✅ Done |
| 6 | Удаление дубликатов HTML (3 копии) | 🟢 Улучшение | 📋 Planned |
| 7 | Kaggle GPU notebook запуск | 🟡 Важно | 📋 Planned |

---

## Формат записей

### Шаблон
```
## YYYY-MM-DD — Краткое описание

### Проблема
Описание что сломалось или чего не хватало.

### Что исправлено
Список изменений по файлам.

### Планы доработок
Таблица задач с приоритетами и статусами.
```

### Статусы
- ✅ Done — выполнено
- 🔄 In Progress — в работе
- 📋 Planned — запланировано
- ❌ Blocked — заблокировано
