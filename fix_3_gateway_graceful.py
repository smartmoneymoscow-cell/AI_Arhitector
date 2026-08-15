"""
Фикс 3: Gateway — graceful degradation при ошибке orchestrator.

Проблема: orchestrator падает → фронтенд получает 500 → "Сервер недоступен".
Реальность: LLM работает, Blender работает, просто один запрос не прошёл.

Решение: возвращаем 200 с partial result + понятным сообщением.
"""


@app.post("/api/v1/orchestrator/execute")
async def orchestrator_execute(
    req: dict,
    _rl: None = Depends(rate_limit_middleware),
):
    from shared.agents import Orchestrator

    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "No prompt provided")

    quality = req.get("quality", "standard")
    export_formats = req.get("export_formats", ["glb"])
    skip_clarification = req.get("skip_clarification", False)
    pipeline_profile = req.get("pipeline_profile", "standard")
    session_id = req.get("session_id", "")

    job_id = uuid.uuid4().hex[:8]

    orch = Orchestrator(
        blender_service_url=settings.BLENDER_SERVICE_URL,
        llm_service_url=settings.LLM_SERVICE_URL,
        output_dir=settings.OUTPUT_DIR,
        blender_service_urls=_get_blender_urls(),
    )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: orch.execute(
                prompt,
                quality=quality,
                export_formats=export_formats,
                skip_clarification=skip_clarification,
                pipeline_profile=pipeline_profile,
                session_id=session_id,
            ),
        )
    except Exception as e:
        logger.error("Orchestrator error: %s: %s", type(e).__name__, str(e)[:500], exc_info=True)

        # ═══ FIX: Graceful degradation вместо 500 ═══
        # Проверяем, на каком этапе упали
        error_type = type(e).__name__
        error_msg = str(e)[:500]

        if "AllModelsFailed" in error_type or "all_models_failed" in error_msg:
            # LLM полностью недоступен
            return {
                "job_id": job_id,
                "session_id": session_id,
                "status": "llm_unavailable",
                "error": {
                    "code": "LLM_UNAVAILABLE",
                    "message": "LLM-парсинг временно недоступен. Все модели не отвечают.",
                    "hint": "Попробуйте через 1-2 минуты, или проверьте ключи: GET /api/v1/keys/status",
                    "retry_after_seconds": 60,
                },
            }
        elif "timeout" in error_msg.lower() or "Timeout" in error_type:
            # Таймаут — сервис жив, но медленный
            return {
                "job_id": job_id,
                "session_id": session_id,
                "status": "timeout",
                "error": {
                    "code": "PIPELINE_TIMEOUT",
                    "message": "Обработка промта заняла слишком много времени.",
                    "hint": "Попробуйте упростить промт или повторить позже.",
                    "retry_after_seconds": 30,
                },
            }
        elif "blender" in error_msg.lower() or "502" in error_msg:
            # Blender недоступен
            return {
                "job_id": job_id,
                "session_id": session_id,
                "status": "blender_unavailable",
                "error": {
                    "code": "BLENDER_UNAVAILABLE",
                    "message": "Сервис рендеринга недоступен.",
                    "hint": "Blender service перезапускается. Попробуйте через 2-3 минуты.",
                    "retry_after_seconds": 120,
                },
            }
        else:
            # Неизвестная ошибка — но не 500, а informative 200
            return {
                "job_id": job_id,
                "session_id": session_id,
                "status": "error",
                "error": {
                    "code": "PIPELINE_ERROR",
                    "message": f"Ошибка обработки: {error_msg}",
                    "hint": "Попробуйте ещё раз. Если повторяется — проверьте логи сервисов.",
                },
            }

    # Успех — как раньше
    result_job_id = result["job_id"]
    _store_job(result_job_id, result)

    r = result.get("result") or {}
    return {
        "job_id": result_job_id,
        "session_id": session_id,
        "status": result["status"],
        "gen_type": r.get("gen_type"),
        "quality": quality,
        "pipeline_profile": pipeline_profile,
        "params": r.get("params"),
        "render": r.get("render"),
        "exports": r.get("exports", {}),
        "confidence": r.get("confidence"),
        "duration_ms": result.get("duration_ms", 0),
        "steps": result.get("steps", []),
        "agent_results": result.get("agent_results", {}),
    }
