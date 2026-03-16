from __future__ import annotations

import re
from html import unescape
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT_SECONDS = 6
MAX_PAGES_TO_SCAN = 6

PHONE_REGEX = re.compile(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")
EMAIL_REGEX = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")

CHAT_VENDOR_TOKENS = [
    "intercom",
    "drift",
    "zendesk",
    "tawk.to",
    "livechat",
    "hubspot",
    "freshchat",
    "olark",
    "tidio",
    "crisp.chat",
    "liveagent",
]

# Facebook Messenger plugin tokens
FB_MESSENGER_TOKENS = [
    "fb-messenger",
    "facebook-messenger",
    "fb-customerchat",
    "customer_chat",
    "m.me/",
    "messenger.com/t/",
    "connect.facebook.net",
]

# "Call Now" button patterns
CALL_NOW_TOKENS = [
    "call now",
    "call us now",
    "call today",
    "click to call",
    "tap to call",
    "tel:",
]

# Online scheduling / appointment tool tokens
SCHEDULING_TOOL_TOKENS = [
    "calendly",
    "acuityscheduling",
    "square appointments",
    "squareup.com",
    "schedulicity",
    "setmore",
    "booksy",
    "vagaro",
    "mindbody",
    "timely",
    "fresha",
    "picktime",
    "simplybook",
    "10to8",
    "appointy",
]

BOOKING_KEYWORDS = [
    "book now",
    "schedule service",
    "schedule appointment",
    "online booking",
    "request appointment",
]

REQUEST_QUOTE_KEYWORDS = ["request quote", "get quote", "free estimate", "request estimate"]
SCHEDULE_SERVICE_KEYWORDS = ["schedule service", "request service", "book now", "request appointment"]
FORM_HINTS = ["contact", "quote", "service", "appointment", "name", "email", "phone"]

LIKELY_PATHS = [
    "/contact",
    "/contact-us",
    "/request-service",
    "/schedule-service",
    "/services",
]


def _is_valid_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_internal_links(base_url: str, html: str) -> List[str]:
    links: List[str] = []
    base_host = (urlparse(base_url).netloc or "").lower()

    for match in re.findall(r'href=["\']([^"\'#]+)', html, flags=re.IGNORECASE):
        absolute = urljoin(base_url, match.strip())
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() != base_host:
            continue

        path = (parsed.path or "").lower()
        if any(token in path for token in ["contact", "service", "schedule", "quote", "book", "appointment"]):
            links.append(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")

    return links


def _fetch_html(url: str, timeout_seconds: int) -> str:
    request = Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; LeadEngineBot/1.0)"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="ignore")


def _detect_contact_form(html_lower: str) -> bool:
    if "<form" not in html_lower:
        return False
    for chunk in re.findall(r"<form[\s\S]{0,4000}?</form>", html_lower):
        if any(hint in chunk for hint in FORM_HINTS):
            return True
    return "contact-form" in html_lower or "wpforms" in html_lower or "gravityforms" in html_lower


def _strip_html(html: str) -> str:
    no_script = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    no_style = re.sub(r"<style[\s\S]*?</style>", " ", no_script, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", no_style)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def scan_website(website_url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, object]:
    """Deterministic bounded multi-page scan for service-site conversion signals."""
    result: Dict[str, object] = {
        "website_reachable": False,
        "scanned_urls": [],
        "has_contact_form": False,
        "has_email_visible": False,
        "has_phone_visible": False,
        "has_chat_widget": False,
        "has_fb_messenger": False,
        "has_call_now_button": False,
        "has_online_booking_keywords": False,
        "has_scheduling_tool": False,
        "has_request_quote_cta": False,
        "has_schedule_service_cta": False,
        "mobile_friendly_hint": False,
        "weak_website_signals": [],
        "positive_conversion_signals": [],
        "automation_opportunity": "unknown",
    }

    if not _is_valid_url(website_url):
        return result

    base_url = website_url.strip()
    parsed_base = urlparse(base_url)
    base_root = f"{parsed_base.scheme}://{parsed_base.netloc}"

    seed_urls = [base_url]
    seed_urls.extend(urljoin(base_root, path) for path in LIKELY_PATHS)

    scanned: List[str] = []
    seen: Set[str] = set()
    text_content_total = 0
    cta_found = False
    gmail_or_yahoo_email = False

    index = 0
    while index < len(seed_urls) and len(scanned) < MAX_PAGES_TO_SCAN:
        url = seed_urls[index]
        index += 1

        if url in seen:
            continue
        seen.add(url)

        try:
            html = _fetch_html(url, timeout_seconds)
        except Exception as exc:
            print(f"[scan warning] {url} fetch failed: {exc}")
            continue

        scanned.append(url)
        html_lower = html.lower()
        text_content_total += len(_strip_html(html_lower))

        if not result["website_reachable"]:
            result["website_reachable"] = True

        if index == 1:
            for discovered in _extract_internal_links(base_url, html):
                if discovered not in seen and discovered not in seed_urls:
                    seed_urls.append(discovered)

        if _detect_contact_form(html_lower):
            result["has_contact_form"] = True

        if EMAIL_REGEX.search(html_lower):
            result["has_email_visible"] = True
            if any(domain in html_lower for domain in ["@gmail.com", "@yahoo.com"]):
                gmail_or_yahoo_email = True

        if PHONE_REGEX.search(html_lower):
            result["has_phone_visible"] = True

        if any(token in html_lower for token in CHAT_VENDOR_TOKENS):
            result["has_chat_widget"] = True

        if any(token in html_lower for token in FB_MESSENGER_TOKENS):
            result["has_fb_messenger"] = True

        if any(token in html_lower for token in CALL_NOW_TOKENS):
            result["has_call_now_button"] = True

        if any(token in html_lower for token in SCHEDULING_TOOL_TOKENS):
            result["has_scheduling_tool"] = True
            cta_found = True

        if any(keyword in html_lower for keyword in BOOKING_KEYWORDS):
            result["has_online_booking_keywords"] = True
            cta_found = True

        if any(keyword in html_lower for keyword in REQUEST_QUOTE_KEYWORDS):
            result["has_request_quote_cta"] = True
            cta_found = True

        if any(keyword in html_lower for keyword in SCHEDULE_SERVICE_KEYWORDS):
            result["has_schedule_service_cta"] = True
            cta_found = True

        if '<meta name="viewport"' in html_lower or "width=device-width" in html_lower:
            result["mobile_friendly_hint"] = True

    result["scanned_urls"] = scanned

    weak_signals: List[str] = []
    positive_signals: List[str] = []

    if result["website_reachable"]:
        positive_signals.append("site reachable")
    if result["has_contact_form"]:
        positive_signals.append("contact form")
    if result["has_online_booking_keywords"]:
        positive_signals.append("booking cta")
    if result["has_request_quote_cta"]:
        positive_signals.append("quote cta")
    if result["has_schedule_service_cta"]:
        positive_signals.append("schedule cta")
    if result["has_chat_widget"] or result["has_fb_messenger"]:
        positive_signals.append("chat widget")
    if result["has_scheduling_tool"]:
        positive_signals.append("scheduling tool")
    if result["has_call_now_button"]:
        positive_signals.append("call now button")
    if result["mobile_friendly_hint"]:
        positive_signals.append("mobile viewport")

    if not result["mobile_friendly_hint"]:
        weak_signals.append("no viewport meta")
    if not cta_found:
        weak_signals.append("no clear cta")
    if not result["has_contact_form"]:
        weak_signals.append("no contact form")
    if text_content_total < 1200:
        weak_signals.append("very low text content")
    if gmail_or_yahoo_email:
        weak_signals.append("consumer email address")
    if result["has_phone_visible"] and not result["has_contact_form"] and not result["has_request_quote_cta"]:
        weak_signals.append("phone-only lead flow")

    result["weak_website_signals"] = weak_signals
    result["positive_conversion_signals"] = positive_signals
    result["automation_opportunity"] = _classify_automation_opportunity(result)

    return result


def _classify_automation_opportunity(result: Dict[str, object]) -> str:
    """
    Deterministic automation opportunity label derived from scan signals.

    Priority order — first matching rule wins:
      missed_after_hours  → phone visible + call-now button + no chat + no scheduling
      no_chat             → contact form present + no chat widget at all
      no_booking          → phone/form present but no scheduling tool or booking keywords
      unknown             → fallback
    """
    has_any_chat = result.get("has_chat_widget") or result.get("has_fb_messenger")
    has_booking  = result.get("has_scheduling_tool") or result.get("has_online_booking_keywords")
    phone        = result.get("has_phone_visible")
    call_btn     = result.get("has_call_now_button")
    form         = result.get("has_contact_form")

    if phone and call_btn and not has_any_chat and not has_booking:
        return "missed_after_hours"
    if form and not has_any_chat:
        return "no_chat"
    if (phone or form) and not has_booking:
        return "no_booking"
    return "unknown"


def generate_lead_insight(scan_result: Dict[str, object]) -> tuple[str, List[str]]:
    """Return a short operator-facing insight sentence plus supporting signals."""
    positive = [str(x) for x in (scan_result.get("positive_conversion_signals") or []) if str(x).strip()]
    weak = [str(x) for x in (scan_result.get("weak_website_signals") or []) if str(x).strip()]

    signals: List[str] = []
    if positive:
        signals.extend(positive[:2])
    if weak:
        signals.extend([f"gap: {w}" for w in weak[:2]])

    if weak:
        sentence = f"Website shows conversion gaps ({weak[0]}), which makes response-capture automation a strong angle."
    elif positive:
        sentence = f"Website already shows {positive[0]}, so positioning should focus on faster after-hours response and lead capture."
    else:
        sentence = "Website signal scan was limited; position outreach around missed-call response speed and lead capture reliability."

    return sentence, signals
