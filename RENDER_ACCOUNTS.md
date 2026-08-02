# Render Accounts — Распределение по 5 аккаунтам

## Архитектура

```
Аккаунт 1                    Аккаунт 2                Аккаунт 3
┌─────────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ ai-arch-blender3d   │      │ (пусто)         │      │ (пусто)         │
│ ├── Blender CLI      │      │ Деплой Blender  │      │ Деплой Blender  │
│ ├── EEVEE 4K        │      │ #2 сюда         │      │ #3 сюда         │
│ └── GLB экспорт     │      └─────────────────┘      └─────────────────┘
└─────────────────────┘
        │
        │         Аккаунт 4                    Аккаунт 5
        │        ┌─────────────────────┐      ┌─────────────────┐
        │        │ architect-gateway    │      │ (пусто)         │
        └───────▶│ architect-blender    │      │ Деплой LLM      │
                 │ architect-llm        │      │ сюда            │
                 │ (полный стек!)       │      └─────────────────┘
                 └─────────────────────┘
```

## Таблица аккаунтов

| # | Render Аккаунт | URL сервиса | Render API Key | Что работает | План | Статус |
|---|----------------|-------------|----------------|--------------|------|--------|
| 1 | Render #1 — Blender #1 | `https://ai-arch-blender3d.onrender.com` | rnd_JN…LwTE | Blender CLI, EEVEE 4K, превью, GLB | starter | ✅ |
| 2 | Render #2 — (пусто) | — | rnd_EM…a3r8 | Не задеплоен. Деплой Blender #2 | — | ⬜ |
| 3 | Render #3 — (пусто) | — | rnd_aF…KycW | Не задеплоен. Деплой Blender #3 | — | ⬜ |
| 4 | Render #4 — Полный стек | `https://architect-gateway.onrender.com` | rnd_0m…ob6Y | Gateway + Blender + LLM (всё в одном) | starter | ✅ |
| 5 | Render #5 — (пусто) | — | rnd_RF…2a6l | Не задеплоен. Деплой LLM сюда. OpenRouter: sk-or-…0f9e | — | ⬜ |

## Живые URL (подтверждены health check)

| Сервис | URL | Health |
|--------|-----|--------|
| Blender #1 | https://ai-arch-blender3d.onrender.com | ✅ ok |
| Blender #2 (Акк 4) | https://architect-blender.onrender.com | ✅ ok |
| LLM (Акк 4) | https://architect-llm-1s1j.onrender.com | ✅ ok |
| Gateway (Акк 4) | https://architect-gateway.onrender.com | ✅ ok |
| LLM (Акк 1) | https://ai-arch-llmproxy.onrender.com | ❌ мёртв |

## Env переменные для Gateway (Аккаунт 4 — рабочий стек)

```bash
LLM_SERVICE_URL=https://architect-llm-1s1j.onrender.com
BLENDER_SERVICE_URL=https://ai-arch-blender3d.onrender.com
BLENDER_SERVICE_URL_2=https://architect-blender.onrender.com
REDIS_URL=<internal redis from account 4>
CORS_ORIGINS=https://smartmoneymoscow-cell.github.io
```

## Env переменные для LLM Service (Аккаунт 4)

```bash
OPENROUTER_API_KEY=sk-or-…0f9e
REDIS_URL=<internal redis from account 4>
PORT=8081
```

## План деплоя на пустые аккаунты

### Аккаунт 2 → Blender #2
```bash
# Repo: AI_Arhitector
# Dockerfile: blender.Dockerfile
# Env: PORT=8082, BLENDER_PATH=blender, OUTPUT_DIR=/app/output
```

### Аккаунт 3 → Blender #3 (16K tiled)
```bash
# Repo: AI_Arhitector
# Dockerfile: blender.Dockerfile
# Env: PORT=8082, BLENDER_PATH=blender, OUTPUT_DIR=/app/output
```

### Аккаунт 5 → LLM Service (backup)
```bash
# Repo: AI_Arhitector
# Dockerfile: llm.Dockerfile
# Env: PORT=8081, OPENROUTER_API_KEY=sk-or-…0f9e
```
