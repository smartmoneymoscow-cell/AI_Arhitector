"""
shared/kaggle_auto_submit.py — Kaggle GPU auto-submit for render tasks.

When KAGGLE_RENDERER_URL is configured, automatically submits render tasks
to Kaggle notebook for GPU-accelerated rendering with T4 GPU.
Polls for results with exponential backoff.
"""

import logging
import os
import time

import httpx

logger = logging.getLogger("archai.kaggle_submit")


class KaggleAutoSubmit:
    """
    Automatic render task submission to Kaggle GPU renderer.

    Usage:
        submitter = KaggleAutoSubmit()
        if submitter.is_configured():
            result = submitter.submit_and_wait(script, output_path)
    """

    def __init__(self, kaggle_url: str = "", poll_interval: float = 5.0, max_wait: float = 600.0):
        self.kaggle_url = kaggle_url or os.environ.get("KAGGLE_RENDERER_URL", "")
        self.poll_interval = poll_interval
        self.max_wait = max_wait

    def is_configured(self) -> bool:
        """Check if Kaggle renderer is configured."""
        return bool(self.kaggle_url)

    def submit_task(self, script: str, output_path: str = "", params: dict | None = None) -> str | None:
        """
        Submit a render task to Kaggle.

        Returns task_id if submitted, None if failed.
        """
        if not self.kaggle_url:
            logger.warning("Kaggle renderer URL not configured")
            return None

        task_data = {
            "prompt": "",
            "params": params or {},
            "script": script,
            "output_path": output_path,
        }

        try:
            # Use the gateway's Kaggle enqueue endpoint
            with httpx.Client(timeout=30.0) as client:
                r = client.post(
                    f"{self.kaggle_url}/api/v1/kaggle/enqueue",
                    json=task_data,
                )
                if r.status_code == 200:
                    task_id = r.json().get("task_id")
                    logger.info("Kaggle task submitted: %s", task_id)
                    return task_id
                logger.error("Kaggle enqueue failed: %s %s", r.status_code, r.text[:200])
        except Exception as e:
            logger.error("Kaggle submit error: %s", e)
        return None

    def poll_result(self, task_id: str) -> dict | None:
        """
        Poll for task result with exponential backoff.

        Returns result dict if completed, None if timed out.
        """
        if not self.kaggle_url:
            return None

        start = time.time()
        interval = self.poll_interval
        max_interval = 30.0

        while time.time() - start < self.max_wait:
            try:
                with httpx.Client(timeout=10.0) as client:
                    r = client.get(f"{self.kaggle_url}/api/v1/kaggle/status/{task_id}")
                    if r.status_code == 200:
                        data = r.json()
                        status = data.get("status", "")
                        if status == "completed":
                            logger.info("Kaggle task %s completed in %.1fs", task_id, time.time() - start)
                            return data
                        elif status == "not_found":
                            logger.warning("Kaggle task %s not found", task_id)
                            return None
                        # Still processing — wait and retry
                        logger.debug("Kaggle task %s status: %s, waiting %.1fs", task_id, status, interval)
            except Exception as e:
                logger.warning("Kaggle poll error: %s", e)

            time.sleep(interval)
            # Exponential backoff
            interval = min(interval * 1.5, max_interval)

        logger.warning("Kaggle task %s timed out after %.0fs", task_id, self.max_wait)
        return None

    def submit_and_wait(self, script: str, output_path: str = "", params: dict | None = None) -> dict | None:
        """
        Submit a render task and wait for completion.

        Returns result dict if completed, None if failed/timed out.
        """
        task_id = self.submit_task(script, output_path, params)
        if not task_id:
            return None
        return self.poll_result(task_id)

    def health_check(self) -> dict:
        """Check Kaggle renderer health."""
        if not self.kaggle_url:
            return {"configured": False, "status": "not_configured"}

        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"{self.kaggle_url}/api/v1/kaggle/health")
                if r.status_code == 200:
                    return {"configured": True, **r.json()}
        except Exception as e:
            return {"configured": True, "status": "error", "error": str(e)}
        return {"configured": True, "status": "unknown"}
