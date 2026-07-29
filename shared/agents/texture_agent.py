"""
shared/agents/texture_agent.py — Агент генерации текстур.

Отвечает за:
- Генерацию PBR текстур (color, normal, roughness)
- Применение текстур к геометрии
- Кэширование текстур
"""

import time
from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus


class TextureAgent(BaseAgent):
    name = "texture"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            material = task.params.get("material", "plaster")
            resolution = task.params.get("resolution", 2048)

            texture_data = self._generate_texture(material, resolution)

            return TaskResult(
                status=TaskStatus.DONE,
                data=texture_data,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def _generate_texture(self, material: str, resolution: int) -> dict:
        """Генерирует параметры текстуры для материала."""
        texture_configs = {
            "brick": {
                "base_color": "#c87040",
                "roughness": 0.88,
                "metallic": 0.0,
                "normal_strength": 0.8,
                "tile_size": [0.128, 0.065],  # meters per brick
            },
            "wood": {
                "base_color": "#b8864e",
                "roughness": 0.82,
                "metallic": 0.0,
                "normal_strength": 0.4,
                "tile_size": [0.1, 0.8],
            },
            "glass": {
                "base_color": "#90b8d0",
                "roughness": 0.04,
                "metallic": 0.15,
                "normal_strength": 0.0,
                "transparent": True,
                "opacity": 0.72,
            },
            "plaster": {
                "base_color": "#f0ece4",
                "roughness": 0.92,
                "metallic": 0.0,
                "normal_strength": 0.1,
            },
            "stone": {
                "base_color": "#8a8278",
                "roughness": 0.9,
                "metallic": 0.0,
                "normal_strength": 0.6,
                "tile_size": [0.3, 0.2],
            },
            "concrete": {
                "base_color": "#9a9a9a",
                "roughness": 0.95,
                "metallic": 0.0,
                "normal_strength": 0.2,
            },
        }

        config = texture_configs.get(material, texture_configs["plaster"])
        config["resolution"] = resolution
        config["material"] = material
        return config
