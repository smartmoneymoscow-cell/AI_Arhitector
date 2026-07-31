"""
shared — общая библиотека для всех микросервисов AI_Arhitector.

Модули:
    shared.config          — конфигурация из env
    shared.models          — Pydantic-модели
    shared.validation      — валидация параметров
    shared.parser          — LLM + regex парсинг промтов
    shared.router          — единый роутер генерации (маршрутизация + шаблоны)
    shared.blender         — генерация bpy-скриптов
    shared.ifc_generator   — генерация IFC через IfcOpenShell
    shared.floorplan       — SVG планы этажей через Shapely
    shared.celery_app      — async очередь задач (Celery + Redis)
    shared.upscaler        — апскейл изображений (Real-ESRGAN)
    shared.graph           — граф здания (NetworkX)
    shared.voice           — голосовой ввод (Whisper)
    shared.agents          — multi-agent система (orchestrator + agents)

Использование:
    from shared.config import settings
    from shared.parser import parse_prompt_sync, fallback_regex_parse
    from shared.validation import validate_params
    from shared.models import GenerateRequest, ParsedParams
    from shared.router import route_generation, GenerationPlan
    from shared.blender import generate_bpy_script, generate_interior_script
    from shared.ifc_generator import generate_ifc_building
    from shared.floorplan import generate_floorplan_svg
    from shared.graph import BuildingGraph
    from shared.agents import Orchestrator
"""

__version__ = "5.0.0"
