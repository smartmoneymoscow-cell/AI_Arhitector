#!/usr/bin/env python3
"""
AI_Arhitector — Multi-Account Kaggle Dispatcher

Разбивает один промт на параллельные подзадачи и распределяет
их по разным Kaggle аккаунтам для одновременного рендера.

Архитектура:
  Промт пользователя
        │
        ▼
  LLM Парсер (30 сек)
        │
        ├──→ Экстерьер → Kaggle Account #1 → 16K рендер
        ├──→ Интерьер  → Kaggle Account #2 → 16K рендер
        ├──→ Ландшафт  → Kaggle Account #3 → 16K рендер
        ├──→ План/Разрез → Kaggle Account #4 → 16K рендер
        │
        ▼
  Склейка всех частей → Финальный результат
"""

import os
import sys
import json
import time
import asyncio
import hashlib
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
from kaggle_renderer import KaggleRenderer


# ============================================================
# TASK TYPES
# ============================================================

class TaskType(str, Enum):
    """Types of rendering tasks."""
    EXTERIOR = "exterior"       # Экстерьер здания
    INTERIOR = "interior"       # Интерьер (мебель, декор)
    LANDSCAPE = "landscape"     # Ландшафтный дизайн
    FLOORPLAN = "floorplan"     # План этажа
    SECTION = "section"         # Разрез здания
    FACADE = "facade"           # Фасад


# ============================================================
# KAGGLE ACCOUNT POOL
# ============================================================

@dataclass
class KaggleAccount:
    """One Kaggle account with its renderer."""
    name: str
    username: str
    api_token: str
    busy: bool = False
    current_task: Optional[str] = None
    renders_today: int = 0
    renderer: Optional[KaggleRenderer] = None

    def __post_init__(self):
        self.renderer = KaggleRenderer(api_token=self.api_token)


class AccountPool:
    """
    Pool of Kaggle accounts with round-robin task assignment.
    Each account can run one render at a time.
    """

    def __init__(self, accounts: List[Dict[str, str]]):
        """
        Initialize account pool.

        Args:
            accounts: List of {"name": "...", "username": "...", "api_token": "KGAT_xxx"}
        """
        self.accounts = [
            KaggleAccount(**acc) for acc in accounts
        ]
        print(f"[AccountPool] Initialized with {len(self.accounts)} accounts:")
        for acc in self.accounts:
            print(f"  - {acc.name} ({acc.username})")

    def get_free_account(self) -> Optional[KaggleAccount]:
        """Get the first free account."""
        for acc in self.accounts:
            if not acc.busy:
                return acc
        return None

    def get_account_by_name(self, name: str) -> Optional[KaggleAccount]:
        """Get account by name."""
        for acc in self.accounts:
            if acc.name == name:
                return acc
        return None

    def mark_busy(self, account: KaggleAccount, task_id: str):
        """Mark account as busy."""
        account.busy = True
        account.current_task = task_id

    def mark_free(self, account: KaggleAccount):
        """Mark account as free."""
        account.busy = False
        account.current_task = None
        account.renders_today += 1

    def get_status(self) -> List[Dict]:
        """Get status of all accounts."""
        return [
            {
                "name": acc.name,
                "username": acc.username,
                "busy": acc.busy,
                "current_task": acc.current_task,
                "renders_today": acc.renders_today
            }
            for acc in self.accounts
        ]


# ============================================================
# TASK SPLITTER
# ============================================================

class TaskSplitter:
    """
    Splits a user prompt into parallel rendering tasks.
    Uses LLM to determine what components are needed.
    """

    # Default bpy templates for each task type
    TEMPLATES = {
        TaskType.EXTERIOR: """
# EXTERIOR RENDER — {description}
# Style: {style}, Material: {material}
# Size: {width}m x {depth}m, {floors} floors, height {height}m

import bpy, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Building shell
for i in range({floors}):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, {height}/{floors} * (i + 0.5)))
    floor = bpy.context.active_object
    floor.scale = ({width}/2, {depth}/2, {height}/{floors}/2)
    floor.name = f"Floor_{{i}}"

# Roof
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, {height} + 0.5))
roof = bpy.context.active_object
roof.scale = ({width}/2 + 1, {depth}/2 + 1, 0.15)
roof.name = "Roof"

# Windows
for i in range({floors}):
    for x in [-{width}/4, {width}/4]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -{depth}/2, {height}/{floors} * (i + 0.5)))
        win = bpy.context.active_object
        win.scale = (1.0, 0.05, 1.2)
        win.name = f"Window_{{i}}_{{x}}"

# Camera for exterior view
bpy.ops.object.camera_add(location=({width}*1.5, -{depth}*1.5, {height}*1.2))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(55), 0, math.radians(45))
bpy.context.scene.camera = cam

# Sun
bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))
light = bpy.context.active_object
light.data.energy = 5.0

# Ground
bpy.ops.mesh.primitive_plane_add(size=100, location=(0, 0, -0.01))
ground = bpy.context.active_object
ground.name = "Ground"

print(f"Exterior: {{'{description}'}} rendered")
print(f"Objects: {{len(bpy.data.objects)}}")
""",

        TaskType.INTERIOR: """
# INTERIOR RENDER — {description}
# Style: {style}, Room: {room_type}
# Size: {width}m x {depth}m, height {height}m

import bpy, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Room shell
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
floor = bpy.context.active_object
floor.scale = ({width}/2, {depth}/2, 1)
floor.name = "Floor"

# Walls
wall_h = {height}
for (x, y, sx, sy) in [
    (0, -{depth}/2, {width}/2, 0.1),   # Front
    (0, {depth}/2, {width}/2, 0.1),     # Back
    (-{width}/2, 0, 0.1, {depth}/2),    # Left
    ({width}/2, 0, 0.1, {depth}/2),     # Right
]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, wall_h/2))
    wall = bpy.context.active_object
    wall.scale = (sx, sy, wall_h/2)
    wall.name = f"Wall_{{x}}_{{y}}"

# Furniture based on room type
furniture_items = []

if "{room_type}" == "kitchen":
    # Kitchen counter
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -{depth}/2 + 0.3, 0.45))
    counter = bpy.context.active_object
    counter.scale = ({width}/2 - 0.5, 0.3, 0.45)
    counter.name = "KitchenCounter"
    furniture_items.append("counter")

    # Island
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.45))
    island = bpy.context.active_object
    island.scale = (1.0, 0.5, 0.45)
    island.name = "KitchenIsland"
    furniture_items.append("island")

elif "{room_type}" == "bedroom":
    # Bed
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.3))
    bed = bpy.context.active_object
    bed.scale = (0.9, 1.0, 0.3)
    bed.name = "Bed"
    furniture_items.append("bed")

    # Nightstands
    for x in [-1.2, 1.2]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0.25))
        ns = bpy.context.active_object
        ns.scale = (0.25, 0.25, 0.25)
        ns.name = f"Nightstand_{{x}}"
        furniture_items.append("nightstand")

elif "{room_type}" == "living":
    # Sofa
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -{depth}/2 + 0.5, 0.25))
    sofa = bpy.context.active_object
    sofa.scale = (1.5, 0.5, 0.25)
    sofa.name = "Sofa"
    furniture_items.append("sofa")

    # Coffee table
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.2))
    table = bpy.context.active_object
    table.scale = (0.5, 0.3, 0.2)
    table.name = "CoffeeTable"
    furniture_items.append("table")

# Camera inside room
bpy.ops.object.camera_add(location=(0, 0, 1.6))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(80), 0, 0)
bpy.context.scene.camera = cam

# Interior light
bpy.ops.object.light_add(type='AREA', location=(0, 0, {height} - 0.2))
light = bpy.context.active_object
light.data.energy = 200
light.data.size = 2.0

print(f"Interior: {room_type} — {{'{description}'}}")
print(f"Furniture: {{furniture_items}}")
print(f"Objects: {{len(bpy.data.objects)}}")
""",

        TaskType.LANDSCAPE: """
# LANDSCAPE RENDER — {description}
# Style: {style}, Area: {width}m x {depth}m

import bpy, math, random
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Ground plane
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
ground = bpy.context.active_object
ground.scale = ({width}/2, {depth}/2, 1)
ground.name = "Ground"

# Grass material
mat_grass = bpy.data.materials.new("Grass")
mat_grass.use_nodes = True
bsdf = mat_grass.node_tree.nodes["Principled BSDF"]
bsdf.inputs[0].default_value = (0.15, 0.4, 0.1, 1)
ground.data.materials.append(mat_grass)

# Trees (random positions)
tree_count = {tree_count}
for i in range(tree_count):
    x = random.uniform(-{width}/2 + 2, {width}/2 - 2)
    y = random.uniform(-{depth}/2 + 2, {depth}/2 - 2)

    # Trunk
    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=3, location=(x, y, 1.5))
    trunk = bpy.context.active_object
    trunk.name = f"Tree_Trunk_{{i}}"

    # Crown
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.2, location=(x, y, 3.5))
    crown = bpy.context.active_object
    crown.name = f"Tree_Crown_{{i}}"
    mat_tree = bpy.data.materials.new(f"Tree_{{i}}")
    mat_tree.use_nodes = True
    bsdf_t = mat_tree.node_tree.nodes["Principled BSDF"]
    bsdf_t.inputs[0].default_value = (0.1, random.uniform(0.3, 0.5), 0.05, 1)
    crown.data.materials.append(mat_tree)

# Path
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.02))
path = bpy.context.active_object
path.scale = (1.0, {depth}/2, 0.02)
path.name = "Path"
mat_path = bpy.data.materials.new("Path")
mat_path.use_nodes = True
bsdf_p = mat_path.node_tree.nodes["Principled BSDF"]
bsdf_p.inputs[0].default_value = (0.6, 0.5, 0.4, 1)
path.data.materials.append(mat_path)

# Fence
for (x, y, sx, sy) in [
    (0, -{depth}/2, {width}/2, 0.05),
    (0, {depth}/2, {width}/2, 0.05),
    (-{width}/2, 0, 0.05, {depth}/2),
    ({width}/2, 0, 0.05, {depth}/2),
]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, 0.5))
    fence = bpy.context.active_object
    fence.scale = (sx, sy, 0.5)
    fence.name = f"Fence"

# Camera for landscape overview
bpy.ops.object.camera_add(location=({width}*1.2, -{depth}*1.2, {width}*0.6))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(60), 0, math.radians(40))
bpy.context.scene.camera = cam

# Sun
bpy.ops.object.light_add(type='SUN', location=(10, -10, 20))
light = bpy.context.active_object
light.data.energy = 4.0

print(f"Landscape: {{'{description}'}}")
print(f"Trees: {tree_count}")
print(f"Objects: {{len(bpy.data.objects)}}")
""",

        TaskType.FLOORPLAN: """
# FLOOR PLAN RENDER — {description}
# Top-down view, {floors} floor(s)

import bpy, math
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Floor
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
floor = bpy.context.active_object
floor.scale = ({width}/2, {depth}/2, 1)
floor.name = "FloorPlan"

mat_floor = bpy.data.materials.new("FloorPlan")
mat_floor.use_nodes = True
bsdf = mat_floor.node_tree.nodes["Principled BSDF"]
bsdf.inputs[0].default_value = (0.95, 0.95, 0.95, 1)
floor.data.materials.append(mat_floor)

# Walls (thick for visibility)
wall_thickness = 0.2
mat_wall = bpy.data.materials.new("Wall")
mat_wall.use_nodes = True
bsdf_w = mat_wall.node_tree.nodes["Principled BSDF"]
bsdf_w.inputs[0].default_value = (0.2, 0.2, 0.2, 1)

# Outer walls
for (x, y, sx, sy) in [
    (0, -{depth}/2, {width}/2, wall_thickness),
    (0, {depth}/2, {width}/2, wall_thickness),
    (-{width}/2, 0, wall_thickness, {depth}/2),
    ({width}/2, 0, wall_thickness, {depth}/2),
]:
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, 0.05))
    wall = bpy.context.active_object
    wall.scale = (sx, sy, 0.05)
    wall.data.materials.append(mat_wall)
    wall.name = "OuterWall"

# Interior walls
rooms = {room_count}
if rooms > 1:
    # Divider wall
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.05))
    divider = bpy.context.active_object
    divider.scale = ({width}/2, wall_thickness, 0.05)
    divider.data.materials.append(mat_wall)
    divider.name = "DividerWall"

# Camera top-down
bpy.ops.object.camera_add(location=(0, 0, max({width}, {depth}) * 1.5))
cam = bpy.context.active_object
cam.rotation_euler = (0, 0, 0)
bpy.context.scene.camera = cam

# Light
bpy.ops.object.light_add(type='SUN', location=(0, 0, 20))
light = bpy.context.active_object
light.data.energy = 3.0

print(f"Floor plan: {rooms} room(s)")
print(f"Objects: {{len(bpy.data.objects)}}")
"""
    }

    @staticmethod
    def parse_prompt(prompt: str) -> Dict[str, Any]:
        """
        Parse user prompt to determine what components are needed.
        In production, this would call the LLM parser.
        For now, use keyword detection.
        """
        prompt_lower = prompt.lower()

        components = []

        # Detect exterior
        exterior_keywords = ["дом", "здание", "коттедж", "таунхаус", "отель", "фасад", "экстерьер"]
        if any(kw in prompt_lower for kw in exterior_keywords):
            components.append(TaskType.EXTERIOR)

        # Detect interior
        interior_keywords = ["кухня", "ванная", "спальня", "гостиная", "детская", "интерьер", "мебель", "дизайн"]
        if any(kw in prompt_lower for kw in interior_keywords):
            components.append(TaskType.INTERIOR)

        # Detect landscape
        landscape_keywords = ["ландшафт", "участок", "сад", "газон", "деревья", "забор", "дорожк"]
        if any(kw in prompt_lower for kw in landscape_keywords):
            components.append(TaskType.LANDSCAPE)

        # Detect floor plan
        plan_keywords = ["план", "разрез", "этаж", "планировк"]
        if any(kw in prompt_lower for kw in plan_keywords):
            components.append(TaskType.FLOORPLAN)

        # Default: if nothing detected, generate exterior + interior
        if not components:
            components = [TaskType.EXTERIOR, TaskType.INTERIOR]

        # Extract parameters
        import re
        width_match = re.search(r'(\d+)\s*[мx×]\s*(\d+)', prompt)
        width = int(width_match.group(1)) if width_match else 10
        depth = int(width_match.group(2)) if width_match else 12

        floors_match = re.search(r'(\d+)\s*(?:этаж|floor)', prompt_lower)
        floors = int(floors_match.group(1)) if floors_match else 2

        return {
            "components": components,
            "description": prompt,
            "style": "modern",
            "material": "brick",
            "width": width,
            "depth": depth,
            "height": floors * 2.8,
            "floors": floors,
            "room_type": TaskSplitter._detect_room_type(prompt_lower),
            "tree_count": 8,
            "room_count": 3,
        }

    @staticmethod
    def _detect_room_type(prompt: str) -> str:
        """Detect room type from prompt."""
        if "кухн" in prompt:
            return "kitchen"
        elif "спальн" in prompt or "детск" in prompt:
            return "bedroom"
        elif "ванн" in prompt or "джакуз" in prompt:
            return "bathroom"
        elif "гостин" in prompt:
            return "living"
        return "living"  # default

    @staticmethod
    def generate_script(task_type: TaskType, params: Dict[str, Any]) -> str:
        """Generate bpy script for a specific task type."""
        template = TaskSplitter.TEMPLATES.get(task_type)
        if not template:
            raise ValueError(f"No template for task type: {task_type}")

        return template.format(**params)


# ============================================================
# PARALLEL DISPATCHER
# ============================================================

class ParallelDispatcher:
    """
    Dispatches parallel rendering tasks across multiple Kaggle accounts.
    """

    def __init__(self, accounts: List[Dict[str, str]]):
        self.pool = AccountPool(accounts)
        self.results: Dict[str, Any] = {}

    def dispatch(self, prompt: str) -> Dict[str, Any]:
        """
        Parse prompt, split into tasks, run in parallel across accounts.

        Args:
            prompt: User's description (e.g., "загородный дом с ландшафтом")

        Returns:
            Dict with results for each component
        """
        print(f"\n{'='*60}")
        print(f"PARALLEL DISPATCH")
        print(f"Prompt: {prompt}")
        print(f"{'='*60}\n")

        # Step 1: Parse prompt
        print("[1/3] Parsing prompt...")
        params = TaskSplitter.parse_prompt(prompt)
        components = params["components"]
        print(f"  Components: {[c.value for c in components]}")
        print(f"  Style: {params['style']}")
        print(f"  Size: {params['width']}x{params['depth']}m, {params['floors']} floors")

        # Step 2: Generate scripts
        print(f"\n[2/3] Generating bpy scripts...")
        tasks = []
        for comp in components:
            script = TaskSplitter.generate_script(comp, params)
            script_path = f"/tmp/architect_{comp.value}.py"
            with open(script_path, 'w') as f:
                f.write(script)
            tasks.append({
                "type": comp,
                "script_path": script_path,
                "params": params
            })
            print(f"  ✅ {comp.value}: {len(script)} chars")

        # Step 3: Run in parallel
        print(f"\n[3/3] Dispatching to {len(self.pool.accounts)} Kaggle accounts...")
        results = self._run_parallel(tasks)

        return results

    def _run_parallel(self, tasks: List[Dict]) -> Dict[str, Any]:
        """Run tasks in parallel across available accounts."""
        results = {}

        with ThreadPoolExecutor(max_workers=len(self.pool.accounts)) as executor:
            # Submit all tasks
            futures = {}
            for task in tasks:
                account = self.pool.get_free_account()
                if account is None:
                    # All accounts busy, wait for one
                    print(f"  ⚠️ All accounts busy, waiting...")
                    # In production: queue the task
                    continue

                self.pool.mark_busy(account, task["type"].value)
                print(f"  → {task['type'].value} → {account.name} ({account.username})")

                future = executor.submit(
                    self._render_task,
                    account,
                    task["type"],
                    task["script_path"]
                )
                futures[future] = (account, task["type"])

            # Collect results
            for future in as_completed(futures):
                account, task_type = futures[future]
                try:
                    result = future.result()
                    results[task_type.value] = result
                    print(f"  ✅ {task_type.value} complete: {result.get('output_path', 'N/A')}")
                except Exception as e:
                    results[task_type.value] = {"status": "error", "error": str(e)}
                    print(f"  ❌ {task_type.value} failed: {e}")
                finally:
                    self.pool.mark_free(account)

        return results

    def _render_task(self, account: KaggleAccount, task_type: TaskType, script_path: str) -> Dict:
        """Render a single task on a specific account."""
        print(f"\n  [{account.name}] Starting {task_type.value} render...")
        start = time.time()

        # Push script as dataset
        dataset_name = f"architect-{task_type.value}"
        if not account.renderer.push_script(script_path, dataset_name):
            return {"status": "error", "message": "Failed to push script"}

        # Push and run kernel
        kernel_script = os.path.join(os.path.dirname(__file__), "architect_16k_render.py")
        if not account.renderer.push_kernel(kernel_script):
            return {"status": "error", "message": "Failed to push kernel"}

        result = account.renderer.run_kernel()
        elapsed = time.time() - start

        if result["status"] == "complete":
            # Pull output
            output_path = account.renderer.pull_output(
                output_dir=f"/tmp/architect_{task_type.value}"
            )
            return {
                "status": "complete",
                "task_type": task_type.value,
                "output_path": output_path,
                "render_time": elapsed,
                "account": account.name
            }
        else:
            return {
                "status": "error",
                "task_type": task_type.value,
                "error": result.get("message", "Unknown error"),
                "account": account.name
            }


# ============================================================
# INTEGRATION WITH GATEWAY
# ============================================================

def create_dispatcher_from_env() -> ParallelDispatcher:
    """
    Create dispatcher from environment variables.
    
    Set KAGGLE_ACCOUNTS as JSON:
    export KAGGLE_ACCOUNTS='[
      {"name": "gpu1", "username": "user1", "key": "KGAT_xxx"},
      {"name": "gpu2", "username": "user2", "key": "KGAT_xxx"}
    ]'
    """
    accounts_json = os.environ.get("KAGGLE_ACCOUNTS", "[]")
    accounts = json.loads(accounts_json)

    if not accounts:
        # Fallback to single account from kaggle.json
        kaggle_json = os.path.expanduser("~/.kaggle/kaggle.json")
        if os.path.exists(kaggle_json):
            with open(kaggle_json) as f:
                config = json.load(f)
            accounts = [{
                "name": "default",
                "username": config["username"],
                "api_token": config["key"]
            }]

    return ParallelDispatcher(accounts)


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parallel_dispatcher.py \"загородный дом с ландшафтом\"")
        print()
        print("Environment variables:")
        print("  KAGGLE_ACCOUNTS - JSON array of accounts")
        sys.exit(1)

    prompt = sys.argv[1]
    dispatcher = create_dispatcher_from_env()
    results = dispatcher.dispatch(prompt)

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
