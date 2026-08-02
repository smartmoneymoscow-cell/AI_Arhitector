"""
shared/upscaler.py — Апскейл изображений через Real-ESRGAN.

Поддерживает:
- Real-ESRGAN (реалистичные фото, рендеры)
- PIL resize как fallback

Зависимости: realesrgan (опционально), Pillow

Использование:
    from shared.upscaler import upscale_image
    result = upscale_image("input.png", "output.png", scale=4)
"""

import os


def upscale_image(input_path: str, output_path: str, scale: int = 4) -> str:
    """
    Апскейлит изображение.

    Args:
        input_path: путь к входному изображению
        output_path: путь для сохранения результата
        scale: коэффициент апскейла (2, 4)

    Returns:
        Путь к апскейленному изображению
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Попытка 1: Real-ESRGAN
    try:
        return _upscale_realesrgan(input_path, output_path, scale)
    except ImportError:
        pass
    except Exception as e:
        print(f"[upscaler] Real-ESRGAN failed: {e}, falling back to PIL")

    # Попытка 2: PIL (базовый апскейл)
    return _upscale_pil(input_path, output_path, scale)


def _upscale_realesrgan(input_path: str, output_path: str, scale: int) -> str:
    """Апскейл через Real-ESRGAN."""
    import cv2
    import torch
    from realesrgan import RealESRGANer

    # Выбор модели в зависимости от scale
    if scale == 4:
        model_name = "realesrgan-x4plus"
        model_path = None  # Автоматическое скачивание
    elif scale == 2:
        model_name = "realesrgan-x2plus"
        model_path = None
    else:
        model_name = "realesrgan-x4plus"
        scale = 4

    # Проверка GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    half = device == "cuda"

    # Инициализация модели
    from basicsr.archs.rrdbnet_arch import RRDBNet

    if "x2" in model_name:
        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
    else:
        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)

    upsampler = RealESRGANer(
        scale=scale,
        model_path=model_path,
        model=model,
        tile=400,
        tile_pad=10,
        pre_pad=0,
        half=half,
        device=device,
    )

    # Чтение и апскейл
    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Cannot read image: {input_path}")

    output, _ = upsampler.enhance(img, outscale=scale)
    cv2.imwrite(output_path, output)

    return output_path


def _upscale_pil(input_path: str, output_path: str, scale: int) -> str:
    """Апскейл через Pillow (базовое качество)."""
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow не установлен. Установите: pip install Pillow")

    img = Image.open(input_path)
    new_size = (img.width * scale, img.height * scale)

    # LANCZOS — лучший фильтр для апскейла
    upscaled = img.resize(new_size, Image.LANCZOS)
    upscaled.save(output_path, "PNG", quality=95)

    return output_path


def upscale_image_bytes(image_bytes: bytes, scale: int = 4, format: str = "PNG") -> bytes:
    """
    Апскейлит изображение из байтов.

    Args:
        image_bytes: байты изображения
        scale: коэффициент апскейла
        format: формат выходного изображения

    Returns:
        Байты апскейленного изображения
    """
    try:
        import io

        from PIL import Image
    except ImportError:
        raise ImportError("Pillow не установлен")

    img = Image.open(io.BytesIO(image_bytes))
    new_size = (img.width * scale, img.height * scale)
    upscaled = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    upscaled.save(buf, format=format, quality=95)
    return buf.getvalue()
