import base64, os

b64_path = r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\_tmp\idx.b64'
out_path = r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html'

with open(b64_path, 'r') as f:
    data = f.read()

decoded = base64.b64decode(data)
with open(out_path, 'wb') as f:
    f.write(decoded)

size = os.path.getsize(out_path)
print(f'Written {size} bytes to {out_path}')
