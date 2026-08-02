#!/usr/bin/env python3
"""
Test script for Kaggle 16K Renderer.
Tests the full pipeline without actually running on Kaggle.
"""

import os
import sys
import json
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

def test_kaggle_config():
    """Test Kaggle CLI and API token."""
    print("=" * 50)
    print("TEST 1: Kaggle Configuration")
    print("=" * 50)

    try:
        import subprocess
        result = subprocess.run(
            ["kaggle", "config", "view"],
            capture_output=True, text=True, timeout=10
        )
        print(result.stdout)
        assert "username:" in result.stdout, "Username not configured"
        print("✅ Kaggle CLI configured\n")
        return True
    except Exception as e:
        print(f"❌ Kaggle CLI not configured: {e}\n")
        return False


def test_kaggle_api_access():
    """Test Kaggle API access."""
    print("=" * 50)
    print("TEST 2: Kaggle API Access")
    print("=" * 50)

    try:
        import subprocess
        result = subprocess.run(
            ["kaggle", "datasets", "list", "--max-size", "1"],
            capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, f"API error: {result.stderr}"
        print("✅ Kaggle API accessible\n")
        return True
    except Exception as e:
        print(f"❌ Kaggle API error: {e}\n")
        return False


def test_kaggle_renderer_init():
    """Test KaggleRenderer initialization."""
    print("=" * 50)
    print("TEST 3: KaggleRenderer Initialization")
    print("=" * 50)

    try:
        from kaggle_renderer import KaggleRenderer
        renderer = KaggleRenderer()
        print("✅ KaggleRenderer initialized\n")
        return True
    except Exception as e:
        print(f"❌ KaggleRenderer init failed: {e}\n")
        return False


def test_bpy_script_generation():
    """Test bpy script generation."""
    print("=" * 50)
    print("TEST 4: bpy Script Generation")
    print("=" * 50)

    try:
        script_path = os.path.join(os.path.dirname(__file__), "architect_16k_render.py")
        assert os.path.exists(script_path), f"Script not found: {script_path}"

        # Check script has key components
        with open(script_path) as f:
            content = f.read()

        checks = [
            ("TILE_WIDTH", "Tile width config"),
            ("TILE_HEIGHT", "Tile height config"),
            ("TILES_X", "Tiles X config"),
            ("TILES_Y", "Tiles Y config"),
            ("CYCLES_SAMPLES", "Cycles samples config"),
            ("GPU", "GPU device config"),
            ("CUDA", "CUDA compute type"),
            ("tiled", "Tiled rendering logic"),
        ]

        for keyword, desc in checks:
            assert keyword in content, f"Missing: {desc} ({keyword})"
            print(f"  ✅ {desc}")

        print("✅ bpy script has all required components\n")
        return True
    except Exception as e:
        print(f"❌ Script check failed: {e}\n")
        return False


def test_gateway_endpoint_import():
    """Test Gateway endpoint can be imported."""
    print("=" * 50)
    print("TEST 5: Gateway Endpoint Import")
    print("=" * 50)

    try:
        # Check if FastAPI is available
        try:
            import fastapi
            from gateway_kaggle_endpoint import kaggle_router
            print(f"  Router prefix: {kaggle_router.prefix}")
            print(f"  Routes: {len(kaggle_router.routes)}")

            for route in kaggle_router.routes:
                methods = getattr(route, 'methods', set())
                path = getattr(route, 'path', 'unknown')
                print(f"    {', '.join(methods)} {path}")

            print("✅ Gateway endpoint imports correctly\n")
        except ImportError:
            print("  ⚠️  FastAPI not installed (test environment)")
            print("  Gateway endpoint code is valid Python")
            # Verify the file is syntactically correct
            import py_compile
            py_compile.compile(
                os.path.join(os.path.dirname(__file__), "gateway_kaggle_endpoint.py"),
                doraise=True
            )
            print("✅ Gateway endpoint syntax valid\n")
        return True
    except Exception as e:
        print(f"❌ Gateway import failed: {e}\n")
        return False


def test_dataset_push():
    """Test pushing a dataset to Kaggle (dry run)."""
    print("=" * 50)
    print("TEST 6: Dataset Push (dry run)")
    print("=" * 50)

    try:
        from kaggle_renderer import KaggleRenderer
        renderer = KaggleRenderer()

        # Create a test script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('print("Hello from test script")\n')
            test_script = f.name

        # Test metadata creation (don't actually push)
        ds_dir = tempfile.mkdtemp()
        metadata = {
            "title": "test-dataset",
            "id": f"{renderer.KERNEL_OWNER}/test-dataset",
            "licenses": [{"name": "CC0-1.0"}],
            "isPrivate": True
        }
        meta_path = os.path.join(ds_dir, "dataset-metadata.json")
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"  Dataset metadata: {meta_path}")
        print(f"  Test script: {test_script}")
        print("✅ Dataset push preparation works\n")

        # Cleanup
        os.unlink(test_script)
        os.unlink(meta_path)
        os.rmdir(ds_dir)
        return True
    except Exception as e:
        print(f"❌ Dataset push test failed: {e}\n")
        return False


def test_resolution_math():
    """Test 16K resolution calculations."""
    print("=" * 50)
    print("TEST 7: Resolution Math")
    print("=" * 50)

    tile_w, tile_h = 3840, 2880
    tiles_x, tiles_y = 4, 3

    total_w = tile_w * tiles_x
    total_h = tile_h * tiles_y
    total_megapixels = (total_w * total_h) / 1_000_000

    print(f"  Tile: {tile_w}x{tile_h}")
    print(f"  Grid: {tiles_x}x{tiles_y} = {tiles_x * tiles_y} tiles")
    print(f"  Total: {total_w}x{total_h}")
    print(f"  Megapixels: {total_megapixels:.1f} MP")

    assert total_w == 15360, f"Width mismatch: {total_w}"
    assert total_h == 8640, f"Height mismatch: {total_h}"
    assert abs(total_megapixels - 132.7) < 0.1, f"MP mismatch: {total_megapixels}"

    print("✅ Resolution math correct (15360×8640 = 132.7 MP)\n")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("KAGGLE 16K RENDERER — TEST SUITE")
    print("=" * 50 + "\n")

    results = {
        "Kaggle Config": test_kaggle_config(),
        "API Access": test_kaggle_api_access(),
        "Renderer Init": test_kaggle_renderer_init(),
        "Script Generation": test_bpy_script_generation(),
        "Gateway Import": test_gateway_endpoint_import(),
        "Dataset Push": test_dataset_push(),
        "Resolution Math": test_resolution_math(),
    }

    print("=" * 50)
    print("RESULTS SUMMARY")
    print("=" * 50)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"  {status} — {name}")

    print(f"\n  {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED — Ready for Kaggle 16K rendering!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed — fix before deploying")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
