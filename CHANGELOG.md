# CHANGELOG — AI_Arhitector

Все значимые изменения, планы доработок и итоги.

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
