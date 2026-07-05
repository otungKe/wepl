"""
Kenyan national-ID text parser + detector.

Pure text processing — takes the raw OCR string of an ID scan and (a) decides
whether it looks like a Kenyan national ID and (b) extracts the fields we can
cross-check against what the applicant typed. No image/OCR engine dependency
here, so this is fully unit-testable without Tesseract installed.

Kenyan second-generation IDs carry labelled fields on the front:
    JAMHURI YA KENYA / REPUBLIC OF KENYA · SERIAL NUMBER · ID NUMBER (8 digits)
    FULL NAMES · DATE OF BIRTH (dd.mm.yyyy) · SEX · DISTRICT OF BIRTH · ...
Extraction is best-effort and advisory — it assists a human reviewer and flags
typos/mismatches; it is never the authority on approval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Tokens that strongly indicate a Kenyan ID. Matched case-insensitively and
# tolerant of OCR spacing noise.
_KENYA_MARKERS = [
    "JAMHURI YA KENYA",
    "REPUBLIC OF KENYA",
    "SERIAL NUMBER",
    "ID NUMBER",
    "FULL NAMES",
    "DATE OF BIRTH",
    "DISTRICT OF BIRTH",
    "PLACE OF ISSUE",
    "HUDUMA",
]

# 7–8 digit national ID number (older IDs are 7, current are 8).
_ID_NUMBER_RE = re.compile(r"\b(\d{7,8})\b")
# dd.mm.yyyy / dd/mm/yyyy / dd-mm-yyyy
_DOB_RE = re.compile(r"\b([0-3]?\d)[.\-/]([01]?\d)[.\-/](\d{4})\b")


def _norm(text: str) -> str:
    """Uppercase and collapse whitespace for tolerant marker matching."""
    return re.sub(r"\s+", " ", (text or "").upper())


@dataclass(frozen=True)
class KenyanIdScan:
    is_kenyan_id:  bool
    marker_hits:   int
    id_number:     str | None = None
    date_of_birth: str | None = None          # normalised ISO yyyy-mm-dd when parseable
    raw_text:      str = ""

    def as_dict(self) -> dict:
        return {
            "is_kenyan_id":  self.is_kenyan_id,
            "marker_hits":   self.marker_hits,
            "id_number":     self.id_number,
            "date_of_birth": self.date_of_birth,
        }


def parse_kenyan_id(text: str) -> KenyanIdScan:
    """Parse raw OCR text of an ID scan into a KenyanIdScan."""
    norm = _norm(text)

    hits = sum(1 for m in _KENYA_MARKERS if m in norm)
    is_id = hits >= 2   # two independent markers → confident it's a Kenyan ID

    id_number = None
    m = _ID_NUMBER_RE.search(norm)
    if m:
        id_number = m.group(1)

    dob = None
    d = _DOB_RE.search(norm)
    if d:
        day, month, year = d.group(1), d.group(2), d.group(3)
        dob = f"{year}-{int(month):02d}-{int(day):02d}"

    return KenyanIdScan(
        is_kenyan_id=is_id,
        marker_hits=hits,
        id_number=id_number,
        date_of_birth=dob,
        raw_text=text or "",
    )


def cross_check(
    scan: KenyanIdScan,
    *,
    id_number: str = "",
    date_of_birth: str = "",
) -> dict:
    """Compare a scan against the applicant's typed values. Returns an advisory
    dict (stored on the KYC row) — a ``False`` match flags a mismatch for the
    reviewer; ``None`` means the field could not be read from the scan."""
    id_match = None
    if scan.id_number is not None and id_number:
        id_match = scan.id_number == re.sub(r"\D", "", id_number)

    dob_match = None
    if scan.date_of_birth is not None and date_of_birth:
        dob_match = scan.date_of_birth == date_of_birth

    return {
        "detected":        scan.is_kenyan_id,
        "marker_hits":     scan.marker_hits,
        "id_number_read":  scan.id_number,
        "id_number_match": id_match,
        "dob_read":        scan.date_of_birth,
        "dob_match":       dob_match,
        # True only when something we could read disagrees with the typed value.
        "mismatch":        id_match is False or dob_match is False,
    }
