"""
shared/agents/ — Multi-agent система для генерации архитектурных моделей.

Архитектура:
    Orchestrator.receive(prompt) → decompose → dispatch → collect → result

Агенты:
    ParserAgent    — парсинг промтов (LLM + regex)
    GeometryAgent  — генерация3D геометрии (Blender bpy)
    TextureAgent   — генерация/применение текстур
    RenderAgent    — рендер изображений (EEVEE/Cycles)
    ExportAgent    — экспорт в форматы (GLB/IFC/SVG)
"""

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.agents.parser_agent import ParserAgent
from shared.agents.geometry_agent import GeometryAgent
from shared.agents.texture_agent import TextureAgent
from shared.agents.render_agent import RenderAgent
from shared.agents.export_agent import ExportAgent
from shared.agents.orchestrator import Orchestrator

__all__ = [
    "BaseAgent", "Task", "TaskResult", "TaskStatus",
    "ParserAgent", "GeometryAgent", "TextureAgent",
    "RenderAgent", "ExportAgent", "Orchestrator",
]
