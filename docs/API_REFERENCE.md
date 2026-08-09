# API Reference — AI_Arhitector v11.0.0

> Полный API Gateway. Все запросы через `/api/v1/...`.
> Авторизация: `X-API-Key` header (если `ARCH_API_KEYS` настроен).

---

## Health & Status

### `GET /health` / `GET /api/v1/health`

```json
{
  "status": "ok",
  "service": "gateway",
  "version": "8.2.0",
  "services": {"llm": "configured", "blender": "configured"},
  "blender_instances": 3,
  "circuit_breakers": {}
}
```

### `GET /api/v1/stats`

Статистика кеша, стоимости, circuit breakers.

```json
{
  "cache": {"l1_entries": 42, "redis_connected": true},
  "cost": {"total_calls": 150, "total_cost_usd": 0.0},
  "circuit_breakers": {"llm": {"failures": 0, "is_open": false}}
}
```

---

## LLM Parsing

### `POST /api/v1/parse`

Парсинг архитектурного промта → структурированные параметры.

**Request:**
```json
{"text": "Построй двухэтажный коттедж 12x10 из кирпича с двускатной крышей"}
```

**Response:**
```json
{
  "object_type": "building",
  "building_type": "cottage",
  "building_description": "Двухэтажный коттедж из кирпича",
  "floors": 2,
  "width_m": 12,
  "length_m": 10,
  "height_m": 3.0,
  "style": "modern",
  "material": "brick",
  "roof_type": "gabled",
  "features": [],
  "furniture": [],
  "confidence": 0.85,
  "reasoning": "Пользователь чётко указал тип, этажность, размеры и материалы",
  "suggestions": ["Добавить гараж", "Выбрать планировку комнат", "Добавить террасу"],
  "references": ["кирпичный коттедж двухэтажный", "современный коттедж"],
  "decomposition": [{"name": "Фундамент", "description": "Ленточный"}, {"name": "Коробка", "description": "Кирпич 2 этажа"}],
  "pipeline_profile": "full"
}
```

**Errors:**
- `503` — все LLM модели недоступны
- `400` — пустой промт

---

## Orchestrator (Full Pipeline)

### `POST /api/v1/orchestrator/execute`

Полный цикл генерации: парсинг → уточнение → агенты → рендер → экспорт.

**Request:**
```json
{
  "prompt": "Современный минималистичный интерьер ванной комнаты 3x4 с джакузи",
  "quality": "standard",
  "pipeline_profile": "interior",
  "skip_clarification": false,
  "export_formats": ["glb"],
  "session_id": "user123"
}
```

**Response (success):**
```json
{
  "job_id": "a1b2c3d4",
  "session_id": "user123",
  "status": "done",
  "gen_type": "interior",
  "quality": "standard",
  "pipeline_profile": "interior",
  "params": {"width_m": 3, "length_m": 4, "room_type": "bathroom", "style": "minimalist"},
  "render": {"image_path": "/app/output/a1b2c3d4_render.png"},
  "exports": {"glb_path": "/app/output/a1b2c3d4.glb"},
  "confidence": 0.9,
  "duration_ms": 45000,
  "steps": [
    {"name": "parse", "status": "done"},
    {"name": "geometry", "status": "done"},
    {"name": "texture", "status": "done"},
    {"name": "render", "status": "done"},
    {"name": "quality", "status": "done"},
    {"name": "export", "status": "done"}
  ],
  "agent_results": {"concept": {...}, "style": {...}, "furniture": {...}}
}
```

**Response (clarification needed):**
```json
{
  "job_id": "e5f6g7h8",
  "status": "clarification_needed",
  "clarification": {
    "questions": [
      {
        "field": "material",
        "text": "Из какого материала фасад?",
        "options": ["Кирпич", "Дерево", "Камень", "Штукатурка"],
        "visual_options": [
          {
            "id": "A",
            "title": "Кирпич",
            "description": "Классический материал",
            "pros": ["Прочность", "Долговечность"],
            "cons": ["Дорого", "Долго строить"],
            "recommended": false,
            "price_range": "4500 ₽/м²"
          }
        ],
        "priority": 1
      }
    ],
    "partial_params": {"object_type": "building", "floors": 2},
    "confidence": 0.4
  }
}
```

### `POST /api/v1/orchestrator/resume`

Продолжение после clarification.

**Request:**
```json
{
  "job_id": "e5f6g7h8",
  "answers": {"material": "Кирпич", "roof_type": "Двускатная"},
  "quality": "standard",
  "pipeline_profile": "standard",
  "export_formats": ["glb"]
}
```

**Response:** Same as orchestrator/execute success response.

### `GET /api/v1/orchestrator/jobs/{job_id}`

Получить статус задачи.

### `GET /api/v1/orchestrator/jobs/{job_id}/stream`

SSE stream событий генерации в реальном времени.

### `GET /api/v1/orchestrator/agents`

Список доступных агентов.

---

## Clarification

### `POST /api/v1/clarify`

Анализ промта → уточняющие вопросы.

**Request:** `{"prompt": "Построй дом"}`

**Response:**
```json
{
  "needs_clarification": true,
  "questions": [
    {"field": "floors", "text": "Сколько этажей?", "options": ["1", "2", "3"], "priority": 1},
    {"field": "material", "text": "Из какого материала?", "options": ["Кирпич", "Дерево"], "priority": 2}
  ],
  "confidence": 0.3,
  "partial_params": {"object_type": "building", "building_type": "house"}
}
```

### `POST /api/v1/clarify/answer`

**Request:** `{"params": {...}, "answers": {"floors": "2", "material": "Кирпич"}}`

---

## PDF/DWG Analysis (NEW in v11.0.0)

### `POST /api/v1/analyze/pdf`

Анализ PDF чертежа/проекта.

**Request:** `multipart/form-data` с файлом

**Response:**
```json
{
  "status": "ok",
  "filename": "project.pdf",
  "pages_analyzed": 5,
  "rooms": [
    {"name": "Гостиная", "area_m2": 25.0, "dimensions": "5x5"},
    {"name": "Кухня", "area_m2": 12.0, "dimensions": "4x3"}
  ],
  "dimensions": {"total_area_m2": 120.0, "floors": 2},
  "systems": {
    "ventilation": {"type": "Приточно-вытяжная", "ducts": 3},
    "heating": {"type": "Автономная котельная", "radiators": 8},
    "water_supply": {"type": "Центральное"},
    "sewage": {"type": "Центральное"}
  },
  "materials": {"walls": "Кирпич", "floor": "Бетон", "roof": "Металлочерепица"},
  "specifications": ["СП 54.13330", "ГОСТ 21.501"],
  "raw_text": "..."
}
```

### `POST /api/v1/analyze/dwg`

Анализ DWG/DXF файлов.

**Request:** `multipart/form-data` с файлом

**Response:**
```json
{
  "status": "ok",
  "filename": "plan.dxf",
  "layers": ["WALLS", "DOORS", "WINDOWS", "FURNITURE", "DIMENSIONS"],
  "blocks": 45,
  "dimensions_count": 23,
  "rooms": [...],
  "elements": {"walls": 12, "doors": 6, "windows": 8}
}
```

---

## 3D Generation (Direct)

### `POST /api/v1/generate`

Генерация 3D модели (без orchestrator).

**Request:** `{"prompt": "...", "quality": "16k"}`

**Response:** Binary GLB file или PNG render.

### `POST /api/v1/preview`

Быстрое превью (1920x1080).

### `POST /api/v1/render/16k`

16K tiled render.

**Request:**
```json
{
  "prompt": "Современный дом 2 этажа",
  "tiles_x": 4,
  "tiles_y": 3,
  "samples": 2048
}
```

---

## Compliance & Analysis

### `POST /api/v1/compliance/check`

Проверка нормативов (без генерации).

**Request:** `{"params": {...}}` или `{"prompt": "..."}`

**Response:**
```json
{
  "compliance": {"passed": true, "issues": []},
  "applicable_norms": ["СП 54.13330", "СП 1.13130", "ГОСТ 21.501"],
  "structural": {
    "load_combinations": {...},
    "foundation": {"bearing_capacity_kPa": 250}
  }
}
```

### `POST /api/v1/variants`

Генерация вариантов дизайна.

---

## Session Context (Multi-turn Dialog)

### `GET /api/v1/context/{session_id}`

Получить контекст проекта.

### `GET /api/v1/context`

Список последних сессий.

### `DELETE /api/v1/context/{session_id}`

Удалить сессию.

---

## Kaggle GPU Renderer

### `POST /api/v1/kaggle/enqueue`

Добавить задачу рендеринга в очередь Kaggle.

### `GET /api/v1/kaggle/poll`

Kaggle notebook опрашивает для получения задачи.

### `POST /api/v1/kaggle/result`

Kaggle notebook отправляет результат.

### `GET /api/v1/kaggle/status/{task_id}`

Статус задачи Kaggle.

### `GET /api/v1/kaggle/health`

Состояние интеграции Kaggle.

---

## Error Codes

| Код | Описание |
|-----|----------|
| 200 | OK |
| 400 | Неверный запрос (пустой prompt, отсутствует файл) |
| 401 | Не авторизован (нет API key) |
| 404 | Ресурс не найден (job, session) |
| 429 | Rate limit превышен |
| 500 | Внутренняя ошибка сервера |
| 502 | Сервис недоступен (Blender/LLM) |
| 503 | Все LLM модели недоступны |
| 504 | Таймаут (Blender render > 300s) |

---

## Authentication

Если `ARCH_API_KEYS` настроен — все запросы требуют `X-API-Key` header:

```bash
curl -H "X-API-Key: your-key" https://api.archai.app/api/v1/parse ...
```

## Rate Limiting

- По умолчанию: 60 запросов/минуту на API key
- При превышении: HTTP 429
- Circuit breaker: 5 неудач → сервис отключается на 60 секунд
