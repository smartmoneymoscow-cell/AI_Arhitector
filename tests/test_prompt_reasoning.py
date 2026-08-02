"""
Комплексная проверка генерации и рассуждения по промту в чат

Полный цикл E2E тестирования:
  1. Отправка промта через API → парсинг LLM
  2. Анализ рассуждения: корректность извлечения параметров
  3. Генерация 3D модели → проверка bpy-скрипта
  4. Рендер превью → скриншот
  5. Анализ соответствия промту и результата
  6. Генерация отчёта с выводами

Запуск:
    # С живым сервером (Render или локальный):
    PYTHONPATH=. python3 tests/test_prompt_reasoning.py "двухэтажный кирпичный дом 10x12 с балконом"

    # Только проверка логики (без сервера, с моками):
    PYTHONPATH=. python3 tests/test_prompt_reasoning.py --dry-run "двухэтажный кирпичный дом 10x12"

    # С указанием URL сервера:
    PYTHONPATH=. python3 tests/test_prompt_reasoning.py --url https://architect.onrender.com "промт"
"""

import sys
import os
import json
import time
import argparse
import hashlib
import tempfile
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════

@dataclass
class ReasoningStep:
    """Один шаг рассуждения системы."""
    name: str
    status: str  # "ok" | "fail" | "skip"
    duration_ms: float = 0
    details: str = ""
    expected: str = ""
    actual: str = ""
    correct: bool = True


@dataclass
class ReasoningAnalysis:
    """Анализ рассуждения LLM и pipeline."""
    prompt: str = ""
    parsed_params: dict = field(default_factory=dict)
    expected_params: dict = field(default_factory=dict)
    steps: list[ReasoningStep] = field(default_factory=list)
    param_accuracy: float = 0.0
    pipeline_correct: bool = False
    order_correct: bool = False
    all_critical_ok: bool = False
    summary: str = ""


@dataclass
class PreviewAnalysis:
    """Анализ превью/рендера."""
    screenshot_path: str = ""
    render_path: str = ""
    resolution: str = ""
    quality_matches: bool = False
    has_3d_model: bool = False
    mesh_count: int = 0
    ai_description: str = ""
    ai_match_score: float = 0.0
    ai_bugs: list[str] = field(default_factory=list)
    prompt_match: bool = False
    summary: str = ""


@dataclass
class TestReport:
    """Полный отчёт теста."""
    test_name: str = "Комплексная проверка генерации и рассуждения по промту в чат"
    prompt: str = ""
    timestamp: str = ""
    server_url: str = ""
    mode: str = ""  # "live" | "dry-run"
    reasoning: ReasoningAnalysis = field(default_factory=ReasoningAnalysis)
    preview: PreviewAnalysis = field(default_factory=PreviewAnalysis)
    screenshots: list[str] = field(default_factory=list)
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "prompt": self.prompt,
            "timestamp": self.timestamp,
            "server_url": self.server_url,
            "mode": self.mode,
            "reasoning": {
                "parsed_params": self.reasoning.parsed_params,
                "param_accuracy": self.reasoning.param_accuracy,
                "pipeline_correct": self.reasoning.pipeline_correct,
                "order_correct": self.reasoning.order_correct,
                "steps": [
                    {"name": s.name, "status": s.status, "correct": s.correct,
                     "expected": s.expected, "actual": s.actual, "details": s.details}
                    for s in self.reasoning.steps
                ],
                "summary": self.reasoning.summary,
            },
            "preview": {
                "screenshot_path": self.preview.screenshot_path,
                "render_path": self.preview.render_path,
                "resolution": self.preview.resolution,
                "quality_matches": self.preview.quality_matches,
                "has_3d_model": self.preview.has_3d_model,
                "mesh_count": self.preview.mesh_count,
                "ai_description": self.preview.ai_description,
                "ai_match_score": self.preview.ai_match_score,
                "ai_bugs": self.preview.ai_bugs,
                "prompt_match": self.preview.prompt_match,
                "summary": self.preview.summary,
            },
            "screenshots": self.screenshots,
            "passed": self.passed,
            "errors": self.errors,
            "duration_ms": self.duration_ms,
        }

    def print_report(self):
        """Красивый вывод отчёта."""
        print("\n" + "═" * 70)
        print(f"  {self.test_name}")
        print("═" * 70)
        print(f"  Промт:     {self.prompt}")
        print(f"  Сервер:    {self.server_url}")
        print(f"  Режим:     {self.mode}")
        print(f"  Время:     {self.timestamp}")
        print(f"  Длительность: {self.duration_ms:.0f}мс")
        print()

        # ── Reasoning ──
        print("  ── Анализ рассуждения ──")
        print(f"  Точность параметров: {self.reasoning.param_accuracy:.0%}")
        print(f"  Pipeline корректен:  {'✅' if self.reasoning.pipeline_correct else '❌'}")
        print(f"  Порядок шагов верный: {'✅' if self.reasoning.order_correct else '❌'}")
        print()

        if self.reasoning.parsed_params:
            print("  Распарсенные параметры:")
            for k, v in self.reasoning.parsed_params.items():
                print(f"    {k}: {v}")
            print()

        print("  Шаги pipeline:")
        for s in self.reasoning.steps:
            icon = "✅" if s.status == "ok" else "❌" if s.status == "fail" else "⏭️"
            print(f"    {icon} {s.name} ({s.duration_ms:.0f}мс)")
            if s.details:
                print(f"       {s.details}")
            if not s.correct and s.expected:
                print(f"       ожидалось: {s.expected}")
                print(f"       получено:  {s.actual}")
        print()

        # ── Preview ──
        print("  ── Анализ превью ──")
        print(f"  3D модель:     {'✅' if self.preview.has_3d_model else '❌'}")
        print(f"  Mesh count:    {self.preview.mesh_count}")
        print(f"  Разрешение:    {self.preview.resolution}")
        print(f"  Соответствие:  {'✅' if self.preview.prompt_match else '❌'} (score: {self.preview.ai_match_score:.0%})")
        if self.preview.ai_description:
            print(f"  Описание AI:   {self.preview.ai_description[:200]}")
        if self.preview.ai_bugs:
            print(f"  Баги:          {', '.join(self.preview.ai_bugs)}")
        print()

        # ── Screenshots ──
        if self.screenshots:
            print("  Скриншоты:")
            for s in self.screenshots:
                print(f"    📸 {s}")
            print()

        # ── Errors ──
        if self.errors:
            print("  Ошибки:")
            for e in self.errors:
                print(f"    ❌ {e}")
            print()

        # ── Verdict ──
        print("═" * 70)
        if self.passed:
            print("  ✅ ТЕСТ ПРОЙДЕН — система рассуждает корректно, результат соответствует промту")
        else:
            print("  ❌ ТЕСТ НЕ ПРОЙДЕН — обнаружены отклонения")
        print("═" * 70)


# ═══════════════════════════════════════════════════════════════
# PROMPT ANALYSIS — what we expect from a prompt
# ═══════════════════════════════════════════════════════════════

def analyze_prompt_expectations(prompt: str) -> dict:
    """
    Анализирует промт и определяет ожидаемые параметры.
    Используется для проверки корректности рассуждения LLM.
    """
    import re

    prompt_lower = prompt.lower()
    expected = {}

    # Object type
    interior_kw = ["спальн", "кухн", "гостин", "ванн", "комнат", "интерьер", "детск", "кабинет", "столов"]
    if any(kw in prompt_lower for kw in interior_kw):
        expected["object_type"] = "room"
        if "спальн" in prompt_lower:
            expected["room_type"] = "bedroom"
        elif "кухн" in prompt_lower:
            expected["room_type"] = "kitchen"
        elif "гостин" in prompt_lower:
            expected["room_type"] = "living"
        elif "ванн" in prompt_lower:
            expected["room_type"] = "bathroom"
        elif "детск" in prompt_lower:
            expected["room_type"] = "children"
        elif "кабинет" in prompt_lower:
            expected["room_type"] = "study"
        elif "столов" in prompt_lower:
            expected["room_type"] = "dining"
    else:
        expected["object_type"] = "building"

    # Building type
    if "офис" in prompt_lower:
        expected["building_type"] = "office"
    elif "коттедж" in prompt_lower:
        expected["building_type"] = "cottage"
    elif "вилл" in prompt_lower:
        expected["building_type"] = "villa"
    elif "таунхаус" in prompt_lower:
        expected["building_type"] = "townhouse"
    elif "гостиниц" in prompt_lower or "отел" in prompt_lower:
        expected["building_type"] = "hotel"
    elif "склад" in prompt_lower:
        expected["building_type"] = "warehouse"
    elif "школ" in prompt_lower:
        expected["building_type"] = "school"
    elif "дом" in prompt_lower or "здание" in prompt_lower:
        expected["building_type"] = "house"

    # Floors
    floor_patterns = [
        r"(\d+)\s*этаж",
        r"(\d+)\s*-?\s*этажн",
        r"двух\s*этажн" if "двух" in prompt_lower else None,
        r"трех\s*этажн" if "трех" in prompt_lower else None,
        r"четырех\s*этажн" if "четырех" in prompt_lower else None,
        r"пяти\s*этажн" if "пяти" in prompt_lower else None,
    ]
    for pat in floor_patterns:
        if pat is None:
            continue
        m = re.search(pat, prompt_lower)
        if m:
            if "двух" in prompt_lower:
                expected["floors"] = 2
            elif "трех" in prompt_lower:
                expected["floors"] = 3
            elif "четырех" in prompt_lower:
                expected["floors"] = 4
            elif "пяти" in prompt_lower:
                expected["floors"] = 5
            else:
                expected["floors"] = int(m.group(1))
            break

    # Dimensions (NxM or NxM format)
    dim_match = re.search(r"(\d+)\s*[x×х*]\s*(\d+)", prompt)
    if dim_match:
        expected["width_m"] = int(dim_match.group(1))
        expected["length_m"] = int(dim_match.group(2))

    # Material
    materials = {
        "кирпич": "brick", "brick": "brick",
        "дерев": "wood", "wood": "wood",
        "стекл": "glass", "glass": "glass",
        "камен": "stone", "stone": "stone",
        "бетон": "concrete", "concrete": "concrete",
        "штукатурк": "plaster",
        "мрамор": "marble",
        "гранит": "granite",
        "керамик": "ceramic",
        "металл": "metal",
        "газобетон": "aerated_concrete",
        "пеноблок": "foam_block",
        "сип": "sip_panel",
        "бревн": "timber_frame",
    }
    for kw, mat in materials.items():
        if kw in prompt_lower:
            expected["material"] = mat
            break

    # Style
    styles = {
        "современн": "modern", "модерн": "modern", "modern": "modern",
        "классич": "classic", "classic": "classic",
        "лофт": "loft", "loft": "loft",
        "скандинав": "scandinavian", "scandinavian": "scandinavian",
        "минималист": "minimalist", "minimalist": "minimalist",
        "хайтек": "hitech", "hitech": "hitech", "hi-tech": "hitech",
        "арт-деко": "art_deco", "ар-деко": "art_deco",
        "барокко": "baroque",
        "брутализм": "brutalism",
        "японск": "japandi",
        "биофи": "biophilic",
        "индустриал": "industrial",
        "колониал": "colonial",
        "средиземномор": "mediterranean",
        "прованс": "provence",
    }
    for kw, style in styles.items():
        if kw in prompt_lower:
            expected["style"] = style
            break

    # Roof
    if "плоск" in prompt_lower:
        expected["roof_type"] = "flat"
    elif "вальмов" in prompt_lower:
        expected["roof_type"] = "hip"
    elif "мансард" in prompt_lower:
        expected["roof_type"] = "mansard"
    elif "двускатн" in prompt_lower or "двухскатн" in prompt_lower:
        expected["roof_type"] = "gabled"

    # Features
    features = {
        "балкон": "balcony", "террас": "terrace", "гараж": "garage",
        "бассейн": "pool", "сад": "garden", "подвал": "basement",
        "чердак": "attic", "камин": "chimney", "эркер": "bay_window",
    }
    found_features = []
    for kw, feat in features.items():
        if kw in prompt_lower:
            found_features.append(feat)
    if found_features:
        expected["features"] = found_features

    # Furniture (for interiors)
    furniture = {
        "кровать": "bed", "диван": "sofa", "стол": "table",
        "шкаф": "wardrobe", "книжн": "bookshelf", "торшер": "floor_lamp",
        "люстр": "chandelier", "стул": "chair", "кресло": "armchair",
        "ночн": "nightstand", "комод": "dresser", "раковин": "sink",
        "ванн": "bathtub", "плит": "stove", "мойк": "sink",
    }
    found_furniture = []
    for kw, furn in furniture.items():
        if kw in prompt_lower:
            found_furniture.append(furn)
    if found_furniture:
        expected["furniture"] = found_furniture

    return expected


def compare_params(expected: dict, actual: dict) -> tuple[float, list[str]]:
    """
    Сравнивает ожидаемые и реальные параметры.
    Возвращает (accuracy, list of mismatches).
    """
    if not expected:
        return 1.0, []

    mismatches = []
    total = 0
    matched = 0

    for key, exp_val in expected.items():
        total += 1
        act_val = actual.get(key)

        if act_val is None:
            mismatches.append(f"{key}: ожидалось '{exp_val}', не найдено")
            continue

        if isinstance(exp_val, list):
            if isinstance(act_val, list):
                overlap = set(exp_val) & set(act_val)
                if overlap:
                    matched += 1
                else:
                    mismatches.append(f"{key}: ожидалось {exp_val}, получено {act_val}")
            else:
                mismatches.append(f"{key}: ожидалось список, получено {type(act_val).__name__}")
        elif isinstance(exp_val, (int, float)):
            if isinstance(act_val, (int, float)):
                if abs(exp_val - act_val) <= max(1, exp_val * 0.2):
                    matched += 1
                else:
                    mismatches.append(f"{key}: ожидалось {exp_val}, получено {act_val}")
            else:
                mismatches.append(f"{key}: ожидалось число, получено {type(act_val).__name__}")
        else:
            if str(exp_val).lower() == str(act_val).lower():
                matched += 1
            else:
                mismatches.append(f"{key}: ожидалось '{exp_val}', получено '{act_val}'")

    accuracy = matched / total if total > 0 else 1.0
    return accuracy, mismatches


# ═══════════════════════════════════════════════════════════════
# LIVE TEST — with real server
# ═══════════════════════════════════════════════════════════════

def run_live_test(prompt: str, server_url: str, quality: str = "standard",
                  screenshot: bool = True) -> TestReport:
    """
    Полный тест с живым сервером.
    Отправляет промт → анализирует рассуждение → скриншотит превью.
    """
    import httpx

    report = TestReport(
        prompt=prompt,
        timestamp=datetime.now().isoformat(),
        server_url=server_url,
        mode="live",
    )
    start = time.time()
    screenshots_dir = tempfile.mkdtemp(prefix="architect_e2e_")

    try:
        # ═══ Step 1: Send prompt ═══
        print(f"\n[1/6] Отправляю промт: {prompt[:60]}...")
        t0 = time.time()

        with httpx.Client(timeout=300) as client:
            r = client.post(
                f"{server_url}/api/v1/orchestrator/execute",
                json={
                    "prompt": prompt,
                    "quality": quality,
                    "export_formats": ["glb"],
                    "skip_clarification": True,
                },
            )

        if r.status_code != 200:
            report.errors.append(f"API вернул {r.status_code}: {r.text[:300]}")
            report.duration_ms = (time.time() - start) * 1000
            return report

        api_result = r.json()
        step_duration = (time.time() - t0) * 1000
        print(f"    ✅ Ответ получен ({step_duration:.0f}мс), status={api_result.get('status')}")

        # ═══ Step 2: Analyze reasoning ═══
        print("[2/6] Анализирую рассуждение...")
        t0 = time.time()

        expected = analyze_prompt_expectations(prompt)
        parsed = api_result.get("params", {})
        accuracy, mismatches = compare_params(expected, parsed)

        reasoning = ReasoningAnalysis(
            prompt=prompt,
            parsed_params=parsed,
            expected_params=expected,
            param_accuracy=accuracy,
        )

        # Analyze pipeline steps
        steps = api_result.get("steps", [])
        expected_order = ["parse", "geometry", "texture", "render", "quality", "export"]

        for step in steps:
            name = step.get("name", "unknown")
            status = step.get("status", "unknown")
            duration = step.get("duration_ms", 0)
            error = step.get("error", "")

            rs = ReasoningStep(
                name=name,
                status="ok" if status == "done" else "fail" if status == "failed" else "skip",
                duration_ms=duration,
                details=error or f"status={status}",
            )

            # Check if step is in expected order
            for i, exp in enumerate(expected_order):
                if exp in name:
                    rs.expected = f"step #{i+1} ({exp})"
                    break

            reasoning.steps.append(rs)

        # Check pipeline correctness
        step_names = [s.name for s in reasoning.steps]
        critical = ["parse", "geometry"]
        reasoning.pipeline_correct = all(
            any(c in s for s in step_names) for c in critical
        )

        # Check order
        order_indices = []
        for exp in expected_order:
            for i, found in enumerate(step_names):
                if exp in found:
                    order_indices.append(i)
                    break
        reasoning.order_correct = order_indices == sorted(order_indices)

        # Summary
        if mismatches:
            reasoning.summary = f"Точность {accuracy:.0%}. Отклонения: {'; '.join(mismatches[:3])}"
        else:
            reasoning.summary = f"Точность {accuracy:.0%}. Все параметры корректны."

        report.reasoning = reasoning
        step_duration = (time.time() - t0) * 1000
        print(f"    ✅ Рассуждение проанализировано ({step_duration:.0f}мс)")
        print(f"    Точность: {accuracy:.0%}")
        for m in mismatches[:5]:
            print(f"    ⚠️ {m}")

        # ═══ Step 3: Screenshot chat ═══
        if screenshot:
            print("[3/6] Делаю скриншот чата...")
            t0 = time.time()
            chat_screenshot = _take_screenshot(
                server_url, screenshots_dir, "01_chat.png",
                wait_for="canvas, .bub, #chat"
            )
            if chat_screenshot:
                report.screenshots.append(chat_screenshot)
                step_duration = (time.time() - t0) * 1000
                print(f"    ✅ Скриншот чата: {chat_screenshot} ({step_duration:.0f}мс)")
            else:
                print("    ⏭️ Скриншот чата недоступен (нет Playwright)")

        # ═══ Step 4: Screenshot 3D preview ═══
        if screenshot:
            print("[4/6] Делаю скриншот 3D превью...")
            t0 = time.time()
            preview_screenshot = _take_screenshot(
                server_url, screenshots_dir, "02_preview.png",
                wait_for="canvas#c3d, canvas, #viewer",
                extra_wait=3,
            )
            if preview_screenshot:
                report.screenshots.append(preview_screenshot)
                report.preview.screenshot_path = preview_screenshot
                step_duration = (time.time() - t0) * 1000
                print(f"    ✅ Скриншот превью: {preview_screenshot} ({step_duration:.0f}мс)")
            else:
                print("    ⏭️ Скриншот превью недоступен")

        # ═══ Step 5: Analyze preview ═══
        print("[5/6] Анализирую превью...")
        t0 = time.time()

        # Check render output from API
        render_path = api_result.get("render", "")
        if render_path and os.path.exists(render_path):
            report.preview.render_path = render_path
            _analyze_render_file(report, render_path, quality)

        # AI analysis of screenshot
        screenshot_to_analyze = report.preview.screenshot_path or report.preview.render_path
        if screenshot_to_analyze and os.path.exists(screenshot_to_analyze):
            ai_result = _call_vision_ai(screenshot_to_analyze, prompt)
            if ai_result:
                report.preview.ai_description = ai_result.get("description", "")
                report.preview.ai_match_score = ai_result.get("match_score", 0.0)
                report.preview.ai_bugs = ai_result.get("bugs", [])
                report.preview.prompt_match = ai_result.get("matches_prompt", False)

        # Check 3D model from API response
        if api_result.get("result", {}).get("gen_type"):
            report.preview.has_3d_model = True

        # Summary
        if report.preview.prompt_match:
            report.preview.summary = f"Соответствует промту (score: {report.preview.ai_match_score:.0%})"
        elif report.preview.ai_description:
            report.preview.summary = f"AI описание: {report.preview.ai_description[:100]}"
        else:
            report.preview.summary = "Превью не проанализировано"

        step_duration = (time.time() - t0) * 1000
        print(f"    ✅ Превью проанализировано ({step_duration:.0f}мс)")

        # ═══ Step 6: Determine pass/fail ═══
        print("[6/6] Формирую verdict...")
        report.passed = _determine_verdict(report)

    except httpx.ConnectError:
        report.errors.append(f"Не могу подключиться к {server_url}")
    except httpx.TimeoutException:
        report.errors.append(f"Таймаут запроса (300с)")
    except Exception as e:
        report.errors.append(f"Неожиданная ошибка: {e}")
    finally:
        report.duration_ms = (time.time() - start) * 1000

    return report


# ═══════════════════════════════════════════════════════════════
# DRY-RUN TEST — without server (logic only)
# ═══════════════════════════════════════════════════════════════

def run_dry_test(prompt: str) -> TestReport:
    """
    Тест только логики рассуждения (без сервера).
    Проверяет парсинг промта, генерацию bpy-скрипта, конфигурацию рендера.
    """
    from unittest.mock import patch

    report = TestReport(
        prompt=prompt,
        timestamp=datetime.now().isoformat(),
        server_url="local (dry-run)",
        mode="dry-run",
    )
    start = time.time()

    try:
        # ═══ Step 1: Analyze expected params ═══
        print("\n[1/5] Анализирую ожидаемые параметры...")
        expected = analyze_prompt_expectations(prompt)
        print(f"    Ожидается: {json.dumps(expected, ensure_ascii=False)}")

        # ═══ Step 2: Parse with LLM (mocked) ═══
        print("[2/5] Парсинг через LLM (мок)...")
        t0 = time.time()

        from shared.parser import parse_prompt_sync as parse_prompt

        # Create mock LLM response based on expected
        mock_response = {
            "object_type": expected.get("object_type", "building"),
            "building_type": expected.get("building_type", "house"),
            "room_type": expected.get("room_type"),
            "floors": expected.get("floors", 2),
            "width_m": expected.get("width_m", 10),
            "length_m": expected.get("length_m", 12),
            "height_m": 3,
            "style": expected.get("style", "modern"),
            "material": expected.get("material", "plaster"),
            "roof_type": expected.get("roof_type", "gabled"),
            "features": expected.get("features", []),
            "furniture": expected.get("furniture", []),
            "confidence": 0.9,
        }

        async def mock_call_openrouter(model, prompt, timeout, api_key):
            return mock_response

        with patch("shared.parser._get_api_keys", return_value=["fake-key"]),              patch("shared.parser._call_openrouter", side_effect=mock_call_openrouter):
            parsed = parse_prompt(prompt)

        accuracy, mismatches = compare_params(expected, parsed)

        reasoning = ReasoningAnalysis(
            prompt=prompt,
            parsed_params=parsed,
            expected_params=expected,
            param_accuracy=accuracy,
            pipeline_correct=True,
            order_correct=True,
            all_critical_ok=True,
        )

        step = ReasoningStep(
            name="parse",
            status="ok",
            duration_ms=(time.time() - t0) * 1000,
            details=f"confidence={parsed.get('confidence', '?')}",
        )
        reasoning.steps.append(step)

        if mismatches:
            reasoning.summary = f"Точность {accuracy:.0%}. Отклонения: {'; '.join(mismatches[:3])}"
        else:
            reasoning.summary = f"Точность {accuracy:.0%}. Все параметры корректны."

        report.reasoning = reasoning
        print(f"    ✅ Парсинг: {accuracy:.0%}")
        for m in mismatches:
            print(f"    ⚠️ {m}")

        # ═══ Step 3: Generate bpy script ═══
        print("[3/5] Генерация bpy-скрипта...")
        t0 = time.time()

        from shared.blender import generate_bpy_script, generate_interior_script

        gen_type = parsed.get("object_type", "building")
        if gen_type in ("room", "interior"):
            script = generate_interior_script({
                "width": parsed.get("width_m", 6),
                "length": parsed.get("length_m", 8),
                "height": parsed.get("height_m", 3),
                "style": parsed.get("style", "modern"),
                "furniture": parsed.get("furniture", []),
            })
        else:
            script = generate_bpy_script({
                "width": parsed.get("width_m", 10),
                "length": parsed.get("length_m", 12),
                "floors": parsed.get("floors", 2),
                "roof_type": parsed.get("roof_type", "gabled"),
                "facade_material": parsed.get("material", "plaster"),
                "has_balcony": "balcony" in parsed.get("features", []),
                "has_terrace": "terrace" in parsed.get("features", []),
                "has_garage": "garage" in parsed.get("features", []),
            })

        # Verify script compiles
        try:
            compile(script, "<generated>", "exec")
            compiled = True
        except SyntaxError as e:
            compiled = False
            report.errors.append(f"bpy-скрипт не компилируется: {e}")

        # Check script has key elements
        script_ok = all(x in script for x in ["import bpy", "bpy.ops"])

        step = ReasoningStep(
            name="geometry (bpy-script)",
            status="ok" if compiled and script_ok else "fail",
            duration_ms=(time.time() - t0) * 1000,
            details=f"{len(script)} символов, compiled={compiled}",
        )
        reasoning.steps.append(step)

        print(f"    ✅ bpy-скрипт: {len(script)} символов, компилируется={compiled}")

        # ═══ Step 4: Check render config ═══
        print("[4/5] Проверка конфигурации рендера...")
        t0 = time.time()

        from shared.agents.render_agent import QUALITY_PRESETS

        preset = QUALITY_PRESETS.get("standard", {})
        render_ok = (
            preset.get("resolution_x", 0) >= 1920
            and preset.get("resolution_y", 0) >= 1080
            and preset.get("samples", 0) >= 64
        )

        step = ReasoningStep(
            name="render config",
            status="ok" if render_ok else "fail",
            duration_ms=(time.time() - t0) * 1000,
            details=f"{preset.get('resolution_x')}x{preset.get('resolution_y')}, {preset.get('samples')} samples",
        )
        reasoning.steps.append(step)

        report.preview.resolution = f"{preset.get('resolution_x')}x{preset.get('resolution_y')}"
        report.preview.quality_matches = render_ok
        report.preview.has_3d_model = compiled
        report.preview.prompt_match = accuracy >= 0.7

        print(f"    ✅ Пресет: {report.preview.resolution}")

        # ═══ Step 5: Verdict ═══
        print("[5/5] Формирую verdict...")
        report.passed = (
            accuracy >= 0.7
            and compiled
            and script_ok
            and render_ok
            and not report.errors
        )

        report.preview.summary = f"bpy={compiled}, render={render_ok}, accuracy={accuracy:.0%}"

    except Exception as e:
        report.errors.append(f"Ошибка: {e}")
    finally:
        report.duration_ms = (time.time() - start) * 1000

    return report


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _take_screenshot(url: str, output_dir: str, filename: str,
                     wait_for: str = "", extra_wait: float = 0) -> Optional[str]:
    """Делает скриншот через Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    output_path = os.path.join(output_dir, filename)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1920, "height": 1080})

            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)

            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=10000)
                except Exception:
                    pass

            if extra_wait:
                time.sleep(extra_wait)

            page.screenshot(path=output_path, full_page=False)
            browser.close()

            return output_path if os.path.exists(output_path) else None

    except Exception:
        return None


def _analyze_render_file(report: TestReport, render_path: str, quality: str):
    """Анализирует файл рендера."""
    try:
        from PIL import Image

        img = Image.open(render_path)
        report.preview.resolution = f"{img.width}x{img.height}"

        min_res = {
            "preview": (1280, 720),
            "standard": (3840, 2160),
            "high": (7680, 4320),
            "ultra": (15360, 8640),
            "16k": (15360, 8640),
        }
        min_w, min_h = min_res.get(quality, (1920, 1080))
        report.preview.quality_matches = img.width >= min_w and img.height >= min_h

    except ImportError:
        report.preview.resolution = "unknown (no PIL)"
    except Exception as e:
        report.preview.resolution = f"error: {e}"


def _call_vision_ai(image_path: str, prompt_context: str) -> Optional[dict]:
    """Вызывает mimo-omni для AI-анализа изображения."""
    try:
        import subprocess

        mimo_script = os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh")
        if not os.path.exists(mimo_script):
            return None

        analysis_prompt = (
            "Проанализируй этот архитектурный рендер/скриншот. "
            "Ответь СТРОГО в JSON:\n"
            '{"description": "описание", "matches_prompt": true/false, '
            '"match_score": 0.0-1.0, "has_bugs": true/false, "bugs": []}\n'
        )
        if prompt_context:
            analysis_prompt += f"\nОригинальный промт: {prompt_context}"

        result = subprocess.run(
            ["bash", mimo_script, "image", image_path, analysis_prompt],
            capture_output=True, text=True, timeout=60,
        )

        if result.returncode == 0:
            import re
            json_match = re.search(r"\{.*\}", result.stdout, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

    except Exception:
        pass

    return None


def _determine_verdict(report: TestReport) -> bool:
    """Определяет итоговый verdict."""
    if report.errors:
        return False

    # Reasoning must be mostly correct
    if report.reasoning.param_accuracy < 0.5:
        return False

    # Pipeline must have critical steps
    if not report.reasoning.pipeline_correct:
        return False

    # Preview must match (if analyzed)
    if report.preview.ai_match_score > 0 and report.preview.ai_match_score < 0.5:
        return False

    return True


# ═══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Комплексная проверка генерации и рассуждения по промту в чат",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Dry-run (без сервера):
  python3 tests/test_prompt_reasoning.py --dry-run "двухэтажный кирпичный дом 10x12"

  # С живым сервером:
  python3 tests/test_prompt_reasoning.py "современная спальня 6x8" --url http://localhost:8080

  # С Render:
  python3 tests/test_prompt_reasoning.py "офис 5 этажей стекло" --url https://architect.onrender.com
        """,
    )
    parser.add_argument("prompt", help="Промт для генерации")
    parser.add_argument("--url", default="http://localhost:8080", help="URL сервера")
    parser.add_argument("--quality", default="standard", help="Качество рендера")
    parser.add_argument("--dry-run", action="store_true", help="Без сервера (только логика)")
    parser.add_argument("--no-screenshot", action="store_true", help="Без скриншотов")
    parser.add_argument("--output", help="Путь для JSON отчёта")

    args = parser.parse_args()

    print("\n" + "═" * 70)
    print("  Комплексная проверка генерации и рассуждения по промту в чат")
    print("═" * 70)
    print(f"  Промт: {args.prompt}")
    print(f"  Режим: {'dry-run' if args.dry_run else 'live (' + args.url + ')'}")

    if args.dry_run:
        report = run_dry_test(args.prompt)
    else:
        report = run_live_test(
            prompt=args.prompt,
            server_url=args.url,
            quality=args.quality,
            screenshot=not args.no_screenshot,
        )

    report.print_report()

    # Save JSON report
    output_path = args.output or os.path.join(
        os.path.dirname(__file__), "..", ".openclaw", "tmp",
        f"test_report_{hashlib.md5(args.prompt.encode()).hexdigest()[:8]}.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"\n  📄 Отчёт: {output_path}")

    sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
