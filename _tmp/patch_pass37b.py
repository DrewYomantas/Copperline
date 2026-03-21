import re

PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"
with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

changes = []

# ── panelScheduleTomorrow pending state ──────────────────────────────────────
OLD1 = re.compile(
    r'(async function panelScheduleTomorrow\(\) \{)\s*'
    r'(const row = _panelCurrentRow\(\);)',
    re.DOTALL
)
NEW1 = (r'\1\n  const _schedBtn = document.getElementById(\'panel-schedule-btn\');\n'
        r'  _btnPending(_schedBtn, \'Scheduling...\');\n'
        r'  \2')
if OLD1.search(src):
    src = OLD1.sub(NEW1, src, count=1)
    changes.append("panelScheduleTomorrow -- pending prefix")
else:
    print("WARNING: panelScheduleTomorrow not matched")

# Now close the try and add _btnRestore after the function's closing try/catch
# Find the function body and add _btnRestore before the closing brace
OLD2 = re.compile(
    r"(toast\(`Scheduled for \$\{_formatSendAfter\(row\.send_after\)\} - waits until that time`, 'ok'\);)\s*"
    r"(    return true;\s*"
    r"  \} catch\(e\) \{\s*"
    r"    toast\('Connection error', 'err'\);\s*"
    r"  \}\s*\})",
    re.DOTALL
)
NEW2 = (r"\1\n    \2\n  _btnRestore(_schedBtn);")

# Simpler: just add _btnRestore at the end of the function's catch block
OLD3 = re.compile(
    r"(  \} catch\(e\) \{\s*\n    toast\('Connection error', 'err'\);\s*\n  \}\s*\n\})"
    r"(\s*\n// Pass 10 — clear existing schedule)",
    re.DOTALL
)
NEW3 = r"  } catch(e) {\n    toast('Connection error', 'err');\n  }\n  _btnRestore(_schedBtn);\n}\2"
if OLD3.search(src):
    src = OLD3.sub(NEW3, src, count=1)
    changes.append("panelScheduleTomorrow -- _btnRestore at end")
else:
    # Fallback: wrap the entire try/catch with pending/restore
    print("INFO: panelScheduleTomorrow close pattern not matched, trying simpler restore")

# ── panelUnschedule pending state ────────────────────────────────────────────
OLD4 = re.compile(
    r'(// Pass 10 [^\n]*\nasync function panelUnschedule\(\) \{)\s*'
    r'(const row = _panelCurrentRow\(\);)',
    re.DOTALL
)
NEW4 = (r'\1\n  const _unschedBtn = document.getElementById(\'panel-schedule-btn\');\n'
        r'  _btnPending(_unschedBtn, \'Clearing...\');\n'
        r'  \2')
if OLD4.search(src):
    src = OLD4.sub(NEW4, src, count=1)
    changes.append("panelUnschedule -- pending prefix")
else:
    print("WARNING: panelUnschedule not matched")

# Add _btnRestore at end of panelUnschedule
OLD5 = re.compile(
    r"(    toast\('Unscheduled - back in the ready-now queue', 'ok'\);\s*\n    return true;\s*\n  \} catch\(e\) \{\s*\n    toast\('Connection error', 'err'\);\s*\n  \}\s*\n\})"
    r"(\s*\n// Pass 10 / Pass 20a)",
    re.DOTALL
)
NEW5 = r"    toast('Unscheduled - back in the ready-now queue', 'ok');\n    return true;\n  } catch(e) {\n    toast('Connection error', 'err');\n  }\n  _btnRestore(_unschedBtn);\n}\2"
if OLD5.search(src):
    src = OLD5.sub(NEW5, src, count=1)
    changes.append("panelUnschedule -- _btnRestore at end")
else:
    print("INFO: panelUnschedule close pattern not matched")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print(f"Applied: {len(changes)}")
for c in changes:
    print(f"  + {c}")
