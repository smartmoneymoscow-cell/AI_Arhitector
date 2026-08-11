# CHANGELOG — AI_Arhitector

## v11.3.1 — Gateway Fix: GEOS libs + Frontend Cleanup

### Дата: 2026-08-11

### Проблема
Gateway не деплоился на Render (update_failed) из-за отсутствия GEOS C-библиотек, необходимых для `shapely`. Frontend содержал кнопки быстрого старта, которые были удалены ранее.

### Что исправлено

| # | Файл | Что | Исправление |
|---|------|-----|-------------|
| 1 | `gateway.Dockerfile` | `shashely` не мог импортироваться — нет `libgeos` | Добавлен `libgeos-dev` (builder) и `libgeos3 libgeos-c1v5` (runtime) |
| 2 | `index.html` | Кнопки быстрого старта (Дом, Офис, Коттедж, Интерьер) | Удалены из welcome screen и empty state |
| 3 | `index.html` | CSS `.quick-actions`, `.qa-btn`, `.qa-icon` | Удалены |
| 4 | `index.html` | i18n ключи `qaHouse`, `qaOffice`, `qaCottage`, `qaInterior` | Удалены из RU и EN |

### Визуальное тестирование (LIVE скриншоты)

| Скриншот | Результат |
|----------|-----------|
| fresh_01_main.png | ✅ Интерфейс рабочий, чистый |
| fresh_02_input.png | ✅ Ввод текста работает |
| fresh_03_sending.png | ⚠️ HTTP 401 — Gateway старый код требует API key |
| fresh_04_response.png | ⚠️ 3D не сгенерировался (та же причина) |

### Анализ PDF воздуховодов

DuctAnalysisAgent успешно проанализировал чертёж МРЭ-РД-ОВ4 (18MB, 56 листов):
- Извлечено 9 систем вентиляции
- 20+ типов воздуховодов (круглые Ø100-630, прямоугольные 100×200 — 800×500)
- 11 противодымных систем (ПД1-ПД10)
- 12 типов клапанов (OKL-2-90, ПРОК, KPU-1N и др.)
- Полная спецификация по ГОСТ 21.1101
- Нормативная база: СП 60.13330, СП 7.13130, СП 253.1325800

---

## v11.3.0 — Duct Analysis Agent + 8-Account Architecture

### Дата: 2026-08-11

### Новые возможности
- DuctAnalysisAgent (800+ строк) — анализ чертежей воздуховодов
- 31 агент в реестре (было 30)
- Pipeline profiles: `duct_analysis`, `document_analysis`
- Репозиторий публичный (Render auto-deploy)
- Python 3.12 Dockerfiles

### Инфраструктура
- Account #2: 8 сервисов LIVE
- Account #4: 3 сервиса (Gateway, LLM, Blender)
- LLM обновлён до нового кода
- Kaggle T4 GPU для рендера

### Известные проблемы
- Gateway update_failed → исправлено в v11.3.1 (GEOS libs)
- Blender build_failed → не нужен, Kaggle T4 отрабатывает
