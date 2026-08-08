"""
tests/visual_test_runner.py — Автоматизированный визуальный тестер.

Запускает промты через Puppeteer, делает скрины, анализирует через mimo-omni.
Использование: python3 tests/visual_test_runner.py [--url URL] [--output DIR]
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestCase:
    """Один тест-кейс."""
    id: str
    prompt: str
    expected_type: str  # interior, building, landscape
    expected_room: str = ""
    expected_building: str = ""
    description: str = ""


@dataclass
class TestResult:
    """Результат теста."""
    test_id: str
    prompt: str
    screenshot_path: str = ""
    analysis: str = ""
    type_correct: bool = False
    quality_ok: bool = False
    reasoning_ok: bool = False
    issues: list = field(default_factory=list)


# ═══ Тест-кейсы из скриншотов + похожие ═══

TEST_CASES = [
    # Из скриншотов (реальные баги)
    TestCase("IMG_1432", "ванная с джакузи", "interior", "bathroom",
             description="Запрос ванной → раньше генерировался дом"),
    TestCase("IMG_1431", "отель", "building", "", "hotel",
             description="Запрос отеля → раньше генерировался жилой дом"),
    TestCase("IMG_1429", "сделай дизайн детской", "interior", "children",
             description="Запрос детской → раньше ошибка uninitialized variable"),
    TestCase("IMG_1430", "кухня в стиле хайтек", "interior", "kitchen",
             description="Запрос кухни → раньше генерировался экстерьер"),
    TestCase("IMG_1428", "сделай таунхаус", "building", "", "townhouse",
             description="Запрос таунхауса → раньше пустой 3D view"),

    # Интерьеры
    TestCase("INT_01", "ванная комната с душевой кабиной", "interior", "bathroom"),
    TestCase("INT_02", "кухня-гостиная в стиле лофт", "interior", "kitchen"),
    TestCase("INT_03", "спальня в японском стиле", "interior", "bedroom"),
    TestCase("INT_04", "детская для мальчика", "interior", "children"),
    TestCase("INT_05", "гостиная с камином", "interior", "living"),
    TestCase("INT_06", "прихожая в современном стиле", "interior", "hallway"),
    TestCase("INT_07", "кабинет с библиотекой", "interior", "study"),
    TestCase("INT_08", "сауна внутри дома", "interior", "sauna"),
    TestCase("INT_09", "дизайн гардеробной", "interior", "dressing"),
    TestCase("INT_10", "ванная с джакузи и душевой", "interior", "bathroom"),

    # Здания
    TestCase("BLD_01", "построй двухэтажный дом", "building", "", "house"),
    TestCase("BLD_02", "создай офисное здание 5 этажей", "building", "", "office"),
    TestCase("BLD_03", "загородный коттедж 12 на 15", "building", "", "cottage"),
    TestCase("BLD_04", "построй баню из бревен", "building", "", "bathhouse"),
    TestCase("BLD_05", "гараж на 2 машины", "building", "", "garage"),
    TestCase("BLD_06", "построй гостиницу на 20 номеров", "building", "", "hotel"),
    TestCase("BLD_07", "таунхаус 3 этажа минимализм", "building", "", "townhouse"),
    TestCase("BLD_08", "вилла с бассейном", "building", "", "villa"),

    # Ландшафт
    TestCase("LND_01", "ландшафтный дизайн участка 10 соток", "landscape"),
    TestCase("LND_02", "сад с прудом и цветниками", "landscape"),
    TestCase("LND_03", "дизайн двора частного дома", "landscape"),
    TestCase("LND_04", "бассейн во дворе с террасой", "landscape"),
]


def run_visual_tests(base_url: str, output_dir: str = "screenshots/test_run") -> list[TestResult]:
    """
    Запускает визуальные тесты.

    Args:
        base_url: URL приложения
        output_dir: директория для скриншотов

    Returns:
        список результатов
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []

    # Puppeteer script template
    puppeteer_script = """
const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900 });

  const tests = TESTS_JSON;

  for (const test of tests) {
    try {
      await page.goto('BASE_URL', { waitUntil: 'networkidle2', timeout: 30000 });

      // Enter prompt
      await page.evaluate((text) => {
        const inp = document.getElementById('ci');
        if (inp) { inp.value = text; inp.dispatchEvent(new Event('input')); }
      }, test.prompt);

      // Click send
      await page.evaluate(() => {
        const btn = document.querySelector('.sbtn:last-of-type');
        if (btn) btn.click();
      });

      // Wait for response
      await new Promise(r => setTimeout(r, 8000));

      // Screenshot
      await page.screenshot({ path: `OUTPUT_DIR/${test.id}.png` });

      // Get chat content
      const chatText = await page.evaluate(() => {
        const msgs = document.querySelectorAll('.bub');
        return Array.from(msgs).map(m => m.textContent).join('\\n');
      });

      console.log(JSON.stringify({ id: test.id, chat: chatText, status: 'ok' }));
    } catch(e) {
      console.log(JSON.stringify({ id: test.id, error: e.message, status: 'error' }));
    }
  }

  await browser.close();
})();
""".replace("TESTS_JSON", json.dumps([{"id": t.id, "prompt": t.prompt} for t in TEST_CASES])) \
        .replace("BASE_URL", base_url) \
        .replace("OUTPUT_DIR", output_dir)

    script_path = os.path.join(output_dir, "run_tests.js")
    with open(script_path, "w") as f:
        f.write(puppeteer_script)

    print(f"🚀 Running {len(TEST_CASES)} visual tests against {base_url}...")
    print(f"📁 Screenshots → {output_dir}/")

    try:
        proc = subprocess.run(
            ["node", script_path],
            capture_output=True, text=True, timeout=300,
            cwd=os.path.dirname(os.path.abspath(__file__)) + "/.."
        )

        for line in proc.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                test_id = data.get("id", "")
                case = next((c for c in TEST_CASES if c.id == test_id), None)
                if case:
                    result = TestResult(
                        test_id=test_id,
                        prompt=case.prompt,
                        screenshot_path=f"{output_dir}/{test_id}.png",
                        analysis=data.get("chat", ""),
                    )
                    results.append(result)
            except json.JSONDecodeError:
                pass

    except subprocess.TimeoutExpired:
        print("⏰ Test run timed out (300s)")
    except Exception as e:
        print(f"❌ Error: {e}")

    return results


def analyze_results(results: list[TestResult]) -> dict:
    """Анализирует результаты тестов."""
    report = {
        "total": len(results),
        "passed": 0,
        "failed": 0,
        "issues": [],
    }

    for r in results:
        issues = []
        analysis_lower = r.analysis.lower()

        # Check for errors
        if "ошибка" in analysis_lower or "error" in analysis_lower:
            issues.append("Generation error")
        if "сервер недоступен" in analysis_lower:
            issues.append("Server unavailable")
        if "cannot access" in analysis_lower:
            issues.append("Uninitialized variable error")

        r.issues = issues
        if not issues:
            report["passed"] += 1
        else:
            report["failed"] += 1
            report["issues"].append({"test_id": r.test_id, "prompt": r.prompt, "issues": issues})

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Visual test runner for AI_Arhitector")
    parser.add_argument("--url", default="https://smartmoneymoscow-cell.github.io/AI_Arhitector/",
                        help="Base URL of the application")
    parser.add_argument("--output", default="screenshots/test_run",
                        help="Output directory for screenshots")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Only analyze existing screenshots")
    args = parser.parse_args()

    if args.analyze_only:
        # Analyze existing screenshots with mimo-omni
        screenshots_dir = args.output
        if not os.path.exists(screenshots_dir):
            print(f"❌ Directory not found: {screenshots_dir}")
            return

        for img in sorted(os.listdir(screenshots_dir)):
            if not img.endswith(".png"):
                continue
            img_path = os.path.join(screenshots_dir, img)
            test_id = img.replace(".png", "")
            case = next((c for c in TEST_CASES if c.id == test_id), None)

            print(f"\n{'='*60}")
            print(f"📸 {img} — {case.prompt if case else 'unknown'}")
            print(f"{'='*60}")

            try:
                result = subprocess.run(
                    ["bash", os.path.expanduser("~/.openclaw/skills/mimo-omni/mimo_api.sh"),
                     "image", img_path,
                     f"Проанализируй скриншот архитектурного приложения. Промт: '{case.prompt if case else 'unknown'}'. "
                     f"Определи: 1) Тип генерации (здание/интерьер/ландшафт) 2) Качество модели 3) "
                     f"Соответствие рассуждений промту 4) Видимые баги",
                     "--max-tokens", "4096"],
                    capture_output=True, text=True, timeout=60
                )
                print(result.stdout)
            except Exception as e:
                print(f"❌ Analysis failed: {e}")
    else:
        results = run_visual_tests(args.url, args.output)
        report = analyze_results(results)

        print(f"\n{'='*60}")
        print(f"📊 RESULTS: {report['passed']}/{report['total']} passed, {report['failed']} failed")
        if report["issues"]:
            print("\n❌ Issues:")
            for issue in report["issues"]:
                print(f"  [{issue['test_id']}] {issue['prompt']}: {', '.join(issue['issues'])}")

        # Save report
        report_path = os.path.join(args.output, "report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n📄 Report saved: {report_path}")


if __name__ == "__main__":
    main()
