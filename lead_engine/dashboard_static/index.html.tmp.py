import re
path = r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    s = line.strip()
    if 'PAGE:' in s or ('id="page-' in s) or ('id="page-map"' in s) or ('id="page-cities"' in s):
        print(f"{i:5}: {s[:120]}".encode('ascii','replace').decode())
