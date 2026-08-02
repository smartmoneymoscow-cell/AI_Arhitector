# Architect v9.0 — AI Architecture Generator

Генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

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
| LLM | `architect-llm-1s1j.onrender.com` | ✅ | Парсинг промтов (7 LLM) |

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
