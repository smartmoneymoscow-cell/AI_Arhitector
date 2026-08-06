# Architect v10.3.1 — AI Architecture Generator

Генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Что нового в v10.3.1

- **Cycles CPU рендер** — заменён EEVEE (требует GPU) на Cycles CPU (работает на Render free tier)
- **Исправлен маппинг интерьеров** — ванная, детская, кухня, спальня, гостиная, кабинет вместо "Жилой дом"
- **Реальный reasoning** — анализ запроса: тип комнаты, стиль, размеры, особенности, мебель
- **Декомпозиция задач** — 5 шагов с агентами: LLM → Geometry → Texture → Lighting → Blender
- **Уточняющие вопросы** — кнопки-ответы для стиля, цвета, качества с опцией "Пропустить"
- **Референсы** — иконки и подписи релевантные промту (джакузи, душевая, камин и т.д.)
- **Динамические чипсины** — адаптируются под тип комнаты
- **Оркестратор integration** — вызов `/api/v1/orchestrator/execute` с fallback на `/api/v1/generate`

## Что нового в v10.2.0

- **Google Gemini FREE API** — бесплатный LLM через Google AI Studio (8 ключей, ротация)
- **Каскад только бесплатных моделей** — убраны все платные модели из LLM_CASCADE
- **Fallback на OpenRouter :free** — если Gemini недоступен, пробуем бесплатные модели OpenRouter
- **Pydantic валидация** — исправлена обработка null для material/roof_type в интерьерах
- **Retry с backoff** — при 429 rate limit автоматическое ожидание и смена ключа

## Что нового в v10.1.0

- **Удалён regex fallback** — обработка ТОЛЬКО через LLM
- **Auto-discovery бесплатных моделей** — автоматический поиск доступных моделей OpenRouter
- **4-key rotation** — ротация между 4 API ключами с failover
- **Kaggle GPU renderer** — Flask + Blender + ngrok на GPU T4
- **Исправлена валидация Pydantic** — интерьерные промты больше не падают
- **Улучшена обработка ошибок** — детальные сообщения вместо 500

## Архитектура (5 Render аккаунтов)

```
                    ┌─────────────────────────────┐
                    │   Пользователь (браузер)     │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
  Render #1         │  Gateway :8080              │
  (основной)        │  ├── FastAPI                │
                    │  ├── Frontend (HTML/JS)     │
                    │  ├── Оркестратор агентов    │
                    │  ├── Load Balancer          │
                    │  └── Redis кеш             │
                    └──┬──────────┬──────────┬────┘
                       │          │          │
          ┌────────────▼──┐  ┌───▼────────┐  ┌──▼───────────┐
  Render #2│ Blender #1   │  │ Blender #2 │  │ LLM Service  │
          │ :8082         │  │ :8082      │  │ :8081        │
          │ EEVEE 4K      │  │ EEVEE 4K   │  │ Каскад 7 LLM│
          │ GLB экспорт   │  │ Failover   │  │ Redis кеш   │
          └───────────────┘  └────────────┘  │ OpenRouter   │
  Render #3                                   └──────────────┘
                                  ┌──────────────┐
  Render #4                       │ Blender #3   │
  (16K tiled)                     │ Cycles 16K   │
                                  │ 4×3 тайла    │
                                  └──────────────┘
  Render #5 (backup LLM)
```

## Сервисы и URL

| Сервис | URL | Статус | Что делает |
|--------|-----|--------|-----------|
| Gateway | `architect-gateway.onrender.com` | ✅ | API, Frontend, оркестрация |
| Blender #1 | `ai-arch-blender3d.onrender.com` | ✅ | EEVEE 4K рендер, GLB |
| Blender #2 | `architect-blender.onrender.com` | ✅ | EEVEE 4K, failover |
| LLM | `architect-llm-1s1j.onrender.com` | ✅ | Парсинг промтов (каскад LLM) |

## Multi-Key LLM

4 OpenRouter API ключа с автоматической ротацией:
- Primary + 3 fallback
- Auto-discovery бесплатных моделей (обновление каждый час)
- Circuit breaker при ошибках
- Автопереключение при 429/401

## Kaggle GPU Renderer

Дополнительный рендер-бэкенд на Kaggle (T4/P100 GPU):
- `kaggle/blender_gpu_renderer.ipynb` — Flask + Blender
- Режимы: ngrok (прямой URL) или polling (опрос Gateway)
- Лимиты: ~30 часов/неделю (T4 free)

См. `kaggle/README.md` для инструкций.

## Правило генерации 16K

16K рендер (15360×8640 = 132 мегапикселя) невозможен за один проход на 512MB RAM.

**Решение — Tiled Rendering:**

```
Полное изображение: 15360 × 8640
Разбивается на тайлы: 4 × 3 = 12 тайлов
Каждый тайл: 3840 × 2880 (~110MB RAM)
Рендерится последовательно в Cycles
Склеивается в одно изображение
```

**Pipeline:**
1. LLM парсит промт → параметры здания
2. Geometry agent генерирует bpy-скрипт
3. Texture agent добавляет PBR-материалы
4. Blender #3 (Cycles) рендерит 12 тайлов
5. Quality agent проверяет: разрешение ≥15360×8640, файл ≥8MB
6. Если качество ниже → retry с увеличенными samples

**Env переменные для 16K:**
```bash
BLENDER_SERVICE_URL_3=https://______.onrender.com  # Render #4
```

## Визуальные тесты скриншотов

Автоматизированный тестер для проверки генерации через реальные промты.

### Запуск

```bash
# Все тесты (28 промтов из скриншотов + похожие)
python3 tests/visual_test_runner.py --url https://architect-gateway.onrender.com

# Только анализ существующих скриншотов
python3 tests/visual_test_runner.py --analyze-only --output screenshots/test_run
```

### Тест-кейсы из скриншотов

| ID | Промт | Ожидаемый тип | Баг был |
|----|-------|---------------|---------|
| IMG_1432 | ванная с джакузи | interior/bathroom | → генерировался дом |
| IMG_1431 | отель | building/hotel | → генерировался жилой дом |
| IMG_1429 | дизайн детской | interior/children | → ошибка uninitialized |
| IMG_1430 | кухня в стиле хайтек | interior/kitchen | → генерировался экстерьер |
| IMG_1428 | сделай таунхаус | building/townhouse | → пустой 3D view |

### Дополнительные тесты (90+ промтов)

- 15 типов интерьеров
- 18 типов зданий
- 10 типов ландшафта
- 15 сложных/неоднозначных промтов

### Что проверяется

1. **Тип генерации** — interior/building/landscape определён правильно
2. **Валидация** — параметры сохраняются после валидации
3. **Качество** — разрешение ≥16K, файл ≥8MB
4. **Агенты** — все 22 агента зарегистрированы, fallback работает
5. **Pipeline** — все профили (quick/standard/full/premium/interior/landscape) корректны

## Зависимости

```
Python: 3.12+
Node.js: 22+
Blender: 4.0+
Redis: 7.0+
```

## Локальный запуск

```bash
# Клонировать
git clone https://github.com/smartmoneymoscow-cell/AI_Arhitector.git
cd AI_Arhitector

# .env
cp .env.example .env
# Заполнить OPENROUTER_API_KEY

# Docker
docker compose up --build

# Или локально
pip install -r requirements.txt
python server.py
```

## Тесты

```bash
# Unit тесты (129 штук)
python3 -m pytest tests/test_detect_gen_type.py tests/test_generation.py tests/test_quality_clarification.py -v

# E2E тесты по скриншотам (97 штук)
python3 -m pytest tests/test_e2e_screenshots.py -v

# Все тесты (309 штук)
python3 -m pytest tests/ --ignore=tests/test_gateway.py --ignore=tests/test_e2e.py -v
```
