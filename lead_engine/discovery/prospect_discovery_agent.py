from __future__ import annotations

import csv
import re
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

REQUIRED_INPUT_COLUMNS = ["business_name", "city", "state"]
ALL_COLUMNS = [
    "business_name",
    "city",
    "state",
    "website",
    "phone",
    "contact_method",
    "likely_opportunity",
    "priority_score",
]

BLANK_LIKE_VALUES = {"", "unknown", "n/a", "na", "none", "null", "-", "--"}
DEFAULT_CITY_ROTATION = [
    ("Chicago", "IL"),
    ("Dallas", "TX"),
    ("Phoenix", "AZ"),
    ("Atlanta", "GA"),
    ("Denver", "CO"),
]


def normalize_value(value: str | None) -> str:
    text = (value or "").strip()
    return "" if text.lower() in BLANK_LIKE_VALUES else text


def normalize_identity_token(value: str | None) -> str:
    return " ".join(normalize_value(value).lower().split())


def dedupe_key_for_prospect(row: Dict[str, str]) -> Tuple[str, str]:
    """Primary key: business_name + website; fallback: business_name + city."""
    business_name = normalize_identity_token(row.get("business_name", ""))
    website = normalize_identity_token(row.get("website", ""))
    city = normalize_identity_token(row.get("city", ""))

    if website:
        return business_name, website
    return business_name, city


def _normalize_header(name: str) -> str:
    return (name or "").strip().lower()


def load_prospects_from_csv(csv_path: str | Path) -> List[Dict[str, str]]:
    """Load and normalize prospects from CSV, skipping invalid rows."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Prospect file not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Prospect CSV must include a header row.")

        normalized_header = [_normalize_header(name) for name in reader.fieldnames]
        missing_required_columns = [
            column for column in REQUIRED_INPUT_COLUMNS if column not in normalized_header
        ]
        if missing_required_columns:
            raise ValueError(
                "Prospect CSV missing required columns: " + ", ".join(missing_required_columns)
            )

        header_map = {
            raw_name: _normalize_header(raw_name)
            for raw_name in reader.fieldnames
            if _normalize_header(raw_name)
        }

        prospects: List[Dict[str, str]] = []
        skipped_invalid = 0

        for row in reader:
            normalized_row = {column: "" for column in ALL_COLUMNS}

            for raw_key, raw_value in row.items():
                key = header_map.get(raw_key, "")
                if key in normalized_row:
                    normalized_row[key] = normalize_value(raw_value)

            if not normalized_row["business_name"] or not normalized_row["city"] or not normalized_row["state"]:
                skipped_invalid += 1
                continue

            prospects.append(normalized_row)

    if skipped_invalid:
        print(f"Skipped {skipped_invalid} prospect rows missing required values (business_name/city/state).")

    return prospects


def _load_keys_from_csv(path: str | Path) -> Set[Tuple[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return set()

    keys: Set[Tuple[str, str]] = set()
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return set()
        for row in reader:
            keys.add(dedupe_key_for_prospect(row))
    return keys


def _parse_city_seed(seed_city: str | None) -> Tuple[str, str] | None:
    if not seed_city:
        return None
    raw = seed_city.strip()
    if not raw:
        return None
    if "," in raw:
        city, state = [part.strip() for part in raw.split(",", 1)]
        return city, state
    return raw, ""


def _discover_with_playwright(industry: str, city: str, state: str, timeout_seconds: int = 10) -> List[Dict[str, str]]:
    """Try browser-driven discovery if Playwright is available; return [] on any issue."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("[discovery] Playwright unavailable; falling back to HTTP discovery.")
        return []

    query = f"{industry} {city} {state}".strip()
    search_url = f"https://duckduckgo.com/?q={quote_plus(query)}&ia=web"
    found: List[Dict[str, str]] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(search_url, timeout=timeout_seconds * 1000)
            page.wait_for_timeout(1200)

            anchors = page.query_selector_all("a[data-testid='result-title-a'], a.result__a")
            for anchor in anchors[:25]:
                title = normalize_value(anchor.inner_text())
                href = normalize_value(anchor.get_attribute("href") or "")
                if not title or not href:
                    continue
                if href.startswith("/") or "duckduckgo.com" in href:
                    continue

                found.append(
                    {
                        "business_name": title,
                        "city": city,
                        "state": state,
                        "website": href,
                        "phone": "",
                        "contact_method": "website",
                        "likely_opportunity": "",
                        "priority_score": "",
                    }
                )
            browser.close()
    except Exception as exc:
        print(f"[discovery warning] Playwright discovery failed for {query}: {exc}")
        return []

    return found


def _discover_with_http(industry: str, city: str, state: str, timeout_seconds: int = 6) -> List[Dict[str, str]]:
    query = f"{industry} {city} {state}".strip()
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    results: List[Dict[str, str]] = []

    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; LeadEngineBot/1.0)"})
        with urlopen(request, timeout=timeout_seconds) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"[discovery warning] HTTP discovery failed for {query}: {exc}")
        return []

    for match in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title_html = match.group("title")
        title = normalize_value(re.sub(r"<[^>]+>", "", title_html))
        website = normalize_value(match.group("href"))
        if not title or not website:
            continue
        if website.startswith("/") or "duckduckgo.com" in website:
            continue

        results.append(
            {
                "business_name": title,
                "city": city,
                "state": state,
                "website": website,
                "phone": "",
                "contact_method": "website",
                "likely_opportunity": "",
                "priority_score": "",
            }
        )

    return results


def discover_prospects_by_industry(
    industry: str,
    limit: int = 30,
    seed_city: str | None = None,
    existing_prospects_csv: str | Path = "lead_engine/data/prospects.csv",
    pending_queue_csv: str | Path = "lead_engine/queue/pending_emails.csv",
    contact_history_csv: str | Path = "lead_engine/data/contact_history.csv",
    timeout_seconds: int = 6,
) -> List[Dict[str, str]]:
    """Deterministic, bounded discovery with Playwright-first fallback to HTTP (safe failure)."""
    if not industry.strip() or limit <= 0:
        return []

    existing_keys = _load_keys_from_csv(existing_prospects_csv)
    queue_keys = _load_keys_from_csv(pending_queue_csv)
    history_keys = _load_keys_from_csv(contact_history_csv)

    city_targets: List[Tuple[str, str]] = []
    parsed_seed = _parse_city_seed(seed_city)
    if parsed_seed:
        city_targets.append(parsed_seed)
    else:
        city_targets.extend(DEFAULT_CITY_ROTATION)

    results: List[Dict[str, str]] = []
    seen_keys: Set[Tuple[str, str]] = set()

    for city, state in city_targets:
        if len(results) >= limit:
            break

        browser_rows = _discover_with_playwright(industry, city, state, timeout_seconds=timeout_seconds)
        rows = browser_rows if browser_rows else _discover_with_http(industry, city, state, timeout_seconds=timeout_seconds)

        for prospect in rows:
            if len(results) >= limit:
                break

            key = dedupe_key_for_prospect(prospect)
            if key in seen_keys or key in existing_keys or key in queue_keys or key in history_keys:
                continue

            seen_keys.add(key)
            results.append(prospect)

        time.sleep(0.35)

    print(f"Discovered {len(results)} prospects for industry={industry}.")
    return results
