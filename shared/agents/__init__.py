"""
shared/agents/ — Multi-agent система (20 агентов).

Lazy-loading: агенты импортируются только при первом обращении,
чтобы не тратить память при старте gateway.
"""

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

# ═══ Lazy import через __getattr__ ═══
_LAZY_IMPORTS = {
    # Pipeline (6)
    "ParserAgent": "shared.agents.parser_agent",
    "GeometryAgent": "shared.agents.geometry_agent",
    "TextureAgent": "shared.agents.texture_agent",
    "RenderAgent": "shared.agents.render_agent",
    "ExportAgent": "shared.agents.export_agent",
    "QualityAgent": "shared.agents.quality_agent",
    # Intelligence (8)
    "ResearchAgent": "shared.agents.research_agent",
    "MarketAgent": "shared.agents.market_agent",
    "ConceptAgent": "shared.agents.concept_agent",
    "MasterplanAgent": "shared.agents.masterplan_agent",
    "LandscapeAgent": "shared.agents.landscape_agent",
    "BrandAgent": "shared.agents.brand_agent",
    "FinancialAgent": "shared.agents.financial_agent",
    "PresentationAgent": "shared.agents.presentation_agent",
    # Specialized (6)
    "StyleAgent": "shared.agents.style_agent",
    "LightingAgent": "shared.agents.lighting_agent",
    "FurnitureAgent": "shared.agents.furniture_agent",
    "MEPAgent": "shared.agents.mep_agent",
    "StructuralAgent": "shared.agents.structural_agent",
    "ComplianceAgent": "shared.agents.compliance_agent",
    # New (v7.1)
    "ELAgent": "shared.agents.el_agent",
    "MEPBIMAgent": "shared.agents.mep_bim_agent",
    # Orchestrator
    "Orchestrator": "shared.agents.orchestrator",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib
        module = importlib.import_module(_LAZY_IMPORTS[name])
        cls = getattr(module, name)
        # Кэшируем в модуле чтобы не импортировать повторно
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseAgent", "Task", "TaskResult", "TaskStatus",
    "ParserAgent", "GeometryAgent", "TextureAgent",
    "RenderAgent", "ExportAgent", "QualityAgent",
    "ResearchAgent", "MarketAgent", "ConceptAgent",
    "MasterplanAgent", "LandscapeAgent", "BrandAgent",
    "FinancialAgent", "PresentationAgent",
    "StyleAgent", "LightingAgent", "FurnitureAgent",
    "MEPAgent", "StructuralAgent", "ComplianceAgent",
    "ELAgent", "MEPBIMAgent",
    "Orchestrator",
]


class _AgentRegistry:
    """Lazy registry — создаёт агентов только при обращении."""

    _names = [
        "parser", "geometry", "texture", "render", "export", "quality",
        "research", "market", "concept", "masterplan", "landscape",
        "brand", "financial", "presentation", "style", "lighting",
        "furniture", "mep", "structural", "compliance",
        "el", "mep_bim",
    ]

    _class_map = {
        "parser": "ParserAgent", "geometry": "GeometryAgent",
        "texture": "TextureAgent", "render": "RenderAgent",
        "export": "ExportAgent", "quality": "QualityAgent",
        "research": "ResearchAgent", "market": "MarketAgent",
        "concept": "ConceptAgent", "masterplan": "MasterplanAgent",
        "landscape": "LandscapeAgent", "brand": "BrandAgent",
        "financial": "FinancialAgent", "presentation": "PresentationAgent",
        "style": "StyleAgent", "lighting": "LightingAgent",
        "furniture": "FurnitureAgent", "mep": "MEPAgent",
        "structural": "StructuralAgent", "compliance": "ComplianceAgent",
        "el": "ELAgent", "mep_bim": "MEPBIMAgent",
    }

    def __getitem__(self, name: str):
        cls_name = self._class_map.get(name)
        if cls_name:
            return globals()[cls_name] if cls_name in globals() else __getattr__(cls_name)
        raise KeyError(name)

    def __iter__(self):
        for name in self._names:
            yield name, self[name]

    def __len__(self):
        return len(self._names)

    def keys(self):
        return self._names

    def items(self):
        return [(name, self[name]) for name in self._names]


AGENT_REGISTRY = _AgentRegistry()
