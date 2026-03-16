from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List


class CityPlanner:
    def __init__(self, store_file: str | Path):
        self.store_file = Path(store_file)
        self._data: List[Dict] = []
        self._load()

    def _load(self) -> None:
        if not self.store_file.exists():
            self._data = []
            return
        try:
            self._data = json.loads(self.store_file.read_text(encoding="utf-8"))
            if not isinstance(self._data, list):
                self._data = []
        except Exception:
            self._data = []

    def _save(self) -> None:
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self.store_file.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def _find(self, city: str, state: str):
        c = (city or "").strip().lower()
        s = (state or "").strip().upper()
        for e in self._data:
            if (e.get("city", "").strip().lower() == c and e.get("state", "").strip().upper() == s):
                return e
        return None

    def ensure_city(self, city: str, state: str, tier: str = "mid") -> Dict:
        entry = self._find(city, state)
        if entry:
            if tier:
                entry["tier"] = tier
            return entry
        entry = {
            "city": city.strip(),
            "state": state.strip().upper(),
            "tier": tier or "mid",
            "last_checked_at": None,
            "next_check_at": None,
            "leads_found": 0,
            "industries": {},
        }
        self._data.append(entry)
        self._save()
        return entry

    def all_cities(self) -> List[Dict]:
        return self._data

    def skip_city(self, city: str, state: str) -> None:
        e = self.ensure_city(city, state)
        e["next_check_at"] = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        self._save()

    def set_tier(self, city: str, state: str, tier: str) -> None:
        e = self.ensure_city(city, state)
        e["tier"] = tier
        self._save()

    def tiers_info(self) -> Dict:
        return {"tiers": ["high", "mid", "low"], "default": "mid"}

    def suggest(self, state: str, q: str, limit: int = 30) -> List[Dict]:
        state_u = (state or "").strip().upper()
        ql = (q or "").strip().lower()
        out = [e for e in self._data if (not state_u or e.get("state", "").upper() == state_u)]
        if ql:
            out = [e for e in out if ql in e.get("city", "").lower()]
        return out[: max(1, int(limit or 30))]

    def record_discovery(self, city: str, state: str, found: int, industry: str = "") -> None:
        e = self.ensure_city(city, state)
        now = datetime.now(timezone.utc).isoformat()
        e["last_checked_at"] = now
        e["next_check_at"] = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        e["leads_found"] = int(e.get("leads_found", 0) or 0) + int(found or 0)
        if industry:
            ind = e.setdefault("industries", {}).setdefault(industry, {
                "leads_found": 0, "last_checked_at": None, "new_leads_last_run": 0, "status": "never_checked"
            })
            ind["last_checked_at"] = now
            ind["new_leads_last_run"] = int(found or 0)
            ind["leads_found"] = int(ind.get("leads_found", 0) or 0) + int(found or 0)
            ind["status"] = "checked"
        self._save()

    def get_industry_matrix(self, industries: List[str]) -> List[Dict]:
        rows = []
        for e in self._data:
            inds = e.get("industries", {})
            industry_rows = []
            covered_count = 0
            never_count = 0
            due_count = 0
            for ind in industries:
                meta = inds.get(ind, {"leads_found": 0, "last_checked_at": None, "new_leads_last_run": 0, "status": "never_checked"})
                status = meta.get("status") or "never_checked"
                if status == "checked":
                    covered_count += 1
                if status == "never_checked":
                    never_count += 1
                if status == "due":
                    due_count += 1
                industry_rows.append({
                    "industry": ind,
                    "status": status,
                    "leads_found": int(meta.get("leads_found", 0) or 0),
                    "last_checked_at": meta.get("last_checked_at"),
                    "new_leads_last_run": int(meta.get("new_leads_last_run", 0) or 0),
                })
            rows.append({
                "city": e.get("city", ""),
                "state": e.get("state", ""),
                "tier": e.get("tier", "mid"),
                "last_checked_at": e.get("last_checked_at"),
                "next_check_at": e.get("next_check_at"),
                "leads_found": int(e.get("leads_found", 0) or 0),
                "industry_rows": industry_rows,
                "total_industries": len(industries),
                "covered_count": covered_count,
                "never_count": never_count,
                "due_count": due_count,
                "city_is_due": due_count > 0,
            })
        return rows
