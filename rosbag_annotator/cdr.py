"""
CDR image parsing and decoding.

Priority: rclpy (official) > hand-written CDR parser (fallback)
Returns QImage (thread-safe). QPixmap conversion must happen in the main thread.
"""
from __future__ import annotations
import struct
from typing import Optional, Tuple

_THUMB_W = 320
_THUMB_H  = 240

# ── optional heavy deps ────────────────────────────────────────────────────────
try:
    import numpy as np
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("[WARN] opencv/numpy not found — image preview disabled")

try:
    from rclpy.serialization import deserialize_message as _rclpy_deser
    HAS_RCLPY_DESER = True
except ImportError:
    HAS_RCLPY_DESER = False

from PyQt6.QtGui import QImage


# ── CDR alignment helper ───────────────────────────────────────────────────────

def _al(o: int, n: int) -> int:
    return (o + n - 1) & ~(n - 1)


# ── hand-written CDR parsers ───────────────────────────────────────────────────

def _parse_image_cdr(raw: bytes) -> Optional[Tuple]:
    """sensor_msgs/msg/Image → (h, w, encoding, pixel_bytes)"""
    try:
        e = '<' if (len(raw) > 1 and raw[1] == 0x01) else '>'
        o = 4
        o = _al(o, 4); o += 8                               # stamp
        slen = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4
        o += slen                                            # frame_id
        o = _al(o, 4)
        h = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4
        w = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4
        slen = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4
        enc = raw[o:o+slen-1].decode("utf-8", errors="ignore"); o += slen
        o += 1                                               # is_bigendian (uint8, no align)
        o = _al(o, 4)
        o += 4                                               # step
        dlen = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4
        if h == 0 or w == 0 or dlen == 0: return None
        return h, w, enc, raw[o:o+dlen]
    except Exception:
        return None


def _parse_compressed_cdr(raw: bytes) -> Optional[Tuple]:
    """sensor_msgs/msg/CompressedImage → (format, compressed_bytes)"""
    try:
        e = '<' if (len(raw) > 1 and raw[1] == 0x01) else '>'
        o = 4
        o = _al(o, 4); o += 8
        slen = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4; o += slen
        o = _al(o, 4)
        slen = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4
        fmt = raw[o:o+slen-1].decode("utf-8", errors="ignore"); o += slen
        o = _al(o, 4)
        dlen = struct.unpack_from(f'{e}I', raw, o)[0]; o += 4
        return fmt, raw[o:o+dlen]
    except Exception:
        return None


# ── bgr conversion helpers ─────────────────────────────────────────────────────

def _enc_to_bgr(arr, h: int, w: int, enc: str):
    """numpy array + encoding → BGR ndarray, or None if unknown."""
    enc = enc.lower()
    if enc in ("mono8", "8uc1"):
        return cv2.cvtColor(arr.reshape(h, w), cv2.COLOR_GRAY2BGR)
    elif enc == "rgb8":
        return cv2.cvtColor(arr.reshape(h, w, 3), cv2.COLOR_RGB2BGR)
    elif enc in ("bgr8", "8uc3"):
        return arr.reshape(h, w, 3).copy()
    elif enc == "bgra8":
        return cv2.cvtColor(arr.reshape(h, w, 4), cv2.COLOR_BGRA2BGR)
    elif enc == "rgba8":
        return cv2.cvtColor(arr.reshape(h, w, 4), cv2.COLOR_RGBA2BGR)
    elif enc in ("mono16", "16uc1"):
        d16 = arr.view(np.uint16).reshape(h, w)
        return cv2.cvtColor(
            cv2.normalize(d16, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U),
            cv2.COLOR_GRAY2BGR)
    return None


def _bgr_via_rclpy(data: bytes, topic_type: str):
    try:
        if "CompressedImage" in topic_type:
            from sensor_msgs.msg import CompressedImage
            msg = _rclpy_deser(data, CompressedImage)
            arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            from sensor_msgs.msg import Image
            msg = _rclpy_deser(data, Image)
            arr = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            return _enc_to_bgr(arr, msg.height, msg.width, msg.encoding)
    except Exception:
        return None


def _bgr_via_cdr(data: bytes, topic_type: str):
    try:
        if "CompressedImage" in topic_type:
            res = _parse_compressed_cdr(data)
            if res:
                arr = np.frombuffer(res[1], dtype=np.uint8)
                return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            res = _parse_image_cdr(data)
            if res:
                h, w, enc, img_bytes = res
                if h == 0 or w == 0 or not img_bytes: return None
                arr = np.frombuffer(img_bytes, dtype=np.uint8)
                return _enc_to_bgr(arr, h, w, enc)
    except Exception:
        return None


# ── public API ─────────────────────────────────────────────────────────────────

def raw_to_image(data: bytes, topic_type: str) -> Optional[QImage]:
    """
    Raw CDR bytes → QImage (thread-safe).
    QPixmap conversion must be done in the main GUI thread.
    """
    if not HAS_CV2:
        return None
    bgr = (_bgr_via_rclpy(data, topic_type) if HAS_RCLPY_DESER
           else _bgr_via_cdr(data, topic_type))
    if bgr is None:
        return None
    ih, iw = bgr.shape[:2]
    scale = min(_THUMB_W / iw, _THUMB_H / ih, 1.0)
    if scale < 1.0:
        bgr = cv2.resize(bgr, (int(iw * scale), int(ih * scale)),
                         interpolation=cv2.INTER_AREA)
    h2, w2 = bgr.shape[:2]
    return QImage(bgr.data, w2, h2, w2 * 3, QImage.Format.Format_BGR888).copy()


def extract_header_stamp_ns(blob: bytes) -> int:
    """
    Quickly extract header.stamp from a CDR message blob.
    Returns absolute nanoseconds, or -1 on failure.
    """
    try:
        e = '<' if (len(blob) > 1 and blob[1] == 0x01) else '>'
        o = (4 + 3) & ~3   # CDR header (4B) then align4
        sec     = struct.unpack_from(f'{e}i', blob, o)[0]
        nanosec = struct.unpack_from(f'{e}I', blob, o + 4)[0]
        if sec < 0 or sec > 4_000_000_000:
            return -1
        return sec * 1_000_000_000 + nanosec
    except Exception:
        return -1
