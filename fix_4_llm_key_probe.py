"""
Фикс 4: LLM Service — Gemini key health probe + proactive cooldown.

Проблема: Gemini ключи исчерпываются молча, parse висит до таймаута.
Решение: proactive health check при старте + быстрый fail при исчерпании.
"""


# ═══ В shared/parser.py добавить: ═══

async def _probe_gemini_key(api_key: str) -> dict:
    """Быстрый probe Gemini ключа (1 сек таймаут)."""
    import httpx

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-001:generateContent?key={api_key}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                json={"contents": [{"parts": [{"text": "ping"}]}]},
                timeout=5.0,
            )
        if r.status_code == 200:
            return {"key": _mask_key(api_key), "alive": True}
        elif r.status_code == 429:
            return {"key": _mask_key(api_key), "alive": False, "reason": "rate_limited"}
        else:
            return {"key": _mask_key(api_key), "alive": False, "reason": f"http_{r.status_code}"}
    except Exception as e:
        return {"key": _mask_key(api_key), "alive": False, "reason": str(e)[:50]}


async def probe_all_gemini_keys() -> list[dict]:
    """Probe всех Gemini ключей. Вызывать при старте и по cron."""
    keys = _get_gemini_keys()
    if not keys:
        return []

    results = await asyncio.gather(*[_probe_gemini_key(k) for k in keys])
    alive = sum(1 for r in results if r["alive"])
    logger.info("Gemini key probe: %d/%d alive", alive, len(keys))

    # Помечаем мёртвые ключи
    for r in results:
        if not r["alive"] and r.get("reason") in ("rate_limited",):
            # Не помечаем как dead — это временно
            pass
        elif not r["alive"]:
            logger.warning("Gemini key dead: %s (%s)", r["key"], r.get("reason"))

    return results


# ═══ В startup event llm-service/app.py: ═══

@app.on_event("startup")
async def _on_startup():
    # ... существующий код ...

    # ═══ FIX: Probe Gemini ключей при старте ═══
    try:
        gemini_results = await probe_all_gemini_keys()
        alive = sum(1 for r in gemini_results if r["alive"])
        logger.info("Startup Gemini probe: %d/%d keys alive", alive, len(gemini_results))
        if alive == 0 and gemini_results:
            logger.error("⚠️ NO GEMINI KEYS ALIVE AT STARTUP — parse will fail!")
    except Exception as e:
        logger.warning("Startup Gemini probe failed: %s", e)


# ═══ Endpoint для мониторинга ключей (в llm-service/app.py): ═══

@app.get("/api/v1/keys/status")
async def keys_status():
    """Статус всех LLM ключей."""
    gemini_keys = _get_gemini_keys()
    or_keys = _get_api_keys()

    gemini_alive = []
    for k in gemini_keys:
        masked = _mask_key(k)
        cooldown = _key_cooldowns.get(k, {})
        is_dead = cooldown.get("until", 0) > time.time()
        gemini_alive.append({
            "key": masked,
            "alive": not is_dead,
            "cooldown_until": cooldown.get("until"),
            "cooldown_reason": cooldown.get("reason"),
        })

    or_alive = []
    for k in or_keys:
        masked = _mask_key(k)
        cooldown = _key_cooldowns.get(k, {})
        is_dead = cooldown.get("until", 0) > time.time()
        or_alive.append({
            "key": masked,
            "alive": not is_dead,
        })

    return {
        "gemini": {
            "total": len(gemini_keys),
            "alive": sum(1 for k in gemini_alive if k["alive"]),
            "keys": gemini_alive,
        },
        "openrouter": {
            "total": len(or_keys),
            "alive": sum(1 for k in or_alive if k["alive"]),
            "keys": or_alive,
        },
        "total": len(gemini_keys) + len(or_keys),
        "total_alive": sum(1 for k in gemini_alive if k["alive"]) + sum(1 for k in or_alive if k["alive"]),
    }
