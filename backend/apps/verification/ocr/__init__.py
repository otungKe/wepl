"""
In-house OCR for KYC ID scans (advisory, no vendor).

`run_id_ocr(image_bytes, id_number=, date_of_birth=)` runs the active OcrEngine
over an ID scan, detects whether it's a Kenyan national ID, extracts fields, and
cross-checks them against the applicant's typed values. The result is advisory —
stored on the KYC row to speed up human review and flag mismatches; it never
decides approval on its own. Degrades to `{"detected": False, ...}` when no OCR
backend is available.
"""
from __future__ import annotations

from .engine import get_engine, use_engine  # noqa: F401 (re-exported)
from .kenyan_id import KenyanIdScan, cross_check, parse_kenyan_id  # noqa: F401


def run_id_ocr(image: bytes, *, id_number: str = "", date_of_birth: str = "") -> dict:
    """Read an ID scan and cross-check it against typed values. Never raises."""
    if not image:
        return {"detected": False, "marker_hits": 0, "id_number_read": None,
                "id_number_match": None, "dob_read": None, "dob_match": None,
                "mismatch": False, "engine": "none"}
    engine = get_engine()
    text = engine.image_to_text(image)
    scan = parse_kenyan_id(text)
    result = cross_check(scan, id_number=id_number, date_of_birth=date_of_birth)
    result["engine"] = engine.name
    return result
