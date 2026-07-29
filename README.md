# Architect v11.0 🏗️

AI-архитектор — генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Что нового в v11.0

### Архитектурные изменения
- **Единый `shared/` пакет** — парсер, валидация, конфигурация и генерация bpy-скриптов в одном месте. Ноль дублирования.
- **Улучшенные bpy-скрипты** — PBR-материалы, окна с рамами и подоконниками, лестницы, водосточные трубы, карнизы, fill-освещение.
- **Исправленный фронтенд** — обработка ошибок Three.js, таймауты, graceful fallback при недоступности сервера.
- **Единая конфигурация** — `.env.example`, один `Settings` объект для всех сервисов.
- **Удалён мёртвый код** — патчи, дублированные парсеры, неиспользуемые тестовые файлы.

### Структура проекта

```
AI_Arhitector/
├── shared/                    # 🆕 Единая библиотека
│   ├── __init__.py
│   ├── config.py              # Настройки из env
│   ├── models.py              # Pydantic-модели
│   ├── validation.py          # Валидация параметров
│   ├── parser.py              # LLM + regex парсер
│   └── blender.py             # Генерация bpy-скриптов
├── gateway/                   # API Gateway (маршрутизация)
├── llm-service/               # LLM прокси + парсинг
├── blender-service/           # Генерация 3D через Blender CLI
├── frontend/                  # Веб-интерфейс
├── server.py                  # Монолит для локальной разработки
├── index.html                 # Фронтенд (GitHub Pages)
├── docker-compose.yml         # Docker Compose
├── render.yaml                # Деплой на Render
├── .env.example               # 🆕 Шаблон переменных окружения
└── tests/                     # Тесты
```

## Быстрый старт

### Онлайн (GitHub Pages)

1. Откройте сайт
2. Нажмите ⚙️ Настройки → введите OpenRouter API ключ от [openrouter.ai/keys](https://openrouter.ai/keys)
3. Опишите здание или интерьер

> ⚠️ На GitHub Pages работает только Three.js рендер (без Blender). Для полного функционала нужен бэкенд.

### Локальный сервер (полный функционал)

```bash
# Установить зависимости
pip install fastapi uvicorn httpx pydantic

# Установить Blender (Ubuntu/Debian)
sudo apt install blender

# Скопировать .env.example и заполнить
cp .env.example .env
# Редактировать .env → ввести OPENROUTER_API_KEY

# Запустить
python server.py
# → http://localhost:8080
```

### Docker Compose

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
docker-compose up --build
# → http://localhost:8080
```

### Render.com (деплой)

1. Зайдите на [render.com](https://render.com) → New → Blueprint
2. Подключите репозиторий
3. Render автоматически создаст сервисы из `render.yaml`
4. В сервисе `ai-arch-llmproxy` добавьте `OPENROUTER_API_KEY`
5. Нажмите Apply (~5-10 мин)

## Архитектура

### Микросервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| `gateway` | 8080 | API Gateway — маршрутизация, статика |
| `llm-service` | 8081 | LLM прокси (OpenRouter) + парсинг промтов |
| `blender-service` | 8082 | Генерация 3D через Blender CLI |

### Shared пакет

Все сервисы используют `shared/` — единый источник правды:
- `shared.config.settings` — конфигурация из env
- `shared.models` — Pydantic-модели запросов/ответов
- `shared.validation` — валидация и нормализация параметров
- `shared.parser` — LLM + regex парсинг промтов
- `shared.blender` — генерация улучшенных bpy-скриптов

### Pipeline генерации

```
Промт → LLM Парсинг → Валидация → Роутинг → bpy-скрипт → Blender CLI → GLB/PNG
         ↓ (fallback)
       Regex → Валидация → Three.js (локально)
```

## API

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/generate` | POST | Единый: текст → GLB/PNG |
| `/api/v1/parse` | POST | Текст → структурированные параметры |
| `/api/v1/generate/building` | POST | Текст → GLB (legacy) |
| `/api/v1/render/interior` | POST | Текст → PNG (legacy) |
| `/health` | GET | Health check |

## Переменные окружения

См. [`.env.example`](.env.example) для полного списка.

| Переменная | Обязательна | Описание |
|-----------|-------------|----------|
| `OPENROUTER_API_KEY` | Да | Ключ от openrouter.ai |
| `LLM_MODEL` | Нет | Модель (по умолчанию: бесплатная) |
| `BLENDER_PATH` | Нет | Путь к Blender |
| `PORT` | Нет | Порт сервера (8080) |

## Лицензия

MIT
