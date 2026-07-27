# Architect v10.2 🏗️

AI-архитектор — генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Статус проекта

> ⚠️ **Текущее состояние:** Генерация по произвольным промтам не работает. Ведётся исправление.  
> Детальный план: [`AI_Arhitector_fix_plan.md`](./AI_Arhitector_fix_plan.md)

### Известные проблемы

| # | Проблема | Импакт |
|---|----------|--------|
| 1 | Regex-парсер не понимает естественный язык | "сделай дизайн коттеджа" → дефолты |
| 2 | Нет маршрутизации building/interior | "детская комната" → генерирует здание вместо интерьера |
| 3 | LLM не используется для парсинга промтов | AI есть, но не помогает генерации |
| 4 | bpy-скрипт генерирует неинициализированные переменные | "Cannot access uninitialized variable" |
| 5 | GitHub Pages не имеет fallback на Three.js | "Сервер рендеринга недоступен" |
| 6 | Тесты проверяют Blender CLI, а не pipeline | Зелёные тесты при сломанной генерации |
| 7 | Render Free Tier cold start без retry | Первый запрос таймаутит 30-60 сек |

---

## Быстрый старт

### Онлайн (GitHub Pages)

1. Откройте сайт
2. Нажмите ⚙️ Настройки → введите OpenRouter API ключ от [openrouter.ai/keys](https://openrouter.ai/keys)
3. Опишите здание или интерьер

> ⚠️ На GitHub Pages работает только Three.js рендер (без Blender). Для полного функционала нужен бэкенд.

### Локальный сервер (полный функционал)

```bash
# Установить зависимости
pip install flask flask-cors httpx

# Установить Blender (Ubuntu/Debian)
sudo apt install blender

# Запустить
export OPENROUTER_API_KEY="sk-or-v1-..."
python server.py
# → http://localhost:8080
```

#### С портативным Blender (без sudo)

```bash
# Скачать Blender 3.6 LTS
curl -L -o blender.tar.xz "https://download.blender.org/release/Blender3.6/blender-3.6.5-linux-x64.tar.xz"
tar xf blender.tar.xz

# Запустить
export BLENDER_PATH="$PWD/blender-3.6.5-linux-x64/blender"
export LD_LIBRARY_PATH="$PWD/blender-3.6.5-linux-x64/lib:$LD_LIBRARY_PATH"
export OPENROUTER_API_KEY="sk-or-v1-..."
python server.py
```

### Docker Compose

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
docker-compose up --build
# → http://localhost:8080
```

### Render.com (деплой)

1. Зайдите на [render.com](https://render.com) → New → Blueprint
2. Подключите репозиторий
3. Render автоматически создаст 3 сервиса из `render.yaml`
4. В сервисе `architect-llm` добавьте `OPENROUTER_API_KEY`
5. Нажмите Apply (~5-10 мин)

---

## Архитектура

### Микросервисы

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (index.html)                     │
│        Chat UI │ 3D View (Three.js) │ 2D Plan               │
└────────────────────────┬────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │ Gateway │  :8080
                    │         │  Маршрутизация + статика
                    └────┬────┘
                         │
              ┌──────────┴──────────┐
              │                     │
        ┌─────▼─────┐        ┌─────▼──────┐
        │ LLM Proxy │        │  Blender   │
        │   :8081   │        │  Service   │
        │           │        │   :8082    │
        │ OpenRouter │        │            │
        └───────────┘        │  ┌────────┐│
                             │  │Blender ││
                             │  │  CLI   ││
                             │  └────────┘│
                             └────────────┘
```

### Эндпоинты

| Endpoint | Сервис | Описание |
|----------|--------|----------|
| `GET /` | Gateway | Фронтенд |
| `GET /api/v1/health` | Gateway | Health check (LLM + Blender) |
| `POST /api/v1/proxy/claude` | Gateway → LLM | Прокси к OpenRouter |
| `POST /api/v1/generate` | Gateway → Blender | Текст → GLB/PNG (единый endpoint) |
| `POST /api/v1/parse` | Gateway → LLM | Текст → структурированные параметры |

### Потоки генерации

**Здание (из чата):**
```
Текст → parse (LLM) → {object_type: "building"} → Blender → GLB → Three.js viewer
                                   ↘ fallback: parseLocal() → Three.js
```

**Интерьер / Комната (из чата):**
```
Текст → parse (LLM) → {object_type: "room", room_type: "bedroom"} → Blender → PNG
                                   ↘ fallback: Three.js interior
```

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Frontend | HTML/CSS/JS, Three.js r160 |
| Gateway | Flask / FastAPI, Python 3.11 |
| LLM Proxy | Flask / FastAPI, httpx → OpenRouter API |
| Blender Service | Flask / FastAPI, Blender 3.6 CLI, Xvfb |
| AI (free) | OpenRouter: nemotron-nano-9b-v2, gemma-4-31b-it |
| AI (vision) | OpenRouter: nemotron-nano-12b-v2-vl |
| 3D рендер | Three.js (браузер) + Blender CLI (сервер) |
| Хранение | localStorage (ключ, URL) |
| Деплой | Render.com (Docker, Free Tier) |

---

## Структура проекта

```
AI_Arhitector/
├── index.html                  # Основной фронтенд (SPA)
├── server.py                   # Монолитный сервер (для локального запуска)
├── promt_parser.py             # LLM-парсер промтов (Шаг 1.1)
├── render.yaml                 # Render Blueprint (3 сервиса)
├── docker-compose.yml          # Docker Compose
├── requirements.txt            # Зависимости монолита
├── test_blender.py             # Smoke-тест Blender CLI
├── AI_Arhitector_fix_plan.md   # План исправления генерации
│
├── frontend/
│   └── index.html              # Фронтенд для Gateway (Docker)
│
├── gateway/
│   ├── Dockerfile
│   ├── app.py                  # Gateway: маршрутизация + статика
│   └── requirements.txt
│
├── llm-service/
│   ├── Dockerfile
│   ├── app.py                  # LLM: прокси к OpenRouter + парсинг
│   └── requirements.txt
│
├── blender-service/
│   ├── Dockerfile
│   ├── app.py                  # Blender: генерация зданий + интерьеров
│   └── requirements.txt
│
├── blender/
│   ├── blenderllm_bridge.py    # BlenderLLM ↔ bpy bridge
│   ├── generate_building.py    # Параметры → bpy → GLB
│   ├── render_interior.py      # Стиль → bpy → PNG
│   └── server.py               # Blender GUI API
│
├── colab/
│   └── ArchAI_Blender.ipynb    # Google Colab notebook
│
├── tests/
│   ├── test_generation.py      # Интеграционные тесты (Шаг 2.1)
│   └── test_blender.py         # Smoke-тест Blender
│
├── output/                     # Сгенерированные файлы (GLB, PNG)
└── .github/
    └── workflows/
        └── test.yml            # CI (Шаг 2.2)
```

---

## План развития

Детальный план с критериями приёмки: [`AI_Arhitector_fix_plan.md`](./AI_Arhitector_fix_plan.md)

### Дорожная карта

```
Фаза 1: Критические исправления          [В ПРОЦЕССЕ]
├── 1.1 LLM-парсер вместо regex           ← промты наконец понимаются
├── 1.2 Роутинг building/interior         ← "спальня" → интерьер, "коттедж" → здание
├── 1.3 Валидация bpy-скрипта             ← убирает "Cannot access uninitialized variable"
├── 1.4 Fallback на Three.js              ← GitHub Pages работает
└── 1.5 Retry в Gateway                   ← cold start не убивает запрос

Фаза 2: Тесты                             [ПЛАНИРУЕТСЯ]
├── 2.1 Интеграционные тесты (10+ промтов)
└── 2.2 CI workflow (GitHub Actions)

Фаза 3: Переписывание на FastAPI          [ПЛАНИРУЕТСЯ]
├── 3.1 LLM-сервис (async + Pydantic)
├── 3.2 Blender-сервис (валидация)
├── 3.3 Gateway (retry + async)
└── 3.4 Requirements

Фаза 4: Фронтенд                         [ПЛАНИРУЕТСЯ]
└── 4.1 Единая функция генерации с fallback

Фаза 5: Деплой                            [ПЛАНИРУЕТСЯ]
├── 5.1 Dockerfile
├── 5.2 docker-compose
└── 5.3 render.yaml
```

### Минимальный viable path

**Только Фаза 1 (шаги 1.1–1.3)** — промты начинают работать. Остальное — усиление.

---

## Тесты

### Запуск тестов

```bash
# Unit-тесты парсинга
python -m pytest tests/test_generation.py -v

# Smoke-тест Blender
python test_blender.py
```

### Анти-галлюцинационные тесты

Проект включает тесты-защиты от «красивого но нерабочего кода»:

- **10 параметризованных промтов** — парсер не выдумывает параметры
- **Garbage inputs** — пустые строки, эмодзи, XSS — парсер не падает
- **36 комбинаций параметров** — bpy-скрипт компилируется для каждой
- **f-string артефакты** — нет `{roof_type}` в выводе
- **PNG magic bytes** — файл реально PNG, а не мусор
- **Meta-тесты** — проверяют что тесты содержат assert, а не pass

---

## Примеры промтов

### Здания

| Промт | Ожидаемый результат |
|-------|-------------------|
| `дом 10×12 кирпич 2 этажа` | GLB: кирпичный дом, 2 этажа, двускатная крыша |
| `офис 5 этажей стекло плоская кровля 20×24` | GLB: офисное здание, стеклянный фасад |
| `деревянный коттедж 2 этажа терраса гараж 12×15` | GLB: коттедж с террасой и гаражом |
| `современный таунхаус 3 этажа минимализм` | GLB: таунхаус в минималистичном стиле |

### Интерьеры и комнаты

| Промт | Ожидаемый результат |
|-------|-------------------|
| `спальня в стиле лофт` | PNG: спальня, лофт-стиль, кровать, шкаф |
| `детская комната` | PNG: детская, кровать, стол, книжный шкаф |
| `кухня в скандинавском стиле` | PNG: кухня, светлые тона |
| `гостиная 6×8 модерн` | PNG: гостиная, диван, стол, люстра |

---

## Вклад

1. Fork репозитория
2. Создайте ветку: `git checkout -b fix/my-fix`
3. Запустите тесты: `python -m pytest tests/ -v`
4. Коммит: `git commit -m "fix: описание"`
5. Push: `git push origin fix/my-fix`
6. Pull Request

### Требования к PR

- [ ] Все тесты зелёные (`pytest tests/test_generation.py -v`)
- [ ] Новые промты добавлены в тестовую матрицу
- [ ] bpy-скрипты проходят `compile()`
- [ ] Нет hardcoded значений которые должны быть параметрами

---

## Лицензия

MIT

---

## Контакты

Issues: [github.com/smartmoneymoscow-cell/AI_Arhitector/issues](https://github.com/smartmoneymoscow-cell/AI_Arhitector/issues)
