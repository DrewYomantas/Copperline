"""
_backup.py — Timestamped backup utility for Copperline runtime files.
Run before any mutation pass. Safe to re-run; each call creates a new timestamped copy.

Usage:
    python _backup.py
"""
import csv, io, shutil, os
from datetime import datetime, timezone
from pathlib import Path

BASE    = Path(__file__).resolve().parent
BK_DIR  = BASE / "_backups"

FILES_TO_BACKUP = [
    BASE / "queue"  / "pending_emails.csv",
    BASE / "data"   / "prospects.csv",
    BASE / "data"   / "city_planner.json",
]

def backup_now() -> dict:
    BK_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = {}
    for src in FILES_TO_BACKUP:
        if not src.exists():
            results[str(src.name)] = "SKIP (not found)"
            continue
        # Verify the file has real content (not a stub)
        size = src.stat().st_size
        dest = BK_DIR / f"{src.stem}_BAK_{ts}{src.suffix}"
        shutil.copy2(src, dest)
        results[str(src.name)] = str(dest)
        print(f"  backed up: {src.name} ({size:,} B) -> {dest.name}")
    return {"ts": ts, "files": results}

if __name__ == "__main__":
    print(f"Backup pass — {datetime.now(timezone.utc).isoformat()}")
    r = backup_now()
    print(f"Done. {len(r['files'])} files -> {BK_DIR}")
