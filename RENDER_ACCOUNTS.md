# Render Accounts — Распределение по 8 аккаунтам

## Архитектура

```
Аккаунт 1 (smart.money.moscow)     Аккаунт 2 (xhungerrr)
┌────────────────────────────┐     ┌──────────────────────────┐
│ architect-llm              │     │ ai-arch-blender3d        │
│ architect-llmproxy (Acc2)  │     │ ai-arch-llmproxy         │
│                            │     │ architect-graphdb        │
│                            │     │ architect-vectordb       │
│                            │     │ architect-freecad        │
│                            │     │ architect-cad            │
│                            │     │ architect-data           │
│                            │     │ architect-ifc            │
│                            │     │ architect-ml             │
│                            │     │ architect-geometry       │
│                            │     │ architect (legacy)       │
└────────────────────────────┘     └──────────────────────────┘

Аккаунт 3 (rrrhunger)              Аккаунт 4 (fdegegvf)
┌────────────────────────────┐     ┌──────────────────────────┐
│ architect-llm              │     │ architect-gateway        │
│                            │     │ architect-llm            │
│                            │     │ architect-blender        │
└────────────────────────────┘     └──────────────────────────┘

Аккаунт 5 (k25334003)              Аккаунт 6 (ror577282)
┌────────────────────────────┐     ┌──────────────────────────┐
│ architect-llm              │     │ architect-llm            │
└────────────────────────────┘     └──────────────────────────┘

Аккаунт 7 (argo7075)               Аккаунт 8 (vietnamsk064)
┌────────────────────────────┐     ┌──────────────────────────┐
│ architect-llm              │     │ architect-llm            │
│ chat-monitor-bot (other)   │     │                          │
└────────────────────────────┘     └──────────────────────────┘
```

## Таблица аккаунтов

| # | Email | Render API Key | LLM URL | OpenRouter Primary | Статус |
|---|-------|----------------|---------|-------------------|--------|
| 1 | smart.money.moscow@gmail.com | rnd_KMg9YhMV1KGHQtxQ8ZKJFeSD8bfP | architect-llm-s5q7.onrender.com | …88f4 | ✅ |
| 2 | xhungerrr@gmail.com | rnd_SUdnZ8X1k3FcHYF18x4Iwwf53Qus | ai-arch-llmproxy.onrender.com | …09d3 | ✅ |
| 3 | rrrhunger@gmail.com | rnd_gGB1SnppOuKq2ZeLuqMKf7eDcOXB | architect-llm-zczl.onrender.com | …8ef8 | ✅ |
| 4 | fdegegvf@gmail.com | rnd_CqhN6epv00T8vkxaQ4EXNf3fhV8U | architect-llm-1s1j.onrender.com | …9396 | ✅ |
| 5 | k25334003@gmail.com | rnd_agw4sqP8qFzydsfg6ojS6zl9mm2K | architect-llm-2pmo.onrender.com | …836d | ✅ |
| 6 | ror577282@gmail.com | rnd_fqbD1eCk9PfDLPsAJrclx61GNX0Y | architect-llm-5mdk.onrender.com | …4437 | ✅ |
| 7 | argo7075@gmail.com | rnd_BqalN0xLZOtqwEHho67ZcZMRImbo | architect-llm-sdrh.onrender.com | …00ab | ✅ |
| 8 | vietnamsk064@gmail.com | rnd_PlYdJd5rbgGgbdsuFxv2Bv6ZkGLS | architect-llm-qarj.onrender.com | …43a9 | ✅ |

## OpenRouter — 8 аккаунтов (400 запросов/сутки)

| # | Ключ (маска) | Primary на сервисе |
|---|-------------|-------------------|
| 1 | sk-or-v1-…88f4 | Acc1 |
| 2 | sk-or-v1-…09d3 | Acc2 |
| 3 | sk-or-v1-…8ef8 | Acc3 |
| 4 | sk-or-v1-…9396 | Acc4 |
| 5 | sk-or-v1-…836d | Acc5 |
| 6 | sk-or-v1-…4437 | Acc6 |
| 7 | sk-or-v1-…00ab | Acc7 |
| 8 | sk-or-v1-…43a9 | Acc8 |

**Каждый LLM-сервис имеет ВСЕ 8 ключей:** 1 primary + 7 fallback.
Каскадное переключение: при 429/402 от текущего ключа → автоматический переход на следующий.

## Живые URL (подтверждены health check — 2026-08-12)

| Сервис | URL | Health |
|--------|-----|:------:|
| LLM Acc1 | https://architect-llm-s5q7.onrender.com | ✅ |
| LLM Acc2 | https://ai-arch-llmproxy.onrender.com | ✅ |
| LLM Acc3 | https://architect-llm-zczl.onrender.com | ✅ |
| LLM Acc4 | https://architect-llm-1s1j.onrender.com | ✅ |
| LLM Acc5 | https://architect-llm-2pmo.onrender.com | ✅ |
| LLM Acc6 | https://architect-llm-5mdk.onrender.com | ✅ |
| LLM Acc7 | https://architect-llm-sdrh.onrender.com | ✅ |
| LLM Acc8 | https://architect-llm-qarj.onrender.com | ✅ |
| Gateway | https://architect-gateway.onrender.com | ✅ |
| Blender | https://ai-arch-blender3d.onrender.com | ✅ |
| Blender #2 | https://architect-blender.onrender.com | ✅ |

## Env переменные для LLM Service (едины для всех 8 аккаунтов)

```bash
PORT=8081
OPENROUTER_BASE=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=<unique primary per account>
OPENROUTER_FALLBACK_KEYS=<7 other keys, comma-separated>
GOOGLE_API_KEY=<unique Google key per account>
GOOGLE_FALLBACK_KEYS=<7 other Google keys>
GEMINI_MODEL=gemini-2.0-flash-lite-001
KEY_COOLDOWN_RATE_LIMIT_SEC=60
KEY_COOLDOWN_QUOTA_SEC=86400
```

## Env переменные для Gateway (Аккаунт 4)

```bash
PORT=10000
LLM_SERVICE_URL=https://architect-llm-1s1j.onrender.com
BLENDER_SERVICE_URL=https://ai-arch-blender3d.onrender.com
BLENDER_SERVICE_URL_2=https://architect-blender.onrender.com
CORS_ORIGINS=https://smartmoneymoscow-cell.github.io
ARCH_API_KEYS=arch-prod-key-2024
```
