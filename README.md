# Architect v10.2 🏗️

AI-архитектор — генерация 3D-моделей зданий и интерьеров по текстовому описанию на русском языке.

## Быстрый старт

1. Откройте сайт
2. Нажмите **⚙️ Настройки** → введите OpenRouter API ключ (`sk-or-v1-...`) от [openrouter.ai/keys](https://openrouter.ai/keys)
3. Опишите здание: *двухэтажный кирпичный дом 10×12*, *офис 5 этажей стекло*, *коттедж с террасой*

> Бесплатные модели работают без баланса, но ключ обязателен.

---

## Деплой

### Render.com (рекомендуется)

Микросервисная архитектура: Gateway + LLM + Blender — всё на Render Free Tier.

1. Зайдите на [render.com](https://render.com) → **New** → **Blueprint**
2. Подключите репозиторий `smartmoneymoscow-cell/AI_Arhitector`
3. Render автоматически создаст 3 сервиса из `render.yaml`:
   - `architect-gateway` — фронтенд + маршрутизация (`:8080`)
   - `architect-llm` — прокси к OpenRouter (`:8081`)
   - `architect-blender` — рендер зданий/интерьеров через Blender (`:8082`)
4. В сервисе **architect-llm** добавьте переменную окружения:
   - `OPENROUTER_API_KEY` = `sk-or-v1-...`
5. Нажмите **Apply** и дождитесь деплоя (~5-10 мин)

> ⚠️ Render Free Tier: сервисы засыпают после 15 мин неактивности. Первый запрос разбудит их за 30-60 сек.

### GitHub Pages (только фронтенд)

Сервис работает в браузере. Three.js рендерит 3D локально, OpenRouter API вызывается напрямую. **Blender-рендеринг недоступен** (нет бэкенда).

### Локальный сервер (полный функционал)

```bash
# Установить зависимости
pip install flask flask-cors httpx

# Установить Blender (Ubuntu/Debian)
sudo apt install blender

# Запустить
export OPENROUTER_API_KEY="sk-or-v1-..."
export BLENDER_PATH="blender"
python server.py
# → http://localhost:8080
```

#### С портативным Blender (без sudo)

```bash
# Скачать Blender 3.6 LTS
curl -L -o blender.tar.xz "https://download.blender.org/release/Blender3.6/blender-3.6.5-linux-x64.tar.xz"
tar xf blender.tar.xz

# Запустить
export BLENDER_PATH="$PWD/blender-3.6.5-linux-x64/blender"
export LD_LIBRARY_PATH="$PWD/blender-3.6.5-linux-x64/lib:$LD_LIBRARY_PATH"
export OPENROUTER_API_KEY="sk-or-v1-..."
python server.py
```

---

## Архитектура

### Микросервисы (Render)

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (index.html)                      │
│  Chat UI │ 3D View (Three.js) │ 2D Plan │ Settings (⚙️)     │
└────────────────────────┬────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │ Gateway │  architect-gateway.onrender.com
                    │  :8080  │  Маршрутизация + статика
                    └────┬────┘
                         │
              ┌──────────┴──────────┐
              │                     │
        ┌─────▼─────┐        ┌─────▼──────┐
        │ LLM Proxy  │        │  Blender   │
        │  :8081     │        │  Service   │
        │            │        │  :8082     │
        │ OpenRouter │        │            │
        └────────────┘        │ ┌────────┐│
                              │ │Blender ││
                              │ │  CLI   ││
                              │ └────────┘│
                              └───────────┘
```

### Эндпоинты

| Endpoint | Сервис | Описание |
|----------|--------|----------|
| `GET /` | Gateway | Фронтенд |
| `GET /api/v1/health` | Gateway | Health check (проверяет LLM + Blender) |
| `POST /api/v1/proxy/claude` | Gateway → LLM | Прокси к OpenRouter |
| `POST /api/v1/generate/building` | Gateway → Blender | Текст → GLB (3D модель) |
| `POST /api/v1/render/interior` | Gateway → Blender | Параметры → PNG (рендер интерьера) |

### Потоки генерации

**Здание (из чата):**
```
Текст → parseLocal() → Three.js (браузер)
                     ↘ Blender Server → GLB (fallback)
```

**Интерьер (из чата):**
```
Текст → INTERIOR_RE match → parseInteriorParams()
      → /api/v1/render/interior → Blender → PNG
```

**Фото:**
```
Изображение → analyzeImage() (OpenRouter Vision)
            → parseLocal() + merge → Three.js
```

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Frontend | HTML/CSS/JS, Three.js r160 |
| Gateway | Flask, Python 3.11 |
| LLM Proxy | Flask, httpx → OpenRouter API |
| Blender Service | Flask, Blender 3.6 CLI, Xvfb |
| AI (free) | OpenRouter: nemotron-nano-9b-v2, gemma-4-31b-it |
| AI (vision) | OpenRouter: nemotron-nano-12b-v2-vl |
| 3D рендер | Three.js (браузер) + Blender CLI (сервер) |
| Хранение | localStorage (ключ, URL) |
| Деплой | Render.com (Docker, Free Tier) |

## Структура проекта

```
AI_Arhitector/
├── index.html                  # Основной фронтенд (SPA)
├── server.py                   # Монолитный сервер (для локального запуска)
├── render.yaml                 # Render Blueprint (3 сервиса)
├── frontend/
│   └── index.html              # Фронтенд для Gateway (Docker)
├── gateway/
│   ├── Dockerfile
│   ├── app.py                  # Gateway: маршрутизация + статика
│   └── requirements.txt
├── llm-service/
│   ├── Dockerfile
│   ├── app.py                  # LLM: прокси к OpenRouter
│   └── requirements.txt
├── blender-service/
│   ├── Dockerfile
│   ├── app.py                  # Blender: генерация зданий + интерьеров
│   └── requirements.txt
├── blender/
│   ├── blenderllm_bridge.py    # BlenderLLM ↔ bpy bridge
│   ├── generate_building.py    # Параметры → bpy → GLB
│   ├── render_interior.py      # Стиль → bpy → PNG
│   └── server.py               # Blender GUI API
├── colab/
│   └── ArchAI_Blender.ipynb    # Google Colab notebook
└── output/                     # Сгенерированные модели
```

## Функции

- 🏠 **3D-генерация** зданий по тексту (Three.js + Blender GLB)
- 📐 **2D-планы** этажей
- 🛋 **Интерьеры** с пресетами стилей (modern, classic, scandinavian, loft, minimalist)
- 📷 **Анализ фото** (загрузка изображений → Vision AI)
- 🎤 **Голосовой ввод** (Web Speech API, RU)
- 🔄 Поворот, зум, навигация по этажам
- ⚙️ Настройки API ключа и backend URL

## Лицензия

Проект открытый. Автор: [smartmoneymoscow-cell](https://github.com/smartmoneymoscow-cell)
# deploy trigger Sun Jul 26 23:06:38 CST 2026
