"""
shared/celery_app.py — Celery-конфигурация для async задач.

Используется для:
- Генерация 3D через Blender (длинные задачи)
- Рендеринг интерьеров
- IFC экспорт
- Апскейл изображений

Зависимости: celery, redis

Использование:
    from shared.celery_app import celery_app, generate_building_task

    # Запуск задачи
    result = generate_building_task.delay(params)

    # Проверка статуса
    result.status  # PENDING, STARTED, SUCCESS, FAILURE
    result.get(timeout=300)  # блокирующее ожидание
"""

import os

# Конфигурация из env
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

try:
    from celery import Celery

    celery_app = Celery(
        "architect",
        broker=CELERY_BROKER,
        backend=CELERY_BACKEND,
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=600,  # 10 мин максимум на задачу
        task_soft_time_limit=500,  # Soft timeout — 8 мин
        worker_prefetch_multiplier=1,  # По одной задаче на воркер
        worker_max_tasks_per_child=50,  # Перезапуск воркера после 50 задач
        task_acks_late=True,  # Ack только после выполнения
        result_expires=3600,  # Результаты живут 1 час
    )

    # ═══════════════════════════════════════════════════════════
    # TASKS
    # ═══════════════════════════════════════════════════════════

    @celery_app.task(bind=True, name="generate_building")
    def generate_building_task(self, params: dict) -> dict:
        """Async задача: генерация GLB здания через Blender."""
        import uuid

        from shared.blender import generate_bpy_script, run_blender
        from shared.config import settings

        job_id = uuid.uuid4().hex[:8]
        output_file = os.path.join(settings.OUTPUT_DIR, f"{job_id}.glb")

        self.update_state(state="PROGRESS", meta={"step": "generating_script", "progress": 10})

        script = generate_bpy_script(params)
        export_cmd = f"\nimport bpy\nbpy.ops.export_scene.gltf(filepath=r'{output_file}', export_format='GLB')"

        self.update_state(state="PROGRESS", meta={"step": "running_blender", "progress": 30})

        try:
            run_blender(script + export_cmd, output_file)
        except Exception as e:
            return {"status": "error", "error": str(e), "job_id": job_id}

        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            return {
                "status": "ok",
                "job_id": job_id,
                "file": output_file,
                "size": size,
            }
        return {"status": "error", "error": "Output file not created", "job_id": job_id}

    @celery_app.task(bind=True, name="render_interior")
    def render_interior_task(self, params: dict) -> dict:
        """Async задача: рендеринг интерьера через Blender."""
        import uuid

        from shared.blender import generate_interior_script, run_blender
        from shared.config import settings
        from shared.validation import DEFAULT_FURNITURE

        room_type = params.get("room_type", "living")
        furniture = params.get("furniture") or DEFAULT_FURNITURE.get(room_type, ["sofa", "table", "chandelier"])

        interior_params = {
            "width": params.get("width_m", 6),
            "length": params.get("length_m", 8),
            "height": params.get("height_m", 3),
            "style": params.get("style", "modern"),
            "furniture": furniture,
        }

        self.update_state(state="PROGRESS", meta={"step": "generating_script", "progress": 10})

        script = generate_interior_script(interior_params)
        job_id = uuid.uuid4().hex[:8]
        output_file = os.path.join(settings.OUTPUT_DIR, f"{job_id}_int.png")

        render_cmd = (
            "\nimport bpy"
            f"\nbpy.context.scene.render.filepath = r'{output_file}'"
            "\nbpy.context.scene.render.engine = 'BLENDER_EEVEE'"
            "\nbpy.context.scene.render.resolution_x = 1920"
            "\nbpy.context.scene.render.resolution_y = 1080"
            "\nbpy.ops.render.render(write_still=True)"
        )

        self.update_state(state="PROGRESS", meta={"step": "rendering", "progress": 30})

        try:
            run_blender(script + render_cmd, output_file, timeout=settings.RENDER_INTERIOR_TIMEOUT)
        except Exception as e:
            return {"status": "error", "error": str(e), "job_id": job_id}

        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            return {
                "status": "ok",
                "job_id": job_id,
                "file": output_file,
                "size": size,
            }
        return {"status": "error", "error": "Render failed", "job_id": job_id}

    @celery_app.task(bind=True, name="generate_ifc")
    def generate_ifc_task(self, params: dict) -> dict:
        """Async задача: генерация IFC-файла."""
        import uuid

        from shared.config import settings
        from shared.ifc_generator import generate_ifc_building

        job_id = uuid.uuid4().hex[:8]
        output_file = os.path.join(settings.OUTPUT_DIR, f"{job_id}.ifc")

        self.update_state(state="PROGRESS", meta={"step": "generating_ifc", "progress": 20})

        try:
            generate_ifc_building(params, output_file)
        except ImportError as e:
            return {"status": "error", "error": f"ifcopenshell not installed: {e}", "job_id": job_id}
        except Exception as e:
            return {"status": "error", "error": str(e), "job_id": job_id}

        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            return {
                "status": "ok",
                "job_id": job_id,
                "file": output_file,
                "size": size,
            }
        return {"status": "error", "error": "IFC generation failed", "job_id": job_id}

    @celery_app.task(bind=True, name="upscale_image")
    def upscale_image_task(self, input_path: str, scale: int = 4) -> dict:
        """Async задача: апскейл изображения через Real-ESRGAN."""
        import uuid

        from shared.config import settings

        job_id = uuid.uuid4().hex[:8]
        output_path = os.path.join(settings.OUTPUT_DIR, f"{job_id}_upscaled.png")

        self.update_state(state="PROGRESS", meta={"step": "upscaling", "progress": 20})

        try:
            from shared.upscaler import upscale_image

            result = upscale_image(input_path, output_path, scale)
            return {
                "status": "ok",
                "job_id": job_id,
                "file": result,
                "size": os.path.getsize(result) if os.path.exists(result) else 0,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "job_id": job_id}

    @celery_app.task(name="generate_floorplan")
    def generate_floorplan_task(params: dict, floor: int = 1) -> dict:
        """Async задача: генерация SVG плана этажа."""
        from shared.floorplan import generate_floorplan_svg

        try:
            svg = generate_floorplan_svg(params, floor)
            return {"status": "ok", "svg": svg}
        except Exception as e:
            return {"status": "error", "error": str(e)}


except ImportError:
    # Celery не установлен — создаём заглушки
    class _FakeTask:
        """Заглушка для задач, когда Celery не установлен."""

        def delay(self, *args, **kwargs):
            raise RuntimeError(
                "Celery не установлен. Установите: pip install celery redis\n"
                "И запустите Redis: docker run -d -p 6379:6379 redis:alpine"
            )

    celery_app = None
    generate_building_task = _FakeTask()
    render_interior_task = _FakeTask()
    generate_ifc_task = _FakeTask()
    upscale_image_task = _FakeTask()
    generate_floorplan_task = _FakeTask()
