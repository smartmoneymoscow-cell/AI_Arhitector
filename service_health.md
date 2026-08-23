# AI_Arhitector — Health Report

**Дата проверки:** 2026-08-23 23:12 (GMT+8)

---

## 1. Gateway

| Параметр | Значение |
|----------|----------|
| URL | `https://architect-gateway-3guo.onrender.com` |
| HTTP статус | ✅ 200 |
| Время ответа | 0.28s |
| Версия | 13.5.0 |
| LLM сервис | configured |
| Blender сервис | configured |
| Redis | not_configured |
| Blender instances | 1 |
| Circuit breaker (LLM) | failures: 0, is_open: false |

**Статус: ✅ HEALTHY**

---

## 2. LLM Service

| Параметр | Значение |
|----------|----------|
| URL | `https://architect-llm-5mdk.onrender.com` |
| HTTP статус | ✅ 200 |
| Время ответа | 0.28s |
| Версия | 13.2.0 |
| Текущая модель | `google/gemma-4-26b-a4b-it:free` |

### Cascade Providers (из /health)

| Провайдер | Статус конфигурации |
|-----------|-------------------|
| Groq | ✅ configured |
| Gemini | ✅ configured |
| DeepSeek | ✅ configured |
| OpenRouter | ✅ configured |

**Статус: ✅ HEALTHY**

---

## 3. Blender Service

| Параметр | Значение |
|----------|----------|
| URL | `https://ai-arch-blender3d.onrender.com` |
| HTTP статус | ✅ 200 |
| Время ответа | 0.28s |
| Версия | 13.4.0 |
| Model | null |
| Services | null |

**Статус: ✅ HEALTHY**

---

## 4. Frontend (GitHub Pages)

| Параметр | Значение |
|----------|----------|
| URL | `https://smartmoneymoscow-cell.github.io/AI_Arhitector/` |
| HTTP статус | ✅ 200 |
| Время ответа | 0.29s |
| Заголовок | Architect — AI Architecture Generator |
| Тема | Dark/Light (переключаемая) |
| Шрифт | Inter |

**Статус: ✅ HEALTHY**

---

## 5. LLM Parse Test

**Запрос:** `POST /api/v1/parse`
**Body:** `{"text":"коттедж 2 этажа 12x15 дерево"}`
**HTTP статус:** ✅ 200
**Время ответа:** 2.37s

**Ответ:**
```json
{
  "object_type": "building",
  "building_type": "cottage",
  "room_type": null,
  "floors": 2,
  "width_m": 12.0,
  "length_m": 15.0,
  "height_m": 6.5,
  "style": "modern_wood",
  "material": "timber",
  "roof_type": "gable",
  "features": ["панорамные окна", "балкон", "терраса"],
  "furniture": []
}
```

**Статус: ✅ PARSE CORRECT** — корректно распознан тип, этажность, размеры, материал.

---

## 6. LLM Cascade — Key Status

| Провайдер | Всего ключей | Живых | Статус |
|-----------|-------------|-------|--------|
| Groq | 1 | 0 | ⚠️ все ключи мертвы |
| Gemini | 2 | 2 | ✅ |
| DeepSeek | 8 | 8 | ✅ |
| OpenRouter | 2 | 2 | ✅ |
| **Итого** | **13** | **12** | |

**Примечание:** Groq имеет 1 ключ, который сейчас помечен как `alive: false`. Cascade автоматически переключится на другие провайдеры (Gemini → DeepSeek → OpenRouter).

---

## 7. Gateway API Endpoints (полный список)

| Endpoint | Описание |
|----------|----------|
| `/health` | Health check |
| `/api/v1/parse` | Парсинг текста |
| `/api/v1/generate` | Генерация 3D |
| `/api/v1/generate/fast` | Быстрая генерация |
| `/api/v1/preview` | Превью |
| `/api/v1/chat` | Чат |
| `/api/v1/orchestrator/execute` | Оркестратор |
| `/api/v1/clarify` | Уточняющие вопросы |
| `/api/v1/compliance/check` | Проверка соответствия |
| `/api/v1/analyze/pdf` | Анализ PDF |
| `/api/v1/analyze/dwg` | Анализ DWG |
| `/api/v1/variants` | Варианты |
| `/api/v1/kaggle/*` | Kaggle интеграция |
| `/api/v1/stats` | Статистика |

---

## 8. LLM Service API Endpoints

| Endpoint | Описание |
|----------|----------|
| `/health` | Health check |
| `/api/v1/chat/completions` | Chat completions (OpenAI-совместимый) |
| `/api/v1/parse` | Парсинг текста |
| `/api/v1/keys/status` | Статус API ключей |
| `/api/v1/cache/stats` | Статистика кэша |
| `/api/v1/models/discover` | Обнаружение моделей |
| `/api/v1/models/refresh` | Обновление моделей |

---

## Сводка

| Сервис | Статус | Версия |
|--------|--------|--------|
| Gateway | ✅ OK | 13.5.0 |
| LLM | ✅ OK | 13.2.0 |
| Blender | ✅ OK | 13.4.0 |
| Frontend | ✅ OK | — |
| Parse API | ✅ OK | — |
| Cascade | ⚠️ 12/13 ключей | Groq key down |

**Общий статус: 🟢 ВСЕ СЕРВИСЫ РАБОТАЮТ**

Единственное замечание: ключ Groq мёртв, но это не критично — cascade автоматически использует Gemini/DeepSeek/OpenRouter.
