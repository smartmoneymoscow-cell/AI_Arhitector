# 🔍 Отчёт тестирования LLM-каскада — AI_Arhitector v11.5.0

**Дата:** 2026-08-16  
**Тестер:** OpenClaw Agent  
**Промт:** "Спроектируй двухэтажный коттедж в скандинавском стиле, 12 на 10 метров, с панорамными окнами и террасой"

---

## 📊 Сводная таблица провайдеров

| # | Провайдер | Кол-во ключей | Статус | Модель | Время | Примечание |
|---|-----------|:---:|--------|--------|:---:|------------|
| 1 | **Groq** | 1 | ✅ WORKS | llama-3.3-70b-versatile | 0.2s | Бесплатный тир, быстрый |
| 2 | **Cohere** | 1 | ✅ WORKS | command-r-08-2024 | 26.1s | Бесплатный, медленный |
| 3 | **Gemini** | 1/8 | ✅ WORKS | gemini-flash-lite-latest | ~1s | Только ключ #1 работает, остальные 401 |
| 4 | **OpenRouter** | 8 | ⚠️ QUOTA | 16 free models | — | Все ключи исчерпали дневной лимит (50/сутки), сброс 2026-08-17 08:00 UTC |
| 5 | **DeepSeek** | 8 | ❌ DEAD | — | 0.4s | Все 8 ключей: 402 Insufficient Balance |
| 6 | **Cerebras** | 1 | ❌ DEAD | — | 0.3s | 402 Payment required |
| 7 | **SambaNova** | 1 | ❌ DEAD | — | 0.6s | balance_units=0 |
| 8 | **Bunny CDN** | 1 | — | — | — | CDN, не LLM |

---

## ✅ Рабочие модели (подтверждённые генерации)

### 1. Groq — llama-3.3-70b-versatile
**Время ответа:** 0.2s  
**Качество JSON:** ✅ Валидный  
**Ответ:**
```json
{"object_type":"building","building_type":"cottage","style":"scandinavian","width_m":12,"length_m":10,"floors":2,"features":["panoramic_windows","terrace"],"confidence":0.95}
```
**Оценка:** Отлично. Быстрый, точный JSON, правильный формат.

### 2. Cohere — command-r-08-2024
**Время ответа:** 26.1s  
**Качество JSON:** ✅ Валидный  
**Ответ:**
```json
{"object_type": "building", "building_type": "cottage", "style": "scandinavian", "width_m": 12, "length_m": 10, ...}
```
**Оценка:** Хорошо, но очень медленно (26s). Для production — неприемлемо.

### 3. Gemini — gemini-flash-lite-latest (Key #1)
**Время ответа:** ~1s  
**Качество JSON:** ✅ Валидный  
**Оценка:** Отлично. Быстрый, бесплатный. Но работает только 1 из 8 ключей.

---

## ❌ Нерабочие провайдеры

### DeepSeek (8 аккаунтов)
**Ошибка:** 402 Insufficient Balance  
**Причина:** DeepSeek не имеет бесплатного тира. Все аккаунты без баланса.  
**Решение:** Удалить из каскада или пополнить баланс.

### Cerebras (1 аккаунт)
**Ошибка:** 402 Payment required  
**Причина:** Бесплатный тир исчерпан или не активирован.  
**Модели в каталоге:** gpt-oss-120b, gemma-4-31b, zai-glm-4.7  
**Решение:** Проверить billing на cloud.cerebras.ai.

### SambaNova (1 аккаунт)
**Ошибка:** 402 balance_units=0  
**Причина:** Нулевой баланс.  
**Модели в каталоге:** DeepSeek-V3.1, DeepSeek-V3.2, Meta-Llama-3.3-70B-Instruct, MiniMax-M2.7, gemma-4-31B-it, gpt-oss-120b  
**Решение:** Пополнить баланс или получить бесплатные кредиты.

### OpenRouter (8 аккаунтов)
**Ошибка:** 429 Rate limit exceeded: free-models-per-day  
**Причина:** Дневной лимит 50 запросов на бесплатные модели исчерпан ВСЕМИ 8 ключами.  
**Сброс:** 2026-08-17 08:00 UTC  
**Обнаружено моделей:** 16 бесплатных  
**Решение:** Дождаться сброса лимита или добавить $10 кредитов (увеличит до 1000/сутки).

---

## 🔄 Динамический каскад — обнаруженные бесплатные модели OpenRouter

| # | Модель | Tier | Статус |
|---|--------|:---:|--------|
| 1 | google/gemma-4-26b-a4b-it:free | 1 | ⚠️ 429 (quota) |
| 2 | google/gemma-4-31b-it:free | 1 | ⚠️ 429 (quota) |
| 3 | nvidia/nemotron-3-ultra-550b-a55b:free | 1 | ⚠️ 429 (quota) |
| 4 | nvidia/nemotron-3-super-120b-a12b:free | 1 | ⚠️ 429 (quota) |
| 5 | nvidia/nemotron-3-nano-30b-a3b:free | 2 | ⚠️ 429 (quota) |
| 6 | poolside/laguna-s-2.1:free | 2 | ⚠️ 429 (quota) |
| 7 | poolside/laguna-xs-2.1:free | 2 | ⚠️ 429 (quota) |
| 8 | cohere/north-mini-code:free | 2 | ⚠️ 429 (quota) |
| 9 | liquid/lfm-2.5-2.6b:free | 3 | ⚠️ 429 (quota) |
| 10 | openai/gpt-oss-20b:free | 3 | ⚠️ 429 (quota) |
| 11 | nvidia/nemotron-3.5-lightning:free | — | ⚠️ 429 (quota) |
| 12 | nvidia/nemotron-nano-12b-v2-vl:free | — | ⚠️ 429 (quota) |
| 13 | nvidia/nemotron-nano-9b-v2:free | — | ⚠️ 429 (quota) |
| 14 | dots-studio/dots-3-note-preview:free | — | ⚠️ 429 (quota) |
| 15 | openrouter/free | — | ⚠️ 429 (quota) |

---

## 🏗️ Архитектурные проблемы текущего кода

### 1. `get_active_cascade()` — ЗАХАРДКОЖЕН
```python
def get_active_cascade(api_key: str = "") -> list[dict]:
    """Always return hardcoded cascade with paid models.
    Free model discovery disabled to avoid daily rate limits."""
    return LLM_CASCADE  # ← ВСЕГДА возвращает хардкод
```
**Проблема:** `discover_free_models()` написана и работает, но результат НИКОГДА не используется.  
**Исправление:** См. патч `parser_patched.py`.

### 2. Сортировка — по алфавиту, не по мощности
```python
free_models.sort(key=lambda x: (x["tier"], x["model"]))  # ← alphabetical
```
**Исправление:** Сортировка по `_estimate_power()` — сначала самые мощные.

### 3. `_PREFERRED` — устаревшие модели
Содержит модели, которых больше нет на OpenRouter (gemini-2.5-flash, llama-3.3-70b-instruct:free).  
**Исправление:** Обновлён текущими рабочими моделями.

---

## ✅ Исправления (патч v11.6.0)

| Изменение | Файл | Описание |
|-----------|------|----------|
| `get_active_cascade()` | shared/parser.py | Возвращает `_DISCOVERED_MODELS` если есть, иначе `LLM_CASCADE` |
| `_estimate_power()` | shared/parser.py | Новая функция оценки мощности модели по ID |
| Сортировка discovery | shared/parser.py | `(tier, -power, model)` вместо `(tier, model)` |
| `_PREFERRED` | shared/parser.py | Обновлён текущими рабочими моделями |
| `_BLOCKLIST` | shared/parser.py | Добавлен dots-studio/dots-3-note-preview:free |
| `SYSTEM_PROMPT_VERSION` | shared/parser.py | v9.0 → v10.0 (кеш инвалидирован) |

---

## 📈 Рекомендации

1. **Добавить $10 на OpenRouter** — увеличит лимит с 50 до 1000 запросов/сутки на каждый из 8 аккаунтов
2. **Пополнить Cerebras/SambaNova** — получить бесплатные кредиты для резервного каскада
3. **Удалить DeepSeek из конфига** — нет бесплатного тира, занимает место в каскаде
4. **Восстановить Gemini ключи #2-#8** — вернуть 401, возможно истёк срок действия
5. **Мониторинг** — добавить `/api/v1/keys/status` в автоматический алертинг

---

## 🎯 Итог

**Рабочих провайдеров:** 3 из 7 (Groq, Cohere, Gemini)  
**Свободных моделей OpenRouter:** 16 (все исчерпали дневной лимит)  
**Критических проблем:** Dynamic cascade отключён, Gemini 7/8 ключей мертвы  
**Патч v11.6.0:** Готов к деплою
