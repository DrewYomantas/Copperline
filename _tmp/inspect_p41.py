"""
Pass 41 — repo inspection.
Reports what stable identifiers are actually present in queue rows,
which drives how strong the key-matching upgrade can be.
"""
import csv

QUEUE = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\queue\pending_emails.csv"

with open(QUEUE, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

total = len(rows)
unsent = [r for r in rows if not r.get("sent_at","").strip()]

def norm_site(url):
    import re
    s = (url or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.rstrip("/")
    return s

def norm_phone(p):
    import re
    return re.sub(r"\D", "", p or "")

has_website  = sum(1 for r in rows if norm_site(r.get("website","")))
has_phone    = sum(1 for r in rows if len(norm_phone(r.get("phone",""))) >= 7)
has_email    = sum(1 for r in rows if "@" in r.get("to_email",""))
has_facebook = sum(1 for r in rows if r.get("facebook_url","").strip())
has_name_city= sum(1 for r in rows if r.get("business_name","").strip() and r.get("city","").strip())

print(f"Total rows : {total}")
print(f"Unsent rows: {len(unsent)}")
print()
print("Stable identifier coverage across ALL rows:")
print(f"  website (normalized, non-empty) : {has_website} / {total}  ({has_website*100//total}%)")
print(f"  phone   (>=7 digits)            : {has_phone}  / {total}  ({has_phone*100//total}%)")
print(f"  email                           : {has_email}  / {total}  ({has_email*100//total}%)")
print(f"  facebook_url                    : {has_facebook} / {total}  ({has_facebook*100//total}%)")
print(f"  name+city                       : {has_name_city} / {total}  ({has_name_city*100//total}%)")
print()

# Check website vs phone coverage overlap
site_set   = {norm_site(r.get("website","")) for r in rows if norm_site(r.get("website",""))}
phone_set  = {norm_phone(r.get("phone","")) for r in rows if len(norm_phone(r.get("phone",""))) >= 7}
print(f"Unique normalized websites : {len(site_set)}")
print(f"Unique normalized phones   : {len(phone_set)}")

# Collisions: rows sharing the same website (would be wrong match target)
from collections import Counter
site_counts  = Counter(norm_site(r.get("website","")) for r in rows if norm_site(r.get("website","")))
phone_counts = Counter(norm_phone(r.get("phone","")) for r in rows if len(norm_phone(r.get("phone",""))) >= 7)
site_collisions  = {k: v for k, v in site_counts.items() if v > 1}
phone_collisions = {k: v for k, v in phone_counts.items() if v > 1}
print(f"Website key collisions (>1 row): {len(site_collisions)}")
for k, v in list(site_collisions.items())[:5]:
    print(f"  {k!r}: {v} rows")
print(f"Phone key collisions (>1 row): {len(phone_collisions)}")
for k, v in list(phone_collisions.items())[:5]:
    print(f"  {k!r}: {v} rows")
