"""
Model-Agnostic Vision Grounding & Coordinate Adapter for Taskmaster.

Provides:
- Multi-model coordinate conversion (normalized_1000, normalized_1, absolute_pixel)
- Set-of-Marks (SoM) visual badge rendering on screenshots
- Base64 screenshot encoding/decoding
"""

import base64
import io
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("taskmaster.browser.vision")

CoordinateConvention = Literal["normalized_1000", "normalized_1", "absolute_pixel"]


class VisionGrounding:
    """Handles screenshot manipulation, Set-of-Marks annotations, and coordinate transformations."""

    @staticmethod
    def denormalize_coordinates(
        x: float,
        y: float,
        viewport_width: int,
        viewport_height: int,
        convention: CoordinateConvention = "normalized_1000",
    ) -> Tuple[int, int]:
        """
        Converts model output coordinates into actual screen pixel coordinates (px, py).
        
        Conventions:
        - 'normalized_1000': 0 to 1000 integer grid (e.g. Gemini Multimodal Vision)
        - 'normalized_1': 0.0 to 1.0 float grid
        - 'absolute_pixel': Direct screen pixel coordinates
        """
        if convention == "normalized_1000":
            px = int((x / 1000.0) * viewport_width)
            py = int((y / 1000.0) * viewport_height)
        elif convention == "normalized_1":
            px = int(x * viewport_width)
            py = int(y * viewport_height)
        elif convention == "absolute_pixel":
            px = int(x)
            py = int(y)
        else:
            raise ValueError(f"Unknown coordinate convention: {convention}")

        # Clamp within viewport
        px = max(0, min(viewport_width - 1, px))
        py = max(0, min(viewport_height - 1, py))
        return px, py

    @staticmethod
    def normalize_coordinates(
        px: int,
        py: int,
        viewport_width: int,
        viewport_height: int,
        convention: CoordinateConvention = "normalized_1000",
    ) -> Tuple[float, float]:
        """Converts screen pixel coordinates into model-requested representation."""
        if convention == "normalized_1000":
            return (round((px / viewport_width) * 1000, 1), round((py / viewport_height) * 1000, 1))
        elif convention == "normalized_1":
            return (round(px / viewport_width, 4), round(py / viewport_height, 4))
        elif convention == "absolute_pixel":
            return float(px), float(py)
        else:
            raise ValueError(f"Unknown coordinate convention: {convention}")

    @staticmethod
    def render_set_of_marks(
        screenshot_bytes: bytes,
        elements: List[Dict[str, Any]],
        highlight_color: str = "#FF0055",
        badge_bg_color: str = "#FFE600",
    ) -> Tuple[bytes, str]:
        """
        Draws high-contrast Set-of-Marks (SoM) numeric badges and bounding boxes over interactable elements.
        Returns: (annotated_bytes, base64_str)
        """
        try:
            image = Image.open(io.BytesIO(screenshot_bytes)).convert("RGBA")
            overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)

            # Attempt to load a default font
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

            for el in elements:
                box = el.get("box")
                ref = el.get("ref", "")
                if not box or box.get("width", 0) <= 0 or box.get("height", 0) <= 0:
                    continue

                x, y, w, h = box["x"], box["y"], box["width"], box["height"]

                # Draw bounding box rectangle
                draw.rectangle([x, y, x + w, y + h], outline=highlight_color, width=2)

                # Draw numeric badge tag [e1]
                badge_text = f" {ref} "
                badge_x = max(0, x)
                badge_y = max(0, y - 14)

                # Badge background pill
                draw.rectangle([badge_x, badge_y, badge_x + 30, badge_y + 14], fill=badge_bg_color, outline="#000000", width=1)
                draw.text((badge_x + 2, badge_y + 1), badge_text, fill="#000000", font=font)

            # Alpha composite overlay
            final_image = Image.alpha_composite(image, overlay).convert("RGB")
            
            output_buffer = io.BytesIO()
            final_image.save(output_buffer, format="JPEG", quality=85)
            annotated_bytes = output_buffer.getvalue()
            base64_str = base64.b64encode(annotated_bytes).decode("utf-8")
            return annotated_bytes, base64_str

        except Exception as e:
            logger.warning(f"Failed to render Set-of-Marks overlay: {e}", exc_info=True)
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            return screenshot_bytes, b64
