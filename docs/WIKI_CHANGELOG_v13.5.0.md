# Changelog — AI_Arhitector v13.5.0

## v13.5.0 — 2026-08-23

### Frontend: Projects Panel Closed by Default + Wiki Update

**Изменения:**
- 🔧 Projects sidebar теперь закрыт по умолчанию (Lovable-style UI)
- 📝 Обновлена wiki-документация до v13.5.0
- 🏗 Добавлена полная архитектурная схема системы
- 📊 Добавлены результаты тестирования промтов
- 🔄 Синхронизированы все frontend файлы (index.html, full_page.html, frontend/index.html)

**Файлы:**
- `frontend/index.html` — projectsOpen=false, collapsed class
- `index.html` — синхронизирован с frontend
- `full_page.html` — синхронизирован с frontend
- `docs/WIKI_v13.5.0.md` — полная документация
- `docs/WIKI_CHANGELOG_v13.5.0.md` — этот файл

**Тестирование:**
- ✅ LLM парсинг: 5/5 промтов корректны
- ✅ Gateway: health check OK
- ✅ LLM Service: 3/3 instances alive
- ✅ Blender Service: health check OK
- ✅ Fast GLB generation: работает (trimesh fallback)

---

## v13.4.0 — 2026-08-22

### Fast GLB Generation + Trimesh Fallback

**Изменения:**
- 🚀 Новый endpoint `/api/v1/generate/fast` — быстрая генерация GLB через trimesh
- 🔄 Trimesh fallback когда Blender недоступен
- 🎯 Auto-discovery Blender URL в Gateway
- 📱 Backend URL configuration в UI

---

## v13.3.0 — 2026-08-21

### Multi-Backend Fallback + Circuit Breaker

**Изменения:**
- 🔌 Multi-backend fallback для frontend
- ⚡ Circuit breaker для всех сервисов
- 🔄 Round-robin load balancing для Blender
- 📊 Key rotation monitoring

---

## v13.2.0 — 2026-08-20

### Chat Endpoint + Orchestrator Resume

**Изменения:**
- 💬 Новый endpoint `/api/v1/chat` — чат с LLM
- 🔄 Orchestrator resume после clarification
- 🎨 Pipeline profile auto-detection
- 📋 Agent results summary в UI

---

## v13.1.0 — 2026-08-19

### Full LLM Cascade + Key Rotation

**Изменения:**
- 🔑 Полный LLM каскад: Groq → Gemini → DeepSeek → OpenRouter
- 🔄 Key rotation с cooldown (429/quota)
- 📊 Proactive health loop каждые 30 мин
- 🎯 Auto-discovery бесплатных моделей OpenRouter

---

## v13.0.0 — 2026-08-18

### Major Release: 30+ Agents + Kaggle GPU

**Изменения:**
- 🤖 30+ изолированных агентов в agent-pool
- 🎮 Kaggle GPU rendering (T4/P100)
- 🏗 10 pipeline профилей (quick→premium)
- 📐 SVG drawings generation
- 🔧 MEP/Structural/Compliance агенты
- 📊 Quality gate с retry для 16K
