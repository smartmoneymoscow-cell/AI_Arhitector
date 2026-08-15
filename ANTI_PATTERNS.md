# 🚫 ANTI-PATTERNS — ЗАПРЕЩЁННЫЕ ПРАКТИКИ

## REGEX FALLBACK — ABSOLUTELY FORBIDDEN

**Никогда, ни при каких обстоятельствах, не предлагать regex fallback для парсинга промтов.**

### Почему запрещён:
1. Код `shared/parser.py` содержит ЖЁСТКУЮ инструкцию:
   ```
   СТРОГОЕ ПРАВИЛО: Парсер РАБОТАЕТ ТОЛЬКО ЧЕРЕЗ LLM.
   Никаких regex fallback, хардкода, локальных парсеров.
   Если все LLM ключи упали → AllModelsFailedError.
   НИКОГДА не добавлять regex/local fallback в этот модуль.
   ```
2. Regex парсинг даёт ненадёжные, хрупкие результаты
3. Архитектурное решение: LLM-first, fail loud, не fail silently с мусором
4. Правильный подход: retry, key rotation, Ollama fallback, keep-alive

### Что делать вместо regex fallback:
- **Retry** с увеличивающимся таймаутом (15с → 30с → 60с)
- **Key rotation** — перебор всех Gemini/OpenRouter ключей
- **Ollama** — локальная модель как L4 fallback
- **Keep-alive** — cron-пинг для предотвращения cold start
- **Graceful degradation** — частичный результат, не мусорный парсинг
- **AllModelsFailedError** — честная ошибка, не подмена данных

### Если кто-то предлагает regex fallback:
1. Отказать немедленно
2. Указать на этот документ
3. Предложить альтернативы из списка выше

---
*Создано: 2026-08-15, после нарушения правила в сессии*
