# Wiki — AI_Arhitector v12.1.0

## Обзор

AI_Arhitector — это веб-приложение для генерации дизайна интерьеров и 3D-моделей зданий через текстовые промты на русском и английском языках.

**Архитектура:** Frontend (GitHub Pages) → Gateway (Render) → LLM Service (Render) → Orchestrator → Blender (Render)

## Живой сервис

| Компонент | URL |
|-----------|-----|
| **Фронтенд** | https://smartmoneymoscow-cell.github.io/AI_Arhitector/ |
| **Gateway API** | https://architect-gateway-3guo.onrender.com |
| **LLM Service** | https://architect-llm-s5q7.onrender.com |
| **Blender Service** | https://ai-arch-blender3d.onrender.com |

## Как использовать

1. Откройте https://smartmoneymoscow-cell.github.io/AI_Arhitector/
2. Введите промт на русском или английском языке
3. Нажмите отправить (Enter или кнопка ➤)
4. AI проанализирует запрос, покажет процесс мышления
5. Оркестратор создаст 3D модель через 7 шагов пайплайна
6. 3D модель отобразится в viewer (Three.js)

### Примеры промтов

**Интерьер:**
- "Дизайн гостиной в стиле лофт, 20 квадратных метров"
- "Кухня в скандинавском стиле, 15 кв.м, с островом"
- "Спальня минимализм, 18 кв.м, панорамные окна"

**Здания:**
- "Двухэтажный коттедж 10x12 из кирпича с двускатной крышей"
- "Современный офис 3 этажа, стеклянный фасад"
- "Таунхаус 8x10, плоская крыша, гараж"

**Ландшафт:**
- "Ландшафтный дизайн участка 10 соток с бассейном"
- "Японский сад с прудом и дорожками"

## LLM Каскад

Сервис использует каскад бесплатных LLM моделей с автоматическим переключением:

| Приоритет | Провайдер | Модель | Тип |
|:---------:|-----------|--------|-----|
| 1 | Groq | qwen/qwen3.6-27b | Прямой API, free tier |
| 2 | DeepSeek | deepseek-chat | Прямой API |
| 3 | Google Gemini | gemini-2.5-flash-lite | Прямой API, round-robin 8 ключей |
| 4 | OpenRouter | Auto-discovery free models | Free модели, автообновление каждый час |
| 5 | Cohere | command | Прямой API |
| 6 | Cerebras | — | Прямой API |
| 7 | SambaNova | — | Прямой API |

### Логика работы каскада

1. Запрос отправляется в первый доступный провайдер
2. При ошибке 429 (rate limit) → ключ помечается на cooldown 60 сек
3. При ошибке 402 (quota exhausted) → ключ помечается на cooldown 24 часа
4. Автоматический переход на следующий провайдер
5. Proactive health check каждые N минут
6. Auto-discovery бесплатных моделей OpenRouter каждый час

## Оркестратор (7 шагов пайплайна)

| Шаг | Название | Описание |
|:---:|----------|----------|
| 1 | **Parse** | LLM парсит промт → структурированные параметры (JSON) |
| 2 | **Route** | Определение типа: interior / building / landscape |
| 3 | **Geometry** | Генерация 3D геометрии (Blender Python API) |
| 4 | **Texture** | Применение материалов и текстур |
| 5 | **Render** | Рендер изображения (Blender Cycles) |
| 6 | **Quality** | Проверка качества результата |
| 7 | **Export** | Экспорт в формат GLB для Three.js viewer |

## API Endpoints

### Gateway (architect-gateway-3guo.onrender.com)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health` | GET | Health check |
| `/api/v1/parse` | POST | LLM парсинг промта |
| `/api/v1/orchestrator/execute` | POST | Полный пайплайн генерации |
| `/api/v1/orchestrator/resume` | POST | Продолжение после уточнений |
| `/api/v1/files/{path}` | GET | Доступ к сгенерированным файлам |

### LLM Service (architect-llm-s5q7.onrender.com)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health` | GET | Health check |
| `/api/v1/chat/completions` | POST | Chat proxy (OpenRouter) |

## Тестовые результаты (2026-08-19)

### Тест 1: LLM Parse — Интерьер
```
Промт: "Создай дизайн интерьера гостиной в стиле лофт, 20 квадратных метров"
Результат:
  object_type: interior
  building_type: apartment
  room_type: living_room
  style: loft
  width_m: 4.0, length_m: 5.0, height_m: 3.0
  features: открытая кирпичная кладка, металлические балки, панорамное освещение
  furniture: кожаный диван, журнальный столик на колесиках, металлический стеллаж
```

### Тест 2: LLM Parse — Здание
```
Промт: "Построй двухэтажный коттедж 10x12 из кирпича с двускатной крышей"
Результат:
  object_type: building
  building_type: cottage
  floors: 2
  width_m: 10.0, length_m: 12.0, height_m: 6.5
  material: brick
  roof_type: pitched
  features: garage, two-story, brick_facade
```

### Тест 3: Полный пайплайн (Оркестратор)
```
Промт: "Создай дизайн интерьера гостиной в стиле лофт, 20 квадратных метров"
Статус: done
Время: 53.3 секунды
Шаги: parse ✅ → route ✅ → geometry ✅ → texture ✅ → render ✅ → quality ✅ → export ✅
GLB: 207,180 bytes
```

### Тест 4: Groq API
```
Модель: qwen/qwen3.6-27b
Статус: OK
Время ответа: ~2 секунды
```

## Инфраструктура

### Render Services (все на free tier)

| Сервис | ID | План | Автодеплой |
|--------|-----|------|------------|
| architect-gateway | srv-da0vceugekts73ftpfk0 | free | ✅ main branch |
| architect-llm | srv-d9tpqom417fc73f14j70 | free | ✅ main branch |

### LLM Ключи (настроены в Render env vars)

| Провайдер | Ключей | Статус |
|-----------|:------:|:------:|
| OpenRouter | 8 | ✅ |
| Google Gemini | 8 | ✅ |
| DeepSeek | 8 | ✅ |
| Groq | 1 | ✅ |
| Cohere | 1 | ✅ |
| Cerebras | 1 | ✅ |
| SambaNova | 1 | ✅ |

## Известные ограничения

1. **Free tier cold start**: Render free tier сервисы "засыпают" после 15 мин неактивности. Первый запрос может занять 50-90 секунд.
2. **Rate limits**: OpenRouter free модели имеют дневные лимиты. Каскад автоматически переключается на другие провайдеры.
3. **Blender рендер**: Работает на Render blender-service. Для лучшего качества рекомендуется Kaggle GPU (T4/P100).
4. **GLB модели**: Генерируются процедурно через Blender Python API. Качество зависит от сложности промта.

## Changelog

См. [CHANGELOG.md](../CHANGELOG.md) для полной истории изменений.
