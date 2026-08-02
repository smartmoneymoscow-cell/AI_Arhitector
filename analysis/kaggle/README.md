# AI_Arhitector — Kaggle GPU Renderer

## ✅ Pipeline

```
Промт → LLM → Asset Loader → Scene Builder → Cycles GPU → Compositor → PNG
         parse   PBR+HDRI+GLB   geometry+     P100 OptiX   Glare+CB    
                                       materials
```

## Архитектура

| Компонент | Файл | Назначение |
|-----------|------|-----------|
| **Asset Downloader** | `download_assets.py` | Скачивание PBR + HDRI + GLB с Poly Haven |
| **Asset Loader** | `asset_loader.py` | PBR материалы, HDRI, импорт GLB в Blender |
| **Enhanced Render** | `enhanced_render.py` | Полный пайплайн: геометрия + PBR + HDRI + мебель + compositor |
| **Blender Render** | `blender_render_kaggle.py` | Базовый рендер 4K/8K/16K |
| **Gateway Endpoint** | `gateway_kaggle_endpoint.py` | API для интеграции с Gateway |
| **Parallel Dispatcher** | `parallel_dispatcher.py` | Мульти-аккаунт диспетчер |

## Режимы

| Режим | Разрешение | Samples | Время |
|-------|-----------|---------|-------|
| 4K | 3840×2160 | 256 | ~2 мин |
| 8K | 7680×4320 | 256 | ~8 мин |
| 16K | 15360×8640 | 2048 | ~18 мин |

## Запуск

```bash
# 1. Скачать ассеты (один раз)
python3 download_assets.py --output ./assets

# 2. Загрузить как Kaggle dataset: architect-assets

# 3. Рендер
python3 enhanced_render.py --quality 4k --scene exterior
python3 enhanced_render.py --quality 4k --scene interior --room living
python3 enhanced_render.py --quality 16k --scene exterior
```

## Источники ассетов (CC0)

| Источник | Тип | Лицензия |
|----------|-----|----------|
| Poly Haven | PBR текстуры, HDRI, модели | CC0 |
| ambientCG | PBR текстуры | CC0 |
| Quaternius | 3D модели | CC0 |

## Kaggle Setup

1. Верифицировать телефон на kaggle.com/settings/account
2. Kernel: GPU = P100, Internet = On
3. Dataset: `architect-assets` (загруженный)
