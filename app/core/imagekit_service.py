"""
ImageKit Service
────────────────
Handles uploading unknown face snapshots to ImageKit.io.

Falls back to local file storage if ImageKit credentials are not configured
(useful for local development without setting up ImageKit).

Usage:
    from app.core.imagekit_service import upload_unknown_face

    result = await upload_unknown_face(rgb_image, face_box)
    # result = {"url": "https://ik.imagekit.io/...", "file_id": "abc123"}
    # or {"url": None, "file_id": None} on failure
"""

import io
import logging
import os
from datetime import datetime
from typing import Optional, Tuple

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


def _crop_face(rgb_image: np.ndarray, face_box) -> Optional[bytes]:
    """
    Crop the face region from an RGB image, add padding, and return as JPEG bytes.
    Returns None if cropping fails.
    """
    try:
        x1, y1, x2, y2 = [int(c) for c in face_box]
        pad = 20
        h, w = rgb_image.shape[:2]
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)

        face_crop = rgb_image[y1:y2, x1:x2]
        if face_crop.shape[0] == 0 or face_crop.shape[1] == 0:
            return None

        bgr_crop = cv2.cvtColor(face_crop, cv2.COLOR_RGB2BGR)
        success, buffer = cv2.imencode(".jpg", bgr_crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            return None
        return buffer.tobytes()
    except Exception as e:
        logger.error(f"Face crop failed: {e}")
        return None


def _generate_filename() -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    return f"unknown_{ts}.jpg"


async def upload_unknown_face(
    rgb_image: np.ndarray,
    face_box,
) -> dict:
    """
    Upload an unknown face snapshot to ImageKit.

    Returns:
        {
            "url": "https://ik.imagekit.io/.../unknown_xxx.jpg",
            "file_id": "imagekit_file_id_string",
        }
        or {"url": None, "file_id": None} on failure.
    """
    jpeg_bytes = _crop_face(rgb_image, face_box)
    if not jpeg_bytes:
        return {"url": None, "file_id": None}

    # ── ImageKit upload ────────────────────────────────────────────────────────
    if settings.imagekit_configured:
        try:
            from imagekitio import ImageKit
            from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
            import base64

            ik = ImageKit(
                public_key=settings.IMAGEKIT_PUBLIC_KEY,
                private_key=settings.IMAGEKIT_PRIVATE_KEY,
                url_endpoint=settings.IMAGEKIT_URL_ENDPOINT,
            )

            filename = _generate_filename()
            b64_data = base64.b64encode(jpeg_bytes).decode("utf-8")

            options = UploadFileRequestOptions(
                folder=settings.IMAGEKIT_UPLOAD_FOLDER,
                is_private_file=False,
                use_unique_file_name=True,
            )

            response = ik.upload_file(
                file=f"data:image/jpeg;base64,{b64_data}",
                file_name=filename,
                options=options,
            )

            return {
                "url": response.url,
                "file_id": response.file_id,
            }

        except Exception as e:
            logger.error(f"ImageKit upload failed: {e}. Falling back to local storage.")

    # ── Fallback: local file storage ───────────────────────────────────────────
    try:
        os.makedirs(settings.UNKNOWN_FACES_DIR, exist_ok=True)
        filename = _generate_filename()
        filepath = os.path.join(settings.UNKNOWN_FACES_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(jpeg_bytes)
        logger.info(f"Saved unknown face locally: {filepath}")
        return {"url": filepath, "file_id": None}
    except Exception as e:
        logger.error(f"Local fallback save also failed: {e}")
        return {"url": None, "file_id": None}


async def delete_unknown_face(file_id: str) -> bool:
    """
    Delete an image from ImageKit by file ID.
    Called when an unknown face alert is resolved.
    Returns True on success.
    """
    if not settings.imagekit_configured or not file_id:
        return False
    try:
        from imagekitio import ImageKit

        ik = ImageKit(
            public_key=settings.IMAGEKIT_PUBLIC_KEY,
            private_key=settings.IMAGEKIT_PRIVATE_KEY,
            url_endpoint=settings.IMAGEKIT_URL_ENDPOINT,
        )
        ik.delete_file(file_id=file_id)
        return True
    except Exception as e:
        logger.error(f"ImageKit delete failed for file_id={file_id}: {e}")
        return False
