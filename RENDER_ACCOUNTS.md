# Render Accounts — Распределение сервисов

> ⚠️ Не заполняй ключи в этом файле — только в `.env` или Render Dashboard.
> Столбец "Ключ" показывает **какая переменная** нужна, не сам ключ.

## Архитектура

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Аккаунт 1  │────▶│  Аккаунт 2  │────▶│  Аккаунт 3  │
│  Gateway    │     │  LLM Service│     │  Blender #1 │
│  + Redis    │     │  (парсинг)  │     │  EEVEE 4K   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                        │
       │              ┌─────────────┐           │
       ├─────────────▶│  Аккаунт 4  │           │
       │              │  Blender #2 │◀──────────┘
       │              │  EEVEE 4K   │
       │              └─────────────┘
       │                    │
       │              ┌─────────────┐
       └─────────────▶│  Аккаунт 5  │
                      │  Blender #3 │
                      │  Tiled 16K  │
                      └─────────────┘
```

## Таблица аккаунтов

| # | Название сервиса | URL | Переменная ключа | Что работает | План | Статус |
|---|-----------------|-----|------------------|--------------|------|--------|
| 1 | Gateway | `https://______.onrender.com` | `ARCH_API_KEYS` | API Gateway, frontend, оркестрация, Redis | starter | ⬜ Не заполнено |
| 1 | Redis | `redis://red-______:6379` | — | Кеш LLM, Celery broker | starter | ⬜ Не заполнено |
| 2 | LLM Service | `https://______.onrender.com` | `OPENROUTER_API_KEY` | Парсинг промтов через каскад 7 LLM | starter | ❌ Не отвечает |
| 3 | Blender #1 | `https://ai-arch-blender3d.onrender.com` | — | EEVEE 4K рендер, превью, экспорт GLB | standard | ✅ Живой |
| 4 | Blender #2 | `https://______.onrender.com` | — | EEVEE 4K рендер (параллельный) | starter | ⬜ Не заполнено |
| 5 | Blender #3 | `https://______.onrender.com` | — | Tiled Cycles 16K рендер | starter | ⬜ Не заполнено |

## Как заполнить

1. Задеплой сервис на каждом аккаунте
2. Заполни URL в таблице выше
3. Пропиши URL в `.env`:

```bash
# Аккаунт 1 — Gateway
GATEWAY_URL=https://______.onrender.com
ARCH_API_KEYS=your-key-here

# Аккаунт 2 — LLM
LLM_SERVICE_URL=https://______.onrender.com
OPENROUTER_API_KEY=sk-or-______

# Аккаунт 3 — Blender #1 (основной)
BLENDER_SERVICE_URL=https://ai-arch-blender3d.onrender.com

# Аккаунт 4 — Blender #2 (параллельный)
BLENDER_SERVICE_URL_2=https://______.onrender.com

# Аккаунт 5 — Blender #3 (16K tiled)
BLENDER_SERVICE_URL_3=https://______.onrender.com
```

## Load Balancing

Gateway автоматически распределяет запросы между Blender инстансами:

```
Запрос на превью    → Blender #1 или #2 (round-robin)
Запрос на 4K рендер → Blender #1 или #2 (round-robin)
Запрос на 16K рендер → Blender #3 (tiled rendering)
Fallback            → Любой живой инстанс
```

## Failover

Если инстанс не отвечает (timeout 30s):
1. Gateway пробует следующий Blender инстанс
2. Circuit breaker: 5 ошибок → инстанс отключается на 60s
3. Если все Blender мертвы → EEVEE fallback в браузере
