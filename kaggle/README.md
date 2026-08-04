# 🖥️ Kaggle GPU Renderer для AI Architect

GPU-рендер Blender на Kaggle (T4/P100) как fallback для Render.

## Архитектура

```
Gateway (Render) ──┬── Blender #1 (Render)    ← основной
                   ├── Blender #2 (Render)    ← failover
                   └── Kaggle GPU (T4/P100)   ← fallback
                        │
                        ├── ngrok-режим: Gateway → ngrok URL → Kaggle
                        └── polling-режим: Kaggle → Gateway /pending → рендер → /result
```

## Быстрый старт (ngrok)

1. Зарегистрируйтесь на [ngrok.com](https://ngrok.com) (бесплатно)
2. Скопируйте authtoken
3. Откройте ноутбук `kaggle/blender_gpu_renderer.ipynb` на Kaggle
4. Включите GPU (Settings → Accelerator → GPU T4)
5. Вставьте ngrok token в ячейку "Настройка ngrok"
6. Запустите все ячейки
7. Скопируйте публичный URL
8. Добавьте в Render env: `KAGGLE_RENDERER_URL=<url>`

## Быстрый старт (polling, без ngrok)

1. Откройте ноутбук на Kaggle с GPU
2. Запустите ячейки до "Polling-режим"
3. Запустите polling-ячейку
4. Ноутбук будет опрашивать Gateway на наличие задач

## API

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/health` | GET | Статус, GPU info, uptime |
| `/api/v1/generate` | POST | Рендер GLB из параметров |
| `/api/v1/preview` | POST | Рендер PNG превью |

## Лимиты Kaggle Free

| Ресурс | Лимит |
|--------|-------|
| GPU T4 | ~30 часов/неделю |
| Сессия | до 9 часов |
| Автоотключение | 60 мин бездействия |
| Память T4 | 16 GB VRAM |

## Gateway endpoints (polling mode)

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/kaggle/enqueue` | POST | Добавить задачу в очередь |
| `/api/v1/kaggle/pending` | GET | Получить следующую задачу (Kaggle poll) |
| `/api/v1/kaggle/result` | POST | Отправить результат |
| `/api/v1/kaggle/status/{id}` | GET | Статус задачи |
| `/api/v1/kaggle/health` | GET | Статус интеграции |
