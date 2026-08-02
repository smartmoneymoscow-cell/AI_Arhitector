#!/usr/bin/env python3
"""
AI_Arhitector — Kaggle GPU Renderer Integration

Интеграция между Gateway и Kaggle T4 GPU для 16K рендера.
Gateway вызывает этот модуль → он запускает Kaggle notebook →
ждет результат → возвращает путь к 16K изображению.

Использование:
  from kaggle_renderer import KaggleRenderer

  renderer = KaggleRenderer()
  result = renderer.render_16k(bpy_script_path="path/to/script.py")
  print(result)  # /path/to/16k_final.png
"""

import os
import sys
import json
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any


class KaggleRenderer:
    """Renders 16K images via Kaggle T4 GPU."""

    KERNEL_SLUG = "architect-16k-render"
    KERNEL_OWNER = "kevwmatthews"
    POLL_INTERVAL = 30  # seconds
    MAX_WAIT = 2400     # 40 minutes max

    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize Kaggle renderer.

        Args:
            api_token: Kaggle API token (KGAT_xxx). If None, reads from env or ~/.kaggle/kaggle.json
        """
        self.api_token = api_token or os.environ.get("KAGGLE_API_TOKEN")
        self._ensure_kaggle_config()
        self._verify_kaggle_cli()

    def _ensure_kaggle_config(self):
        """Ensure kaggle.json exists with valid credentials."""
        kaggle_dir = os.path.expanduser("~/.kaggle")
        kaggle_json = os.path.join(kaggle_dir, "kaggle.json")

        if self.api_token and not os.path.exists(kaggle_json):
            os.makedirs(kaggle_dir, exist_ok=True)
            # Extract key from KGAT_xxx format
            key = self.api_token
            if key.startswith("KGAT_"):
                key = key[5:]  # Remove KGAT_ prefix for legacy format

            config = {
                "username": self.KERNEL_OWNER,
                "key": key
            }
            with open(kaggle_json, 'w') as f:
                json.dump(config, f)
            os.chmod(kaggle_json, 0o600)
            print(f"[KaggleRenderer] Created {kaggle_json}")

    def _verify_kaggle_cli(self):
        """Verify Kaggle CLI is available."""
        try:
            result = subprocess.run(
                ["kaggle", "--version"],
                capture_output=True, text=True, timeout=10
            )
            print(f"[KaggleRenderer] Kaggle CLI: {result.stdout.strip()}")
        except FileNotFoundError:
            print("[KaggleRenderer] Installing Kaggle CLI...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "kaggle"],
                capture_output=True, timeout=60
            )

    def push_script(self, script_path: str, dataset_name: str = "architect-bpy-scripts") -> bool:
        """
        Push bpy script as Kaggle dataset for the notebook to use.

        Args:
            script_path: Path to the bpy script
            dataset_name: Name for the dataset

        Returns:
            True if successful
        """
        print(f"[KaggleRenderer] Pushing script: {script_path}")

        # Create dataset directory
        ds_dir = tempfile.mkdtemp(prefix="kaggle_ds_")
        ds_subdir = os.path.join(ds_dir, dataset_name)
        os.makedirs(ds_subdir, exist_ok=True)

        # Copy script
        shutil.copy2(script_path, os.path.join(ds_subdir, os.path.basename(script_path)))

        # Create dataset metadata
        metadata = {
            "title": dataset_name,
            "id": f"{self.KERNEL_OWNER}/{dataset_name}",
            "licenses": [{"name": "CC0-1.0"}],
            "isPrivate": True
        }
        with open(os.path.join(ds_subdir, "dataset-metadata.json"), 'w') as f:
            json.dump(metadata, f, indent=2)

        # Push to Kaggle
        try:
            result = subprocess.run(
                ["kaggle", "datasets", "create", "-r", "zip", "-p", ds_subdir],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                print(f"[KaggleRenderer] Dataset pushed: {dataset_name}")
                return True
            else:
                # Try version update if dataset exists
                result2 = subprocess.run(
                    ["kaggle", "datasets", "version", "-r", "zip", "-p", ds_subdir,
                     "-m", f"Update {time.strftime('%Y-%m-%d %H:%M')}"],
                    capture_output=True, text=True, timeout=120
                )
                if result2.returncode == 0:
                    print(f"[KaggleRenderer] Dataset updated: {dataset_name}")
                    return True
                else:
                    print(f"[KaggleRenderer] Error: {result2.stderr}")
                    return False
        except Exception as e:
            print(f"[KaggleRenderer] Error pushing dataset: {e}")
            return False
        finally:
            shutil.rmtree(ds_dir, ignore_errors=True)

    def push_kernel(self, script_path: str) -> bool:
        """
        Push the rendering notebook to Kaggle.

        Args:
            script_path: Path to the notebook script

        Returns:
            True if successful
        """
        print(f"[KaggleRenderer] Pushing kernel: {script_path}")

        kernel_dir = tempfile.mkdtemp(prefix="kaggle_kernel_")

        # Copy script
        shutil.copy2(script_path, os.path.join(kernel_dir, "architect_16k_render.py"))

        # Create kernel metadata
        metadata = {
            "title": "AI_Arhitector 16K Blender Cycles T4 GPU",
            "id": f"{self.KERNEL_OWNER}/{self.KERNEL_SLUG}",
            "language": "python",
            "kernel_type": "script",
            "is_private": True,
            "enable_gpu": True,
            "enable_internet": True,
            "dataset_sources": [f"{self.KERNEL_OWNER}/architect-bpy-scripts"],
            "competition_sources": [],
            "code_file": "architect_16k_render.py"
        }
        with open(os.path.join(kernel_dir, "kernel-metadata.json"), 'w') as f:
            json.dump(metadata, f, indent=2)

        try:
            result = subprocess.run(
                ["kaggle", "kernels", "push", "-p", kernel_dir],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                print(f"[KaggleRenderer] Kernel pushed: {self.KERNEL_SLUG}")
                return True
            else:
                print(f"[KaggleRenderer] Error: {result.stderr}")
                return False
        except Exception as e:
            print(f"[KaggleRenderer] Error pushing kernel: {e}")
            return False
        finally:
            shutil.rmtree(kernel_dir, ignore_errors=True)

    def run_kernel(self) -> Dict[str, Any]:
        """
        Run the rendering kernel on Kaggle and wait for completion.

        Returns:
            Dict with status, output_path, render_time, etc.
        """
        print(f"[KaggleRenderer] Running kernel: {self.KERNEL_OWNER}/{self.KERNEL_SLUG}")

        # Start the kernel
        try:
            result = subprocess.run(
                ["kaggle", "kernels", "push", "--enable-gpu", "--enable-internet"],
                capture_output=True, text=True, timeout=120
            )
        except Exception as e:
            return {"status": "error", "message": f"Failed to start kernel: {e}"}

        # Poll for completion
        start_time = time.time()
        while time.time() - start_time < self.MAX_WAIT:
            status = self._get_kernel_status()
            print(f"[KaggleRenderer] Status: {status.get('status', 'unknown')} "
                  f"({int(time.time() - start_time)}s elapsed)")

            if status.get("status") == "complete":
                return {
                    "status": "complete",
                    "render_time": time.time() - start_time,
                    "output": status.get("output", [])
                }
            elif status.get("status") in ("error", "cancelled"):
                return {
                    "status": "error",
                    "message": status.get("error", "Unknown error"),
                    "output": status.get("output", [])
                }

            time.sleep(self.POLL_INTERVAL)

        return {"status": "timeout", "message": f"Render timed out after {self.MAX_WAIT}s"}

    def _get_kernel_status(self) -> Dict[str, Any]:
        """Get current kernel status."""
        try:
            result = subprocess.run(
                ["kaggle", "kernels", "status", f"{self.KERNEL_OWNER}/{self.KERNEL_SLUG}"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            return {"status": "unknown", "error": result.stderr}
        except json.JSONDecodeError:
            return {"status": "unknown", "raw": result.stdout}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def pull_output(self, output_dir: str = "/tmp/architect_16k") -> Optional[str]:
        """
        Pull rendered output from Kaggle.

        Args:
            output_dir: Local directory to save output

        Returns:
            Path to the 16K image, or None if failed
        """
        os.makedirs(output_dir, exist_ok=True)

        print(f"[KaggleRenderer] Pulling output to {output_dir}")

        try:
            result = subprocess.run(
                ["kaggle", "kernels", "output",
                 f"{self.KERNEL_OWNER}/{self.KERNEL_SLUG}",
                 "-p", output_dir],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                # Find the 16K image
                for f in os.listdir(output_dir):
                    if "16k" in f.lower() and f.endswith(".png"):
                        full_path = os.path.join(output_dir, f)
                        print(f"[KaggleRenderer] Output: {full_path}")
                        return full_path

                # If no 16K image, look for any PNG
                for f in sorted(os.listdir(output_dir)):
                    if f.endswith(".png"):
                        full_path = os.path.join(output_dir, f)
                        print(f"[KaggleRenderer] Output: {full_path}")
                        return full_path

                print("[KaggleRenderer] No output images found")
                return None
            else:
                print(f"[KaggleRenderer] Error pulling: {result.stderr}")
                return None
        except Exception as e:
            print(f"[KaggleRenderer] Error: {e}")
            return None

    def render_16k(self, bpy_script_path: str) -> Dict[str, Any]:
        """
        Full 16K render pipeline:
        1. Push bpy script as dataset
        2. Push kernel
        3. Run kernel on Kaggle T4
        4. Pull output

        Args:
            bpy_script_path: Path to the bpy generation script

        Returns:
            Dict with status, output_path, render_time, etc.
        """
        print(f"[KaggleRenderer] Starting 16K render pipeline")
        print(f"  Script: {bpy_script_path}")

        # Step 1: Push script as dataset
        if not self.push_script(bpy_script_path):
            return {"status": "error", "message": "Failed to push script dataset"}

        # Step 2: Push kernel
        kernel_script = os.path.join(
            os.path.dirname(__file__), "architect_16k_render.py"
        )
        if not os.path.exists(kernel_script):
            return {"status": "error", "message": f"Kernel script not found: {kernel_script}"}

        if not self.push_kernel(kernel_script):
            return {"status": "error", "message": "Failed to push kernel"}

        # Step 3: Run kernel
        result = self.run_kernel()
        if result["status"] != "complete":
            return result

        # Step 4: Pull output
        output_path = self.pull_output()
        if output_path is None:
            return {"status": "error", "message": "Failed to pull output"}

        # Get file info
        file_size = os.path.getsize(output_path) / 1024 / 1024  # MB

        return {
            "status": "complete",
            "output_path": output_path,
            "file_size_mb": round(file_size, 1),
            "render_time": result.get("render_time", 0),
            "resolution": "15360x8640"
        }


def render_from_gateway(bpy_script_path: str, api_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function for Gateway integration.

    Args:
        bpy_script_path: Path to the bpy script from the orchestrator
        api_token: Kaggle API token (reads from env if None)

    Returns:
        Dict with render results
    """
    renderer = KaggleRenderer(api_token=api_token)
    return renderer.render_16k(bpy_script_path)


if __name__ == "__main__":
    # CLI usage
    if len(sys.argv) < 2:
        print("Usage: python kaggle_renderer.py <bpy_script.py> [api_token]")
        sys.exit(1)

    script = sys.argv[1]
    token = sys.argv[2] if len(sys.argv) > 2 else None

    result = render_from_gateway(script, api_token=token)
    print(json.dumps(result, indent=2))
