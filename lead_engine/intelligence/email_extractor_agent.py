from __future__ import annotations

from pathlib import Path
from typing import Dict


def enrich_prospects_with_emails(csv_path: str | Path, limit: int = 0, overwrite: bool = False) -> Dict[str, int]:
    """Compatibility stub until email extractor is restored."""
    return {
        "processed": 0,
        "updated": 0,
        "skipped": 0,
        "limit": int(limit or 0),
        "overwrite": 1 if overwrite else 0,
    }
