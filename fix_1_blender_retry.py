"""
Фикс 1: LLM parse retry с увеличивающимся таймаутом.
Заменяет _parse_via_llm_service в blender-service/app.py.

Проблема: один таймаут 15с → сразу 503.
Решение: 3 попытки с таймаутами 15с → 30с → 60с + exponential backoff.
"""


async def _parse_via_llm_service(prompt: str) -> dict:
    """Парсинг промта через LLM-service. Retry 3 раза с растущим таймаутом."""
    llm_url = settings.LLM_SERVICE_URL
    if not llm_url:
        raise HTTPException(503, "LLM service not configured")

    attempts = [
        {"timeout": 15.0, "label": "fast"},
        {"timeout": 30.0, "label": "medium"},
        {"timeout": 60.0, "label": "patient"},
    ]

    last_error = None
    for i, attempt in enumerate(attempts):
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{llm_url}/api/v1/parse",
                    json={"text": prompt},
                    timeout=attempt["timeout"],
                )
            if r.status_code == 200:
                if i > 0:
                    logger.info("LLM parse succeeded on attempt %d (%s)", i + 1, attempt["label"])
                return r.json()
            elif r.status_code == 503:
                last_error = "LLM service unavailable — all models failed"
                logger.warning("LLM parse attempt %d: 503, retrying...", i + 1)
            else:
                last_error = f"LLM returned {r.status_code}: {r.text[:200]}"
                logger.warning("LLM parse attempt %d: %s", i + 1, last_error)
        except httpx.TimeoutException:
            last_error = f"LLM timeout after {attempt['timeout']}s"
            logger.warning("LLM parse attempt %d (%s): timeout", i + 1, attempt["label"])
        except httpx.ConnectError:
            last_error = "LLM service unreachable"
            logger.warning("LLM parse attempt %d: connection refused", i + 1)
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:200]}"
            logger.warning("LLM parse attempt %d: %s", i + 1, last_error)

        # Exponential backoff между попытками
        if i < len(attempts) - 1:
            await asyncio.sleep(2 * (i + 1))

    # Все попытки исчерпаны — честная ошибка
    logger.error("LLM parse failed after %d attempts: %s", len(attempts), last_error)
    raise HTTPException(503, detail={
        "error": "llm_parse_failed",
        "message": f"Парсинг недоступен после {len(attempts)} попыток. Последняя ошибка: {last_error}",
        "hint": "Проверьте LLM ключи: GET /api/v1/keys/status",
    })
