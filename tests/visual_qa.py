"""
Visual QA — AI-powered screenshot analysis using MiMo vision model.

Sends screenshots to MiMo multimodal model and compares output with expected prompt.

Usage:
    python3 tests/visual_qa.py --screenshot path/to/screen.png --prompt "детская комната" --type interior
    python3 tests/visual_qa.py --dir .openclaw/tmp/test_screenshots --prompt "кирпичный дом" --type building
"""

import sys
import os
import json
import base64
import argparse
import subprocess
from pathlib import Path


def analyze_screenshot(screenshot_path: str, prompt: str, gen_type: str) -> dict:
    """
    Analyze a screenshot using MiMo vision model.
    Returns dict with visual analysis results.
    """
    result = {
        "screenshot": screenshot_path,
        "prompt": prompt,
        "expected_type": gen_type,
        "vision_analysis": "",
        "match": False,
        "match_score": 0,
        "issues": [],
    }

    if not os.path.exists(screenshot_path):
        result["issues"].append(f"Screenshot not found: {screenshot_path}")
        return result

    # Build the analysis question based on type
    if gen_type == "interior":
        question = (
            f"Это скриншот 3D-генератора архитектуры. Пользователь запросил: \"{prompt}\". "
            f"Проанализируй скриншот:\n"
            f"1. Есть ли на скриншоте 3D-модель комнаты/интерьера?\n"
            f"2. Соответствует ли стиль интерьеру (мебель, стены, пол)?\n"
            f"3. Есть ли визуальные артефакты или ошибки рендера?\n"
            f"4. Оцени соответствие промту от 0 до 100.\n"
            f"Ответь кратко, затем выведи строку: MATCH_SCORE=<число>"
        )
    else:
        question = (
            f"Это скриншот 3D-генератора архитектуры. Пользователь запросил: \"{prompt}\". "
            f"Проанализируй скриншот:\n"
            f"1. Есть ли на скриншоте 3D-модель здания?\n"
            f"2. Соответствует ли количество этажей, материал, форма?\n"
            f"3. Есть ли визуальные артефакты или ошибки рендера?\n"
            f"4. Оцени соответствие промту от 0 до 100.\n"
            f"Ответь кратко, затем выведи строку: MATCH_SCORE=<число>"
        )

    vision_result = None

    # 1. Direct API call (most reliable in CI)
    vision_result = _call_mimo_api_direct(screenshot_path, question)

    # 2. Fallback: mimo_api.sh (local development)
    if not vision_result:
        script_dir = os.path.expanduser("~/.openclaw/skills/mimo-omni")
        mimo_sh = os.path.join(script_dir, "mimo_api.sh")
        if os.path.exists(mimo_sh):
            try:
                proc = subprocess.run(
                    ["bash", mimo_sh, "image", screenshot_path, question, "--max-tokens", "4096"],
                    capture_output=True, text=True, timeout=120
                )
                vision_result = proc.stdout.strip()
            except (subprocess.TimeoutExpired, Exception) as e:
                result["issues"].append(f"mimo_api.sh failed: {e}")

    # 3. Fallback: mimo_api.py
    if not vision_result:
        mimo_py = os.path.join(os.path.expanduser("~/.openclaw/skills/mimo-omni"), "mimo_api.py")
        if os.path.exists(mimo_py):
            try:
                proc = subprocess.run(
                    ["python3", mimo_py, "image", screenshot_path, question, "--max-tokens", "4096"],
                    capture_output=True, text=True, timeout=120
                )
                vision_result = proc.stdout.strip()
            except (subprocess.TimeoutExpired, Exception) as e:
                result["issues"].append(f"mimo_api.py failed: {e}")

    if not vision_result:
        result["issues"].append("All MiMo vision methods failed")
        return result

    result["vision_analysis"] = vision_result

    # Extract match score
    score = _extract_score(vision_result)
    result["match_score"] = score
    result["match"] = score >= 50

    # Extract issues from analysis
    if "артефакт" in vision_result.lower() or "ошибк" in vision_result.lower():
        result["issues"].append("Visual artifacts detected in analysis")
    if "нет модели" in vision_result.lower() or "no model" in vision_result.lower():
        result["issues"].append("No 3D model visible in screenshot")
        result["match"] = False
    if "пуст" in vision_result.lower() or "empty" in vision_result.lower():
        result["issues"].append("Empty viewer visible in screenshot")
        result["match"] = False

    return result


def _call_mimo_api_direct(screenshot_path: str, question: str) -> str | None:
    """Direct API call to MiMo as last resort."""
    api_key = os.environ.get("MIMO_API_KEY", "")
    if not api_key:
        return None

    try:
        import httpx
    except ImportError:
        return None

    with open(screenshot_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    api_url = os.environ.get("MIMO_API_BASE_URL", "https://api-sgp-oc.xiaomimimo.com/v1")
    model = os.environ.get("MIMO_OMNI_MODEL", "mimo-v2.5")

    try:
        r = httpx.post(
            f"{api_url}/chat/completions",
            headers={"api-key": api_key, "User-Agent": "architect-ci", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    {"type": "text", "text": question}
                ]}],
                "max_tokens": 4096,
            },
            timeout=60,
        )
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        pass
    return None


def _extract_score(text: str) -> int:
    """Extract MATCH_SCORE from vision analysis text."""
    import re
    # Look for MATCH_SCORE=<number>
    m = re.search(r'MATCH_SCORE\s*=\s*(\d+)', text)
    if m:
        return int(m.group(1))
    # Look for percentage patterns
    m = re.search(r'(\d{1,3})\s*%', text)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return val
    # Look for score patterns
    m = re.search(r'(?:оценк|score|соответств).*?(\d{1,3})', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 0 <= val <= 100:
            return val
    return 0


def analyze_test_screenshots(screenshots_dir: str, test_cases: list[dict]) -> dict:
    """
    Analyze all test screenshots and produce a visual QA report.
    
    test_cases: [{name, prompt, expect_type, screenshots: [path1, path2, ...]}]
    """
    report = {
        "total": len(test_cases),
        "passed": 0,
        "failed": 0,
        "results": [],
    }

    for tc in test_cases:
        tc_result = {
            "name": tc["name"],
            "prompt": tc["prompt"],
            "expected_type": tc.get("expect_type", "building"),
            "screenshots": [],
            "overall_match": False,
            "overall_score": 0,
        }

        # Analyze the "generated" screenshot (the final one)
        gen_screenshot = None
        for s in tc.get("screenshots", []):
            if "04_generated" in s or "generated" in s:
                gen_screenshot = s
                break
        if not gen_screenshot and tc.get("screenshots"):
            gen_screenshot = tc["screenshots"][-1]

        if gen_screenshot:
            qa = analyze_screenshot(gen_screenshot, tc["prompt"], tc.get("expect_type", "building"))
            tc_result["screenshots"].append(qa)
            tc_result["overall_match"] = qa["match"]
            tc_result["overall_score"] = qa["match_score"]

        if tc_result["overall_match"]:
            report["passed"] += 1
        else:
            report["failed"] += 1

        report["results"].append(tc_result)

    return report


def main():
    parser = argparse.ArgumentParser(description="Visual QA — AI screenshot analysis")
    parser.add_argument("--screenshot", help="Single screenshot to analyze")
    parser.add_argument("--prompt", required=True, help="Original user prompt")
    parser.add_argument("--type", default="building", choices=["building", "interior"], help="Generation type")
    parser.add_argument("--dir", help="Directory with test screenshots")
    parser.add_argument("--output", help="Output JSON report path")
    args = parser.parse_args()

    if args.screenshot:
        result = analyze_screenshot(args.screenshot, args.prompt, args.type)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["match"] else 1)

    if args.dir:
        # Find all test case screenshots
        screenshot_dir = Path(args.dir)
        test_cases = _discover_test_cases(screenshot_dir, args.prompt, args.type)
        report = analyze_test_screenshots(args.dir, test_cases)

        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report["failed"] == 0 else 1)


def _discover_test_cases(screenshot_dir: Path, default_prompt: str, default_type: str) -> list[dict]:
    """Discover test cases from screenshot filenames."""
    test_cases = []
    seen_names = set()

    for f in sorted(screenshot_dir.glob("*_report.json")):
        try:
            with open(f) as fh:
                report = json.load(fh)
            name = report.get("name", f.stem.replace("_report", ""))
            tc = {
                "name": name,
                "prompt": report.get("prompt", default_prompt),
                "expect_type": "interior" if report.get("result", {}).get("isInterior") else "building",
                "screenshots": [],
            }
            # Find matching screenshots
            for img in sorted(screenshot_dir.glob(f"{name}_*.png")):
                tc["screenshots"].append(str(img))
            if tc["screenshots"]:
                test_cases.append(tc)
                seen_names.add(name)
        except Exception:
            continue

    # Fallback: discover from screenshot filenames
    if not test_cases:
        for img in sorted(screenshot_dir.glob("*_04_generated.png")):
            name = img.stem.replace("_04_generated", "")
            if name not in seen_names:
                tc = {
                    "name": name,
                    "prompt": default_prompt,
                    "expect_type": default_type,
                    "screenshots": [str(img)],
                }
                test_cases.append(tc)

    return test_cases


if __name__ == "__main__":
    main()
