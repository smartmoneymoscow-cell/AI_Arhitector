# Wiki — Architect AI v13.5.0

## 🏗 Архитектура системы

```
┌─────────────────────────────────────────────────────────────────┐
│                    Пользователь (браузер)                        │
│                    Frontend (Three.js 3D)                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx (routing, SSL)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Gateway (:8080) — architect-gateway                 │
│  ├── FastAPI Backend (routing, circuit breaker)                  │
│  ├── Оркестратор пайплайна (20+ агентов)                        │
│  ├── Load Balancer (Blender instances, round-robin)              │
│  ├── Redis Jobs Store (in-memory fallback)                       │
│  └── Kaggle Polling Queue (GPU rendering)                       │
└────┬──────────────┬──────────────┬──────────────────────────────┘
     │              │              │
     ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────────────┐
│ Agent    │  │ LLM      │  │ Blender          │
│ Pool     │  │ Service  │  │ Service          │
│ :8083    │  │ :8081    │  │ :8082 / Kaggle   │
│          │  │          │  │                  │
│ 30+      │  │ Каскад:  │  │ Cycles GPU       │
│ агентов  │  │ Groq →   │  │ T4/P100          │
│ изолир.  │  │ Gemini → │  │ bpy-скрипты      │
│ threads  │  │ DeepSeek │  │ tiled render     │
│          │  │ → OpenR  │  │ до 16K           │
└──────────┘  └──────────┘  └──────────────────┘
     │              │
     ▼              ▼
┌──────────┐  ┌──────────┐
│ Redis    │  │ Google   │
│ :6379    │  │ Gemini   │
│ state    │  │ API      │
└──────────┘  └──────────┘
```

## 🔄 LLM Каскад (полный)

```
1. Groq (free tier, ~300 tok/s, qwen/qwen3-32b)
   ↓ если все ключи исчерпаны
2. Google Gemini API (8 ключей, round-robin, gemini-2.5-flash-lite)
   ↓ если все 8 исчерпаны
3. DeepSeek (прямой API, deepseek-chat)
   ↓ если все ключи исчерпаны
4. OpenRouter Free Models (auto-discovery, 15+ моделей)
   ↓ если все модели/ключи недоступны
5. Ollama (локальный, если настроен)
   ↓ если не настроен
6. 503 All providers failed
```

## 🤖 Агенты (30+)

### Pipeline агенты (7)
| Агент | Описание | Критичность |
|-------|----------|-------------|
| Parser | LLM парсинг промтов | КРИТИЧЕСКИЙ |
| Geometry | Генерация 3D геометрии (bpy) | КРИТИЧЕСКИЙ |
| Texture | PBR материалы и текстуры | Не критичный |
| Render | Рендер через Blender Cycles | Не критичный |
| Export | Экспорт GLB/FBX/OBJ | Не критичный |
| Quality | Проверка качества (4K+) | Не критичный |
| Compliance | Проверка нормативов | Не критичный |

### Интеллектуальные агенты (9)
| Агент | Описание |
|-------|----------|
| Dialog | Многотurnовый контекст |
| Research | Исследование референсов |
| Market | Анализ рынка |
| Concept | Концептуальный дизайн |
| Masterplan | Генеральный план |
| Landscape | Ландшафтный дизайн |
| Brand | Брендинг |
| Financial | Финансовый анализ |
| Presentation | Презентация |

### Специализированные агенты (6)
| Агент | Описание |
|-------|----------|
| Style | Стилистический анализ |
| Lighting | Настройка освещения |
| Furniture | Расстановка мебели |
| MEP | Инженерные системы |
| Structural | Структурный анализ |
| EL | Электрика |

## 🎨 Pipeline профили

| Профиль | Агенты | Использование |
|---------|--------|---------------|
| quick | parser→geometry→texture→render→quality→export | Быстрая генерация |
| standard | parser→style→geometry→texture→lighting→structural→compliance→render→quality→export | Стандартный |
| interior | parser→concept→style→furniture→lighting→texture→render→quality→export | Интерьеры |
| landscape | parser→research→landscape→masterplan→compliance→export | Ландшафт |
| full | Все 14 агентов | Полный цикл |
| premium | Все 20 агентов | Премиум |

## 🖥 Frontend

### Интерфейс
- **Чат-панель** (400px) — ввод промтов, история чата
- **3D Viewer** (flex) — Three.js, GLB/GLTF загрузка
- **Projects sidebar** (260px) — закрыт по умолчанию (v13.5.0)
- **Top bar** — аккаунт, настройки, экспорт

### 3D Viewer
- Three.js r147 с GLTFLoader и OrbitControls
- Автоматическое центрирование камеры
- Поддержка GLB/GLTF форматов
- Тональная компрессия (ACES Filmic)

### Экспорт форматов
- GLB/GLTF — 3D модель (Unity, Web)
- FBX — Unreal, Maya, 3ds Max
- OBJ + MTL — универсальный формат
- PNG 16K — рендер 15360×8640 px
- PDF — архитектурные чертежи
- IFC — BIM модель

## 🔧 API Endpoints

### Gateway
| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Статус сервиса |
| `/api/v1/parse` | POST | LLM парсинг промта |
| `/api/v1/generate` | POST | Генерация 3D модели |
| `/api/v1/generate/fast` | POST | Быстрая генерация (trimesh) |
| `/api/v1/orchestrator/execute` | POST | Полный pipeline |
| `/api/v1/orchestrator/resume` | POST | Продолжение после уточнений |
| `/api/v1/preview` | POST | Быстрое превью |
| `/api/v1/chat` | POST | Чат с LLM |
| `/api/v1/files/{path}` | GET | Файлы output |

### LLM Service
| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Статус + количество ключей |
| `/api/v1/parse` | POST | Парсинг промта |
| `/api/v1/chat/completions` | POST | Чат |
| `/api/v1/keys/status` | GET | Статус ключей |

### Blender Service
| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Статус сервиса |
| `/api/v1/generate` | POST | Генерация GLB |
| `/api/v1/generate/fast` | POST | Быстрая генерация (trimesh) |
| `/api/v1/preview` | POST | PNG превью |

## 🧪 Тестирование (v13.5.0)

### Протестированные промты

| # | Промт | object_type | Результат |
|---|-------|-------------|-----------|
| 1 | "коттедж 2 этажа 12x15 дерево" | building | ✅ Парсинг корректен |
| 2 | "ванная комната с джакузи мрамор хайтек" | interior | ✅ Определен как интерьер |
| 3 | "офис 5 этажей стекло 20x24" | building | ✅ Все параметры верны |
| 4 | "ландшафтный дизайн сад с прудом" | landscape | ✅ Корректно определен |
| 5 | "кухня минимализм с островом" | interior | ✅ room_type=kitchen |

### Статус сервисов

| Сервис | URL | Статус |
|--------|-----|--------|
| Gateway | architect-gateway-3guo.onrender.com | ✅ OK (v13.5.0) |
| LLM #1 | architect-llm-5mdk.onrender.com | ✅ OK (v13.2.0) |
| LLM #2 | architect-llm-s5q7.onrender.com | ✅ OK (v13.2.0) |
| LLM #3 | architect-llm-zczl.onrender.com | ✅ OK (v13.2.0) |
| Blender | ai-arch-blender3d.onrender.com | ✅ OK (v13.4.0) |

## 📦 Деплой

### GitHub Pages (Frontend)
- Автоматический деплой при push в main
- URL: https://smartmoneymoscow-cell.github.io/AI_Arhitector/

### Render (Backend)
- Gateway: architect-gateway.onrender.com
- LLM: architect-llm-{N}.onrender.com (8 instances)
- Blender: ai-arch-blender3d.onrender.com

### Kaggle (GPU Rendering)
- Kernel: hungerrrr2222/archai-blender-gpu-renderer
- GPU: T4/P100
- Internet: enabled
