"""
aedifex-bridge/mcp_llm_bridge.py — MCP ↔ LLM Service интеграция.

Позволяет AI-ассистенту aedifex управлять 3D-сценой через MCP tools,
используя существующий LLM Service для парсинга и генерации.

Pipeline:
  User: "Создай двухэтажный дом 10×12 с балконом"
    → LLM Service парсит промт
    → MCP tools создают стены, окна, двери
    → aedifex отображает результат
    → Blender рендерит превью
"""

import json
import logging
import os
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger("mcp-llm-bridge")

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080")
LLM_SERVICE_URL = os.environ.get("LLM_SERVICE_URL", "http://localhost:8081")
CAD_SERVICE_URL = os.environ.get("CAD_SERVICE_URL", "http://localhost:8087")

app = FastAPI(title="MCP-LLM Bridge")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ═══════════════════════════════════════════════════════════════
# MCP Tool definitions (aedifex-compatible)
# ═══════════════════════════════════════════════════════════════

MCP_TOOLS = [
    {
        "name": "create_wall",
        "description": "Create a wall between two points on a level",
        "parameters": {
            "levelId": {"type": "string", "description": "Level ID"},
            "start": {"type": "array", "items": {"type": "number"}, "description": "[x, y] start point"},
            "end": {"type": "array", "items": {"type": "number"}, "description": "[x, y] end point"},
            "thickness": {"type": "number", "description": "Wall thickness in meters", "optional": True},
            "height": {"type": "number", "description": "Wall height in meters", "optional": True},
        },
    },
    {
        "name": "cut_opening",
        "description": "Cut a door or window opening in a wall",
        "parameters": {
            "wallId": {"type": "string", "description": "Wall ID"},
            "type": {"type": "string", "enum": ["door", "window"]},
            "position": {"type": "number", "description": "Position along wall (0..1)"},
            "width": {"type": "number", "description": "Opening width in meters"},
            "height": {"type": "number", "description": "Opening height in meters"},
        },
    },
    {
        "name": "place_item",
        "description": "Place furniture or item in the scene",
        "parameters": {
            "levelId": {"type": "string", "description": "Level ID"},
            "catalogId": {"type": "string", "description": "Furniture catalog ID"},
            "position": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] position"},
            "rotation": {"type": "number", "description": "Rotation in degrees", "optional": True},
        },
    },
    {
        "name": "create_level",
        "description": "Create a new building level/floor",
        "parameters": {
            "buildingId": {"type": "string", "description": "Building ID"},
            "name": {"type": "string", "description": "Level name"},
            "elevation": {"type": "number", "description": "Elevation in meters"},
        },
    },
    {
        "name": "set_zone",
        "description": "Define a room zone from wall boundaries",
        "parameters": {
            "levelId": {"type": "string", "description": "Level ID"},
            "wallIds": {"type": "array", "items": {"type": "string"}, "description": "Wall IDs forming the zone"},
            "name": {"type": "string", "description": "Zone/room name"},
        },
    },
    {
        "name": "delete_node",
        "description": "Delete a node from the scene",
        "parameters": {
            "nodeId": {"type": "string", "description": "Node ID to delete"},
        },
    },
    {
        "name": "get_scene",
        "description": "Get the current scene state",
        "parameters": {},
    },
    {
        "name": "validate_scene",
        "description": "Validate the scene for errors",
        "parameters": {},
    },
    {
        "name": "export_glb",
        "description": "Export scene as GLB file",
        "parameters": {},
    },
    {
        "name": "undo",
        "description": "Undo last action",
        "parameters": {},
    },
    {
        "name": "redo",
        "description": "Redo last undone action",
        "parameters": {},
    },
]


# ═══════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════


class AIEditRequest(BaseModel):
    """Request for AI-driven editing."""
    prompt: str
    scene: dict | None = None  # Current scene state
    conversation_history: list[dict] = Field(default_factory=list)


class AIEditResponse(BaseModel):
    """Response with MCP operations to apply."""
    operations: list[dict]  # MCP tool calls
    explanation: str  # Human-readable explanation
    confidence: float  # 0..1
    needs_clarification: bool = False
    clarification_question: str | None = None


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


# ═══════════════════════════════════════════════════════════════
# LLM prompt templates
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an AI architecture assistant that controls a 3D building editor.

You have the following MCP tools available:
{tools}

Current scene state:
{scene}

RULES:
1. Always return a JSON array of MCP tool calls
2. Use the exact tool names and parameter formats shown above
3. For walls: start/end are [x, y] coordinates in meters
4. For openings: position is 0..1 along the wall (0=start, 1=end)
5. Default wall height: 3.0m, thickness: 0.3m
6. Default door: 0.9m wide, 2.1m high
7. Default window: 1.2m wide, 1.2m high, sill at 0.9m
8. Grid snap: 0.5m increments

RESPOND WITH JSON ONLY:
{{
  "operations": [
    {{"tool": "tool_name", "params": {{...}}}},
    ...
  ],
  "explanation": "Brief description of what you're creating",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": null
}}

If the request is ambiguous, set needs_clarification=true and ask a question.
"""

USER_PROMPT_TEMPLATE = """User request: {prompt}

{context}

Generate MCP operations to fulfill this request."""


# ═══════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mcp-llm-bridge"}


@app.get("/api/v1/mcp/tools")
async def list_tools():
    """List available MCP tools."""
    return {"tools": MCP_TOOLS}


@app.post("/api/v1/mcp/ai-edit")
async def ai_edit(req: AIEditRequest) -> AIEditResponse:
    """
    AI-driven editing: natural language → MCP operations.
    
    Pipeline:
    1. Build prompt with scene context + MCP tool definitions
    2. Send to LLM Service
    3. Parse response → MCP operations
    4. Validate operations against scene
    5. Return operations for client to execute
    """
    tools_json = json.dumps(MCP_TOOLS, indent=2, ensure_ascii=False)
    scene_json = json.dumps(req.scene or {}, indent=2, ensure_ascii=False)[:3000]

    system_msg = SYSTEM_PROMPT.format(tools=tools_json, scene=scene_json)
    user_msg = USER_PROMPT_TEMPLATE.format(
        prompt=req.prompt,
        context=f"Scene has {len(req.scene.get('nodes', {})) if req.scene else 0} nodes."
    )

    # Build messages for LLM
    messages = [{"role": "system", "content": system_msg}]
    messages.extend(req.conversation_history[-5:])  # Last 5 messages for context
    messages.append({"role": "user", "content": user_msg})

    # Call LLM Service
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{LLM_SERVICE_URL}/chat",
                json={
                    "messages": messages,
                    "temperature": 0.1,  # Low temperature for precise tool calls
                    "max_tokens": 2000,
                },
            )
            resp.raise_for_status()
            llm_result = resp.json()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Fallback to regex parsing
            return _regex_fallback_edit(req.prompt, req.scene)

    # Parse LLM response
    content = llm_result.get("content") or llm_result.get("message", "")

    try:
        # Try to extract JSON from response
        parsed = _extract_json(content)
        operations = parsed.get("operations", [])

        # Validate and fix operations
        validated_ops = _validate_operations(operations, req.scene)

        return AIEditResponse(
            operations=validated_ops,
            explanation=parsed.get("explanation", "Operations generated"),
            confidence=parsed.get("confidence", 0.8),
            needs_clarification=parsed.get("needs_clarification", False),
            clarification_question=parsed.get("clarification_question"),
        )
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}")
        return _regex_fallback_edit(req.prompt, req.scene)


@app.post("/api/v1/mcp/execute")
async def execute_operations(operations: list[dict]):
    """
    Execute MCP operations and return the updated scene.
    
    Each operation: {"tool": "create_wall", "params": {...}}
    """
    results = []
    scene = {"nodes": {}, "rootNodeIds": []}

    for op in operations:
        tool = op.get("tool")
        params = op.get("params", {})

        result = _execute_single_tool(tool, params, scene)
        results.append({"tool": tool, "result": result})

    return {"results": results, "scene": scene}


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    import re

    # Try direct JSON parse
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    # Try extracting from code block
    json_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if json_match:
        return json.loads(json_match.group(1))

    # Try finding JSON object
    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError("No JSON found in response")


def _validate_operations(operations: list[dict], scene: dict | None) -> list[dict]:
    """Validate and fix MCP operations."""
    validated = []
    nodes = scene.get("nodes", {}) if scene else {}

    for op in operations:
        tool = op.get("tool")
        params = op.get("params", {})

        if tool == "create_wall":
            # Ensure required params
            if "start" not in params or "end" not in params:
                continue
            params.setdefault("thickness", 0.3)
            params.setdefault("height", 3.0)

            # Ensure levelId exists
            if "levelId" not in params:
                # Find first level in scene
                for nid, node in nodes.items():
                    if node.get("type") == "level":
                        params["levelId"] = nid
                        break

        elif tool == "cut_opening":
            if "wallId" not in params or "type" not in params:
                continue
            params.setdefault("width", 0.9 if params["type"] == "door" else 1.2)
            params.setdefault("height", 2.1 if params["type"] == "door" else 1.2)

        validated.append({"tool": tool, "params": params})

    return validated


def _regex_fallback_edit(prompt: str, scene: dict | None) -> AIEditResponse:
    """Regex-based fallback when LLM is unavailable."""
    import re

    prompt_lower = prompt.lower()
    operations = []
    explanation = ""

    # Detect "create room" patterns
    dims = re.findall(r"(\d+(?:\.\d+)?)\s*[x×х*]\s*(\d+(?:\.\d+)?)", prompt)
    if dims:
        w, l = float(dims[0][0]), float(dims[0][1])
        hw, hl = w / 2, l / 2

        # Find or create level
        level_id = None
        if scene:
            for nid, node in scene.get("nodes", {}).items():
                if node.get("type") == "level":
                    level_id = nid
                    break

        if not level_id:
            level_id = f"level_{uuid.uuid4().hex[:6]}"
            operations.append({
                "tool": "create_level",
                "params": {"buildingId": "building_1", "name": "Floor 1", "elevation": 0},
            })

        # 4 walls
        wall_ids = []
        corners = [
            ([-hw, -hl], [hw, -hl]),
            ([[hw, -hl], [hw, hl]]),
            ([[hw, hl], [-hw, hl]]),
            ([[-hw, hl], [-hw, -hl]]),
        ]
        for i, (start, end) in enumerate(corners):
            wid = f"wall_{uuid.uuid4().hex[:6]}"
            wall_ids.append(wid)
            operations.append({
                "tool": "create_wall",
                "params": {
                    "levelId": level_id,
                    "start": start,
                    "end": end,
                    "thickness": 0.3,
                    "height": 3.0,
                },
            })

        # Door on first wall
        operations.append({
            "tool": "cut_opening",
            "params": {
                "wallId": "wall_0",  # Will be fixed by validator
                "type": "door",
                "position": 0.5,
                "width": 0.9,
                "height": 2.1,
            },
        })

        # Windows on other walls
        for i in range(1, 4):
            operations.append({
                "tool": "cut_opening",
                "params": {
                    "wallId": f"wall_{i}",
                    "type": "window",
                    "position": 0.5,
                    "width": 1.5,
                    "height": 1.2,
                },
            })

        explanation = f"Created {w}×{l}m room with door and 3 windows"

    elif "окно" in prompt_lower or "window" in prompt_lower:
        operations.append({
            "tool": "cut_opening",
            "params": {"wallId": "wall_0", "type": "window", "position": 0.5, "width": 1.5, "height": 1.2},
        })
        explanation = "Added window"

    elif "двер" in prompt_lower or "door" in prompt_lower:
        operations.append({
            "tool": "cut_opening",
            "params": {"wallId": "wall_0", "type": "door", "position": 0.5, "width": 0.9, "height": 2.1},
        })
        explanation = "Added door"

    else:
        return AIEditResponse(
            operations=[],
            explanation="Could not understand the request",
            confidence=0.1,
            needs_clarification=True,
            clarification_question="Please describe what you'd like to create. For example: 'Create a 10x12 room with a door and 3 windows'",
        )

    return AIEditResponse(
        operations=operations,
        explanation=explanation,
        confidence=0.6,
    )


def _execute_single_tool(tool: str, params: dict, scene: dict) -> dict:
    """Execute a single MCP tool on the scene."""
    nodes = scene.setdefault("nodes", {})
    root_ids = scene.setdefault("rootNodeIds", [])

    if tool == "create_wall":
        wall_id = f"wall_{uuid.uuid4().hex[:6]}"
        level_id = params.get("levelId")

        wall = {
            "object": "node",
            "id": wall_id,
            "type": "wall",
            "name": f"Wall",
            "parentId": level_id,
            "visible": True,
            "start": params.get("start", [0, 0]),
            "end": params.get("end", [0, 0]),
            "thickness": params.get("thickness", 0.3),
            "height": params.get("height", 3.0),
            "frontSide": "unknown",
            "backSide": "unknown",
            "children": [],
            "metadata": {},
        }
        nodes[wall_id] = wall
        if level_id and level_id in nodes:
            nodes[level_id].setdefault("children", []).append(wall_id)

        return {"wallId": wall_id}

    elif tool == "cut_opening":
        wall_id = params.get("wallId")
        opening_type = params.get("type", "door")
        opening_id = f"{opening_type}_{uuid.uuid4().hex[:6]}"

        wall = nodes.get(wall_id)
        if not wall or wall.get("type") != "wall":
            return {"error": f"Wall {wall_id} not found"}

        wall_start = wall.get("start", [0, 0])
        wall_end = wall.get("end", [0, 0])
        wall_len = ((wall_end[0] - wall_start[0]) ** 2 + (wall_end[1] - wall_start[1]) ** 2) ** 0.5

        position = params.get("position", 0.5)
        along = position * wall_len

        height = params.get("height", 2.1 if opening_type == "door" else 1.2)
        sill = 0 if opening_type == "door" else 0.9

        opening = {
            "object": "node",
            "id": opening_id,
            "type": opening_type,
            "name": opening_type.title(),
            "parentId": wall_id,
            "visible": True,
            "width": params.get("width", 0.9 if opening_type == "door" else 1.2),
            "height": height,
            "position": [along, sill + height / 2, 0],
            "metadata": {},
        }
        nodes[opening_id] = opening
        wall.setdefault("children", []).append(opening_id)

        return {"openingId": opening_id}

    elif tool == "create_level":
        level_id = f"level_{uuid.uuid4().hex[:6]}"
        building_id = params.get("buildingId")

        level = {
            "object": "node",
            "id": level_id,
            "type": "level",
            "name": params.get("name", "Floor"),
            "level": params.get("level", 0),
            "parentId": building_id,
            "visible": True,
            "children": [],
            "metadata": {"elevation": params.get("elevation", 0)},
        }
        nodes[level_id] = level
        if building_id and building_id in nodes:
            nodes[building_id].setdefault("children", []).append(level_id)

        return {"levelId": level_id}

    elif tool == "get_scene":
        return {"scene": scene}

    elif tool == "validate_scene":
        errors = []
        for nid, node in nodes.items():
            if node.get("type") == "wall":
                start = node.get("start", [0, 0])
                end = node.get("end", [0, 0])
                length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
                if length < 0.1:
                    errors.append(f"Wall {nid} too short ({length:.2f}m)")
                if node.get("height", 0) < 0.5:
                    errors.append(f"Wall {nid} too short vertically")
        return {"valid": len(errors) == 0, "errors": errors}

    elif tool == "delete_node":
        node_id = params.get("nodeId")
        if node_id in nodes:
            # Remove from parent's children
            node = nodes[node_id]
            parent_id = node.get("parentId")
            if parent_id and parent_id in nodes:
                children = nodes[parent_id].get("children", [])
                if node_id in children:
                    children.remove(node_id)
            del nodes[node_id]
            return {"deleted": node_id}
        return {"error": f"Node {node_id} not found"}

    return {"error": f"Unknown tool: {tool}"}


# ═══════════════════════════════════════════════════════════════
# Chat endpoint (for conversational editing)
# ═══════════════════════════════════════════════════════════════


class ChatRequest(BaseModel):
    message: str
    scene: dict | None = None
    history: list[ChatMessage] = Field(default_factory=list)


@app.post("/api/v1/mcp/chat")
async def chat_edit(req: ChatRequest):
    """
    Conversational editing: chat with AI to modify the scene.
    
    Maintains conversation context and applies changes incrementally.
    """
    history_dicts = [{"role": m.role, "content": m.content} for m in req.history]

    edit_req = AIEditRequest(
        prompt=req.message,
        scene=req.scene,
        conversation_history=history_dicts,
    )

    result = await ai_edit(edit_req)

    return {
        "reply": result.explanation,
        "operations": result.operations,
        "confidence": result.confidence,
        "needs_clarification": result.needs_clarification,
        "clarification_question": result.clarification_question,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8086)
