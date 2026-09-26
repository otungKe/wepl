"""
OcrEngine port — the image→text step, behind an interface so the rest of the
code (and tests) never depend on Tesseract being installed.

Adapters:
  TesseractEngine — real OCR via pytesseract + Pillow. Needs the `tesseract`
                    system binary (not present on Render's native Python runtime;
                    requires the Docker runtime — see ADR-0023 follow-up).
  NullOcrEngine   — returns '' — used automatically when no OCR backend is
                    available, so KYC degrades gracefully to manual review.
  FakeOcrEngine   — returns canned text; used by tests and local dev.

Selection (settings.OCR_ENGINE): 'tesseract' | 'null' | 'fake' | '' (auto).
Auto picks Tesseract when its binary is importable+callable, else Null.
"""
from __future__ import annotations

import io
import logging
from abc import ABC, abstractmethod
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)


class OcrEngine(ABC):
    name: str = "base"

    @abstractmethod
    def image_to_text(self, image: bytes) -> str:
        """Return the recognised text of an image given its raw bytes."""


class NullOcrEngine(OcrEngine):
    name = "null"

    def image_to_text(self, image: bytes) -> str:
        return ""


class FakeOcrEngine(OcrEngine):
    name = "fake"

    def __init__(self, text: str = ""):
        self._text = text

    def image_to_text(self, image: bytes) -> str:
        return self._text


class TesseractEngine(OcrEngine):
    name = "tesseract"

    def image_to_text(self, image: bytes) -> str:
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(io.BytesIO(image)))
        except Exception as exc:               # binary missing / unreadable image
            logger.warning("OCR failed (%s) — treating as unreadable.", exc)
            return ""


def _tesseract_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


_override: OcrEngine | None = None


@lru_cache(maxsize=None)
def _build(name: str) -> OcrEngine:
    if name == "tesseract":
        return TesseractEngine()
    if name == "null":
        return NullOcrEngine()
    if name == "fake":
        return FakeOcrEngine()
    raise ValueError(f"Unknown OCR_ENGINE: {name!r}")


def get_engine() -> OcrEngine:
    """Return the active OCR engine (test override wins)."""
    if _override is not None:
        return _override
    name = (getattr(settings, "OCR_ENGINE", "") or "").strip()
    if not name:
        name = "tesseract" if _tesseract_available() else "null"
    return _build(name)


def use_engine(engine: OcrEngine | None) -> None:
    """Install an engine override (tests/sandbox). Pass None to clear."""
    global _override
    _override = engine
