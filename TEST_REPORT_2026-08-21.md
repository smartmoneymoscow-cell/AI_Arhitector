# Architect AI — Комплексный отчёт тестирования
**Дата:** 2026-08-21
**Тестер:** AI Assistant

---

## 1. Статус живых сервисов

| Сервис | URL | Статус |
|--------|-----|--------|
| Gateway | architect-gateway-3guo.onrender.com | ✅ Alive (200) |
| LLM #1 | architect-llm-s5q7.onrender.com | ✅ Alive (200) |
| LLM #2 | architect-llm-zczl.onrender.com | ✅ Alive (200) |
| LLM #3 | architect-llm-2pmo.onrender.com | ⚠️ Slow |
| LLM #4 | architect-llm-5mdk.onrender.com | ✅ Alive (200) |
| Blender | ai-arch-blender3d.onrender.com | ✅ Alive (200) |
| Gateway (old) | architect-gateway.onrender.com | ❌ Suspended (503) |
| Blender (old) | architect-blender.onrender.com | ❌ Suspended (503) |

---

## 2. Тестирование GitHub Pages сайта

### 2.1 Структура страницы
- ✅ Title: "Architect — AI Architecture Generator"
- ✅ Three.js загружен
- ✅ Canvas для 3D (1 шт)
- ✅ Chat panel с полем ввода
- ✅ Projects panel
- ✅ Top bar с кнопками
- ✅ 25 кнопок на странице

### 2.2 Визуальные тесты
- ✅ Главная страница загружается корректно
- ✅ Поле ввода работает
- ✅ Кнопка отправки работает
- ⚠️ 404 ошибка при загрузке ресурса (favicon)

### 2.3 Тесты генерации по промтам

| Промт | Парсинг | Генерация | 3D модель |
|-------|---------|-----------|-----------|
| "Построй двухэтажный кирпичный дом 10x12" | ✅ | ⚠️ clarification_needed | ❌ |
| "Маленькая комната 4x5 в стиле лофт" | ✅ | ❌ timeout | ❌ |
| "ванная комната хайтек с джакузи 3x4" | ✅ | ❌ failed | ❌ |
| "простой дом 6x8 1 этаж" (direct blender) | ✅ | ✅ GLB создан | ✅ |

---

## 3. Тестирование API

### 3.1 LLM Parse (прямой вызов)
```bash
curl -X POST "https://architect-llm-s5q7.onrender.com/api/v1/parse" \
  -d '{"text":"дом 2 этажа кирпичный 10x12"}'
```
**Результат:** ✅ 200 OK, корректный JSON с параметрами

### 3.2 Blender Generate (прямой вызов)
```bash
curl -X POST "https://ai-arch-blender3d.onrender.com/api/v1/generate" \
  -d '{"prompt":"простой дом 6x8"}'
```
**Результат:** ✅ 200 OK, GLB файл (28KB)

### 3.3 Orchestrator Execute
```bash
curl -X POST "https://architect-gateway-3guo.onrender.com/api/v1/orchestrator/execute" \
  -d '{"prompt":"дом 2 этажа","skip_clarification":true}'
```
**Результат:** ✅ status=done, но exports={} (пусто)

### 3.4 Gateway Generate (требует API key)
```bash
curl -X POST "https://architect-gateway-3guo.onrender.com/api/v1/generate" \
  -d '{"prompt":"дом"}'
```
**Результат:** ❌ 401 Missing API key

---

## 4. Выявленные проблемы

### 4.1 Критические
1. **Оркестратор не экспортирует GLB** — все шаги done, но exports={}
2. **Generate endpoint требует API key** — фронтенд не может вызвать напрямую
3. **CORS блокирует прямые вызовы** с localhost к Render сервисам

### 4.2 Средние
4. **Clarification flow не работает** — фронтенд показывает "модель не создана" вместо вопросов
5. **Render сервисы могут уснуть** — free tier auto-suspend после 15 мин
6. **Gateway parse timeout** — LLM сервис может не отвечать >60с

### 4.3 Минорные
7. **404 на favicon** — не критично
8. **3 копии index.html** — дедупликация нужна

---

## 5. Исправления (применены локально)

### 5.1 Фронтенд: skip_clarification=true
```javascript
// Было:
skip_clarification: false,
// Стало:
skip_clarification: true,
```

### 5.2 Фронтенд: Fallback на прямой blender
```javascript
// Добавлен fallback в _handleOrchestratorResult:
const genR = await fetch(API_BASE + '/api/v1/generate', {
  method: 'POST',
  headers: _apiHeaders(),
  body: JSON.stringify({prompt: prompt, quality: 'standard'})
});
```

### 5.3 Упрощённый фронтенд (simple.html)
Создан автономный фронтенд без зависимости от оркестратора.

---

## 6. Рекомендации

1. **Push исправлений на GitHub** — нужен PAT для деплоя
2. **Настроить ARCH_API_KEYS** в gateway для generate endpoint
3. **Добавить CORS_ORIGINS** для localhost в разработке
4. **Проверить Kaggle Blender** — ноутбук может быть не запущен
5. **Мониторинг Render** — сервисы могут уснуть

---

## 7. Kaggle Blender

### Конфигурация
- Slug: `hungerrrr2222/archai-blender-gpu-renderer`
- GPU: T4 (free tier)
- Режим: Polling или ngrok

### Статус
⚠️ Требуется проверка — ноутбук может быть не активен.
Для проверки: `kaggle kernels status hungerrrr2222/archai-blender-gpu-renderer`
