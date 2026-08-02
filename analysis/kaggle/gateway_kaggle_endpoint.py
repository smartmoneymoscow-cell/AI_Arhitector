"""
AI_Arhitector — Gateway Kaggle 16K Render Endpoint

Добавляет endpoint /api/v1/render/16k/kaggle в Gateway.
Gateway отправляет bpy-скрипт в Kaggle → получает 16K рендер.

Интеграция:
  1. Добавить этот файл в gateway/
  2. Импортировать в gateway/app.py
  3. Добавить route: app.include_router(kaggle_router)
"""

import os
import json
import asyncio
import hashlib
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

kaggle_router = APIRouter(prefix="/api/v1/render", tags=["kaggle-16k"])

# In-memory job tracker (move to Redis in production)
_kaggle_jobs: dict = {}

KAGGLE_API_TOKEN = os.environ.get("KAGGLE_API_TOKEN", "")
KAGGLE_OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")


class KaggleRenderRequest(BaseModel):
    """Request to render via Kaggle T4 GPU."""
    script: str  # bpy script content
    samples: int = 2048
    tiles_x: int = 4
    tiles_y: int = 3
    tile_width: int = 3840
    tile_height: int = 2880


class KaggleRenderResponse(BaseModel):
    """Response from Kaggle render request."""
    job_id: str
    status: str
    message: str


class KaggleRenderStatus(BaseModel):
    """Status of a Kaggle render job."""
    job_id: str
    status: str  # pending, running, complete, error
    progress: Optional[str] = None
    output_url: Optional[str] = None
    resolution: Optional[str] = None
    file_size_mb: Optional[float] = None
    render_time_sec: Optional[float] = None
    error: Optional[str] = None


@kaggle_router.post("/16k/kaggle", response_model=KaggleRenderResponse)
async def start_kaggle_render(request: KaggleRenderRequest, background_tasks: BackgroundTasks):
    """
    Start a 16K render via Kaggle T4 GPU.

    The bpy script is sent to Kaggle, rendered on T4 GPU,
    and the result is pulled back to the Gateway.

    Returns a job_id for status polling.
    """
    # Generate job ID
    script_hash = hashlib.md5(request.script.encode()).hexdigest()[:8]
    job_id = f"kaggle-16k-{int(time.time())}-{script_hash}"

    # Save script to temp file
    script_path = os.path.join(KAGGLE_OUTPUT_DIR, f"{job_id}.py")
    os.makedirs(KAGGLE_OUTPUT_DIR, exist_ok=True)
    with open(script_path, 'w') as f:
        f.write(request.script)

    # Initialize job
    _kaggle_jobs[job_id] = {
        "status": "pending",
        "script_path": script_path,
        "created_at": time.time(),
        "params": {
            "samples": request.samples,
            "tiles": f"{request.tiles_x}x{request.tiles_y}",
            "tile_size": f"{request.tile_width}x{request.tile_height}",
            "resolution": f"{request.tiles_x * request.tile_width}x{request.tiles_y * request.tile_height}"
        }
    }

    # Start render in background
    background_tasks.add_task(_run_kaggle_render, job_id, request)

    return KaggleRenderResponse(
        job_id=job_id,
        status="pending",
        message=f"16K render queued. Poll /api/v1/render/16k/kaggle/{job_id} for status."
    )


@kaggle_router.get("/16k/kaggle/{job_id}", response_model=KaggleRenderStatus)
async def get_kaggle_render_status(job_id: str):
    """Get status of a Kaggle 16K render job."""
    job = _kaggle_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    return KaggleRenderStatus(
        job_id=job_id,
        status=job["status"],
        progress=job.get("progress"),
        output_url=job.get("output_url"),
        resolution=job.get("params", {}).get("resolution"),
        file_size_mb=job.get("file_size_mb"),
        render_time_sec=job.get("render_time_sec"),
        error=job.get("error")
    )


async def _run_kaggle_render(job_id: str, request: KaggleRenderRequest):
    """Background task to run Kaggle render."""
    job = _kaggle_jobs[job_id]

    try:
        job["status"] = "running"
        job["progress"] = "Pushing script to Kaggle..."

        # Import the Kaggle renderer
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from kaggle_renderer import KaggleRenderer

        renderer = KaggleRenderer(api_token=KAGGLE_API_TOKEN)

        # Push script as dataset
        job["progress"] = "Uploading bpy script..."
        script_path = job["script_path"]
        if not renderer.push_script(script_path):
            job["status"] = "error"
            job["error"] = "Failed to push script to Kaggle"
            return

        # Push kernel
        job["progress"] = "Pushing kernel to Kaggle..."
        kernel_script = os.path.join(os.path.dirname(__file__), "architect_16k_render.py")
        if not os.path.exists(kernel_script):
            job["status"] = "error"
            job["error"] = f"Kernel script not found: {kernel_script}"
            return

        if not renderer.push_kernel(kernel_script):
            job["status"] = "error"
            job["error"] = "Failed to push kernel to Kaggle"
            return

        # Run kernel
        job["progress"] = "Running on Kaggle T4 GPU..."
        result = renderer.run_kernel()

        if result["status"] == "complete":
            # Pull output
            job["progress"] = "Pulling 16K output..."
            output_path = renderer.pull_output(
                output_dir=os.path.join(KAGGLE_OUTPUT_DIR, job_id)
            )

            if output_path:
                # Copy to main output directory
                import shutil
                final_path = os.path.join(KAGGLE_OUTPUT_DIR, f"{job_id}_16k.png")
                shutil.copy2(output_path, final_path)

                job["status"] = "complete"
                job["output_url"] = f"/output/{job_id}_16k.png"
                job["file_size_mb"] = round(os.path.getsize(final_path) / 1024 / 1024, 1)
                job["render_time_sec"] = result.get("render_time", 0)
                job["progress"] = "Done"
            else:
                job["status"] = "error"
                job["error"] = "Failed to pull output from Kaggle"
        else:
            job["status"] = "error"
            job["error"] = result.get("message", "Kaggle render failed")

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        print(f"[Kaggle 16K] Error for {job_id}: {e}")
