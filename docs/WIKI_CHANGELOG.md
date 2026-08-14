# Changelog — AI_Arhitector (Wiki)

## v11.5.0 — 2026-08-14

### Pipeline Timeouts Fix + GLB URL + Deploy Fix

**Исправлено:**
- OpenRouter discovery зависает → streaming с 2MB limit
- Cascade timeout 30s → 3s на модель
- GEMINI_MODEL default неверный → gemini-2.0-flash-lite-001
- GLB URL с двойным слешем → cleanPath fix
- Auth middleware блокирует запросы → исправлено
- Blender fallback не работает → добавлена логика
- Deploy workflow exit code 127 → shell: bash + PATH fix

**Коммиты:** e3801af, b61503d, 41b53bd, e6c6cf8

---

## v11.4.0 — 2026-08-12

### 8-Account OpenRouter Cascade

- OpenRouter: 5 → 8 ключей (400 запросов/сутки)
- Каскад: 1 primary + 7 fallback
- 18 живых сервисов на 8 Render-аккаунтах

---

## v11.3.2 — 2026-08-12

### Gemini Direct Integration + Proactive Health Check

- Модель: gemini-2.0-flash-lite-001 → gemini-3.1-flash-lite
- Proactive key health loop каждые 30 мин

---

## v11.3.1 — 2026-08-11

### Gateway Fix: GEOS libs + Frontend Cleanup

- Dockerfile: libgeos-dev для shapely
- Удалены кнопки быстрого старта

---

## v11.3.0 — 2026-08-11

### Duct Analysis Agent

- DuctAnalysisAgent (800+ строк)
- 31 агент в реестре
