from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image
from PyQt6.QtGui import QImage


def image_to_base64(image: Image.Image) -> str:
    """
    将 PIL 图片编码为 PNG 格式的 Base64 字符串。
    """
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def qimage_to_pil_image(qimage: QImage) -> Image.Image:
    """
    将 QImage 安全转换为 PIL.Image（RGB）。
    """
    if qimage.isNull():
        raise ValueError("剪贴板中的图片数据无效。")

    converted = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()

    ptr = converted.bits()
    buffer = ptr.asstring(bytes_per_line * height)

    return Image.frombuffer(
        "RGBA",
        (width, height),
        buffer,
        "raw",
        "RGBA",
        bytes_per_line,
        1,
    ).convert("RGB")
