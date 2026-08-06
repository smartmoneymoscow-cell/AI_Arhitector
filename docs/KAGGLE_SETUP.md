# Kaggle GPU Renderer — Инструкция по настройке

## API Ключ Kaggle

```
KAGGLE_API_TOKEN=KGAT_b9977a84a45238ab9f714c48422b04d0
```

### Сохранение ключа

```bash
mkdir -p ~/.kaggle
echo 'KGAT_b9977a84a45238ab9f714c48422b04d0' > ~/.kaggle/access_token
chmod 600 ~/.kaggle/access_token
```

### Проверка

```bash
kaggle kernels list --mine
```

## Ноутбук

- **Slug:** `hungerrrr2222/archai-blender-gpu-renderer`
- **URL:** https://www.kaggle.com/code/hungerrrr2222/archai-blender-gpu-renderer
- **GPU:** T4 (free tier, ~30h/week)
- **Лимиты:** сессия до 9 часов, автоотключение 60 мин бездействия

### Запуск ноутбука

```bash
# Push обновлённого ноутбука
cd AI_Arhitector/kaggle
kaggle kernels push -p .

# Проверить статус
kaggle kernels status hungerrrr2222/archai-blender-gpu-renderer

# Скачать результат
kaggle kernels output hungerrrr2222/archai-blender-gpu-renderer -p ./output
```

## Режимы работы

### 1. Polling-режим (без ngrok)

Ноутбук сам опрашивает Gateway на наличие задач:

```
Gateway (Render) ←── Kaggle ноутбук (GPU T4)
  /api/v1/kaggle/pending   ← GET запрос от Kaggle
  /api/v1/kaggle/result    ← POST результат от Kaggle
```

**Env переменные Gateway:**
```
KAGGLE_RENDERER_URL=<не нужен для polling>
```

### 2. Ngrok-режим (прямое подключение)

Gateway отправляет запросы напрямую в Kaggle:

```
Gateway (Render) ──→ ngrok URL ──→ Kaggle ноутбук (GPU T4)
```

**Env переменные Gateway:**
```
KAGGLE_RENDERER_URL=https://xxxx.ngrok.io
```

**Ngrok token:** нужен бесплатный аккаунт на ngrok.com

## Использование в коде

### Прямой вызов Blender API на Kaggle

```python
import httpx

# Если ngrok запущен
kaggle_url = "https://xxxx.ngrok.io"

# Рендер
r = httpx.post(f"{kaggle_url}/api/v1/generate", json={
    "prompt": "ванная хайтек с джакузи",
    "quality": "standard"
}, timeout=300)
```

### Polling через Gateway

```bash
# Добавить задачу в очередь
curl -X POST https://architect-gateway.onrender.com/api/v1/kaggle/enqueue \
  -H "Content-Type: application/json" \
  -H "X-API-Key: arch-prod-key-2024" \
  -d '{"script": "...", "output_path": "/tmp/render.png"}'

# Проверить статус
curl https://architect-gateway.onrender.com/api/v1/kaggle/status/{job_id}
```

## Лимиты Kaggle Free Tier

| Ресурс | Лимит |
|--------|-------|
| GPU T4 | ~30 часов/неделю |
| Сессия | до 9 часов |
| Автоотключение | 60 мин бездействия |
| Память T4 | 16 GB VRAM |
| Интернет | ограничен (только Kaggle datasets) |

## Troubleshooting

### "Authentication required"
```bash
# Проверить что ключ сохранён
cat ~/.kaggle/access_token
# Должно быть: KGAT_b9977a84a45238ab9f714c48422b04d0

# Или через kaggle.json
cat ~/.kaggle/kaggle.json
# Должно быть: {"username":"hungerrrr2222","key":"KGAT_b9977a84a45238ab9f714c48422b04d0"}
```

### Ноутбук не запускается
```bash
# Проверить статус
kaggle kernels status hungerrrr2222/archai-blender-gpu-renderer

# Если "error" — посмотреть логи на kaggle.com
open https://www.kaggle.com/code/hungerrrr2222/archai-blender-gpu-renderer
```

### Gateway не видит Kaggle
```bash
# Проверить health
curl https://architect-gateway.onrender.com/api/v1/kaggle/health
```
