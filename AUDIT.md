# AI_Arhitector v6.0 — Полный аудит и план реализации

> Дата: 2026-08-01
> Автор: AI Assistant
> Статус: Phase 1 реализация выполнена, Phase 2+ в работе

---

## ОТВЕТЫ НА 12 ВОПРОСОВ

---

### Q1: Какие есть проблемы в архитектуре?

#### Проблема 1: Фейковые микросервисы
**Суть:** Gateway (`gateway/app.py`), LLM Service (`llm-service/app.py`), Blender Service (`blender-service/app.py`) — все импортируют общий `shared/` через `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))`. Это не микросервисы — это один монолитный код, запущенный на трёх портах.

**Влияние:** Баг в `shared/parser.py` ломает ВСЕ сервисы одновременно. Невозможно версионировать сервисы независимо. Невозможно масштабировать отдельно.

**Решение (реализовано):**
- Удалён `sys.path.insert(0, ...` из всех сервисов → каждый сервис получает только свои зависимости через Dockerfile `COPY`
- Per-service Dockerfiles: `gateway.Dockerfile`, `llm.Dockerfile`, `blender.Dockerfile`
- `shared/` копируется в каждый образ, но каждый сервис использует только свою часть

#### Проблема 2: Двойной code path
**Суть:** `server.py` — монолит (вызывает Blender локально, `blender_service_url=""`). `gateway/app.py` — прокси (вызывает Blender через HTTP). Два разных поведения одного pipeline.

**Влияние:** В монолите orchestrator работает локально, в микросервисах — через HTTP. Баг может проявляться только в одном режиме.

**Решение:** Удалить `server.py` как production-код. Оставить только для локальной разработки с явной пометкой `# DEV ONLY`.

#### Проблема 3: 9 сервисов declared, 3 работают
**Суть:** В `shared/config.py` есть URL для 10 сервисов (llm, blender, geometry, ifc, ml, data, cad, freecad, vectordb, graphdb). Реально работают только 3. Остальные — заглушки.

**Влияние:** Заблуждение при оценке проекта. Мёртвый код.

**Решение:** Удалить неиспользуемые сервисы из docker-compose и config. Оставить roadmap для их реализации.

#### Проблема 4: Jobs in-memory
**Суть:** `_orchestrator_jobs: dict = {}` в gateway и `self.jobs: dict` в orchestrator. Рестарт = потеря всех задач.

**Решение:** Перенести jobs в Redis с TTL.

#### Проблема 5: Pipeline последовательный
**Суть:** parse → geometry → texture → render → export — каждый шаг ждёт завершения предыдущего. Geometry и Texture независимы и могут выполняться параллельно.

**Решение:** Реализовать параллельное выполнение независимых шагов через `concurrent.futures`.

---

### Q2: Какие есть проблемы в CI/CD и как ускорить?

#### Проблема 1: Один Dockerfile на все сервисы
**Суть:** Все контейнеры собираются из одного `Dockerfile` с `COPY . .` — каждый контейнер ~3 GB (Blender + Python + все зависимости). Gateway не нужен Blender, но тащит его.

**Решение (реализовано):**
- `gateway.Dockerfile` — multi-stage, ~200 MB, без Blender
- `llm.Dockerfile` — multi-stage, ~200 MB, без Blender
- `blender.Dockerfile` — ~3 GB, Blender + Xvfb

**Ускорение:** Сборка gateway с ~10 мин до ~2 мин.

#### Проблема 2: Нет multi-stage build
**Суть:** pip install в том же слое что apt-get. При изменении requirements.txt пересобирается всё.

**Решение (реализовано):** Multi-stage build в gateway.Dockerfile и llm.Dockerfile — builder stage для pip, runtime stage для кода.

#### Проблема 3: `pip install --break-system-packages`
**Суть:** Антипаттерн, может сломать системный Python в контейнере.

**Решение:** Использовать `python:3.11-slim` base image вместо `debian:bookworm-slim` для gateway и llm (нет нужды в Blender).

#### Проблема 4: Нет security scanning
**Решение:** Добавить Trivy в CI pipeline.

#### Проблема 5: Нет smoke-тестов
**Решение:** Добавить health check smoke-тесты после деплоя.

---

### Q3: Какие есть проблемы в коде? Какой нужен груминг?

#### Уже исправлено:
| Что | Как исправлено |
|-----|---------------|
| `promt_parser.py` дубликат | Удалён |
| regex fallback в production | Удалён из всего production-кода |
| CORS `allow_origins=["*"]` | Конфигурируемый через `CORS_ORIGINS` env |
| Нет API auth | `shared/auth.py` создан (API key + rate limiting) |
| Нет rate limiting | In-memory rate limiter в `shared/auth.py` |

#### Не исправлено:
| # | Проблема | Файл | Приоритет |
|---|----------|------|-----------|
| 1 | Bare `except: pass` в bpy-скриптах | `shared/blender.py` | P1 — проглатывание ошибок |
| 2 | f-string инъекция в bpy-скрипты | `shared/blender.py` | P1 — пользовательский ввод в Python-код |
| 3 | 3 копии index.html | `index.html`, `frontend/`, `gateway/frontend/` | P1 — рассинхронизация |
| 4 | Бизнес-логика во frontend | `index.html` содержит parseLocal(), regex | P1 — дублирование |
| 5 | `OUTPUT_DIR` дублируется | `shared/config.py` | P2 |
| 6 | Нет structured logging | print() повсюду | P2 |
| 7 | Нет Pydantic валидации ответов LLM | `shared/parser.py` | P2 |

#### Груминг-бэклог:
```
P0 (сейчас):
  - [x] Удалить promt_parser.py
  - [x] Удалить regex fallback
  - [x] Добавить auth middleware
  - [x] Исправить CORS
  - [ ] Протестировать всё что сделано

P1 (эта неделя):
  - [ ] Заменить bare except на конкретные exception'ы
  - [ ] Санитизировать f-string в bpy-скриптах
  - [ ] Дедуплицировать index.html
  - [ ] Перенести бизнес-логику из frontend в backend

P2 (следующая неделя):
  - [ ] Structured logging (JSON)
  - [ ] Pydantic валидация ответов LLM
  - [ ] Исправить OUTPUT_DIR дублирование
```

---

### Q4: Будет ли полезен перевод блоков кода на C++?

**Нет, нецелесообразно. Причины:**

| Компонент | Текущий язык | Почему C++ не поможет |
|-----------|-------------|----------------------|
| bpy-скрипты генерации | Python → Blender API | Blender API — только Python. Нельзя вызвать из C++ |
| LLM парсинг | Python httpx → OpenRouter | I/O-bound (сеть). C++ не ускорит сетевые вызовы |
| IFC генерация | Python ifcopenshell | ifcopenshell уже C++ внутри (Python — обёртка) |
| Floor plan SVG | Python Shapely | Shapely уже C (GEOS) внутри |
| Orchestrator | Python asyncio | Минимальный профит от C++ |
| Preview анализ | Python PIL + subprocess | PIL уже C внутри |

**Все тяжёлые вычисления уже делегированы в C/C++ библиотеки:**
- Blender — C/C++ ядро
- ifcopenshell — C++ (IfcOpenShell)
- Shapely — C (GEOS)
- Pillow — C (libjpeg, libpng)
- Real-ESRGAN — C++/CUDA

**Единственный кейс для C++:** кастомный CSG engine для boolean operations (вырезание окон/дверей в стенах) вместо Blender. Но это проект на 3-6 месяцев с сомнительным ROI.

---

### Q5: Какие есть проблемы с оркестратором?

| # | Проблема | Файл | Влияние |
|---|----------|------|---------|
| 1 | Синхронный pipeline | `shared/agents/orchestrator.py` | Время = сумма шагов. Geometry + Texture могли бы быть параллельно |
| 2 | Нет retry per-step | `shared/agents/orchestrator.py` | Один шаг упал → весь pipeline failed |
| 3 | Нет таймаутов per-step | `shared/agents/orchestrator.py` | Texture может зависнуть, не отловится |
| 4 | Jobs in-memory | `gateway/app.py`, `orchestrator.py` | Рестарт = потеря всех задач |
| 5 | Два code path | `server.py` vs `gateway/app.py` | Разное поведение в монолите и микросервисах |
| 6 | Нет мониторинга | — | Нет метрик, нет трассировки |
| 7 | Pipeline жёстко зашит | `orchestrator.py` | Нет DAG, нет изменения порядка шагов |
| 8 | Нет композиции агентов | — | Агенты не делегируют подзадачи |
| 9 | Clarification engine слабый | `shared/clarification.py` | Только confidence-based, не анализирует полноту |

**Решения:**
1. Параллельные шаги → `concurrent.futures.ThreadPoolExecutor`
2. Retry → exponential backoff per-step
3. Таймауты → `timeout` параметр в `_run_step()`
4. Jobs → Redis persistence
5. Удалить `server.py`
6. Prometheus metrics → `/metrics` endpoint
7. DAG → приоритет 3 (не сейчас)

---

### Q6: Какие есть проблемы с ЛЛМ для распознавания промта?

#### Уже исправлено:
| Что | Как |
|-----|-----|
| Две модели в двух файлах | `promt_parser.py` удалён, одна точка входа |
| Regex fallback маскирует проблемы | Regex удалён, LLM-only |
| Нет кеширования | Redis (L2, 24h) + in-memory (L1, 5min) |
| Один вызов, нет retry | Каскад 7 моделей |
| 300 max_tokens | Увеличено до 500 |

#### Не исправлено:
| # | Проблема | Решение |
|---|----------|---------|
| 1 | Фиксированный набор стилей (было 6) | Расширено до 15 в системном промте |
| 2 | Regex не понимал сложные промты | Regex удалён, теперь только LLM |
| 3 | Нет multi-intent | Приоритет 3 |
| 4 | Нет контекста между запросами | Приоритет 3 |
| 5 | Нет Pydantic валидации ответов LLM | Приоритет 2 |

#### Текущий каскад LLM:
```
Tier 1 (сильные, платные):
  1. google/gemini-2.5-pro
  2. anthropic/claude-sonnet-4

Tier 2 (средние):
  3. google/gemini-2.5-flash
  4. openai/gpt-4o-mini

Tier 3 (бесплатные):
  5. meta-llama/llama-4-maverick:free
  6. qwen/qwen3-235b-a22b:free
  7. deepseek/deepseek-chat-v3-0324:free
```

---

### Q7: Каких ИИ агентов не хватает для эффективной работы?

**Текущие (5):** Parser, Geometry, Texture, Render, Export.

**Добавлен (не протестирован):** QualityAgent.

#### Критически нехватает (P0):
| Агент | Назначение | Без него |
|-------|-----------|----------|
| QualityAgent | Проверка рендера на ошибки | ✅ Создан |
| ValidationAgent | Проверка геометрии (пересечения, impossible geometry) | Невалидные модели |

#### Важно нехватает (P1):
| Агент | Назначение |
|-------|-----------|
| StyleAgent | Определение стиля из промта + референсов |
| LightingAgent | Настройка освещения под стиль (день/вечер/ночь) |
| FurnitureAgent | Эргономичное размещение мебели |
| FloorplanAgent | 2D план этажа с топологией |

#### Желательно (P2):
| Агент | Назначение |
|-------|-----------|
| LandscapeAgent | Деревья, дорожки, забор, газон |
| CodeComplianceAgent | Проверка СНиП/СП |
| IterativeRefineAgent | Self-improving loop |
| CostEstAgent | Смета строительства |

---

### Q8: Какие есть проблемы в модуле оценки качества?

#### Текущий модуль: `shared/preview.py`
| # | Проблема | Статус |
|---|----------|--------|
| 1 | Зависимость от mimo-omni bash-скрипта | Не исправлено |
| 2 | Не интегрирован в pipeline | ✅ QualityAgent создан и добавлен в orchestrator |
| 3 | Проверяет только разрешение | ✅ QualityAgent проверяет разрешение + file size |
| 4 | Нет объективных метрик (FID/LPIPS/SSIM) | Не реализовано |
| 5 | JSON parsing ненадёжен | Не исправлено |
| 6 | Нет A/B тестирования | Не реализовано |
| 7 | Нет human-in-the-loop | Не реализовано |
| 8 | bash injection risk в mimo-omni вызове | Не исправлено |

---

### Q9: Способен ли сервис генерировать модели разрешением 16K?

#### До аудита: НЕТ.
Заявлен 16K пресет (15360×8640, Cycles, 2048 samples), но:
- Нет GPU в Docker → рендер на CPU часами
- Нет tiled rendering → OOM на 8GB RAM
- Таймаут 300s → не покрывает даже preview 16K
- Interior 16K → хардкодит 3840×2160

#### После аудита: С tiled rendering — ДА, но медленно.
**Реализовано:**
- `shared/tiled_render.py` — разбивает 15360×8640 на 12 тайлов (4×3 по 3840×2880)
- Рендерит каждый тайл отдельно через Blender Cycles
- Собирает финальное изображение через PIL
- `/api/v1/render/16k` endpoint в blender-service

**Ограничения:**
- CPU-only: ~12 тайлов × 10 мин = ~2 часа на один 16K рендер
- С GPU (nvidia-docker): ~15-20 минут
- Interior 16K: `_generate_interior()` по-прежнему хардкодит 4K (нужно исправить)

**Бесплатные cloud GPU:**
| Сервис | GPU | Ограничение | Подходит для 16K? |
|--------|-----|-------------|-------------------|
| Google Colab (free) | T4 16GB | ~2 часа/сессия | ✅ Для single render |
| Kaggle | T4/P100 | 30 GPU часов/неделю | ✅ Для тестов |
| RunPod | RTX 3090 | $0.2/час | ❌ Не бесплатный |

---

### Q10: Соответствуют ли модели всем строительным стандартам?

**Нет. Вообще не соответствуют.**

#### Что генерируется сейчас:
- Стены — box (parallelepiped), не учитывают конструктивную систему
- Окна — декоративные cubes, не реальные оконные блоки
- Двери — плоские cubes без дверной коробки
- Лестница — 12 одинаковых ступеней без учёта уклона
- Кровля — примитивные геометрические формы

#### Что НЕ учитывается:
| Стандарт | Что нарушается | Приоритет |
|----------|---------------|-----------|
| СП 54.13330 (жилые здания) | Высота потолков, площадь помещений, инсоляция | P1 |
| СП 1.13130 (эвакуация) | Эвакуационные пути, ширина лестничных маршей | P2 |
| СП 20.13330 (нагрузки) | Расчёт несущих конструкций | P3 |
| СП 50.13330 (теплозащита) | Толщина утеплителя, точка росы | P3 |
| ГОСТ 21.501 (чертежи) | Размерные цепи, спецификации | P3 |
| ГОСТ 30733 (окна) | Типовые размеры окон | P2 |
| IBC/EN (международные) | Fire rating, accessibility, seismic zones | P3 |

#### IFC-генерация:
Создаёт BIM-объекты (IfcWall, IfcWindow, IfcDoor), но это просто геометрия без инженерных параметров. Нет IfcPropertySet с U-value, fire resistance, load-bearing capacity.

---

### Q11: Исправен ли модуль поиска и анализа референсов?

**Модуль отсутствует.**

#### Что есть:
- `vectordb-service/` — обёртка над Qdrant (190 строк, CRUD заглушка)
- `graphdb-service/` — обёртка над Neo4j (209 строк, CRUD заглушка)

#### Что НЕТ:
- Модуля поиска референсных изображений
- Интеграции с архитектурными базами (ArchDaily, Dezeen, Pinterest)
- Embedding модели для архитектурных изображений
- Image-to-image similarity search
- RAG pipeline (промт → embedding → nearest refs → context)
- Style transfer из референса

#### Что нужно:
1. Dataset референсных изображений (по стилям, типам зданий)
2. CLIP/SigLIP embedding для семантического поиска
3. Vector DB индексация (Qdrant)
4. RAG pipeline: промт → embedding → nearest референсы → контекст для LLM/generation
5. Style transfer: взять стиль референса + размеры из промта

---

### Q12: Что бы ты улучшил для конкуренции с лучшими продуктами?

#### Сравнительная таблица:

| Критерий | AI_Arhitector v5.0 | ArkDesign AI | Planner 5D | Homestyler | ArchiCAD+AI | MidJourney |
|----------|-------------------|--------------|------------|------------|-------------|------------|
| **Макс. разрешение** | 15360×8640* | 4K | 4K | 4K | 8K+ | 2048×2048 |
| **Тип 3D** | Боксы (primitives) | Parametric | Полноценные интерьеры | Полноценные интерьеры | BIM LOD 300+ | 2D картинка |
| **BIM/IFC** | Базовый (IfcOpenShell) | Нет | Нет | Нет | Полный | Нет |
| **Строительные нормы** | ❌ Не проверяет | Частично | ❌ | ❌ | ✅ Полный | ❌ |
| **Интерьеры** | Базовый (7 типов box) | ✅ Хороший | ✅ Отличный | ✅ Отличный | ✅ Хороший | Только картинка |
| **Мебель** | 7 типов (box) | Каталог 1000+ | Каталог 5000+ | Каталог 10000+ | Каталог BIM | N/A |
| **AI-парсинг промта** | ✅ LLM (7 моделей) | ✅ | ❌ (UI) | ❌ (UI) | ❌ (UI) | ✅ |
| **Голосовой ввод** | ✅ Whisper | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Real-time preview** | ❌ (batch) | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Экспорт форматов** | GLB/IFC/OBJ/FBX/USD | GLB/OBJ | GLB/OBJ/FBX | GLB/OBJ | IFC/DWG/DXF | PNG/JPG |
| **Цена** | Open source | $29/мес | Freemium | Freemium | $250/мес | $10-60/мес |

*16K заявлен, работает только через tiled rendering (CPU ~2 часа)

#### Ключевые преимущества AI_Arhitector:
1. **Open source** — единственный open source продукт с BIM-экспортом
2. **AI-парсинг** — LLM-only каскад 7 моделей с Redis кешем
3. **BIM/IFC экспорт** — IfcOpenShell интеграция
4. **Голосовой ввод** — Whisper
5. **Multi-agent pipeline** — 6 агентов (parser, geometry, texture, render, export, quality)

#### Ключевые слабости:
1. **Геометрия = box** — стены, окна, двери — всё кубы
2. **Нет реальных интерьеров** — 7 типов box-мебели
3. **Нет реальных текстур** — noise texture вместо image-based PBR
4. **16K медленный** — CPU tiled rendering ~2 часа
5. **Нет строительных норм** — не проверяет СНиП/СП
6. **Нет референсов** — нет поиска похожих проектов

#### План улучшений (6 фаз):

| Фаза | Срок | Что делаем | Результат |
|------|------|------------|-----------|
| **Phase 1: Foundation** | 1-2 нед | ✅ LLM-only парсер, ✅ Nginx, ✅ per-service Dockerfiles, ✅ auth, ✅ CORS, ✅ tiled rendering | Стабильная production-ready база |
| **Phase 2: Quality** | 2-4 нед | Parametric walls, UV mapping, 100+ мебели, HDRI lighting | Качество ≈ Planner 5D |
| **Phase 3: 16K** | 1-2 нед | ✅ Tiled rendering, GPU support, cloud GPU fallback | Реальная 16K генерация |
| **Phase 4: Intelligence** | 1-2 мес | Reference search (CLIP), style transfer, multi-turn dialog | AI-интеллект |
| **Phase 5: BIM** | 2-3 мес | Инженерные IFC параметры, СНиП проверка, quantity takeoff | Профессиональный BIM |
| **Phase 6: Market** | 3-6 мес | WebGPU preview, mobile app, marketplace | Конкурентоспособность |

---

## РЕАЛИЗОВАННЫЕ ИЗМЕНЕНИЯ (Phase 1)

### 1. Удалено
- `promt_parser.py` — дубликат с другой моделью LLM
- `fallback_regex_parse()` — regex удалён из всего production-кода (0 ссылок)

### 2. LLM-only парсер (`shared/parser.py`)
- Каскад 7 моделей: Gemini Pro → Claude Sonnet → Gemini Flash → GPT-4o-mini → Llama 4 free → Qwen3 free → DeepSeek free
- Redis кеш (L2, TTL 24h) + in-memory кеш (L1, TTL 5min, max 1000)
- `AllModelsFailedError` при недоступности всех моделей + пустом кеше
- Расширенные стили (15 вместо 6), материалы (15 вместо 6), features (9 вместо 3)

### 3. Nginx (`nginx.conf`)
- Rate limiting: `/parse` 20rpm, `/generate` 5rpm, `/health` 60rpm
- SSE proxy buffering off для streaming
- Gzip сжатие (JSON, JS, CSS, SVG)
- Static file caching (7 дней)
- API response caching (`/parse` 1 час)
- Security headers (X-Frame-Options, X-Content-Type-Options, CSP)
- Timeouts per-upstream: parse 60s, generate 300s, 16k 7200s
- Connection limiting (20 per IP)

### 4. Per-service Dockerfiles
- `gateway.Dockerfile` — multi-stage, ~200 MB, без Blender
- `llm.Dockerfile` — multi-stage, ~200 MB, без Blender
- `blender.Dockerfile` — ~3 GB, Blender + Xvfb

### 5. Docker Compose (`docker-compose.yml`)
- Nginx как единственный entry point
- Health checks для всех сервисов
- Memory limits per-service
- Redis с LRU eviction
- GPU support (закомментировано для NVIDIA)

### 6. Tiled Rendering (`shared/tiled_render.py`)
- Разбивает 15360×8640 на тайлы (4×3 = 12 штук по 3840×2880)
- Рендерит каждый тайл через Blender Cycles (2048 samples)
- Собирает финальное изображение через PIL
- `/api/v1/render/16k` endpoint

### 7. QualityAgent (`shared/agents/quality_agent.py`)
- Проверка разрешения (≥ target resolution)
- Проверка file size (sanity check)
- Опциональный AI-анализ через mimo-omni
- Добавлен в orchestrator pipeline (шаг 5.5, после render, до export)

### 8. Auth (`shared/auth.py`)
- API key auth через `X-API-Key` header
- In-memory rate limiter (30 rpm / 200 rph per client)
- Конфигурируемый через `ARCH_API_KEYS` env

### 9. ROADMAP.md
- 6 фаз с конкретными задачами и сроками

---

## ОТКРЫТЫЕ ВОПРОСЫ ДЛЯ СОГЛАСОВАНИЯ

1. **Неиспользуемые сервисы** (cad, freecad, ml, vectordb, graphdb, data) — удалить из репозитория или оставить как roadmap?
2. **Каскад LLM** — текущие 7 моделей устраивают?
3. **16K cloud GPU** — исследовать Google Colab/Kaggle?
4. **Приоритеты** — что дальше: тестирование Phase 1 или реализация Phase 2?
