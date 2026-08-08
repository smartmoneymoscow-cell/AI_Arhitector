# CHANGELOG — AI_Arhitector

Все значимые изменения, планы доработок и итоги.

---

## 2026-08-08 — Исправление LLM-цепочки и бесплатного доступа

### Проблема
Генерация 3D-моделей не работала: OpenRouter возвращал ошибку 402 (нет кредитов), хотя в каскаде стояли бесплатные модели. Все модели `:free` на OpenRouter требуют ненулевой баланс аккаунта.

### Корневая причина
В `shared/parser.py` уже был реализован прямой вызов Google Gemini API (бесплатно), но:
1. Ключи `GOOGLE_API_KEY` и `GOOGLE_FALLBACK_KEYS` **не пробрасывались** в `docker-compose.yml` → LLM-сервис не видел ключи
2. В `llm-service` переменные `OPENROUTER_API_KEY` были обязательными (`:?`) → падал при запуске без ключей

### Что исправлено

#### `docker-compose.yml`
- **llm-service**: добавлены `GOOGLE_API_KEY`, `GOOGLE_FALLBACK_KEYS`, `GEMINI_MODEL`
- **llm-service**: `OPENROUTER_API_KEY` сделан необязательным (`:-`) — Gemini работает первым, OpenRouter — фолбэк
- **gateway**: добавлены `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `KAGGLE_RENDERER_URL`, `KAGGLE_POLLING_ENABLED`
- **blender-service**: добавлен `KAGGLE_RENDERER_URL` для GPU-рендера

### Архитектура LLM-цепочки (после исправления)
```
Промт пользователя
    ↓
1. Google Gemini API (прямой, бесплатно, 4 ключа с ротацией)
    ↓ если не ответил
2. OpenRouter каскад (8 бесплатных моделей :free)
    ↓ если не ответил
3. Ollama (локальный, если настроен)
    ↓ если не ответил
4. Regex fallback (базовый парсинг)
```

### Планы доработок (на 2026-08-08)

| # | Задача | Приоритет | Статус |
|---|--------|-----------|--------|
| 1 | Проброс GOOGLE_API_KEY в Docker | 🔴 Критично | ✅ Done |
| 2 | Frontend → orchestrator + clarification flow | 🟡 Важно | ✅ Done |
| 3 | Kaggle GPU polling endpoints | 🟡 Важно | ✅ Done (были реализованы) |
| 4 | answerClarification → resume orchestrator | 🟡 Важно | ✅ Done |
| 5 | _handleOrchestratorResult (clarif/success/fail) | 🟡 Важно | ✅ Done |
| 6 | Удаление дубликатов HTML (3 копии) | 🟢 Улучшение | 📋 Planned |
| 7 | Kaggle GPU notebook запуск | 🟡 Важно | 📋 Planned |

---

## Формат записей

### Шаблон
```
## YYYY-MM-DD — Краткое описание

### Проблема
Описание что сломалось или чего не хватало.

### Что исправлено
Список изменений по файлам.

### Планы доработок
Таблица задач с приоритетами и статусами.
```

### Статусы
- ✅ Done — выполнено
- 🔄 In Progress — в работе
- 📋 Planned — запланировано
- ❌ Blocked — заблокировано
