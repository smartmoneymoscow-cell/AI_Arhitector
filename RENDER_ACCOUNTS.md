# Render Accounts — Распределение по 5 аккаунтам

Каждый аккаунт = отдельный Render проект со своими сервисами.

## Архитектура

```
Аккаунт 1 (основной)         Аккаунт 2                Аккаунт 3
┌─────────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ Gateway :8080       │      │ Blender #1 :8082│      │ Blender #2 :8082│
│ ├── FastAPI          │─────▶│ ├── Blender CLI  │      │ ├── Blender CLI  │
│ ├── Frontend (HTML)  │      │ ├── Xvfb         │      │ ├── Xvfb         │
│ ├── Оркестратор      │      │ ├── EEVEE 4K     │      │ ├── EEVEE 4K     │
│ └── Redis :6379      │      │ └── GLB экспорт  │      │ └── GLB экспорт  │
└─────────────────────┘      └─────────────────┘      └─────────────────┘
        │                                                     │
        │         Аккаунт 4                Аккаунт 5          │
        │        ┌─────────────────┐      ┌─────────────────┐ │
        │        │ Blender #3 :8082│      │ LLM Service:8081│ │
        └───────▶│ ├── Blender CLI  │      │ ├── Каскад 7 LLM│◀┘
                 │ ├── Xvfb         │      │ ├── Redis кеш   │
                 │ ├── Cycles 16K   │      │ └── OpenRouter  │
                 │ └── Tiled render │      └─────────────────┘
                 └─────────────────┘
```

## Таблица аккаунтов

| # | Render Аккаунт | URL сервиса | Ключи | Что работает на аккаунте | Render План | Статус |
|---|----------------|-------------|-------|--------------------------|-------------|--------|
| 1 | Render #1 — Gateway | `https://______.onrender.com` |rnd_JN65Ycm8hWZuMPHITQlPHseQLwTE| Gateway (FastAPI), Frontend (HTML/JS), Оркестратор, Redis кеш, маршрутизация между Blender инстансами | Render starter | ⬜ |
| 2 | Render #2 — Blender #1 | `https://______.onrender.com` | — | Blender CLI + Xvfb, EEVEE 4K рендер, превью, экспорт GLB, материалы PBR | Render starter | ⬜ |
| 3 | Render #3 — Blender #2 | `https://______.onrender.com` | — | Blender CLI + Xvfb, EEVEE 4K рендер (параллельный), failover для #2 | Render starter | ⬜ |
| 4 | Render #4 — Blender #3 | `https://______.onrender.com` | — | Blender CLI + Xvfb, Cycles 16K tiled рендер (4×3 тайла), тяжёлые рендеры | Render starter | ⬜ |
| 5 | Render #5 — LLM Service | `https://______.onrender.com` | `OPENROUTER_API_KEY` | Парсинг промтов (каскад 7 LLM), Redis кеш ответов, определение типа генерации | Render starter | ⬜ |

## Распределение нагрузки

| Тип запроса | Куда идёт | Почему |
|-------------|-----------|--------|
| Превью (быстрое) | Blender #1 или #2 (round-robin) | EEVEE — быстро, 4K достаточно |
| Рендер 4K | Blender #1 или #2 (round-robin) | EEVEE 4K, параллельно |
| Рендер 16K | Blender #3 (только он) | Cycles tiled, нужно много ресурсов |
| Парсинг промта | LLM Service | 7 моделей в каскаде |
| Всё остальное | Gateway | API, frontend, оркестрация |

## Failover

```
Blender #1 упал? → Gateway пробует Blender #2
Blender #2 упал? → Gateway пробует Blender #1
Все Blender мертвы? → EEVEE fallback в браузере
LLM Service упал? → Ollama local fallback (если настроен)
```

## Env переменные (прописать в Аккаунте 1 — Gateway)

```bash
# Ссылки на другие аккаунты
LLM_SERVICE_URL=https://______.onrender.com          # Аккаунт 5
BLENDER_SERVICE_URL=https://______.onrender.com       # Аккаунт 2
BLENDER_SERVICE_URL_2=https://______.onrender.com     # Аккаунт 3
BLENDER_SERVICE_URL_3=https://______.onrender.com     # Аккаунт 4
REDIS_URL=redis://red-______:6379                     # Свой Redis
ARCH_API_KEYS=your-secret-key
CORS_ORIGINS=https://smartmoneymoscow-cell.github.io
```

## Что деплоить на каждом аккаунте

### Аккаунт 1 — Gateway
```bash
# Dockerfile: gateway.Dockerfile
# Port: 8080
# Env: см. выше
```

### Аккаунты 2, 3, 4 — Blender
```bash
# Dockerfile: blender.Dockerfile
# Port: 8082
# Env:
PORT=8082
BLENDER_PATH=blender
OUTPUT_DIR=/app/output
LLM_SERVICE_URL=https://______.onrender.com  # Аккаунт 5
REDIS_URL=redis://red-______:6379            # Аккаунт 1
```

### Аккаунт 5 — LLM Service
```bash
# Dockerfile: llm.Dockerfile
# Port: 8081
# Env:
PORT=8081
OPENROUTER_API_KEY=***
REDIS_URL=redis://red-______:6379  # Аккаунт 1
```
