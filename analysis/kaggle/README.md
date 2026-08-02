# Kaggle GPU — Blender 4.0.2 Renderer

## ✅ Статус: РАБОТАЕТ

**GPU:** Tesla P100-PCIE-16GB (Kaggle Free)
**Blender:** 4.0.2 portable (OptiX)
**1080p 256 samples:** 25.8 секунд

## Режимы

| Режим | Разрешение | Samples | Время (оценка) | Тайлы |
|-------|-----------|---------|----------------|-------|
| **4K** | 3840×2160 | 256 | ~1.5 мин | 1 |
| **8K** | 7680×4320 | 256 | ~6 мин | 4 (2×2) |
| **16K** | 15360×8640 | 2048 | ~18 мин | 12 (4×3) |

## Запуск

```bash
python3 blender_render_kaggle.py --quality 4k
python3 blender_render_kaggle.py --quality 8k
python3 blender_render_kaggle.py --quality 16k
```

## Kaggle Setup

1. Верифицировать телефон на https://www.kaggle.com/settings/account
2. Kernel settings: GPU = P100, Internet = On
3. Запустить `blender_render_kaggle.py`

Аккаунт: `hungerrrr2222`

## Важно

**НЕ использовать apt-get install blender** — ставит Blender 3.0.1 со сломанным color management (чёрные картинки). Скрипт скачивает Blender 4.0.2 portable автоматически.

## Файлы

| Файл | Назначение |
|------|-----------|
| `blender_render_kaggle.py` | Основной рендер (4K/8K/16K) |
| `kaggle_renderer.py` | Gateway модуль |
| `gateway_kaggle_endpoint.py` | FastAPI endpoint |
| `parallel_dispatcher.py` | Параллельная диспетчеризация |
| `test_kaggle_integration.py` | Тесты |

## Gateway интеграция

```python
# gateway/app.py
from gateway_kaggle_endpoint import kaggle_router
app.include_router(kaggle_router)

# POST /api/v1/render/16k/kaggle
# GET  /api/v1/render/16k/kaggle/{job_id}
```
