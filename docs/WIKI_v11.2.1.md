# Wiki — v11.2.1 Release Notes

**Дата:** 2026-08-10
**Тег:** v11.2.1

---

## Главное: Agent Pool Microservice

Архитектура изменилась. Раньше 27 из 30 агентов выполнялись in-process в gateway через `importlib.import_module()`. Теперь все агенты работают в отдельном сервисе **agent-pool** (порт 8083).

### Как это работает

```
Пользователь → Nginx → Gateway → Agent Pool (HTTP) → 30 агентов
                              → LLM Service (HTTP) → Gemini/OpenRouter
                              → Blender Service (HTTP) → Blender CLI
                              → Redis
```

1. Gateway получает запрос
2. Вызывает `agent-pool:8083/api/v1/agents/{name}/run` через HTTP
3. Agent-pool запускает агента в изолированном thread с timeout
4. Возвращает результат

### Fallback (3 уровня)

| Приоритет | Условие | Поведение |
|-----------|---------|-----------|
| 1 | `AGENT_POOL_URL` задан | HTTP-вызов в agent-pool |
| 2 | `FORCE_SUBPROCESS=1` | multiprocessing в отдельном процессе |
| 3 | По умолчанию | in-process с threading timeout |

### Конфигурация

```env
# .env
AGENT_POOL_URL=http://agent-pool:8083
```

Если `AGENT_POOL_URL` не задан — fallback на in-process (старое поведение).

---

## Quality Agent — все 5 уровней работают

Раньше только 2 из 5 уровней quality agent реально работали:

| Уровень | До v11.2.1 | После v11.2.1 |
|---------|-----------|---------------|
| 1. Resolution | ✅ | ✅ |
| 2. File integrity | ✅ | ✅ |
| 3. Visual bugs (AI) | ❌ mimo-omni dead path | ✅ Gemini Vision |
| 4. Prompt match (AI) | ❌ PIL fallback → always pass | ✅ Gemini Vision + fail-safe |
| 5. Geometry sanity (AI) | ❌ always pass | ✅ Gemini Vision + fail-safe |

### Fail-safe behavior

Если vision LLM недоступен:
- `passed: False` (не `True` как раньше)
- `vision_available: False` / `checked: False`
- Caller видит что проверка не проводилась

---

## Threading Timeout

`_run_in_process()` теперь имеет timeout через `threading.Thread` + `worker.join(timeout=)`. Если агент зависает (например, HTTP-вызов без timeout), gateway больше не блокируется для всех пользователей.

---

## Другие исправления

- **CORS**: wildcard `*` удалён из LLM/Blender сервисов (default: empty)
- **30+ bare `except:`** → конкретные типы (KeyError, AttributeError, TypeError, Exception)
- **Post-pipeline agents** параллельно (ThreadPoolExecutor)
- **sys.path.insert** удалён, PYTHONPATH в Dockerfiles
- **print()** → structured logging
- **Dependencies**: Python 3.13, fastapi≥0.141, httpx≥0.28, pydantic≥2.13, redis≥8.1
- **Aedifex bridge**: IFC/CAD routes, auth anonymous, nginx fix
- **Docstrings**: честное описание in-process поведения

---

## Миграция

### Обязательно
1. Добавить `AGENT_POOL_URL=http://agent-pool:8083` в `.env`
2. Добавить `CORS_ORIGINS=https://yourdomain.com` в `.env` (wildcard удалён)

### Опционально
- `FORCE_SUBPROCESS=1` для multiprocessing изоляции (нужен >512MB RAM)
- `MIMO_OMNI_SCRIPT=/path/to/script` если используете mimo-omni локально
