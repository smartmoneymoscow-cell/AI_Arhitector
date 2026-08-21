#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Render Environment Variables Setup — Full LLM Cascade
# ═══════════════════════════════════════════════════════════════
# Этот скрипт показывает какие env переменные нужно установить
# на Render для каждого LLM-сервиса.
#
# Каскад: Groq → Gemini → DeepSeek → OpenRouter → Ollama
# ═══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════"
echo "  Architect AI — Render Environment Setup"
echo "  Каскад: Groq → Gemini → DeepSeek → OpenRouter → Ollama"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Установите следующие env переменные в Render Dashboard"
echo "для КАЖДОГО LLM-сервиса (architect-llm-*):"
echo ""
echo "─── GROQ (ПЕРВЫЙ в каскаде, free tier) ───"
echo "GROQ_API_KEY=<groq_primary_key>"
echo "GROQ_FALLBACK_KEYS=<groq_key2>,<groq_key3>"
echo ""
echo "─── Google Gemini (БЕСПЛАТНО) ───"
echo "GOOGLE_API_KEY=<gemini_primary_key>"
echo "GOOGLE_FALLBACK_KEYS=<gemini_key2>,...,<gemini_key8>"
echo "GEMINI_MODEL=gemini-2.5-flash-lite"
echo ""
echo "─── DeepSeek (прямой API) ───"
echo "DEEPSEEK_API_KEY=<deepseek_primary_key>"
echo "DEEPSEEK_FALLBACK_KEYS=<deepseek_key2>,...,<deepseek_key8>"
echo ""
echo "─── OpenRouter (бесплатные модели) ───"
echo "OPENROUTER_API_KEY=<openrouter_primary_key>"
echo "OPENROUTER_FALLBACK_KEYS=<or_key2>,...,<or_key8>"
echo "OPENROUTER_BASE=https://openrouter.ai/api/v1"
echo ""
echo "─── Ollama (опционально, локальный) ───"
echo "# OLLAMA_URL=http://host.docker.internal:11434"
echo "# OLLAMA_MODEL=llama3.1:8b"
echo ""
echo "─── Другие ───"
echo "CORS_ORIGINS=https://smartmoneymoscow-cell.github.io,https://architect-gateway-3guo.onrender.com"
echo "REDIS_URL=redis://redis:6379/0"
echo "KEY_COOLDOWN_RATE_LIMIT_SEC=60"
echo "KEY_COOLDOWN_QUOTA_SEC=86400"
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  После установки переменных перезадеплойте сервисы:"
echo "  Render Dashboard → Service → Manual Deploy → Deploy latest"
echo "═══════════════════════════════════════════════════════════"
