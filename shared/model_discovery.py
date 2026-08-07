"""
shared/model_discovery.py — Background scheduler for free model discovery.

Runs as a background task in the LLM service.
Every 4 hours queries OpenRouter for free models and rebuilds cascade.
Also validates that current Gemini keys are still working.

Usage:
    from shared.model_discovery import start_discovery_scheduler, get_discovery_status

    # In FastAPI lifespan:
    start_discovery_scheduler()
"""

import asyncio
import logging
import time

logger = logging.getLogger("archai.model_discovery")

# Background task handle
_bg_task: asyncio.Task | None = None
_status = {
    "running": False,
    "last_run": None,
    "last_duration": None,
    "last_error": None,
    "runs_total": 0,
    "runs_failed": 0,
}


async def _discovery_loop():
    """Background loop that runs discovery every DISCOVERY_INTERVAL."""
    from shared.model_manager import get_model_manager, DISCOVERY_INTERVAL

    manager = get_model_manager()

    # Initial discovery on startup
    logger.info("Starting model discovery scheduler (interval=%ds)", DISCOVERY_INTERVAL)

    while True:
        try:
            _status["running"] = True
            start = time.time()

            # Run discovery
            models = await manager.discover_free_models(force=True)

            duration = time.time() - start
            _status["last_run"] = time.time()
            _status["last_duration"] = round(duration, 2)
            _status["last_error"] = None
            _status["runs_total"] += 1

            logger.info(
                "Model discovery completed: %d free models found in %.1fs",
                len(models), duration,
            )

            # Validate Gemini keys (try a simple request)
            await _validate_gemini_keys(manager)

        except Exception as e:
            _status["last_error"] = str(e)
            _status["runs_failed"] += 1
            logger.error("Model discovery error: %s", e)

        finally:
            _status["running"] = False

        # Wait for next cycle
        await asyncio.sleep(DISCOVERY_INTERVAL)


async def _validate_gemini_keys(manager):
    """Quick validation that Gemini keys are working."""
    from shared.model_manager import ApiKey, Provider

    try:
        # Try a minimal request to check key health
        result = await manager.send_request(
            messages=[{"role": "user", "content": "Reply with: ok"}],
            max_tokens=5,
            temperature=0.0,
            system_prompt="Reply with exactly: ok",
        )
        logger.debug("Gemini validation: %s via %s", result.get("model"), result.get("provider"))
    except Exception as e:
        logger.warning("Gemini validation failed: %s", e)


def start_discovery_scheduler():
    """Start the background discovery scheduler."""
    global _bg_task
    if _bg_task is not None and not _bg_task.done():
        logger.warning("Discovery scheduler already running")
        return
    loop = asyncio.get_event_loop()
    _bg_task = loop.create_task(_discovery_loop())
    logger.info("Discovery scheduler started")


def stop_discovery_scheduler():
    """Stop the background discovery scheduler."""
    global _bg_task
    if _bg_task and not _bg_task.done():
        _bg_task.cancel()
        _bg_task = None
        logger.info("Discovery scheduler stopped")


def get_discovery_status() -> dict:
    """Get scheduler status."""
    return {
        **_status,
        "scheduler_active": _bg_task is not None and not _bg_task.done(),
    }
