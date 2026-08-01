"""
shared/agents/ — Multi-agent система для генерации архитектурных моделей.

Архитектура (20 агентов):
    Orchestrator.receive(prompt) → decompose → dispatch → collect → result

Pipeline агенты (6):
    ParserAgent      — парсинг промтов (LLM каскад)
    GeometryAgent    — генерация 3D геометрии (Blender bpy)
    TextureAgent     — генерация/применение текстур
    RenderAgent      — рендер изображений (EEVEE/Cycles)
    ExportAgent      — экспорт в форматы (GLB/IFC/SVG)
    QualityAgent     — проверка качества рендера

Интеллектуальные агенты (8):
    ResearchAgent    — поиск референсов, анализ трендов
    MarketAgent      — анализ рынка недвижимости
    ConceptAgent     — концептуальный дизайн, мудборды
    MasterplanAgent  — генерация мастер-плана участка
    LandscapeAgent   — ландшафтный дизайн
    BrandAgent       — бренд-стиль, айдентика
    FinancialAgent   — финансовая оценка, ROI
    PresentationAgent — генерация презентаций

Специализированные агенты (6):
    StyleAgent       — определение и применение стиля
    LightingAgent    — настройка освещения
    FurnitureAgent   — эргономичное размещение мебели
    MEPAgent         — инженерные системы (электрика, водоснабжение, HVAC)
    StructuralAgent  — конструктивный расчёт
    ComplianceAgent  — проверка соответствия нормам (СП, ГОСТ, IBC)
"""

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus
from shared.agents.brand_agent import BrandAgent
from shared.agents.compliance_agent import ComplianceAgent
from shared.agents.concept_agent import ConceptAgent
from shared.agents.export_agent import ExportAgent
from shared.agents.financial_agent import FinancialAgent
from shared.agents.furniture_agent import FurnitureAgent
from shared.agents.geometry_agent import GeometryAgent
from shared.agents.landscape_agent import LandscapeAgent
from shared.agents.lighting_agent import LightingAgent
from shared.agents.market_agent import MarketAgent
from shared.agents.masterplan_agent import MasterplanAgent
from shared.agents.mep_agent import MEPAgent

# Оркестратор
from shared.agents.orchestrator import Orchestrator

# Pipeline агенты
from shared.agents.parser_agent import ParserAgent
from shared.agents.presentation_agent import PresentationAgent
from shared.agents.quality_agent import QualityAgent
from shared.agents.render_agent import RenderAgent

# Интеллектуальные агенты
from shared.agents.research_agent import ResearchAgent
from shared.agents.structural_agent import StructuralAgent

# Специализированные агенты
from shared.agents.style_agent import StyleAgent
from shared.agents.texture_agent import TextureAgent

__all__ = [
    # Base
    "BaseAgent",
    "BrandAgent",
    "ComplianceAgent",
    "ConceptAgent",
    "ExportAgent",
    "FinancialAgent",
    "FurnitureAgent",
    "GeometryAgent",
    "LandscapeAgent",
    "LightingAgent",
    "MEPAgent",
    "MarketAgent",
    "MasterplanAgent",
    # Orchestrator
    "Orchestrator",
    # Pipeline
    "ParserAgent",
    "PresentationAgent",
    "QualityAgent",
    "RenderAgent",
    # Intelligence
    "ResearchAgent",
    "StructuralAgent",
    # Specialized
    "StyleAgent",
    "Task",
    "TaskResult",
    "TaskStatus",
    "TextureAgent",
]

# Реестр всех агентов
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "parser": ParserAgent,
    "geometry": GeometryAgent,
    "texture": TextureAgent,
    "render": RenderAgent,
    "export": ExportAgent,
    "quality": QualityAgent,
    "research": ResearchAgent,
    "market": MarketAgent,
    "concept": ConceptAgent,
    "masterplan": MasterplanAgent,
    "landscape": LandscapeAgent,
    "brand": BrandAgent,
    "financial": FinancialAgent,
    "presentation": PresentationAgent,
    "style": StyleAgent,
    "lighting": LightingAgent,
    "furniture": FurnitureAgent,
    "mep": MEPAgent,
    "structural": StructuralAgent,
    "compliance": ComplianceAgent,
}
