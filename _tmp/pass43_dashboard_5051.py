import sys
sys.path.insert(0, r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine')
import dashboard_server as ds

ds.app.run(host='127.0.0.1', port=5051, debug=False)
