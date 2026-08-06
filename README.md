# Architect v10.5.0 — AI Architecture Generator

Генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Что нового в v10.5.0

- **Render pipeline fix** — исправлен критический баг: render_agent получал неправильные параметры (`geometry_script` вместо `script`, отсутствовал `blender_service_url`)
- **Denoising fix** — отключён OpenImageDenoiser (недоступен на Render free tier), используется Cycles CPU без шумоподавления
- **Bathroom furniture** — добавлены: jacuzzi, shower, shower_cabin, toilet, mirror, cabinet, faucet, washing_machine, dryer, bidet, towel_rack, double_bed, tv, sofa_bed, dining_table, kitchen_counter, fridge
- **Russian→English mapping** — автоматическая конвертация русских названий мебели (кровать→bed, джакузи→jacuzzi, душ→shower и т.д.)
- **File download endpoint** — `/api/v1/files/{path}` для скачивания рендеров с Blender сервиса
- **return_file parameter** — `/api/v1/execute` может возвращать файл напрямую (PNG, GLB)
- **Kaggle GPU Renderer** — документация по настройке Kaggle T4 GPU для рендеринга
- **CV-тестирование** — полный анализ компьютерным зрением (mimo-omni) всех скриншотов

## Баги исправленные в v10.5.0

| Баг | Описание | Фикс |
|-----|----------|------|
| Render null image_path | render_agent не получал script и blender_service_url | orchestrator передаёт правильные параметры |
| OIDN not available | Blender на Render не имеет OpenImageDenoiser | use_denoising=False для всех пресетов |
| Мебель не маппится | Русские названия (кровать, джакузи) не конвертировались | Добавлен RU→EN маппинг |
| Нет bathroom furniture | jacuzzi, shower, toilet отсутствовали в VALID_FURNITURE | Добавлены 15+ новых items |
| Нет file download | Рендеры оставались на сервере | Добавлен /api/v1/files endpoint |

## CV-тест результаты (mimo-omni)

| Проверка | Статус |
|----------|--------|
| LLM парсит промты | ✅ Все 6 промтов корректно |
| Reasoning в чате | ✅ Пошаговый процесс |
| Декомпозиция задач | ✅ 5 этапов |
| Уточняющие вопросы | ✅ Качество (Премиум/Стандарт/Быстрый) |
| Чипсины подсказки | ✅ Дом, Офис, Коттедж |
| Адаптивность | ✅ Поле ввода не обрезается |
| 3D модель генерируется | ⚠️ Работает с фиксом |
| Текстуры | ⚠️ Базовые, нужен Kaggle GPU |
| Качество рендера | ⚠️ 4/10 (CPU), улучшится с GPU |
