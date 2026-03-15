data = open(r'C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html', encoding='utf-8').read()
lines = data.splitlines()

checks = [
    ('leaflet_css',          'leaflet.min.css' in data),
    ('leaflet_js',           'leaflet.min.js' in data),
    ('nav_map_tab',          'data-page="map"' in data),
    ('page_map_div',         'id="page-map"' in data),
    ('map_container',        'id="map-container"' in data),
    ('map_industry_select',  'id="map-industry"' in data),
    ('btn_map_search',       'id="btnMapSearch"' in data),
    ('fn_mapInit',           'function _mapInit()' in data),
    ('fn_mapDrawCircle',     'function _mapDrawCircle' in data),
    ('fn_mapSearch',         'async function mapSearch()' in data),
    ('fn_mapClearCircle',    'function mapClearCircle()' in data),
    ('fn_mapPopulate',       'function _mapPopulateIndustries()' in data),
    ('switchPage_map',       "name === 'map'" in data),
    ('api_discover_area',    'discover_area' in data),
    ('L_map_call',           'L.map(' in data),
    ('L_circle_call',        'L.circle(' in data),
    ('osm_tiles',            'openstreetmap.org' in data),
    ('script_close_2x',      data.count('</script>') == 2),
    ('body_close',           '</body>' in data),
    ('html_close',           '</html>' in data),
    ('DOMContentLoaded',     'DOMContentLoaded' in data),
    ('loadAll_called',       'loadAll()' in data),
]

for k, v in checks:
    print('OK  ' if v else 'FAIL', k)

failed = [k for k, v in checks if not v]
print()
print('TOTAL', len(checks), '| FAILED', len(failed), ':', failed if failed else 'none')
print('Lines:', len(lines))
