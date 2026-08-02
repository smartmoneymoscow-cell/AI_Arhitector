"""
shared/pbr_scraper.py — PBR texture scraping from ambientCG and Poly Haven.

Downloads PBR texture sets (albedo, normal, roughness, displacement)
for architectural materials. Caches locally.

Compatible with LilySurfaceScraper approach but standalone (no Blender addon).

Usage:
    from shared.pbr_scraper import PBRScraper

    scraper = PBRScraper(cache_dir="/app/output/textures")
    result = scraper.get_material("brick")
    # result = {
    #     "albedo": "/app/output/textures/brick/albedo.jpg",
    #     "normal": "/app/output/textures/brick/normal.jpg",
    #     "roughness": "/app/output/textures/brick/roughness.jpg",
    #     "displacement": "/app/output/textures/brick/displacement.jpg",
    # }
"""

import logging
import os

logger = logging.getLogger("archai.pbr_scraper")

# ═══════════════════════════════════════════════════════════════
# MATERIAL MAPPING — Russian names → ambientCG search terms
# ═══════════════════════════════════════════════════════════════

MATERIAL_SEARCH_MAP = {
    # Russian → English search terms for ambientCG
    "кирпич": "brick",
    "brick": "brick",
    "дерево": "wood",
    "wood": "wood",
    "бетон": "concrete",
    "concrete": "concrete",
    "штукатурка": "plaster",
    "plaster": "plaster",
    "камень": "stone",
    "stone": "stone",
    "металл": "metal",
    "metal": "metal",
    "стекло": "glass",
    "glass": "glass",
    "керамогранит": "tiles",
    "плитка": "tiles",
    "tiles": "tiles",
    "асфальт": "asphalt",
    "asphalt": "asphalt",
    "трава": "grass",
    "grass": "grass",
    "вода": "water",
    "water": "water",
    "мрамор": "marble",
    "marble": "marble",
    "гранит": "granite",
    "granite": "granite",
    "песчаник": "sandstone",
    "sandstone": "sandstone",
}

# ambientCG API
AMBIENTCG_API = "https://ambientcg.com/api/v2/full_json"
AMBIENTCG_ASSETS = "https://ambientcg.com/get"

# Poly Haven API
POLYHAVEN_API = "https://api.polyhaven.com/assets"
POLYHAVEN_FILES = "https://files.polyhaven.com"

# Map material categories
MATERIAL_CATEGORIES = {
    "brick": "brick",
    "wood": "wood",
    "concrete": "concrete",
    "plaster": "plaster",
    "stone": "stone",
    "metal": "metal",
    "glass": "glass",
    "tiles": "tile",
    "asphalt": "asphalt",
    "grass": "grass",
    "water": "water",
    "marble": "marble",
    "granite": "stone",
    "sandstone": "stone",
}

# PBR channel filenames
PBR_CHANNELS = {
    "albedo": ["albedo", "color", "diffuse", "basecolor", "base_color"],
    "normal": ["normal", "normalgl", "normal_gl", "nrm"],
    "roughness": ["roughness", "rough", "rgh"],
    "displacement": ["displacement", "height", "disp", "heightmap"],
    "metallic": ["metallic", "metal", "met"],
    "ao": ["ao", "ambient_occlusion", "occlusion"],
}


class PBRScraper:
    """
    Downloads and caches PBR texture sets from ambientCG / Poly Haven.

    Fallback chain: local cache → ambientCG → Poly Haven → procedural.
    """

    def __init__(self, cache_dir: str = "/app/output/textures"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._cache: dict[str, dict] = {}

    def get_material(self, material_name: str, resolution: str = "2K") -> dict:
        """
        Get PBR texture paths for a material.

        Args:
            material_name: material name (Russian or English)
            resolution: "1K", "2K", "4K"

        Returns:
            dict with channel paths:
            {
                "albedo": "/path/to/albedo.jpg",
                "normal": "/path/to/normal.jpg",
                "roughness": "/path/to/roughness.jpg",
                "displacement": "/path/to/displacement.jpg",
                "found": True/False,
                "source": "ambientcg" | "polyhaven" | "none",
            }
        """
        # Normalize name
        search_term = MATERIAL_SEARCH_MAP.get(material_name.lower(), material_name.lower())
        cache_key = f"{search_term}_{resolution}"

        # Check memory cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Check disk cache
        material_dir = os.path.join(self.cache_dir, search_term)
        cached = self._check_disk_cache(material_dir, resolution)
        if cached:
            self._cache[cache_key] = cached
            return cached

        # Try ambientCG
        result = self._try_ambientcg(search_term, resolution, material_dir)
        if result and result.get("found"):
            self._cache[cache_key] = result
            return result

        # Try Poly Haven
        result = self._try_polyhaven(search_term, resolution, material_dir)
        if result and result.get("found"):
            self._cache[cache_key] = result
            return result

        # Fallback: return empty (agent will use procedural)
        return {
            "albedo": None,
            "normal": None,
            "roughness": None,
            "displacement": None,
            "found": False,
            "source": "none",
        }

    def generate_blender_material_script(self, material_name: str, texture_paths: dict) -> str:
        """
        Generate bpy script to create a PBR material from texture files.

        Compatible with existing texture agent output format.
        """
        if not texture_paths.get("found"):
            return ""

        def _path(p):
            if p:
                return p.replace("\\", "/")
            return ""

        albedo = _path(texture_paths.get("albedo"))
        normal = _path(texture_paths.get("normal"))
        roughness = _path(texture_paths.get("roughness"))
        displacement = _path(texture_paths.get("displacement"))

        # Sanitize for script
        def _s(v):
            return str(v).replace('"', '\\"').replace("'", "\\'")

        script = f"""
# PBR Material from textures: {_s(material_name)}
mat_{material_name} = bpy.data.materials.new("{_s(material_name)}")
mat_{material_name}.use_nodes = True
nodes = mat_{material_name}.node_tree.nodes
links = mat_{material_name}.node_tree.links
nodes.clear()

# Principled BSDF
bsdf = nodes.new('ShaderNodeBsdfPrincipled')
bsdf.location = (0, 0)

# Output
output = nodes.new('ShaderNodeOutputMaterial')
output.location = (300, 0)
links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

# Texture coordinate
tex_coord = nodes.new('ShaderNodeTexCoord')
tex_coord.location = (-800, 0)

# Mapping
mapping = nodes.new('ShaderNodeMapping')
mapping.location = (-600, 0)
mapping.inputs["Scale"].default_value = (2.0, 2.0, 2.0)
links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])
"""

        if albedo:
            script += f"""
# Albedo
tex_albedo = nodes.new('ShaderNodeTexImage')
tex_albedo.location = (-400, 200)
try:
    tex_albedo.image = bpy.data.images.load("{_s(albedo)}")
except:
    pass
links.new(mapping.outputs["Vector"], tex_albedo.inputs["Vector"])
links.new(tex_albedo.outputs["Color"], bsdf.inputs["Base Color"])
"""

        if roughness:
            script += f"""
# Roughness
tex_rough = nodes.new('ShaderNodeTexImage')
tex_rough.location = (-400, 0)
tex_rough.image.colorspace_settings.name = 'Non-Color'
try:
    tex_rough.image = bpy.data.images.load("{_s(roughness)}")
except:
    pass
links.new(mapping.outputs["Vector"], tex_rough.inputs["Vector"])
links.new(tex_rough.outputs["Color"], bsdf.inputs["Roughness"])
"""

        if normal:
            script += f"""
# Normal
tex_normal = nodes.new('ShaderNodeTexImage')
tex_normal.location = (-400, -200)
tex_normal.image.colorspace_settings.name = 'Non-Color'
try:
    tex_normal.image = bpy.data.images.load("{_s(normal)}")
except:
    pass
links.new(mapping.outputs["Vector"], tex_normal.inputs["Vector"])

normal_map = nodes.new('ShaderNodeNormalMap')
normal_map.location = (-200, -200)
links.new(tex_normal.outputs["Color"], normal_map.inputs["Color"])
links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
"""

        if displacement:
            script += f"""
# Displacement
tex_disp = nodes.new('ShaderNodeTexImage')
tex_disp.location = (-400, -400)
tex_disp.image.colorspace_settings.name = 'Non-Color'
try:
    tex_disp.image = bpy.data.images.load("{_s(displacement)}")
except:
    pass
links.new(mapping.outputs["Vector"], tex_disp.inputs["Vector"])

disp_node = nodes.new('ShaderNodeDisplacement')
disp_node.location = (-200, -400)
disp_node.inputs["Scale"].default_value = 0.02
links.new(tex_disp.outputs["Color"], disp_node.inputs["Height"])
links.new(disp_node.outputs["Displacement"], output.inputs["Displacement"])
"""

        return script

    # ── Internal methods ──

    def _check_disk_cache(self, material_dir: str, resolution: str) -> dict | None:
        """Check if textures already downloaded."""
        result = {
            "albedo": None,
            "normal": None,
            "roughness": None,
            "displacement": None,
            "found": False,
            "source": "cache",
        }

        if not os.path.isdir(material_dir):
            return None

        # Look for texture files
        for channel, aliases in PBR_CHANNELS.items():
            for alias in aliases:
                for ext in ["jpg", "png", "jpeg"]:
                    pattern = os.path.join(material_dir, f"*{alias}*.{ext}")
                    import glob

                    matches = glob.glob(pattern)
                    if matches:
                        result[channel] = matches[0]
                        break

        # Check if at least albedo exists
        if result["albedo"]:
            result["found"] = True
            return result

        return None

    def _try_ambientcg(self, search_term: str, resolution: str, output_dir: str) -> dict | None:
        """Try downloading from ambientCG API."""
        try:
            import httpx

            # Map resolution
            res_map = {"1K": "1K", "2K": "2K", "4K": "4K"}
            res = res_map.get(resolution, "2K")

            # Search for material
            params = {
                "type": "Material",
                "query": search_term,
                "limit": 5,
                "include": "downloadData,displayData",
            }

            r = httpx.get(AMBIENTCG_API, params=params, timeout=30)
            if r.status_code != 200:
                logger.warning("ambientCG API returned %d", r.status_code)
                return None

            data = r.json()
            assets = data.get("foundAssets", [])
            if not assets:
                logger.info("ambientCG: no assets found for '%s'", search_term)
                return None

            # Find best match with requested resolution
            best_asset = None
            for asset in assets:
                downloads = asset.get("downloadFolders", {})
                default_folder = downloads.get("default", {})
                download_files = default_folder.get("downloadFileCategories", {})

                # Check if has required resolution
                for category in ["Textures", ""]:
                    cat_data = download_files.get(category, download_files.get("Textures", {}))
                    if isinstance(cat_data, dict):
                        for file_type, file_info in cat_data.get("downloadFiles", {}).items():
                            if res in file_info.get("attribute", {}).get("resolution", ""):
                                best_asset = asset
                                break
                if best_asset:
                    break

            if not best_asset:
                best_asset = assets[0]

            # Download textures
            os.makedirs(output_dir, exist_ok=True)
            result = {
                "albedo": None,
                "normal": None,
                "roughness": None,
                "displacement": None,
                "found": False,
                "source": "ambientcg",
            }

            downloads = best_asset.get("downloadFolders", {}).get("default", {})
            categories = downloads.get("downloadFileCategories", {})

            for cat_name, cat_data in categories.items():
                if not isinstance(cat_data, dict):
                    continue
                for file_type, file_info in cat_data.get("downloadFiles", {}).items():
                    download_url = file_info.get("downloadLink", "")
                    if not download_url:
                        continue

                    # Determine channel
                    file_lower = file_type.lower()
                    channel = None
                    for ch, aliases in PBR_CHANNELS.items():
                        if any(alias in file_lower for alias in aliases):
                            channel = ch
                            break

                    if channel:
                        filepath = os.path.join(output_dir, f"{channel}.jpg")
                        if not os.path.exists(filepath):
                            try:
                                dl_r = httpx.get(download_url, timeout=60, follow_redirects=True)
                                if dl_r.status_code == 200:
                                    with open(filepath, "wb") as f:
                                        f.write(dl_r.content)
                                    result[channel] = filepath
                                    result["found"] = True
                            except Exception as e:
                                logger.warning("Download failed for %s: %s", file_type, e)
                        else:
                            result[channel] = filepath
                            result["found"] = True

            return result if result["found"] else None

        except Exception as e:
            logger.warning("ambientCG scraping failed: %s", e)
            return None

    def _try_polyhaven(self, search_term: str, resolution: str, output_dir: str) -> dict | None:
        """Try downloading from Poly Haven API."""
        try:
            import httpx

            # Poly Haven uses different naming
            poly_category = MATERIAL_CATEGORIES.get(search_term, search_term)

            # Search assets
            r = httpx.get(
                POLYHAVEN_API,
                params={"type": "textures", "categories": poly_category},
                timeout=30,
            )
            if r.status_code != 200:
                return None

            assets = r.json()
            if not assets:
                return None

            # Pick first asset
            asset_id = list(assets.keys())[0]

            # Get file list
            files_r = httpx.get(f"{POLYHAVEN_API}/{asset_id}", timeout=30)
            if files_r.status_code != 200:
                return None

            files_data = files_r.json()
            include_map = files_data.get("include", {})

            # Map resolution
            res_map = {"1K": "1k", "2K": "2k", "4K": "4k"}
            res = res_map.get(resolution, "2k")

            os.makedirs(output_dir, exist_ok=True)
            result = {
                "albedo": None,
                "normal": None,
                "roughness": None,
                "displacement": None,
                "found": False,
                "source": "polyhaven",
            }

            # Download each channel
            for channel, aliases in PBR_CHANNELS.items():
                for alias in aliases:
                    for file_key, file_info in include_map.items():
                        if alias in file_key.lower() and res in file_key.lower():
                            download_url = f"{POLYHAVEN_FILES}/{asset_id}/{file_key}"
                            filepath = os.path.join(output_dir, f"{channel}.jpg")

                            if os.path.exists(filepath):
                                result[channel] = filepath
                                result["found"] = True
                                continue

                            try:
                                dl_r = httpx.get(download_url, timeout=60, follow_redirects=True)
                                if dl_r.status_code == 200:
                                    with open(filepath, "wb") as f:
                                        f.write(dl_r.content)
                                    result[channel] = filepath
                                    result["found"] = True
                            except Exception as e:
                                logger.warning("Poly Haven download failed: %s", e)
                            break

            return result if result["found"] else None

        except Exception as e:
            logger.warning("Poly Haven scraping failed: %s", e)
            return None


# ═══════════════════════════════════════════════════════════════
# HDRI SCRAPER — environment maps
# ═══════════════════════════════════════════════════════════════


class HDRIScraper:
    """Downloads HDRI environment maps from Poly Haven."""

    # Pre-defined environment presets
    PRESETS = {
        "morning": "kloofendal_48d_partly_cloudy_puresky",
        "day": "the_sky_is_on_fire",
        "evening": "symmetrical_garden_02",
        "night": "moonless_golf",
        "studio": "studio_small_09",
        "city": "potsdamer_platz",
        "park": "rooitou_park",
        "interior": "bathroom_interior",
    }

    def __init__(self, cache_dir: str = "/app/output/hdri"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get_hdri(self, preset: str = "day", resolution: str = "2k") -> str | None:
        """
        Get HDRI file path for a preset.

        Returns:
            Path to HDRI file or None
        """
        hdri_id = self.PRESETS.get(preset, self.PRESETS["day"])
        filepath = os.path.join(self.cache_dir, f"{hdri_id}_{resolution}.hdr")

        if os.path.exists(filepath):
            return filepath

        try:
            import httpx

            # Get file list
            r = httpx.get(f"{POLYHAVEN_API}/{hdri_id}", timeout=30)
            if r.status_code != 200:
                return None

            files_data = r.json()
            include_map = files_data.get("include", {})

            # Find HDR file
            for file_key, file_info in include_map.items():
                if file_key.endswith(".hdr") and resolution in file_key:
                    download_url = f"{POLYHAVEN_FILES}/{hdri_id}/{file_key}"
                    dl_r = httpx.get(download_url, timeout=120, follow_redirects=True)
                    if dl_r.status_code == 200:
                        with open(filepath, "wb") as f:
                            f.write(dl_r.content)
                        return filepath

        except Exception as e:
            logger.warning("HDRI download failed: %s", e)

        return None

    def generate_blender_hdri_script(self, hdri_path: str, rotation: float = 0.0) -> str:
        """Generate bpy script to set HDRI environment."""
        if not hdri_path:
            return ""

        def _s(v):
            return str(v).replace('"', '\\"')

        return f"""
# HDRI Environment
import bpy
world = bpy.context.scene.world
if not world:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True
nodes = world.node_tree.nodes
links = world.node_tree.links
nodes.clear()

# Environment Texture
env_tex = nodes.new('ShaderNodeTexEnvironment')
env_tex.location = (-300, 0)
try:
    env_tex.image = bpy.data.images.load("{_s(hdri_path)}")
except:
    pass

# Background
bg = nodes.new('ShaderNodeBackground')
bg.location = (0, 0)
bg.inputs["Strength"].default_value = 1.0

# Output
output = nodes.new('ShaderNodeOutputWorld')
output.location = (200, 0)

# Links
links.new(env_tex.outputs["Color"], bg.inputs["Color"])
links.new(bg.outputs["Background"], output.inputs["Surface"])

# Rotation
mapping = nodes.new('ShaderNodeMapping')
mapping.location = (-500, 0)
mapping.inputs["Rotation"].default_value = (0, 0, {rotation})

tex_coord = nodes.new('ShaderNodeTexCoord')
tex_coord.location = (-700, 0)
links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
links.new(mapping.outputs["Vector"], env_tex.inputs["Vector"])
"""
