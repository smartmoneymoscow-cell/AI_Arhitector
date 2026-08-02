# AI_Arhitector — Комплексный план исправлений

> Дата:2026-07-29 | Статус: В работе
> Репозиторий: https://github.com/smartmoneymoscow-cell/AI_Arhitector

---

## Содержание

1. [Уже исправлено (done)](#1-уже-исправлено)
2. [Критические баги фронтенда](#2-критические-баги-фронтенда)
3. [Бэкенд: оркестратор и pipeline генерации](#3-бэкенд-оркестратор-и-pipeline-генерации)
4. [Микросервисы: превращение заглушек в реальные сервисы](#4-микросервисы)
5. [ЛЛМ: обработка и уточнение запросов](#5-ллм-обработка-и-уточнение-запросов)
6. [Качество генерируемых моделей (4K+)](#6-качество-генерируемых-моделей)
7. [Multi-agent декомпозиция задач](#7-multi-agent-декомпозиция)
8. [Производительность и скорость](#8-производительность)
9. [Тесты: полное покрытие](#9-тесты)
10. [Дедупликация и синхронизация фронтендов](#10-дедупликация-фронтендов)
11. [DevOps и деплой](#11-devops)
12. [Приоритеты и порядок реализации](#12-приоритеты)

---

## 1. Уже исправлено

| # | Что | Файл | Суть |
|---|-----|------|------|
| 1 | Сломанные script-теги | `gateway/frontend/index.html` | JS-код был внутри `<script src="...">` — браузер игнорировал. Исправлено на `<script src="..."></script>` + отдельный `<script>` |
| 2 | Dead code (×3 дубликата Voice Input) | `gateway/frontend/index.html` | Удалено190 строк мёртвого кода из CDN-тегов |
| 3 | Отсутствующие CDN-скрипты | `gateway/frontend/index.html` | Добавлены `RoomEnvironment.js` и `web-ifc-api.js` |
| 4 | Рендер интерьера640×480 | `blender-service/app.py`, `server.py` | Изменено на3840×2160 (4K) |
| 5 | Тесты импортируют `promt_parser.py` | `tests/test_generation.py` | Исправлено на `shared/parser.py` + `shared/validation.py` |
| 6 | Тесты gateway/server на Flask | `tests/test_gateway.py`, `tests/test_server.py` | Переписаны для FastAPI (Starlette TestClient) |
| 7 | Некомпилируемый `promt_parser` тест | `tests/test_generation.py` | Заменён на `shared/parser.py` компиляцию |

**Результат**:79/79 тестов проходят.

---

## 2. Критические баги фронтенда

###2.1 Дедупликация фронтендов

**Проблема**:3 копии HTML:
- `index.html` (2915 строк) — актуальная версия
- `frontend/index.html` (2915 строк) — идентична корневой
- `gateway/frontend/index.html` (2623 строки) — другая версия (API_BASE URL, отсутствие web-ifc, RoomEnvironment)

**План**:
```
[ ] Синхронизировать gateway/frontend/index.html с index.html
    - Единственное отличие: API_BASE URL в gateway версии指向 'https://architect-zpif.onrender.com'
    - Сделать API_BASE конфигурируемым через <meta> тег или data-атрибут
    - Удалить frontend/index.html (избыточная копия)
    - Обновить gateway/Dockerfile COPY инструкцию
```

###2.2 Управление состоянием Three.js

**Проблема**: `initThree()` вызывается на DOMContentLoaded, но если CDN не загрузился (offline, медленный интернет) — все последующие вызовы `buildModel()` падают с "scene is null".

**План**:
```
[ ] Добавить retry-логику для initThree():
    - Проверять typeof THREE !== 'undefined' перед инициализацией
    - Показывать пользователю сообщение "3D-движок загружается..."
    - Перезапускать initThree() при ошибке (макс3 попытки)
[ ] Добавить fallback: если Three.js не загрузился за10с — показать2D SVG preview
```

###2.3 Мобильный интерфейс

**Проблема**: На мобильных sidebar перекрывает viewer, touch-управление нестабильное.

**План**:
```
[ ] Добавить мобильное меню-гамбургер ( уже есть #mob-btn, но toggleSB() не всегда работает)
[ ] Исправить touch-события: passive:false для touchmove вызывает warnings
[ ] Добавить pinch-to-zoom debounce (сейчас дерганый)
[ ] Проверить вёрстку на viewport375px (iPhone SE)
```

###2.4 Ошибки в консоли браузера

**Проблема**: `RGBELoader` и `RoomEnvironment` могут не загрузиться с CDN.

**План**:
```
[ ] Добавить fallback для HDRI: если RGBELoader не загружен — использовать процедурный environment
[ ] Обернуть все THREE.* вызовы в try/catch с понятными сообщениями
[ ] Добавить глобальный error handler: window.onerror → показать toast пользователю
```

---

## 3. Бэкенд: оркестратор и pipeline генерации

###3.1 Единый pipeline генерации

**Текущий flow** (в `_sendInner()` фронтенда):
```
Промт → regex parse → LLM parse → Blender server → Three.js fallback
```

**Проблема**: Pipeline размазан между фронтендом и бэкендом. Фронтенд содержит бизнес-логику (парсинг, маршрутизацию).

**План**:
```
[ ] Перенести ВСЮ логику парсинга и маршрутизации на бэкенд
    - Фронтенд отправляет POST /api/v1/generate {prompt: "..."}
    - Gateway принимает, парсит (LLM + regex), определяет тип, маршрутизирует
    - Ответ: {status: "ok", type: "building|interior", model_url: "...", params: {...}}
[ ] Фронтенд только отображает результат и управляет3D-сценой
[ ] Убрать из index.html: parseLocal(), applyParams(), TPLS, BUILD_RE, INTERIOR_RE
    - Всё это → shared/parser.py + shared/router.py
```

###3.2 Оркестратор задач

**Проблема**: Нет центрального оркестратора. Gateway просто проксирует запросы.

**План**:
```
[ ] Создать shared/orchestrator.py:
    - Принимает промт
    - Парсит (LLM → regex fallback)
    - Определяет pipeline: building | interior | floorplan | ifc
    - Разбивает на этапы: parse → generate_geometry → render → export
    - Каждый этап → соответствующий микросервис
    - Возвращает job_id + polling URL
[ ] Добавить WebSocket/SSE для real-time progress:
    - GET /api/v1/jobs/{id}/stream → SSE events
    - Events: {step: "parsing", progress: 10}, {step: "generating", progress: 50}, ...
```

###3.3 Обработка ошибок

**Проблема**: При недоступности микросервиса Gateway возвращает502 без fallback.

**План**:
```
[ ] Добавить circuit breaker pattern:
    - Если сервис недоступен3 раза подряд → пометить как "down" на60с
    - Автоматический fallback на локальную генерацию (shared/blender.py)
[ ] Добавить retry с exponential backoff ( уже есть request_with_retry, но max_retries=2 мало)
[ ] Логировать все ошибки в structured format (JSON logs)
```

---

## 4. Микросервисы: превращение заглушек в реальные

###4.1 geometry-service (556 строк — самый развитый)

**Текущее состояние**: Реализует Shapely + NetworkX анализ. Работает для floorplan SVG и graph analysis.

**План**:
```
[ ] Добавить генерацию3D геометрии (не только2D SVG):
    - Extrude floor plan →3D volume
    - Boolean operations для окон/дверей
    - Экспорт в GLB через trimesh
[ ] Добавить room detection из image (AI Vision → room boundaries → Shapely)
[ ] Интегрировать с gateway: POST /api/v1/floorplan/svg → реальный ответ
```

###4.2 ifc-service (381 строк)

**Текущее состояние**: IfcOpenShell генерация IFC. Endpoint'ы работают.

**План**:
```
[ ] Добавить IFC → GLB конвертацию (ifcopenshell → trimesh → GLB)
[ ] Добавить IFC validation (проверка на ошибки BIM)
[ ] Интегрировать с pipeline: промт → IFC → GLB → Three.js viewer
[ ] Добавить импорт IFC файлов (загрузка существующих BIM моделей)
```

###4.3 ml-service (486 строк)

**Текущее состояние**: Заглушки для classify-style, classify-room, pointcloud, analyze-image.

**План**:
```
[ ] Реализовать style classification:
    - Использовать предобученную модель (ResNet/EfficientNet на arch dataset)
    - Или: few-shot через LLM (classify по описанию)
[ ] Реализовать image analysis:
    - Florence-2 / BLIP-2 для captioning
    - DINO для object detection (стены, окна, двери)
[ ] Добавить generate-floorplan: ML-based room layout из текстового описания
```

###4.4 cad-service (622 строки)

**Текущее состояние**: OpenCascade (pythonocc-core) операции: primitive, boolean, fillet, export.

**План**:
```
[ ] Интегрировать с pipeline: параметры здания → CAD модель → STEP/IGES экспорт
[ ] Добавить точные размеры стен (не box approximation)
[ ] Добавить параметрические окна/двери (boolean cut)
[ ] Экспорт в STEP для инженерных расчётов
```

###4.5 freecad-service (266 строк)

**Текущее состояние**: FreeCAD automation через Python API.

**План**:
```
[ ] Реализовать parametric building modeling
[ ] Добавить экспорт в IFC через FreeCAD
[ ] Интегрировать с cad-service для boolean operations
```

###4.6 data-service (347 строки)

**Текущее состояние**: SQLite хранение проектов + templates. Работает.

**План**:
```
[ ] Добавить историю генераций (prompt → params → model_url → timestamp)
[ ] Добавить экспорт проекта (zip с GLB + IFC + SVG + metadata)
[ ] Добавить шаблоны (сохранённые параметры → быстрая генерация)
[ ] Добавить shared проекты (public URL для демонстрации)
```

###4.7 vectordb-service (190 строк) и graphdb-service (209 строк)

**Текущее состояние**: Обёртки над Qdrant и Neo4j. Базовые CRUD операции.

**План**:
```
[ ] vectordb: Добавить semantic search по промтам
    - Embedding промтов →相似 поиск → "похожие проекты"
[ ] graphdb: Добавить BIM knowledge graph
    - Связи: здание → этаж → помещение → элемент
    - Запросы: "найти все здания с гаражом", "смежные комнаты"
[ ] Интегрировать с data-service для полнотекстового + векторного поиска
```

---

## 5. ЛЛМ: обработка и уточнение запросов

###5.1 Двухуровневый парсинг

**Текущее состояние**: LLM парсинг (OpenRouter) → regex fallback. Работает.

**Проблема**: LLM может вернуть невалидный JSON, hallucinate параметры.

**План**:
```
[ ] Добавить валидацию ответа LLM через Pydantic:
    - LLM возвращает JSON → Pydantic model_validate → reject если невалидно
    - При невалидном ответе → retry с более строгим промтом → regex fallback
[ ] Добавить confidence score:
    - LLM возвращает {params: {...}, confidence: 0.95}
    - Если confidence <0.7 → задать уточняющие вопросы пользователю
[ ] Добавить multi-turn clarification:
    - "Вы хотели жилой дом или офис?" / "Какой этажности?"
    - Через ChatRequest → ChatResponse
```

###5.2 Уточняющий диалог

**Проблема**: Сейчас промт → immediate generation. Нет возможности уточнить.

**План**:
```
[ ] Добавить состояние диалога (conversation state machine):
    - STATE_IDLE →收到 промт → STATE_PARSING
    - STATE_PARSING → LLM парсит → если не хватает параметров → STATE_CLARIFYING
    - STATE_CLARIFYING → задаём вопросы → пользователь отвечает → STATE_GENERATING
    - STATE_GENERATING → генерация → STATE_DONE
[ ] Хранить состояние в sessionStorage (фронтенд) + Redis (бэкенд)
[ ] Добавить кнопку "Уточнить параметры" перед генерацией
```

###5.3 Модель LLM

**Текущее состояние**: `nvidia/nemotron-3-nano-30b-a3b:free` (бесплатная).

**План**:
```
[ ] Добавить fallback модель: если основная недоступна → переключиться
    - Primary: nvidia/nemotron-3-nano-30b-a3b:free
    - Fallback: meta-llama/llama-3.2-3b-instruct:free
    - Emergency: regex-only (без LLM)
[ ] Добавить кэширование ответов LLM:
    - Redis TTL=1 час для одинаковых промтов
    - Снижает latency и стоимость
```

---

## 6. Качество генерируемых моделей

###6.1 Текстуры

**Текущее состояние**: Процедурные canvas-текстуры (256-1024px). Brick, wood, glass, stone, roof tiles.

**План**:
```
[ ] Увеличить разрешение процедурных текстур до2048×2048
[ ] Добавить normal map генерацию (из height map)
[ ] Добавить PBR roughness/metallic maps ( не только color)
[ ] Опционально: загрузка текстур из Poly Haven (CC0,4K)
    - CDN fallback если offline
```

###6.2 Геометрия

**Текущее состояние**: Box-based (стены = кубы, окна = кубы). Нет скосов, фасонных элементов.

**План**:
```
[ ] Добавить скосы на фасадах (chamfer corners)
[ ] Добавить карнизы (extruded profile, не просто box)
[ ] Добавить водосточные трубы (cylinder + elbow)
[ ] Добавить лестничные марши (spiral staircase для >2 этажей)
[ ] Добавить мансардные окна (dormer windows)
[ ] Добавить эркеры (bay windows)
```

###6.3 Освещение

**Текущее состояние**: Sun + HemisphereLight + fill. HDRI через Poly Haven CDN.

**План**:
```
[ ] Добавить IES light profiles для интерьеров
[ ] Добавить ambient occlusion (SSAO post-processing)
[ ] Добавить time-of-day slider (утро → день → вечер → ночь)
[ ] Кэшировать HDRI в localStorage (avoid re-download)
```

###6.4 Рендер Blender

**Текущее состояние**: Blender EEVEE,4K (после фикса). bpy-скрипт с PBR материалами.

**План**:
```
[ ] Добавить Cycles рендер (более реалистичный, но медленнее):
    - EEVEE для preview (быстро)
    - Cycles для финального рендора (качество)
    - Переключатель на фронтенде
[ ] Добавить denoising (Intel OIDN / OptiX)
[ ] Добавить multi-camera рендер (экстерьер + интерьер + план)
[ ] Увеличить timeout для4K Cycles рендора (300с →600с)
```

---

## 7. Multi-agent декомпозиция

###7.1 Архитектура агентов

**Текущее состояние**: Нет multi-agent. Один pipeline: parse → generate → render.

**План**:
```
[ ] Создать shared/agents/ директорию:
    ├── __init__.py
    ├── base.py          # BaseAgent interface
    ├── parser_agent.py  # Парсинг промтов (LLM)
    ├── geometry_agent.py # Генерация геометрии (Blender/CAD)
    ├── texture_agent.py  # Генерация текстур (procedural/PBR)
    ├── render_agent.py   # Рендер (Blender EEVEE/Cycles)
    ├── export_agent.py   # Экспорт (GLB/IFC/STEP)
    └── orchestrator.py   # Оркестратор агентов

[ ] Каждый агент:
    - Принимает задачу (Task)
    - Возвращает результат (TaskResult)
    - Может декомпозировать на подзадачи
    - Логирует время выполнения и ошибки
```

###7.2 Декомпозиция задач

**Пример**: "Построй двухэтажный кирпичный дом10×12 с балконом"

```
Orchestrator.receive("Построй двухэтажный кирпичный дом10×12 с балконом")
├─ ParserAgent.parse(prompt)
│  └─ Result: {type: house, floors:2, W:10, L:12, material: brick, balcony: true}
│
├─ GeometryAgent.generate(params)
│  ├─ SubTask: generate_walls(W, L, floors, material)
│  ├─ SubTask: generate_windows(W, L, floors)
│  ├─ SubTask: generate_roof(W, L, roof_type)
│  ├─ SubTask: generate_balcony(W, L, floor=2)
│  └─ Result: geometry_data (vertices, faces, materials)
│
├─ TextureAgent.apply(geometry, material)
│  ├─ SubTask: generate_brick_texture(2048px)
│  ├─ SubTask: generate_glass_texture(512px)
│  └─ Result: textured_geometry
│
├─ RenderAgent.render(geometry, camera_params)
│  ├─ SubTask: render_exterior(camera=front)
│  ├─ SubTask: render_exterior(camera=side)
│  └─ Result: images[]
│
└─ ExportAgent.export(geometry, formats)
   ├─ SubTask: export_glb(geometry)
   ├─ SubTask: export_ifc(geometry)
   └─ Result: files[]
```

###7.3 Реализация

**План**:
```
[ ] shared/agents/base.py:
    - class Task: {id, type, params, parent_id, status, result}
    - class TaskResult: {status, data, error, duration_ms}
    - class BaseAgent(ABC): {name, process(task) → TaskResult}

[ ] shared/agents/orchestrator.py:
    - class Orchestrator:
        - receive(prompt) → job_id
        - decompose(task) → subtasks[]
        - dispatch(subtasks) → parallel execution
        - collect(results) → final result
        - on_error(task, error) → retry/fallback

[ ] shared/agents/parser_agent.py:
    - Использует shared/parser.py
    - Добавляет multi-turn clarification
    - Возвращает confidence score

[ ] shared/agents/geometry_agent.py:
    - Использует shared/blender.py для bpy-скриптов
    - Использует cad-service для точной геометрии
    - Параллельная генерация стен/крыши/балкона

[ ] shared/agents/texture_agent.py:
    - Процедурные текстуры (shared/blender.py)
    - PBR maps (normal, roughness, metallic)
    - Кэширование текстур

[ ] shared/agents/render_agent.py:
    - Blender EEVEE для preview
    - Blender Cycles для финального рендора
    - Multi-camera support

[ ] shared/agents/export_agent.py:
    - GLB (Three.js viewer)
    - IFC (BIM)
    - STEP (CAD)
    - SVG (floor plan)
```

---

## 8. Производительность

###8.1 Фронтенд

**План**:
```
[ ] Lazy load Three.js:
    - Загружать Three.js только при первом использовании
    - Показывать CSS skeleton пока грузится
[ ] Texture atlas:
    - Объединить мелкие текстуры в atlas (减少 draw calls)
[ ] InstancedMesh для повторяющихся объектов:
    - Fence posts, window panes, stairs — уже есть частично
    - Расширить на все повторяющиеся элементы
[ ] LOD (Level of Detail):
    - Далеко → low-poly, близко → high-poly
    - Уже есть LOD система для interior/exterior
    - Добавить3 уровня: far, mid, near
[ ] Web Worker для парсинга:
    - Перенести parseLocal() в Web Worker
    - Не блокировать UI thread
```

###8.2 Бэкенд

**План**:
```
[ ] Кэширование bpy-скриптов:
    - Redis: hash(params) → script
    - TTL=24 часа (одинаковые параметры → одинаковый скрипт)
[ ] Connection pooling для httpx:
    - Переиспользовать HTTP соединения между сервисами
[ ] Async Blender execution:
    - Не блокировать event loop Blender subprocess
    - Использовать asyncio.create_subprocess_exec
[ ] Celery оптимизации:
    - worker_concurrency=4 (сейчас2)
    - task_routes: building → fast queue, render → slow queue
[ ] GPU рендер в Blender:
    - Если доступен GPU → Cycles GPU (в10× быстрее CPU)
    - Detect GPU: bpy.context.preferences.addons['cycles'].preferences.compute_device_type
```

---

## 9. Тесты

###9.1 Текущее состояние

| Файл | Тестов | Статус |
|------|--------|--------|
| test_generation.py |60 | ✅ Все проходят |
| test_server.py |12 | ✅ Все проходят |
| test_gateway.py |7 | ✅ Все проходят |
| test_chat.js |11 | ⚠️ Node.js тесты (не запускались в CI) |

###9.2 План расширения

```
[ ] test_parser.py — расширенные тесты парсера:
    -50+ промтов на русском языке
    - Edge cases: смешанный регистр, опечатки, аббревиатуры
    - LLM mock тесты (мокаем OpenRouter ответ)
    - Timeout handling
    - Rate limiting (429 ответ)

[ ] test_blender.py — тесты генерации bpy-скриптов:
    - Компиляция скрипта (compile())
    - Валидный Python синтаксис
    - Нет hardcoded значений (всё через параметры)
    - Материалы существуют в скрипте
    - Окна/двери корректно позиционированы

[ ] test_orchestrator.py — тесты оркестратора:
    - Декомпозиция промта на подзадачи
    - Параллельное выполнение
    - Error handling (один агент упал → fallback)
    - Timeout (задача >300с → cancel)

[ ] test_microservices.py — интеграционные тесты:
    - Каждый сервис: health endpoint
    - Gateway → LLM → response
    - Gateway → Blender → GLB file
    - Gateway → IFC → IFC file
    - Gateway → Geometry → SVG

[ ] test_performance.py — нагрузочные тесты:
    - Парсинг:100 промтов за <10с
    - Генерация bpy: <1с на скрипт
    - Gateway latency: <200ms (без Blender)

[ ] test_chat.js — расширить:
    - Добавить тесты для всех view modes (plan, section, facade)
    - Тест settings persistence
    - Тест file upload → generation
    - Тест error recovery
```

###9.3 CI/CD

```
[ ] Обновить .github/workflows/ci.yml:
    - Запускать ВСЕ тесты (не только test_server.py)
    - Добавить OUTPUT_DIR env для тестов
    - Добавить coverage report (pytest-cov)
    - Добавить Node.js тесты (test_chat.js)
    - Добавить интеграционные тесты с Docker Compose
```

---

## 10. Дедупликация фронтендов

###10.1 Проблема

3 файла с почти одинаковым содержимым:
```
index.html              (2915 строк) — root, используется server.py
frontend/index.html     (2915 строк) — копия root, используется gateway/Dockerfile
gateway/frontend/index.html (2623 строки) — другая версия, используется gateway app.py
```

###10.2 Решение

```
[ ] Оставить ОДИН файл: frontend/index.html
[ ] index.html (root) → symlink на frontend/index.html
[ ] gateway/frontend/index.html → удалить
[ ] gateway/app.py: FRONTEND_DIR → /app/frontend (Docker) или ./frontend (local)
[ ] server.py: FRONTEND_DIR → ./frontend
[ ] API_BASE сделать конфигурируемым:
    - <meta name="archai-api-base" content="https://...">
    - Или: window.ARCHAI_API_BASE = "..."
    - Фронтенд читает из meta/env, не хардкодит URL
```

---

## 11. DevOps

###11.1 Docker Compose

**Проблема**: docker-compose.yml содержит только gateway, llm-service, blender-service, redis.

**План**:
```
[ ] Добавить все сервисы в docker-compose.yml:
    - geometry-service (порт8083)
    - ifc-service (порт8084)
    - ml-service (порт8085)
    - data-service (порт8086)
    - cad-service (порт8087)
    - freecad-service (порт8088)
    - vectordb-service (порт8089)
    - graphdb-service (порт8090)
    - qdrant (порт6333)
    - neo4j (порт7474)
[ ] Добавить health checks для всех сервисов
[ ] Добавить depends_on с condition: service_healthy
[ ] Добавить volumes для output и data
```

###11.2 Render deploy

```
[ ] Обновить render.yaml:
    - Добавить missing env vars
    - Добавить health check paths
    - Добавить auto-deploy ветки main
[ ] Добавить staging environment
```

###11.3 Мониторинг

```
[ ] Добавить /api/v1/metrics endpoint:
    - Количество генераций (total, success, error)
    - Среднее время генерации
    - Очередь Celery (pending, active, failed)
    - Использование памяти/CPU
[ ] Добавить structured logging (JSON format)
[ ] Добавить error tracking (Sentry или аналог)
```

---

## 12. Приоритеты и порядок реализации

### Фаза1: Критические фиксы (1-2 дня) — ✅ ЧАСТИЧНО ВЫПОЛНЕНО

| # | Задача | Статус |
|---|--------|--------|
|1.1| Fix gateway script tags | ✅ Done |
|1.2| Fix render resolution4K | ✅ Done |
|1.3| Fix test imports | ✅ Done |
|1.4| Sync gateway frontend с root | 🔲 TODO |
|1.5| Удалить дублированный frontend | 🔲 TODO |
|1.6| Добавить initThree() retry | 🔲 TODO |

### Фаза2: Pipeline & Orchestration (3-5 дней)

| # | Задача | Приоритет |
|---|--------|-----------|
|2.1| Перенести логику парсинга на бэкенд | 🔴 Высокий |
|2.2| Создать shared/agents/orchestrator.py | 🔴 Высокий |
|2.3| Добавить SSE progress streaming | 🔴 Высокий |
|2.4| Multi-turn clarification | 🟡 Средний |
|2.5| Circuit breaker для микросервисов | 🟡 Средний |

### Фаза3: Микросервисы (5-7 дней)

| # | Задача | Приоритет |
|---|--------|-----------|
|3.1| geometry-service:3D генерация | 🔴 Высокий |
|3.2| ifc-service: IFC→GLB конвертация | 🟡 Средний |
|3.3| data-service: история генераций | 🟡 Средний |
|3.4| ml-service: style classification | 🟢 Низкий |
|3.5| cad-service: интеграция с pipeline | 🟢 Низкий |
|3.6| vectordb/graphdb: semantic search | 🟢 Низкий |

### Фаза4: Качество моделей (3-5 дней)

| # | Задача | Приоритет |
|---|--------|-----------|
|4.1| PBR текстуры2048px + normal maps | 🔴 Высокий |
|4.2| Детализированная геометрия (эркеры, мансарды) | 🟡 Средний |
|4.3| Cycles рендер с denoising | 🟡 Средний |
|4.4| HDRI кэширование | 🟢 Низкий |

### Фаза5: Multi-agent (5-7 дней)

| # | Задача | Приоритет |
|---|--------|-----------|
|5.1| shared/agents/ архитектура | 🔴 Высокий |
|5.2| Декомпозиция задач | 🔴 Высокий |
|5.3| Параллельное выполнение | 🟡 Средний |
|5.4| Error recovery & fallback | 🟡 Средний |

### Фаза6: Тесты & DevOps (3-5 дней)

| # | Задача | Приоритет |
|---|--------|-----------|
|6.1| Расширить тесты до200+ | 🔴 Высокий |
|6.2| Интеграционные тесты с Docker | 🟡 Средний |
|6.3| Performance тесты | 🟡 Средний |
|6.4| Обновить CI/CD pipeline | 🟡 Средний |
|6.5| Docker Compose все сервисы | 🟢 Низкий |
|6.6| Мониторинг & метрики | 🟢 Низкий |

---

## Оценка общего объёма

| Фаза | Дни | Сложность |
|------|-----|-----------|
| Фаза1: Критические фиксы |1-2 | Низкая |
| Фаза2: Pipeline |3-5 | Средняя |
| Фаза3: Микросервисы |5-7 | Высокая |
| Фаза4: Качество моделей |3-5 | Средняя |
| Фаза5: Multi-agent |5-7 | Высокая |
| Фаза6: Тесты & DevOps |3-5 | Средняя |
| **Итого** | **20-31 день** | |

---

## Технический стек (текущий и целевой)

| Компонент | Текущий | Целевой |
|-----------|---------|---------|
| Frontend | Vanilla JS + Three.js | Vanilla JS + Three.js (без фреймворков) |
| Backend | FastAPI + shared package | FastAPI + shared + agents |
| LLM | OpenRouter (free model) | OpenRouter + fallback models |
|3D Engine | Three.js (browser) + Blender CLI | Three.js + Blender EEVEE/Cycles |
| Task Queue | Celery + Redis | Celery + Redis + priority queues |
| Storage | File system + SQLite | SQLite + Redis cache |
| BIM | IfcOpenShell | IfcOpenShell + FreeCAD |
| CAD | pythonocc-core (OpenCascade) | OpenCascade + trimesh |
| Search | — | Qdrant (vector) + Neo4j (graph) |
| Tests | pytest + Node.js | pytest + Jest + Docker integration |
| Deploy | Render + Docker | Render + Docker + staging |
