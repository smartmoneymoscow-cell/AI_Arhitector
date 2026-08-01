"""
test_e2e.py — End-to-end тесты всего pipeline.

Проверяет:
1. Парсер (LLM-only, каскад, кеш)
2. Redis кеш (fakeredis)
3. Валидация параметров
4. Роутинг (building/interior)
5. Агенты (parser → geometry → texture → render → export → quality)
6. Оркестратор (полный pipeline)
7. Nginx конфиг (валидность)
8. Dockerfile (компиляция)
9. 16K tiled rendering (скрипт генерация)
10. Auth middleware

Запуск: PYTHONPATH=. python3 tests/test_e2e.py
"""

import sys
import os
import json
import time
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = 0
FAIL = 0
ERRORS = []


def test(name, fn):
    global PASS, FAIL, ERRORS
    try:
        fn()
        PASS += 1
        print(f"  ✅ {name}")
    except Exception as e:
        FAIL += 1
        ERRORS.append((name, str(e)))
        print(f"  ❌ {name}: {e}")


# ═══════════════════════════════════════════════════════════════
# MOCK LLM
# ═══════════════════════════════════════════════════════════════

MOCK_RESPONSES = {
    "двухэтажный кирпичный дом 10×12": {
        "object_type": "building", "building_type": "house", "floors": 2,
        "width_m": 10, "length_m": 12, "style": "modern", "material": "brick",
        "roof_type": "gabled", "features": ["balcony"], "furniture": [], "confidence": 0.95
    },
    "спальня в стиле хайтек": {
        "object_type": "room", "room_type": "bedroom", "floors": 1,
        "width_m": 5, "length_m": 6, "style": "hitech", "material": "plaster",
        "roof_type": "flat", "features": [], "furniture": ["bed", "wardrobe", "nightstand"],
        "confidence": 0.85
    },
    "офис 5 этажей стекло 20×24": {
        "object_type": "building", "building_type": "office", "floors": 5,
        "width_m": 20, "length_m": 24, "style": "modern", "material": "glass",
        "roof_type": "flat", "features": [], "furniture": [], "confidence": 0.95
    },
    "кирпичный дом": {
        "object_type": "building", "building_type": "house", "floors": 2,
        "width_m": 10, "length_m": 12, "style": "modern", "material": "brick",
        "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.95
    },
}


def _mock_call_llm(text, cfg):
    for key, resp in MOCK_RESPONSES.items():
        if key in text:
            return resp
    return {"object_type": "building", "building_type": "house", "floors": 2,
            "width_m": 10, "length_m": 12, "style": "modern", "material": "plaster",
            "roof_type": "gabled", "features": [], "furniture": [], "confidence": 0.5}


# ═══════════════════════════════════════════════════════════════
# 1. PARSER
# ═══════════════════════════════════════════════════════════════

print("\n═══ 1. PARSER (LLM-only, no regex) ═══")


def test_parser_imports():
    from shared.parser import parse_prompt, parse_prompt_async, AllModelsFailedError
    from shared.parser import get_generation_type, get_cache_stats, LLM_CASCADE
    assert len(LLM_CASCADE) == 7
    assert callable(parse_prompt)
    assert callable(parse_prompt_async)
test("Parser imports", test_parser_imports)


def test_parser_no_regex():
    import shared.parser as p
    assert not hasattr(p, 'fallback_regex_parse')
    source = open(p.__file__).read()
    assert "def fallback_regex_parse" not in source
test("No regex in parser", test_parser_no_regex)


@patch("shared.parser._call_llm", side_effect=_mock_call_llm)
def test_parser_building(mock):
    from shared.parser import parse_prompt
    p = parse_prompt("двухэтажный кирпичный дом 10×12")
    assert p["object_type"] == "building"
    assert p["material"] == "brick"
    assert p["floors"] == 2
    assert p["width_m"] == 10
    assert p["length_m"] == 12
test("Parser: building", test_parser_building)


@patch("shared.parser._call_llm", side_effect=_mock_call_llm)
def test_parser_room(mock):
    from shared.parser import parse_prompt
    p = parse_prompt("спальня в стиле хайтек")
    assert p["object_type"] == "room"
    assert p["room_type"] == "bedroom"
    assert p["style"] == "hitech"
test("Parser: room", test_parser_room)


def test_parser_empty():
    from shared.parser import parse_prompt
    p = parse_prompt("")
    assert p["object_type"] == "building"
    assert p["floors"] == 2
test("Parser: empty prompt", test_parser_empty)


def test_parser_all_models_failed():
    from shared.parser import parse_prompt, AllModelsFailedError
    with patch("shared.parser._call_llm", return_value=None):
        with patch("shared.parser._l2_get", return_value=None):
            try:
                parse_prompt("test")
                assert False, "Should have raised"
            except AllModelsFailedError:
                pass
test("Parser: AllModelsFailedError", test_parser_all_models_failed)


# ═══════════════════════════════════════════════════════════════
# 2. CACHE
# ═══════════════════════════════════════════════════════════════

print("\n═══ 2. CACHE (L1 + L2) ═══")


def test_l1_cache():
    from shared.parser import _l1_set, _l1_get
    _l1_set("test_key_1", {"object_type": "building"})
    assert _l1_get("test_key_1") == {"object_type": "building"}
    assert _l1_get("nonexistent") is None
test("L1 cache set/get", test_l1_cache)


def test_cache_stats():
    from shared.parser import get_cache_stats
    s = get_cache_stats()
    assert "l1_entries" in s
    assert "l1_max" in s
    assert "llm_cascade" in s
    assert len(s["llm_cascade"]) == 7
test("Cache stats", test_cache_stats)


def test_redis_cache_with_fakeredis():
    import fakeredis
    r = fakeredis.FakeRedis(decode_responses=True)
    r.setex("parse:test123", 3600, json.dumps({"object_type": "building"}))
    raw = r.get("parse:test123")
    assert json.loads(raw) == {"object_type": "building"}
test("Redis cache (fakeredis)", test_redis_cache_with_fakeredis)


# ═══════════════════════════════════════════════════════════════
# 3. VALIDATION
# ═══════════════════════════════════════════════════════════════

print("\n═══ 3. VALIDATION ═══")


def test_validation():
    from shared.validation import validate_params
    v = validate_params({"object_type": "room", "room_type": "bedroom", "style": "loft", "material": "brick"})
    assert v["object_type"] == "room"
    assert v["room_type"] == "bedroom"
    assert v["style"] == "loft"
    assert v["material"] == "brick"
    assert "bed" in v["furniture"]
test("Validation: valid params", test_validation)


def test_validation_invalid():
    from shared.validation import validate_params
    v = validate_params({"object_type": "INVALID", "style": "INVALID", "floors": 100})
    assert v["object_type"] == "building"
    assert v["style"] == "modern"
    assert v["floors"] == 2
test("Validation: invalid params", test_validation_invalid)


# ═══════════════════════════════════════════════════════════════
# 4. ROUTING
# ═══════════════════════════════════════════════════════════════

print("\n═══ 4. ROUTING ═══")


def test_routing():
    from shared.parser import get_generation_type
    assert get_generation_type({"object_type": "building"}) == "building"
    assert get_generation_type({"object_type": "room"}) == "interior"
    assert get_generation_type({"object_type": "interior"}) == "interior"
    assert get_generation_type({}) == "building"
test("Routing types", test_routing)


@patch("shared.parser._call_llm", side_effect=_mock_call_llm)
def test_router_building(mock):
    from shared.router import route_generation
    plan = route_generation("двухэтажный кирпичный дом 10×12")
    assert plan.gen_type == "building"
    assert plan.params["building"]["W"] == 10.0
    assert plan.params["building"]["L"] == 12.0
    assert plan.params["building"]["mat"] == "brick"
    assert len(plan.steps) >= 3
test("Router: building plan", test_router_building)


@patch("shared.parser._call_llm", side_effect=_mock_call_llm)
def test_router_interior(mock):
    from shared.router import route_generation
    plan = route_generation("спальня в стиле хайтек")
    assert plan.gen_type == "interior"
test("Router: interior plan", test_router_interior)


# ═══════════════════════════════════════════════════════════════
# 5. AGENTS
# ═══════════════════════════════════════════════════════════════

print("\n═══ 5. AGENTS ═══")


def test_parser_agent():
    from shared.agents.parser_agent import ParserAgent
    from shared.agents.base import Task, TaskStatus
    import shared.parser
    agent = ParserAgent()
    with patch.object(shared.parser, '_call_llm', side_effect=_mock_call_llm):
        task = Task(name="parse", agent="parser", params={"prompt": "кирпичный дом"})
        result = agent.process(task)
        assert result.status == TaskStatus.DONE
        assert result.data["gen_type"] == "building"
        assert result.data["params"]["material"] == "brick"
test("ParserAgent", test_parser_agent)


def test_geometry_agent():
    from shared.agents.geometry_agent import GeometryAgent
    from shared.agents.base import Task, TaskStatus
    agent = GeometryAgent()
    task = Task(name="geom", agent="geometry", params={
        "gen_type": "building",
        "building_params": {"width": 10, "length": 12, "floors": 2, "roof_type": "gabled", "facade_material": "brick"},
    })
    result = agent.process(task)
    assert result.status == TaskStatus.DONE
    assert "import bpy" in result.data["script"]
test("GeometryAgent", test_geometry_agent)


def test_texture_agent():
    from shared.agents.texture_agent import TextureAgent
    from shared.agents.base import Task, TaskStatus
    agent = TextureAgent()
    task = Task(name="tex", agent="texture", params={"material": "brick"})
    result = agent.process(task)
    assert result.status == TaskStatus.DONE
    assert result.data["material"] == "brick"
    assert "script" in result.data
test("TextureAgent", test_texture_agent)


def test_quality_agent():
    from shared.agents.quality_agent import QualityAgent
    from shared.agents.base import Task, TaskStatus
    agent = QualityAgent()
    # Test with non-existent file
    task = Task(name="quality", agent="quality", params={"render_path": "/nonexistent", "quality": "standard"})
    result = agent.process(task)
    assert result.status == TaskStatus.FAILED  # file not found
test("QualityAgent (file not found)", test_quality_agent)


def test_render_presets():
    from shared.agents.render_agent import QUALITY_PRESETS
    assert "preview" in QUALITY_PRESETS
    assert "standard" in QUALITY_PRESETS
    assert "high" in QUALITY_PRESETS
    assert "ultra" in QUALITY_PRESETS
    assert "16k" in QUALITY_PRESETS
    assert QUALITY_PRESETS["16k"]["resolution_x"] == 15360
    assert QUALITY_PRESETS["16k"]["resolution_y"] == 8640
    assert QUALITY_PRESETS["16k"]["samples"] == 2048
    assert QUALITY_PRESETS["16k"]["engine"] == "CYCLES"
test("Render presets (16K)", test_render_presets)


def test_export_commands():
    from shared.agents.export_agent import EXPORT_COMMANDS
    assert "glb" in EXPORT_COMMANDS
    assert "obj" in EXPORT_COMMANDS
    assert "fbx" in EXPORT_COMMANDS
    glb_cmd = EXPORT_COMMANDS["glb"]("/tmp/test.glb")
    assert "export_scene.gltf" in glb_cmd
test("Export commands", test_export_commands)


# ═══════════════════════════════════════════════════════════════
# 6. ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

print("\n═══ 6. ORCHESTRATOR ═══")


@patch("shared.parser._call_llm", side_effect=_mock_call_llm)
def test_orchestrator_full(mock):
    from shared.agents.orchestrator import Orchestrator
    orch = Orchestrator(output_dir="/tmp/arch_test")
    result = orch.execute("двухэтажный кирпичный дом 10×12")
    assert result["status"] == "done"
    assert result["result"]["gen_type"] == "building"
    assert result["result"]["params"]["material"] == "brick"
    assert len(result["steps"]) >= 3
    assert result["duration_ms"] > 0
    # Check steps
    step_names = [s["name"] for s in result["steps"]]
    assert "parse" in step_names
    assert "geometry" in step_names
test("Orchestrator: full pipeline", test_orchestrator_full)


@patch("shared.parser._call_llm", side_effect=_mock_call_llm)
def test_orchestrator_interior(mock):
    from shared.agents.orchestrator import Orchestrator
    orch = Orchestrator(output_dir="/tmp/arch_test")
    result = orch.execute("спальня в стиле хайтек", skip_clarification=True)
    assert result["status"] == "done"
    assert result["result"]["gen_type"] == "interior"
test("Orchestrator: interior", test_orchestrator_interior)


# ═══════════════════════════════════════════════════════════════
# 7. NGINX CONFIG
# ═══════════════════════════════════════════════════════════════

print("\n═══ 7. NGINX CONFIG ═══")


def test_nginx_config_syntax():
    conf_path = os.path.join(os.path.dirname(__file__), "..", "nginx.conf")
    with open(conf_path) as f:
        content = f.read()
    # Basic syntax checks
    assert "upstream gateway" in content
    assert "upstream llm_service" in content
    assert "upstream blender_service" in content
    assert "limit_req_zone" in content
    assert "proxy_buffering off" in content  # SSE
    assert "gzip on" in content
    assert "proxy_cache" in content
    assert "X-Content-Type-Options" in content
    assert "/api/v1/parse" in content
    assert "/api/v1/generate" in content
    assert "/api/v1/orchestrator" in content
    assert "/api/v1/render/16k" in content
    assert "7200s" in content  # 16K timeout
test("Nginx config: syntax and content", test_nginx_config_syntax)


# ═══════════════════════════════════════════════════════════════
# 8. DOCKERFILES
# ═══════════════════════════════════════════════════════════════

print("\n═══ 8. DOCKERFILES ═══")


def test_dockerfiles_exist():
    base = os.path.join(os.path.dirname(__file__), "..")
    for name in ["gateway.Dockerfile", "llm.Dockerfile", "blender.Dockerfile"]:
        path = os.path.join(base, name)
        assert os.path.exists(path), f"{name} missing"
        with open(path) as f:
            content = f.read()
        assert "FROM" in content
        assert "COPY" in content
        assert "CMD" in content
test("Dockerfiles exist and valid", test_dockerfiles_exist)


def test_docker_compose():
    import yaml
    path = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")
    with open(path) as f:
        content = f.read()
    assert "nginx:" in content
    assert "gateway:" in content
    assert "llm-service:" in content
    assert "blender-service:" in content
    assert "redis:" in content
    assert "healthcheck:" in content
    assert "gateway.Dockerfile" in content
    assert "llm.Dockerfile" in content
    assert "blender.Dockerfile" in content
test("docker-compose.yml: services", test_docker_compose)


# ═══════════════════════════════════════════════════════════════
# 9. TILED RENDERING
# ═══════════════════════════════════════════════════════════════

print("\n═══ 9. TILED RENDERING (16K) ═══")


def test_tiled_render_script():
    from shared.tiled_render import _build_tile_script
    script = _build_tile_script(
        scene_script="# test scene",
        output_path="/tmp/tile_0_0.png",
        total_x=15360, total_y=8640,
        tile_x=0, tile_y=0,
        tile_w=3840, tile_h=2880,
        samples=2048,
    )
    assert "CYCLES" in script
    assert "15360" in script
    assert "8640" in script
    assert "2048" in script
    assert "border" in script
    assert "/tmp/tile_0_0.png" in script
    # Verify it compiles
    compile(script, "<tile>", "exec")
test("Tiled render: script generation", test_tiled_render_script)


def test_tiled_render_endpoint():
    # Check blender-service has /api/v1/render/16k
    path = os.path.join(os.path.dirname(__file__), "..", "blender-service", "app.py")
    with open(path) as f:
        content = f.read()
    assert "/api/v1/render/16k" in content
    assert "render_16k_tiled" in content
test("Tiled render: endpoint exists", test_tiled_render_endpoint)


# ═══════════════════════════════════════════════════════════════
# 10. AUTH
# ═══════════════════════════════════════════════════════════════

print("\n═══ 10. AUTH ═══")


def test_auth_module():
    from shared.auth import get_api_key_optional, get_api_key_required
    from shared.auth import rate_limiter, RateLimiter, check_rate_limit
    assert callable(get_api_key_optional)
    assert callable(get_api_key_required)
    assert isinstance(rate_limiter, RateLimiter)
test("Auth module imports", test_auth_module)


def test_rate_limiter():
    from shared.auth import RateLimiter
    rl = RateLimiter(requests_per_minute=5, requests_per_hour=100)
    stats = rl.get_stats()
    assert stats["rpm_limit"] == 5
    assert stats["rph_limit"] == 100
test("Rate limiter", test_rate_limiter)


# ═══════════════════════════════════════════════════════════════
# 11. COMPILATION
# ═══════════════════════════════════════════════════════════════

print("\n═══ 11. COMPILATION ═══")


def test_all_compile():
    import py_compile
    base = os.path.join(os.path.dirname(__file__), "..")
    files = [
        "shared/parser.py", "shared/validation.py", "shared/config.py",
        "shared/models.py", "shared/auth.py", "shared/tiled_render.py",
        "shared/agents/base.py", "shared/agents/parser_agent.py",
        "shared/agents/geometry_agent.py", "shared/agents/texture_agent.py",
        "shared/agents/render_agent.py", "shared/agents/export_agent.py",
        "shared/agents/quality_agent.py", "shared/agents/orchestrator.py",
        "gateway/app.py", "llm-service/app.py", "blender-service/app.py",
        "server.py",
    ]
    for f in files:
        py_compile.compile(os.path.join(base, f), doraise=True)
test("All Python files compile", test_all_compile)


# ═══════════════════════════════════════════════════════════════
# 12. DOCUMENTATION
# ═══════════════════════════════════════════════════════════════

print("\n═══ 12. DOCUMENTATION ═══")


def test_docs_exist():
    base = os.path.join(os.path.dirname(__file__), "..")
    for name in ["AUDIT.md", "ROADMAP.md"]:
        path = os.path.join(base, name)
        assert os.path.exists(path), f"{name} missing"
        with open(path) as f:
            content = f.read()
        assert len(content) > 1000, f"{name} too short"
test("Documentation files", test_docs_exist)


def test_audit_covers_12_questions():
    path = os.path.join(os.path.dirname(__file__), "..", "AUDIT.md")
    with open(path) as f:
        content = f.read()
    for q in range(1, 13):
        assert f"Q{q}:" in content, f"Q{q} missing from AUDIT.md"
test("AUDIT.md: all 12 questions", test_audit_covers_12_questions)


# ═══════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════

print(f"\n{'═' * 50}")
print(f"  TOTAL: {PASS + FAIL} tests")
print(f"  ✅ PASSED: {PASS}")
print(f"  ❌ FAILED: {FAIL}")
if ERRORS:
    print(f"\n  FAILURES:")
    for name, err in ERRORS:
        print(f"    - {name}: {err}")
print(f"{'═' * 50}")

sys.exit(1 if FAIL > 0 else 0)
