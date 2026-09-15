"""Photo handling.

Accept-any-image: whatever the driver gives us gets stored. Photos are proof
only - they are never rejected and never read by the app. We try hard to
normalise to a small JPEG (so 11 agents x 30 days of photos stay cheap), and if
a format cannot be decoded at all we keep the original bytes as-is.
"""
from __future__ import annotations

import base64
import io
from typing import Optional, Tuple

from . import config as C

# Optional HEIC/HEIF support. Photos now only ever arrive from st.camera_input,
# which hands over PNG/JPEG, so this is belt-and-braces rather than required -
# it is not in requirements.txt. Absent is fine.
try:  # pragma: no cover
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover
    pass


def _guess_mime(raw: bytes, fallback: str = "image/jpeg") -> str:
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[4:12] in (b"ftypheic", b"ftypheix", b"ftyphevc", b"ftypmif1"):
        return "image/heic"
    return fallback


def to_data_url(file_or_bytes) -> Optional[str]:
    """Normalise any uploaded/captured image to a base64 data URL.

    Returns None only when there is nothing to store.
    """
    if file_or_bytes is None:
        return None

    raw = file_or_bytes if isinstance(file_or_bytes, (bytes, bytearray)) else file_or_bytes.getvalue()
    raw = bytes(raw)
    if not raw:
        return None

    # Preferred path: decode, respect the phone's rotation flag, downscale, JPEG.
    try:
        from PIL import Image, ImageOps

        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((C.MAX_IMAGE_EDGE, C.MAX_IMAGE_EDGE), Image.LANCZOS)

        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=C.JPEG_QUALITY, optimize=True)
        out = buf.getvalue()

        # A tiny original (already compressed hard) beats our re-encode.
        if len(raw) < len(out) and _guess_mime(raw, "") == "image/jpeg":
            out = raw
        return "data:image/jpeg;base64," + base64.b64encode(out).decode("ascii")
    except Exception:
        pass

    # Fallback: keep the original bytes untouched.
    return "data:{};base64,{}".format(
        _guess_mime(raw), base64.b64encode(raw).decode("ascii")
    )


def decode(data_url: Optional[str]) -> Optional[bytes]:
    """data URL -> raw bytes, for handing to st.image()."""
    if not data_url or "base64," not in data_url:
        return None
    try:
        return base64.b64decode(data_url.split("base64,", 1)[1])
    except Exception:
        return None


def approx_size(data_url: Optional[str]) -> int:
    """Stored size in bytes, near enough for a 'photo too big' check."""
    if not data_url:
        return 0
    b64 = data_url.split("base64,", 1)[-1]
    return int(len(b64) * 3 / 4)


def too_big(data_url: Optional[str]) -> bool:
    return approx_size(data_url) > C.MAX_PHOTO_BYTES


def human_size(n: int) -> Tuple[str, str]:
    if n < 1024:
        return str(n), "B"
    if n < 1024 * 1024:
        return "{:.0f}".format(n / 1024), "KB"
    return "{:.1f}".format(n / 1024 / 1024), "MB"
