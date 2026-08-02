#!/usr/bin/env python3
"""
Asset Downloader — скачивание бесплатных PBR текстур, HDRI и моделей
с Poly Haven (CC0) для AI_Arhitector.

Использование:
  python3 download_assets.py --output ./assets
  python3 download_assets.py --output /kaggle/working/assets --max-textures 5

Результат:
  assets/
  ├── textures/
  │   ├── brick_wall/    (albedo.jpg, roughness.jpg, normal.jpg, ao.jpg)
  │   ├── concrete/      
  │   ├── wood_floor/    
  │   ├── roof_tiles/    
  │   ├── plaster/       
  │   └── grass/
  ├── hdris/
  │   ├── sky_clear.hdr
  │   ├── sky_cloudy.hdr
  │   └── studio_soft.hdr
  └── models/
      ├── sofa.glb
      ├── table.glb
      └── chair.glb
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error

# ============================================================
# POLY HAVEN API (CC0, no auth needed)
# ============================================================
POLYHAVEN_API = "https://api.polyhaven.com"

def polyhaven_list_assets(asset_type, categories=None, limit=10):
    """List assets from Poly Haven API.
    
    asset_type: 'textures', 'hdris', 'models'
    categories: list of category filters
    """
    url = f"{POLYHAVEN_API}/assets?t={asset_type}"
    if categories:
        url += "&c=" + "&c=".join(categories)
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Arhitector/1.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        
        # Sort by download count (popularity) and limit
        assets = []
        for name, info in data.items():
            assets.append({
                "name": name,
                "categories": info.get("categories", []),
                "tags": info.get("tags", []),
            })
        
        return assets[:limit]
    except Exception as e:
        print(f"  Error listing {asset_type}: {e}")
        return []


def polyhaven_get_files(asset_name, asset_type="textures"):
    """Get download URLs for an asset.
    
    Returns dict of file_type -> url
    """
    url = f"{POLYHAVEN_API}/files/{asset_name}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Arhitector/1.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  Error getting files for {asset_name}: {e}")
        return {}


def download_file(url, output_path, timeout=120):
    """Download a file with progress."""
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Arhitector/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        
        with open(output_path, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
        
        sz = os.path.getsize(output_path) / 1024 / 1024
        return True, sz
    except Exception as e:
        return False, str(e)


# ============================================================
# TEXTURE DOWNLOADER
# ============================================================

# Texture categories relevant for architecture
TEXTURE_CATEGORIES = {
    "brick": ["Brick", "brick"],
    "concrete": ["Concrete", "concrete"],
    "wood": ["Wood", "wood"],
    "roof": ["Roofing", "roof"],
    "plaster": ["Plaster", "plaster"],
    "grass": ["Ground", "grass"],
    "stone": ["Stone", "stone"],
    "metal": ["Metal", "metal"],
    "fabric": ["Fabric", "fabric"],
    "tile": ["Tile", "tile"],
}

def download_textures(output_dir, max_per_category=2, resolution="2k"):
    """Download PBR textures from Poly Haven."""
    textures_dir = os.path.join(output_dir, "textures")
    os.makedirs(textures_dir, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("DOWNLOADING PBR TEXTURES")
    print("=" * 60)
    
    downloaded = []
    
    for mat_name, categories in TEXTURE_CATEGORIES.items():
        print(f"\n--- {mat_name.upper()} ---")
        
        assets = polyhaven_list_assets("textures", categories, limit=max_per_category)
        if not assets:
            print(f"  No assets found")
            continue
        
        for asset in assets[:max_per_category]:
            name = asset["name"]
            asset_dir = os.path.join(textures_dir, f"{mat_name}_{name}")
            
            if os.path.exists(asset_dir) and len(os.listdir(asset_dir)) >= 3:
                print(f"  {name}: already exists, skipping")
                downloaded.append(asset_dir)
                continue
            
            print(f"  {name}: downloading...")
            files = polyhaven_get_files(name, "textures")
            
            if not files:
                print(f"    No files available")
                continue
            
            os.makedirs(asset_dir, exist_ok=True)
            
            # Download key PBR maps
            maps_to_download = {
                "albedo": f"diffuse_{resolution}",
                "roughness": f"rough_{resolution}",
                "normal": f"nor_gl_{resolution}",
                "displacement": f"disp_{resolution}",
                "ao": f"ao_{resolution}",
            }
            
            count = 0
            for map_name, file_key in maps_to_download.items():
                if file_key in files:
                    file_info = files[file_key]
                    if isinstance(file_info, dict) and "url" in file_info:
                        url = file_info["url"]
                        ext = url.split(".")[-1].split("?")[0]
                        out_path = os.path.join(asset_dir, f"{map_name}.{ext}")
                        
                        if os.path.exists(out_path):
                            count += 1
                            continue
                        
                        ok, info = download_file(url, out_path)
                        if ok:
                            count += 1
                            print(f"    {map_name}: {info:.1f} MB")
                        else:
                            print(f"    {map_name}: FAILED ({info})")
            
            if count >= 3:
                downloaded.append(asset_dir)
                print(f"    ✅ {count} maps downloaded")
            else:
                print(f"    ⚠️ Only {count} maps (need 3+)")
    
    return downloaded


# ============================================================
# HDRI DOWNLOADER
# ============================================================

HDRI_SEARCHES = [
    "sky",
    "cloudy",
    "sunset",
    "studio",
    "overcast",
]

def download_hdris(output_dir, max_count=5, resolution="2k"):
    """Download HDRI environment maps from Poly Haven."""
    hdris_dir = os.path.join(output_dir, "hdris")
    os.makedirs(hdris_dir, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("DOWNLOADING HDRI ENVIRONMENT MAPS")
    print("=" * 60)
    
    downloaded = []
    
    # Search for HDRIs
    assets = polyhaven_list_assets("hdris", limit=max_count * 2)
    
    # Filter for outdoor/sky types
    sky_keywords = ["sky", "cloud", "sun", "overcast", "clear", "blue", "sunset", "dawn", "day"]
    
    for asset in assets:
        if len(downloaded) >= max_count:
            break
        
        name = asset["name"]
        tags = [t.lower() for t in asset.get("tags", [])]
        categories = [c.lower() for c in asset.get("categories", [])]
        
        # Check if it's a sky/outdoor HDRI
        is_sky = any(kw in " ".join(tags + categories + [name.lower()]) for kw in sky_keywords)
        if not is_sky and len(downloaded) < 2:
            # First 2 can be anything
            pass
        elif not is_sky:
            continue
        
        out_path = os.path.join(hdris_dir, f"{name}.hdr")
        if os.path.exists(out_path):
            print(f"  {name}: already exists")
            downloaded.append(out_path)
            continue
        
        print(f"  {name}: downloading...")
        files = polyhaven_get_files(name, "hdris")
        
        if not files:
            continue
        
        # Find the requested resolution
        hdri_key = f"hdri_{resolution}"
        if hdri_key not in files:
            # Try lower resolution
            for res in ["1k", "2k", "4k"]:
                hdri_key = f"hdri_{res}"
                if hdri_key in files:
                    break
        
        if hdri_key in files:
            file_info = files[hdri_key]
            if isinstance(file_info, dict) and "url" in file_info:
                url = file_info["url"]
                ok, info = download_file(url, out_path)
                if ok:
                    downloaded.append(out_path)
                    print(f"    ✅ {info:.1f} MB")
                else:
                    print(f"    ❌ Failed: {info}")
    
    return downloaded


# ============================================================
# MODEL DOWNLOADER
# ============================================================

MODEL_SEARCHES = {
    "furniture": ["chair", "table", "sofa", "bed", "shelf"],
    "decor": ["lamp", "plant", "vase", "painting"],
    "exterior": ["tree", "bush", "fence", "bench"],
}

def download_models(output_dir, max_count=10):
    """Download 3D models from Poly Haven."""
    models_dir = os.path.join(output_dir, "models")
    os.makedirs(models_dir, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("DOWNLOADING 3D MODELS")
    print("=" * 60)
    
    downloaded = []
    
    assets = polyhaven_list_assets("models", limit=max_count * 3)
    
    for asset in assets:
        if len(downloaded) >= max_count:
            break
        
        name = asset["name"]
        
        out_path = os.path.join(models_dir, f"{name}.glb")
        if os.path.exists(out_path):
            print(f"  {name}: already exists")
            downloaded.append(out_path)
            continue
        
        print(f"  {name}: downloading...")
        files = polyhaven_get_files(name, "models")
        
        if not files:
            continue
        
        # Find GLB format
        glb_file = None
        for key in ["glb", "gltf", "GLB"]:
            if key in files:
                glb_file = files[key]
                break
        
        # Try nested structure
        if not glb_file:
            for key, val in files.items():
                if isinstance(val, dict):
                    for subkey in ["glb", "gltf"]:
                        if subkey in val:
                            glb_file = val[subkey]
                            break
                if glb_file:
                    break
        
        if glb_file and isinstance(glb_file, dict) and "url" in glb_file:
            url = glb_file["url"]
            ok, info = download_file(url, out_path)
            if ok:
                downloaded.append(out_path)
                print(f"    ✅ {info:.1f} MB")
            else:
                print(f"    ❌ Failed: {info}")
    
    return downloaded


# ============================================================
# AMBIENTCG FALLBACK
# ============================================================

def download_ambientcg_textures(output_dir, max_count=5):
    """Download textures from ambientCG as fallback."""
    textures_dir = os.path.join(output_dir, "textures")
    os.makedirs(textures_dir, exist_ok=True)
    
    print("\n" + "=" * 60)
    print("DOWNLOADING FROM AMBIENTCG (fallback)")
    print("=" * 60)
    
    categories = ["Brick", "Concrete", "Wood", "Plaster", "Ground", "Roofing"]
    downloaded = []
    
    for cat in categories:
        if len(downloaded) >= max_count:
            break
        
        try:
            url = f"https://ambientcg.com/api/v1/full_json?type=Material&category={cat}&limit=1&sort=Latest"
            req = urllib.request.Request(url, headers={"User-Agent": "AI-Arhitector/1.0"})
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            
            for asset_id, asset_info in data.get("foundAssets", {}).items():
                name = asset_info.get("assetId", asset_id)
                asset_dir = os.path.join(textures_dir, f"acg_{cat.lower()}_{name}")
                
                if os.path.exists(asset_dir):
                    downloaded.append(asset_dir)
                    continue
                
                # Find download URL
                downloads = asset_info.get("downloads", {})
                # Prefer 2K JPG
                for res in ["2K-JPG", "2K-PNG", "1K-JPG"]:
                    if res in downloads:
                        dl_url = downloads[res].get("downloadLink")
                        if dl_url:
                            os.makedirs(asset_dir, exist_ok=True)
                            zip_path = os.path.join(asset_dir, "temp.zip")
                            ok, info = download_file(dl_url, zip_path)
                            if ok:
                                # Extract
                                import zipfile
                                with zipfile.ZipFile(zip_path, "r") as zf:
                                    zf.extractall(asset_dir)
                                os.remove(zip_path)
                                downloaded.append(asset_dir)
                                print(f"  {name}: ✅")
                            break
        except Exception as e:
            print(f"  {cat}: Error - {e}")
    
    return downloaded


# ============================================================
# ASSET MANIFEST
# ============================================================

def create_manifest(output_dir, textures, hdris, models):
    """Create asset manifest for Blender scripts."""
    manifest = {
        "textures": {},
        "hdris": [],
        "models": {},
    }
    
    # Textures
    for tex_dir in textures:
        if os.path.isdir(tex_dir):
            name = os.path.basename(tex_dir)
            maps = {}
            for f in os.listdir(tex_dir):
                map_name = os.path.splitext(f)[0]
                maps[map_name] = os.path.join(tex_dir, f)
            if maps:
                manifest["textures"][name] = maps
    
    # HDRIs
    for hdri_path in hdris:
        if os.path.exists(hdri_path):
            manifest["hdris"].append(hdri_path)
    
    # Models
    for model_path in models:
        if os.path.exists(model_path):
            name = os.path.splitext(os.path.basename(model_path))[0]
            manifest["models"][name] = model_path
    
    # Save
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"MANIFEST: {manifest_path}")
    print(f"  Textures: {len(manifest['textures'])}")
    print(f"  HDRIs: {len(manifest['hdris'])}")
    print(f"  Models: {len(manifest['models'])}")
    print(f"{'='*60}")
    
    return manifest


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Download free assets for AI_Arhitector")
    parser.add_argument("--output", default="./assets", help="Output directory")
    parser.add_argument("--max-textures", type=int, default=6, help="Max textures per source")
    parser.add_argument("--max-hdris", type=int, default=4, help="Max HDRI maps")
    parser.add_argument("--max-models", type=int, default=8, help="Max 3D models")
    parser.add_argument("--resolution", default="2k", help="Texture resolution (1k/2k/4k)")
    parser.add_argument("--source", default="polyhaven", choices=["polyhaven", "ambientcg", "both"])
    args = parser.parse_args()
    
    print("=" * 60)
    print("AI_Arhitector — Asset Downloader")
    print("=" * 60)
    print(f"Output: {args.output}")
    print(f"Source: {args.source}")
    print(f"Resolution: {args.resolution}")
    
    t0 = time.time()
    
    # Download textures
    textures = []
    if args.source in ("polyhaven", "both"):
        textures = download_textures(args.output, args.max_textures, args.resolution)
    if args.source == "ambientcg" or (args.source == "both" and len(textures) < 3):
        textures += download_ambientcg_textures(args.output, args.max_textures - len(textures))
    
    # Download HDRIs
    hdris = download_hdris(args.output, args.max_hdris, args.resolution)
    
    # Download models
    models = download_models(args.output, args.max_models)
    
    # Create manifest
    manifest = create_manifest(args.output, textures, hdris, models)
    
    elapsed = time.time() - t0
    print(f"\nTotal time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Ready for rendering! 🎉")
    
    return manifest


if __name__ == "__main__":
    main()
