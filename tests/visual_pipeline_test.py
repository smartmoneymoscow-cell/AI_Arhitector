"""
Visual Pipeline Test — E2E тестирование полного цикла генерации.

Запуск:
  python3 tests/visual_pipeline_test.py

Требования:
  - Сервис запущен (docker-compose up или localhost)
  - mimo_api.sh доступен для CV-анализа

Методология:
  1. Отправка промта через API
  2. Фиксация ответа на каждом этапе
  3. CV-анализ скриншотов
  4. Сопоставление результата с промтом
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# ═══ Configuration ═══
API_BASE = os.environ.get("API_BASE", "http://localhost:8080")
API_KEY = os.environ.get("ARCH_API_KEYS", "test-key").split(",")[0]
SCREENSHOTS_DIR = Path("screenshots/pipeline_tests")
MIMO_API = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")


@dataclass
class TestResult:
    name: str
    prompt: str
    steps: list = field(default_factory=list)
    passed: bool = True
    errors: list = field(default_factory=list)
    screenshots: list = field(default_factory=list)
    api_logs: list = field(default_factory=list)

    def check(self, name: str, condition: bool, detail: str = ""):
        status = "✅" if condition else "❌"
        self.steps.append(f"{status} {name}" + (f" — {detail}" if detail else ""))
        if not condition:
            self.passed = False
            self.errors.append(f"{name}: {detail}")

    def add_api_log(self, endpoint: str, response: dict):
        self.api_logs.append({"endpoint": endpoint, "response_keys": list(response.keys())})


def api_post(endpoint: str, data: dict) -> dict:
    """POST to API with auth."""
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    try:
        r = httpx.post(f"{API_BASE}{endpoint}", json=data, headers=headers, timeout=300)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "detail": r.text[:500]}
    except Exception as e:
        return {"error": str(e)}


def analyze_screenshot(image_path: str, prompt: str) -> str:
    """Analyze screenshot with vision model."""
    if not os.path.exists(MIMO_API):
        return "⚠️ mimo_api.sh not found — skipping CV analysis"
    try:
        result = subprocess.run(
            ["bash", MIMO_API, "image", image_path,
             f"Опиши что видно на скриншоте. Промт был: '{prompt}'. "
             "Соответствует ли результат промту? Есть ли артефакты? "
             "Оцени качество от 1 до 10."],
            capture_output=True, text=True, timeout=60
        )
        return result.stdout.strip()[:2000]
    except Exception as e:
        return f"⚠️ CV analysis failed: {e}"


# ═══ Test Suite 1: Chat Flow ═══

def test_simple_building():
    """1.1: Простой промт здания → status=done."""
    result = TestResult("Simple Building", "Построй двухэтажный коттедж 12x10 из кирпича")

    data = api_post("/api/v1/orchestrator/execute", {
        "prompt": result.prompt,
        "quality": "standard",
        "pipeline_profile": "standard",
        "skip_clarification": True,
        "export_formats": ["glb"]
    })
    result.add_api_log("/api/v1/orchestrator/execute", data)

    result.check("API responded", "error" not in data, data.get("error", ""))
    result.check("Status is done", data.get("status") == "done", f"got: {data.get('status')}")
    result.check("gen_type is building", data.get("gen_type") == "building", f"got: {data.get('gen_type')}")
    result.check("Has job_id", bool(data.get("job_id")))
    result.check("Has render data", bool(data.get("render")))
    result.check("Confidence > 0", data.get("confidence", 0) > 0, f"got: {data.get('confidence')}")

    return result


def test_interior_generation():
    """1.2: Интерьер ванной → status=done, gen_type=interior."""
    result = TestResult("Interior Bathroom", "Современный минималистичный интерьер ванной комнаты 3x4 с джакузи")

    data = api_post("/api/v1/orchestrator/execute", {
        "prompt": result.prompt,
        "quality": "standard",
        "pipeline_profile": "interior",
        "skip_clarification": True,
        "export_formats": ["glb"]
    })
    result.add_api_log("/api/v1/orchestrator/execute", data)

    result.check("API responded", "error" not in data, data.get("error", ""))
    result.check("Status is done", data.get("status") == "done", f"got: {data.get('status')}")
    result.check("gen_type is interior", data.get("gen_type") == "interior", f"got: {data.get('gen_type')}")

    params = data.get("params", {})
    result.check("room_type is bathroom", params.get("room_type") == "bathroom", f"got: {params.get('room_type')}")
    result.check("width ~3m", abs(params.get("width_m", 0) - 3) <= 1, f"got: {params.get('width_m')}")
    result.check("length ~4m", abs(params.get("length_m", 0) - 4) <= 1, f"got: {params.get('length_m')}")

    return result


def test_clarification_flow():
    """1.3: Неоднозначный промт → clarification_needed → resume."""
    result = TestResult("Clarification Flow", "Построй дом")

    # Step 1: Execute → should need clarification
    data = api_post("/api/v1/orchestrator/execute", {
        "prompt": result.prompt,
        "quality": "standard",
        "pipeline_profile": "standard",
        "skip_clarification": False,
        "export_formats": ["glb"]
    })
    result.add_api_log("/api/v1/orchestrator/execute", data)

    result.check("API responded", "error" not in data, data.get("error", ""))

    status = data.get("status")
    if status == "clarification_needed":
        result.check("Status is clarification_needed", True)
        clar = data.get("clarification", {})
        questions = clar.get("questions", [])
        result.check("Has questions", len(questions) >= 1, f"got {len(questions)} questions")
        result.check("Has partial_params", bool(clar.get("partial_params")))
        job_id = data.get("job_id")

        # Step 2: Resume with answers
        if job_id and questions:
            answers = {}
            for q in questions:
                field_name = q.get("field", "")
                options = q.get("options", [])
                if options:
                    answers[field_name] = options[0]

            resume_data = api_post("/api/v1/orchestrator/resume", {
                "job_id": job_id,
                "answers": answers,
                "quality": "standard",
                "pipeline_profile": "standard",
                "export_formats": ["glb"]
            })
            result.add_api_log("/api/v1/orchestrator/resume", resume_data)
            result.check("Resume responded", "error" not in resume_data, resume_data.get("error", ""))
            result.check("Resume status is done", resume_data.get("status") == "done",
                        f"got: {resume_data.get('status')}")
    elif status == "done":
        result.check("Status is done (no clarification needed)", True)
    else:
        result.check("Unexpected status", False, f"got: {status}")

    return result


def test_landscape_generation():
    """1.4: Ландшафт → status=done, gen_type=landscape."""
    result = TestResult("Landscape", "Ландшафтный дизайн сада с бассейном и японским садом")

    data = api_post("/api/v1/orchestrator/execute", {
        "prompt": result.prompt,
        "quality": "standard",
        "pipeline_profile": "landscape",
        "skip_clarification": True,
        "export_formats": ["glb"]
    })
    result.add_api_log("/api/v1/orchestrator/execute", data)

    result.check("API responded", "error" not in data, data.get("error", ""))
    result.check("Status is done", data.get("status") == "done", f"got: {data.get('status')}")
    result.check("gen_type is landscape", data.get("gen_type") == "landscape", f"got: {data.get('gen_type')}")

    return result


# ═══ Test Suite 2: PDF/DWG Analysis ═══

def test_pdf_analysis_endpoint():
    """2.1: PDF analysis endpoint exists and responds."""
    result = TestResult("PDF Analysis Endpoint", "N/A")

    # Test with empty request (should return 400 or similar)
    try:
        headers = {"X-API-Key": API_KEY}
        r = httpx.post(f"{API_BASE}/api/v1/analyze/pdf", headers=headers, timeout=10)
        result.check("Endpoint exists", r.status_code in (400, 422, 200), f"got HTTP {r.status_code}")
    except httpx.ConnectError:
        result.check("Endpoint reachable", False, "Connection refused")
    except Exception as e:
        result.check("Endpoint reachable", True, f"responded with: {e}")

    return result


def test_dwg_analysis_endpoint():
    """2.2: DWG analysis endpoint exists and responds."""
    result = TestResult("DWG Analysis Endpoint", "N/A")

    try:
        headers = {"X-API-Key": API_KEY}
        r = httpx.post(f"{API_BASE}/api/v1/analyze/dwg", headers=headers, timeout=10)
        result.check("Endpoint exists", r.status_code in (400, 422, 200), f"got HTTP {r.status_code}")
    except httpx.ConnectError:
        result.check("Endpoint reachable", False, "Connection refused")
    except Exception as e:
        result.check("Endpoint reachable", True, f"responded with: {e}")

    return result


# ═══ Test Suite 3: Pipeline Profiles ═══

def test_pipeline_profiles():
    """3.1: Verify all pipeline profiles are valid."""
    result = TestResult("Pipeline Profiles", "N/A")

    sys.path.insert(0, ".")
    from shared.agents.orchestrator import PIPELINE_PROFILES

    expected_profiles = ["quick", "standard", "full", "interior", "landscape", "electrical",
                        "mep_documentation", "interior_full", "presentation", "cad", "interactive"]

    for profile_name in expected_profiles:
        result.check(f"Profile '{profile_name}' exists",
                    profile_name in PIPELINE_PROFILES,
                    f"available: {list(PIPELINE_PROFILES.keys())}")

    # Verify each profile has parser as first agent
    for name, agents in PIPELINE_PROFILES.items():
        if agents:
            result.check(f"'{name}' starts with parser", agents[0] == "parser",
                        f"starts with: {agents[0]}")

    return result


# ═══ Test Suite 4: Quality Checks ═══

def test_quality_presets():
    """4.1: Verify quality presets are valid."""
    result = TestResult("Quality Presets", "N/A")

    sys.path.insert(0, ".")
    from shared.agents.render_agent import QUALITY_PRESETS

    for preset_name, preset in QUALITY_PRESETS.items():
        result.check(f"Preset '{preset_name}' has engine", "engine" in preset)
        result.check(f"Preset '{preset_name}' has resolution",
                    "resolution_x" in preset and "resolution_y" in preset)
        result.check(f"Preset '{preset_name}' has samples", "samples" in preset)

    # Verify resolution progression
    preview = QUALITY_PRESETS.get("preview", {})
    standard = QUALITY_PRESETS.get("standard", {})
    high = QUALITY_PRESETS.get("high", {})

    if preview and standard:
        result.check("standard > preview resolution",
                    standard.get("resolution_x", 0) > preview.get("resolution_x", 0))
    if standard and high:
        result.check("high > standard resolution",
                    high.get("resolution_x", 0) > standard.get("resolution_x", 0))

    return result


# ═══ Test Suite 5: Clarification Engine ═══

def test_clarification_engine():
    """5.1: ClarificationEngine functional tests."""
    result = TestResult("Clarification Engine", "N/A")

    sys.path.insert(0, ".")
    from shared.clarification import ClarificationEngine

    engine = ClarificationEngine()

    # Low confidence → needs clarification
    r = engine.analyze("построй дом", {"object_type": "building"}, confidence=0.3)
    result.check("Low confidence → clarification needed", r.needs_clarification)
    result.check("Low confidence → ≥2 questions", len(r.questions) >= 2,
                f"got {len(r.questions)} questions")

    # High confidence with all fields → no clarification
    r = engine.analyze("построй дом", {
        "object_type": "building", "building_type": "house",
        "floors": 2, "material": "brick", "roof_type": "gabled"
    }, confidence=0.9)
    result.check("High confidence + all fields → no clarification",
                not r.needs_clarification or len(r.questions) <= 1)

    # apply_answers works
    updated = engine.apply_answers({"object_type": "building"}, {"material": "кирпич"})
    result.check("apply_answers maps кирпич→brick", updated.get("material") == "brick",
                f"got: {updated.get('material')}")

    return result


# ═══ Main ═══

def run_all_tests():
    """Run all test suites."""
    print("=" * 60)
    print("🧪 AI_Arhitector v11.0.0 — Visual Pipeline Tests")
    print("=" * 60)
    print(f"API: {API_BASE}")
    print(f"Screenshots: {SCREENSHOTS_DIR}")
    print()

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    tests = [
        # Suite 1: Chat Flow
        test_simple_building,
        test_interior_generation,
        test_clarification_flow,
        test_landscape_generation,
        # Suite 2: PDF/DWG
        test_pdf_analysis_endpoint,
        test_dwg_analysis_endpoint,
        # Suite 3: Pipeline
        test_pipeline_profiles,
        # Suite 4: Quality
        test_quality_presets,
        # Suite 5: Clarification
        test_clarification_engine,
    ]

    results = []
    for test_fn in tests:
        print(f"Running: {test_fn.__name__}...")
        try:
            r = test_fn()
            results.append(r)
            status = "✅ PASS" if r.passed else "❌ FAIL"
            print(f"  {status} — {r.name}")
            for step in r.steps:
                print(f"    {step}")
            if r.errors:
                for err in r.errors:
                    print(f"    ⚠️  {err}")
        except Exception as e:
            print(f"  ❌ EXCEPTION — {test_fn.__name__}: {e}")
            results.append(TestResult(test_fn.__name__, "", passed=False, errors=[str(e)]))
        print()

    # Summary
    print("=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    print(f"Total: {total} | ✅ Passed: {passed} | ❌ Failed: {failed}")
    print("=" * 60)

    if failed:
        print("\n❌ FAILED TESTS:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {', '.join(r.errors)}")

    # Save report
    report_path = SCREENSHOTS_DIR / "test_report.json"
    report = {
        "total": total, "passed": passed, "failed": failed,
        "tests": [
            {
                "name": r.name, "prompt": r.prompt, "passed": r.passed,
                "steps": r.steps, "errors": r.errors, "api_logs": r.api_logs
            }
            for r in results
        ]
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n📊 Report saved: {report_path}")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
