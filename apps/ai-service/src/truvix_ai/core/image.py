"""Image preparation utilities for AI consumption."""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError
import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """An image prepared for AI analysis."""
    data: bytes
    media_type: str


def prepare_for_vision(raw_bytes: bytes) -> PreparedImage | None:
    """
    Prepare raw image bytes for vision models.
    
    Validates format, resizes, strips EXIF, and converts to JPEG.
    Gracefully returns None if processing fails to avoid crashing.
    """
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            # Validate format
            if img.format not in {"JPEG", "PNG", "WEBP", "HEIC"}:
                logger.warning("unsupported_image_format", format=img.format)
                return None
                
            # Convert to RGB (drops alpha/transparency)
            if img.mode != "RGB":
                img = img.convert("RGB")
                
            # Strip EXIF by re-creating the image data
            data = list(img.getdata())
            img_no_exif = Image.new(img.mode, img.size)
            img_no_exif.putdata(data)
            
            # Resize if necessary (max 1024px on longest side)
            max_size = 1024
            if max(img_no_exif.size) > max_size:
                img_no_exif.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
            # Save to JPEG
            output = io.BytesIO()
            img_no_exif.save(output, format="JPEG", quality=80)
            
            return PreparedImage(data=output.getvalue(), media_type="image/jpeg")
            
    except UnidentifiedImageError:
        logger.warning("invalid_image_data")
        return None
    except Exception as e:
        logger.error("image_preparation_failed", error=str(e))
        return None
