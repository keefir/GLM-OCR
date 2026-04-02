"""Markdown processing utilities."""

import ast
import base64
import io
import re
from pathlib import Path
from typing import List, Tuple

from PIL import Image
from glmocr.utils.image_utils import (
    crop_image_region,
    pdf_to_images_pil,
    PYPDFIUM2_AVAILABLE,
)
from glmocr.utils.logging import get_logger

logger = get_logger(__name__)


def extract_image_refs(markdown_text: str) -> List[Tuple[int, List[int], str]]:
    """Extract image references from Markdown.

    Args:
        markdown_text: Markdown text.

    Returns:
        List of (page_idx, bbox, original_tag).
    """
    # Pattern: ![](page=0,bbox=[57, 199, 884, 444])
    pattern = r"!\[\]\(page=(\d+),bbox=(\[[\d,\s]+\])\)"
    matches = re.finditer(pattern, markdown_text)

    image_refs = []
    for match in matches:
        page_idx = int(match.group(1))
        bbox_str = match.group(2)
        # Parse bbox string safely
        try:
            bbox = ast.literal_eval(bbox_str)
            if not isinstance(bbox, list) or len(bbox) != 4:
                raise ValueError(f"Invalid bbox format: {bbox_str}")
        except (ValueError, SyntaxError) as e:
            logger.warning("Cannot parse bbox %s: %s", bbox_str, e)
            continue
        original_tag = match.group(0)
        image_refs.append((page_idx, bbox, original_tag))

    return image_refs


def crop_and_embed_images_base64(
    markdown_text: str,
    original_images: List[str],
) -> str:
    """Crop referenced image regions and embed them as base64 in Markdown tags.

    Args:
        markdown_text: Source Markdown.
        original_images: Original image paths.

    Returns:
        updated_markdown
    """
    # Extract image references
    image_refs = extract_image_refs(markdown_text)

    if not image_refs:
        # No image references
        return markdown_text

    required_pages = {page_idx for page_idx, _, _ in image_refs}

    # Load originals (supports PDFs) - load ONLY required pages
    loaded_images = {}
    try:
        for img_path in original_images:
            path = Path(img_path)
            suffix = path.suffix.lower()

            if suffix == ".pdf":
                # PDF: convert to images (pypdfium2 only)
                if not PYPDFIUM2_AVAILABLE:
                    raise RuntimeError(
                        "PDF support requires pypdfium2. Install: pip install pypdfium2"
                    )
                try:
                    import pypdfium2 as pdfium
                    from glmocr.utils.image_utils import _page_to_image
                    pdf = pdfium.PdfDocument(img_path)
                    for req_page in required_pages:
                        if 0 <= req_page < len(pdf):
                            page = pdf[req_page]
                            try:
                                image, _ = _page_to_image(page, dpi=200, max_width_or_height=3500)
                                loaded_images[req_page] = image
                            finally:
                                page.close()
                    pdf.close()
                except Exception as e:
                    logger.warning(f"Failed to convert required PDF pages: {e}")
            else:
                # Normal image file
                with Image.open(img_path) as img:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    loaded_images[0] = img.copy()

        # Process each reference
        result_markdown = markdown_text

        for idx, (page_idx, bbox, original_tag) in enumerate(image_refs):
            # Validate page index
            if page_idx not in loaded_images:
                logger.warning(
                    "page_idx %d out of range or not loaded, skipping",
                    page_idx,
                )
                continue

            # Crop from original
            original_image = loaded_images[page_idx]
            cropped_image = None
            try:
                cropped_image = crop_image_region(original_image, bbox)

                buffer = io.BytesIO()
                cropped_image.save(buffer, format="JPEG", quality=95)
                b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

                # Replace Markdown image tag with a base64 data URI
                new_tag = f"![Image {page_idx}-{idx}](data:image/jpeg;base64,{b64_str})"
                result_markdown = result_markdown.replace(original_tag, new_tag, 1)

            except Exception as e:
                logger.warning("Failed to crop and embed image %d: %s", idx, e)
            finally:
                if cropped_image is not None:
                    try:
                        cropped_image.close()
                    except Exception:
                        pass
    finally:
        for img in loaded_images.values():
            try:
                img.close()
            except Exception:
                pass

    return result_markdown
