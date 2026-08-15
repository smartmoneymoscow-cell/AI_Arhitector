# 🔧 Фиксы для AI_Arhitector — Pipeline Reliability

## Проблема

Все генерации интерьеров падают с ошибкой "Сервер рендеринга недоступен".
Root cause: LLM parse endpoint таймаутит → Blender получает 503 → фронтенд показывает ошибку.

## Фикс 1: Blender → LLM retry (blender-service/app.py)

**Файл:** `fix_1_blender_retry.py`

**Что меняет:** `_parse_via_llm_service()` — 3 попытки с таймаутами 15с → 30с → 60с.
Сейчас: 1 попытка, 15 сек, сразу 503.

**Применение:**
```python
# В blender-service/app.py заменить _parse_via_llm_service на версию из fix_1_blender_retry.py
```

## Фикс 2: Keep-alive daemon

**Файл:** `keep-alive.sh`

**Что делает:** Пингует health endpoints каждые 10 минут.
Render Free Tier засыпает через 15 мин бездействия → cold start 30-60 сек.

**Применение:**
```bash
# Cron (на любом сервере или GitHub Actions)
*/10 * * * * /path/to/keep-alive.sh --once

# Или как daemon
nohup ./keep-alive.sh &
```

## Фикс 3: Gateway graceful degradation (gateway/app.py)

**Файл:** `fix_3_gateway_graceful.py`

**Что меняет:** `orchestrator_execute()` — вместо HTTP 500 возвращает HTTP 200 с partial result и понятным сообщением.

| Ошибка | Было | Стало |
|--------|------|-------|
| LLM недоступен | 500 internal | 200 `status: llm_unavailable` + hint |
| Таймаут | 500 internal | 200 `status: timeout` + retry_after |
| Blender недоступен | 500 internal | 200 `status: blender_unavailable` + hint |

## Фикс 4: LLM key probe (llm-service)

**Файл:** `fix_4_llm_key_probe.py`

**Что делает:**
- Probe всех Gemini ключей при старте (5 сек таймаут на ключ)
- Endpoint `GET /api/v1/keys/status` — мониторинг в реальном времени
- Proactive cooldown — помечает исчерпанные ключи

## Применение

```bash
# 1. Blender retry — править blender-service/app.py
# 2. Keep-alive — запустить cron
# 3. Gateway — править gateway/app.py
# 4. LLM probe — править shared/parser.py + llm-service/app.py
```

## ⚠️ ЗАПРЕЩЕНО

- Regex fallback
- Локальные парсеры
- Хардкод промтов
- Тихая подмена данных

→ См. `ANTI_PATTERNS.md`
