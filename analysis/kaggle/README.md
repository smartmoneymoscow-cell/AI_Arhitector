# Kaggle T4/P100 GPU — Blender Cycles Renderer

## Статус: ✅ Работает

**GPU:** Tesla P100-PCIE-16GB (Kaggle Free)
**Blender:** apt-get install blender (35 сек установка)
**Cycles CUDA:** ✅ OptiX недоступен на P100, CUDA работает

## Режимы рендера

| Режим | Разрешение | Samples | Время | Тайлы |
|-------|-----------|---------|-------|-------|
| **4K** (по умолчанию) | 3840×2160 | 256 | ~2 мин | 1 |
| **8K** | 7680×4320 | 256 | ~8 мин | 4 (2×2) |
| **16K** | 15360×8640 | 2048 | ~18 мин | 12 (4×3) |

## Запуск

```bash
# 4K (быстро, по умолчанию)
python3 blender_render_kaggle.py --quality 4k

# 8K
python3 blender_render_kaggle.py --quality 8k

# 16K
python3 blender_render_kaggle.py --quality 16k
```

## Kaggle Setup

Аккаунт: `hungerrrr2222`
Требуется: верификация телефона для GPU

```bash
export KAGGLE_API_TOKEN="KGAT_..."
kaggle kernels push -p kernel_dir/
```

## Файлы

| Файл | Назначение |
|------|-----------|
| `blender_render_kaggle.py` | Основной скрипт рендера (4K/8K/16K) |
| `kaggle_renderer.py` | Python-модуль для Gateway интеграции |
| `gateway_kaggle_endpoint.py` | FastAPI endpoint |
| `parallel_dispatcher.py` | Параллельная диспетчеризация по аккаунтам |
| `test_kaggle_integration.py` | Тесты |

## Тестовые результаты

| Тест | Статус |
|------|--------|
| GPU (P100 16GB) | ✅ |
| Internet (PyPI) | ✅ |
| Blender install | ✅ (35 сек) |
| Cycles CUDA render | ✅ |
| 4K output | ✅ |
