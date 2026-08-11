"""
agent-pool/app.py — Agent Pool Microservice.

Runs all agents in isolated threads with timeout.
Gateway calls this via HTTP instead of importlib.import_module().

POST /api/v1/agents/{agent_name}/run  → execute agent
GET  /api/v1/agents                   → list available agents
GET  /health                          → health check
"""

import importlib
import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared.logging_config import setup_logging

setup_logging("agent-pool")
logger = logging.getLogger("archai.agent_pool")

app = FastAPI(
    title="Agent Pool Service",
    description="Runs all architecture agents via HTTP. Gateway → Agent Pool → Agent",
    version="1.0.0",
)

_cors_origins = os.environ.get("CORS_ORIGINS", "")
_origins_list = [o.strip() for o in _cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins_list,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


# ═══════════════════════════════════════════════════════════════
# AGENT REGISTRY — all known agents and their module paths
# ═══════════════════════════════════════════════════════════════

AGENT_REGISTRY = {
    "parser": "shared.agents.parser_agent.ParserAgent",
    "dialog": "shared.agents.dialog_agent.DialogAgent",
    "geometry": "shared.agents.geometry_agent.GeometryAgent",
    "cad": "shared.agents.cad_agent.CADAgent",
    "texture": "shared.agents.texture_agent.TextureAgent",
    "render": "shared.agents.render_agent.RenderAgent",
    "export": "shared.agents.export_agent.ExportAgent",
    "quality": "shared.agents.quality_agent.QualityAgent",
    "research": "shared.agents.research_agent.ResearchAgent",
    "market": "shared.agents.market_agent.MarketAgent",
    "concept": "shared.agents.concept_agent.ConceptAgent",
    "masterplan": "shared.agents.masterplan_agent.MasterplanAgent",
    "landscape": "shared.agents.landscape_agent.LandscapeAgent",
    "brand": "shared.agents.brand_agent.BrandAgent",
    "financial": "shared.agents.financial_agent.FinancialAgent",
    "presentation": "shared.agents.presentation_agent.PresentationAgent",
    "style": "shared.agents.style_agent.StyleAgent",
    "lighting": "shared.agents.lighting_agent.LightingAgent",
    "furniture": "shared.agents.furniture_agent.FurnitureAgent",
    "mep": "shared.agents.mep_agent.MEPAgent",
    "structural": "shared.agents.structural_agent.StructuralAgent",
    "compliance": "shared.agents.compliance_agent.ComplianceAgent",
    "el": "shared.agents.el_agent.ELAgent",
    "mep_bim": "shared.agents.mep_bim_agent.MEPBIMAgent",
    "seismic": "shared.agents.seismic_agent.SeismicAgent",
    "foundation": "shared.agents.foundation_agent.FoundationAgent",
    "stitching": "shared.agents.stitching_agent.StitchingAgent",
    "dwg_analysis": "shared.agents.dwg_analysis_agent.DWGAnalysisAgent",
    "pdf_analysis": "shared.agents.pdf_analysis_agent.PDFAnalysisAgent",
    "structural_analysis": "shared.agents.structural_analysis_agent.StructuralAnalysisAgent",
    "duct_analysis": "shared.agents.duct_analysis_agent.DuctAnalysisAgent",
}

# Cache loaded agent classes
_agent_cache: dict[str, type] = {}


def _get_agent_class(agent_name: str):
    """Load and cache agent class by name."""
    if agent_name in _agent_cache:
        return _agent_cache[agent_name]

    class_path = AGENT_REGISTRY.get(agent_name)
    if not class_path:
        return None

    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    agent_cls = getattr(module, class_name)
    _agent_cache[agent_name] = agent_cls
    return agent_cls


# ═══════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════


class AgentRunRequest(BaseModel):
    name: str
    agent: str
    params: dict = {}
    timeout: int = 120


class AgentRunResponse(BaseModel):
    status: str  # "done" | "failed" | "timeout"
    data: dict | None = None
    error: str | None = None
    duration_ms: float = 0
    fallback: bool = False
    agent_name: str = ""


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "agent-pool",
        "version": "1.0.0",
        "agents_registered": len(AGENT_REGISTRY),
    }


@app.get("/api/v1/agents")
async def list_agents():
    """List all available agents."""
    agents = []
    for name, class_path in AGENT_REGISTRY.items():
        agents.append({
            "name": name,
            "class": class_path,
            "loaded": name in _agent_cache,
        })
    return {"agents": agents, "count": len(agents)}


@app.post("/api/v1/agents/{agent_name}/run", response_model=AgentRunResponse)
async def run_agent(agent_name: str, req: AgentRunRequest):
    """Run an agent in an isolated thread with timeout."""
    agent_cls = _get_agent_class(agent_name)
    if not agent_cls:
        raise HTTPException(404, f"Unknown agent: {agent_name}")

    from shared.agents.base import Task, TaskStatus

    timeout = req.timeout or 120
    result_holder: dict = {}

    def _target():
        try:
            agent = agent_cls()
            task = Task(
                name=req.name,
                agent=req.agent,
                params=req.params,
            )
            start = time.time()
            result = agent.process(task)
            duration = (time.time() - start) * 1000
            result_holder["status"] = result.status.value
            result_holder["data"] = result.data
            result_holder["error"] = result.error
            result_holder["duration_ms"] = duration
        except Exception as e:
            result_holder["status"] = "failed"
            result_holder["error"] = f"{type(e).__name__}: {str(e)}"

    start = time.time()
    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=timeout)

    if worker.is_alive():
        logger.error("Agent %s TIMEOUT after %ds", agent_name, timeout)
        return AgentRunResponse(
            status="timeout",
            error=f"Agent {agent_name} timed out after {timeout}s",
            duration_ms=(time.time() - start) * 1000,
            agent_name=agent_name,
        )

    if result_holder.get("status") == "failed":
        logger.warning("Agent %s FAILED: %s", agent_name, result_holder.get("error", "")[:200])

    return AgentRunResponse(
        status=result_holder.get("status", "failed"),
        data=result_holder.get("data"),
        error=result_holder.get("error"),
        duration_ms=result_holder.get("duration_ms", (time.time() - start) * 1000),
        agent_name=agent_name,
    )


# ═══════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════


@app.on_event("startup")
async def _on_startup():
    logger.info("Agent Pool starting — %d agents registered", len(AGENT_REGISTRY))
    # Pre-import critical agents
    for name in ("parser", "geometry", "texture", "render", "quality"):
        try:
            _get_agent_class(name)
            logger.info("Pre-loaded agent: %s", name)
        except Exception as e:
            logger.warning("Failed to pre-load %s: %s", name, e)
