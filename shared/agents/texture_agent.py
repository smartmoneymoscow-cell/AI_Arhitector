"""
shared/agents/texture_agent.py — Агент генерации текстур (PBR bpy-скрипт).

Генерирует реальный bpy-скрипт создания PBR-материалов,
который выполняется в Blender.
"""

import time

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

# PBR-конфигурации материалов
MATERIAL_CONFIGS = {
    "brick": {
        "base_color": (0.71, 0.40, 0.12),
        "roughness": 0.88,
        "metallic": 0.0,
        "normal_strength": 0.8,
        "tile_size": [0.128, 0.065],
    },
    "wood": {
        "base_color": (0.55, 0.41, 0.13),
        "roughness": 0.82,
        "metallic": 0.0,
        "normal_strength": 0.4,
        "tile_size": [0.1, 0.8],
    },
    "glass": {
        "base_color": (0.8, 0.9, 1.0),
        "roughness": 0.04,
        "metallic": 0.15,
        "normal_strength": 0.0,
        "transparent": True,
        "opacity": 0.72,
    },
    "plaster": {
        "base_color": (0.91, 0.88, 0.83),
        "roughness": 0.92,
        "metallic": 0.0,
        "normal_strength": 0.1,
    },
    "stone": {
        "base_color": (0.50, 0.50, 0.50),
        "roughness": 0.9,
        "metallic": 0.0,
        "normal_strength": 0.6,
        "tile_size": [0.3, 0.2],
    },
    "concrete": {
        "base_color": (0.63, 0.63, 0.63),
        "roughness": 0.95,
        "metallic": 0.0,
        "normal_strength": 0.2,
    },
}


def generate_pbr_material_script(material_name: str, config: dict) -> str:
    """Генерирует bpy-скрипт создания PBR-материала с нодами."""
    r, g, b = config["base_color"]
    roughness = config["roughness"]
    metallic = config["metallic"]

    script = f"""
# PBR Material: {material_name}
mat_{material_name} = bpy.data.materials.new("{material_name}")
mat_{material_name}.use_nodes = True
nodes_{material_name} = mat_{material_name}.node_tree.nodes
links_{material_name} = mat_{material_name}.node_tree.links
nodes_{material_name}.clear()

# Principled BSDF
bsdf_{material_name} = nodes_{material_name}.new('ShaderNodeBsdfPrincipled')
bsdf_{material_name}.location = (0, 0)
bsdf_{material_name}.inputs["Base Color"].default_value = ({r}, {g}, {b}, 1.0)
bsdf_{material_name}.inputs["Roughness"].default_value = {roughness}
bsdf_{material_name}.inputs["Metallic"].default_value = {metallic}
"""

    if config.get("transparent"):
        script += f"""bsdf_{material_name}.inputs["Alpha"].default_value = {config.get("opacity", 0.8)}
mat_{material_name}.blend_method = 'BLEND'
"""

    # Noise texture for surface variation
    script += f"""
# Noise texture for surface variation
noise_{material_name} = nodes_{material_name}.new('ShaderNodeTexNoise')
noise_{material_name}.location = (-400, 0)
noise_{material_name}.inputs["Scale"].default_value = 15.0
noise_{material_name}.inputs["Detail"].default_value = 8.0
noise_{material_name}.inputs["Roughness"].default_value = 0.6

# Color ramp for subtle variation
ramp_{material_name} = nodes_{material_name}.new('ShaderNodeValToRGB')
ramp_{material_name}.location = (-200, 0)
ramp_{material_name}.color_ramp.elements[0].position = 0.4
ramp_{material_name}.color_ramp.elements[0].color = ({r * 0.9}, {g * 0.9}, {b * 0.9}, 1.0)
ramp_{material_name}.color_ramp.elements[1].position = 0.6
ramp_{material_name}.color_ramp.elements[1].color = ({min(1, r * 1.1)}, {min(1, g * 1.1)}, {min(1, b * 1.1)}, 1.0)

# Bump map for surface detail
bump_{material_name} = nodes_{material_name}.new('ShaderNodeBump')
bump_{material_name}.location = (-200, -200)
bump_{material_name}.inputs["Strength"].default_value = {config.get("normal_strength", 0.3)}

# Output
output_{material_name} = nodes_{material_name}.new('ShaderNodeOutputMaterial')
output_{material_name}.location = (300, 0)

# Links
links_{material_name}.new(noise_{material_name}.outputs["Fac"], ramp_{material_name}.inputs["Fac"])
links_{material_name}.new(ramp_{material_name}.outputs["Color"], bsdf_{material_name}.inputs["Base Color"])
links_{material_name}.new(noise_{material_name}.outputs["Fac"], bump_{material_name}.inputs["Height"])
links_{material_name}.new(bump_{material_name}.outputs["Normal"], bsdf_{material_name}.inputs["Normal"])
links_{material_name}.new(bsdf_{material_name}.outputs["BSDF"], output_{material_name}.inputs["Surface"])
"""
    return script


class TextureAgent(BaseAgent):
    """Агент генерации PBR-материалов для Blender."""

    name = "texture"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            material = task.params.get("material", "plaster")
            resolution = task.params.get("resolution", 2048)

            config = MATERIAL_CONFIGS.get(material, MATERIAL_CONFIGS["plaster"])
            script = generate_pbr_material_script(material, config)

            return TaskResult(
                status=TaskStatus.DONE,
                data={
                    "material": material,
                    "config": config,
                    "script": script,
                    "resolution": resolution,
                },
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )
