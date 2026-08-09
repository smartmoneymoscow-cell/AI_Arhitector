# AI_Arhitector — ROADMAP

> Обновлено: 2026-08-09 (v11.0.0)

---

## Phase 1 — Foundation ✅ DONE

### 1.1 Устранение дублирования
- [x] Удалить `promt_parser.py` (дубликат `shared/parser.py`)
- [x] Обновить все импорты на `shared.parser`
- [ ] Синхронизировать `gateway/frontend/index.html` с `index.html`
- [ ] Удалить `frontend/index.html` (избыточная копия)

### 1.2 Безопасность
- [x] Добавить `shared/auth.py` — API key auth + rate limiting
- [x] Исправить CORS: конфигурируемые origins через `CORS_ORIGINS` env
- [ ] Добавить Bearer token auth для OpenRouter (не логировать API key)

### 1.3 Парсер
- [x] LRU-кеширование результатов (TTL 5 мин, max 500 записей)
- [x] Retry chain: primary model → fallback models → regex
- [x] Расширенный набор стилей (16 vs 6)
- [x] Расширенный набор материалов (15 vs 6)
- [x] Расширенный набор features (10 vs 3)
- [x] Поддержка confidence и ambiguities в LLM-ответе
- [x] LLM-определение pipeline_profile в ответе парсера (v11.0.0)

### 1.4 Docker
- [x] Разделить Dockerfile на per-service
- [x] Multi-stage build для gateway и llm
- [x] Обновить `docker-compose.yml` для per-service Dockerfiles
- [x] Добавить memory limits per-service

### 1.5 Качество
- [x] Добавить `QualityAgent` в orchestrator pipeline
- [x] Автоматическая проверка разрешения после рендера
- [x] Проверка file size (sanity check)
- [x] Опциональный AI-анализ через mimo-omni

---

## Phase 2 — Quality ✅ DONE (v11.0.0)

### 2.1 Геометрия
- [x] Окна со стеклом (Transmission 0.9, IOR 1.52) + рамы + подоконники
- [x] Двери с коробкой и ручками
- [x] Плинтусы и карнизы (baseboard + crown molding)
- [ ] Parametric wall generation (не box, а real wall with openings)
- [ ] Boolean operations для окон/дверей (CSG)
- [ ] UV mapping для текстур
- [ ] Asset library: 100+ типов мебели (low-poly GLB)

### 2.2 Текстуры
- [x] PBR материалы с правильными параметрами (roughness, metallic)
- [x] Материал пола по стилю интерьера
- [ ] Image-based PBR текстуры (Poliigon/ambientCG)
- [ ] UV unwrap автоматический
- [ ] Texture atlas для оптимизации

### 2.3 Освещение
- [x] HDRI world — процедурный небесный купол (Nishita sky)
- [x] Contact shadows (GTAO/SSAO)
- [x] Встроенные потолочные светильники (recessed lights)
- [ ] Время суток (утро/день/вечер/ночь)
- [ ] IES profiles для светильников

### 2.4 Окружение
- [ ] Landscape generation (деревья, кусты, газон)
- [ ] Road/path generation
- [ ] Sky dome / HDRI background

### 2.5 Рендеринг
- [x] Tiled rendering для 16K (разбить на тайлы)
- [x] Kaggle GPU auto-submit (T4 GPU)
- [x] Quality gate retry: 4096 samples при неудаче 16K
- [ ] GPU support в Docker (nvidia-docker)

---

## Phase 3 — Intelligence (3-4 месяца)

### 3.1 Reference Search
- [ ] CLIP/SigLIP embedding для архитектурных изображений
- [ ] Vector DB (Qdrant) индексация референсов
- [ ] RAG pipeline: промт → embedding → nearest refs → context

### 3.2 Style Transfer
- [ ] Определение стиля из референсного изображения
- [ ] Применение стиля к генерируемой модели

### 3.3 Multi-turn Dialog
- [x] Контекст предыдущих запросов (dialog agent)
- [x] Итеративная модификация ("добавь балкон", "измени стиль")
- [x] LLM-генерация уточняющих вопросов (v11.0.0)

### 3.4 Quality Loop
- [ ] Self-improving: рендер → анализ → исправление → рендер
- [ ] Автоматическое исправление обнаруженных багов

### 3.5 Новые агенты
- [x] StyleAgent — определение стиля из промта + референсов
- [x] LightingAgent — настройка освещения под стиль
- [x] FurnitureAgent — эргономичное размещение мебели
- [x] LandscapeAgent — генерация окружения
- [x] PDF Analysis Agent — парсинг PDF чертежей (v11.0.0)
- [x] DWG/DXF Analysis Agent — парсинг CAD файлов (v11.0.0)

---

## Phase 4 — BIM & Compliance (4-6 месяцев)

### 4.1 IFC Enhancement
- [ ] Инженерные параметры (U-value, fire rating)
- [ ] Конструктивная система (несущие стены, перекрытия)
- [ ] Quantity takeoff (смета материалов)

### 4.2 Building Codes
- [ ] СП 1.13130 (эвакуационные пути)
- [ ] СП 54.13330 (жилые здания)
- [ ] ГОСТ 21.501 (чертежи)
- [ ] IBC (международные)

### 4.3 CAD Integration
- [x] DXF парсинг через ezdxf (v11.0.0)
- [ ] STEP/IGES экспорт через OpenCASCADE
- [ ] Интеграция с Revit/ArchiCAD (IFC round-trip)

---

## Phase 5 — Market Ready (6-9 месяцев)

### 5.1 Real-time
- [ ] WebGPU preview в браузере
- [ ] Blender EEVEE Next в реальном времени

### 5.2 Collaboration
- [ ] Multi-user editing
- [ ] Shared projects (public URL)
- [ ] Comments/annotations на 3D модели

### 5.3 Mobile
- [ ] React Native + expo-three
- [ ] Touch-optimized 3D viewer

### 5.4 Marketplace
- [ ] Шаблоны зданий
- [ ] Каталог стилей
- [ ] Пользовательские asset packs

### 5.5 API & SDK
- [ ] REST API документация (OpenAPI)
- [ ] Python SDK
- [ ] Webhook для async результатов
