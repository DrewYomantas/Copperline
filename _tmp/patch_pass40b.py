"""
Wire _scRecord into statusCellHtml return — augment subline with obs + next-action.
Uses string replacement on known stable anchor text instead of complex regex.
"""
PATH = r"C:\Users\beyon\OneDrive\Desktop\OfficeAutomation\lead_engine\dashboard_static\index.html"

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

# The return block we need to replace. Read from file to get exact bytes.
OLD = (
    '  return `<div class="status-stack">` +\n'
    '    `<span class="badge ${meta.badgeClass}" title="${escHtml(meta.title || meta.label)}">${escHtml(meta.label)}</span>` +\n'
    '    `<div class="status-sub ${meta.tone || \'info\'}">${escHtml(meta.subline || \'\')}</div>` +\n'
    '    (meta.detail ? `<div class="status-sub exact">${escHtml(meta.detail)}</div>` : \'\') +\n'
    '    `</div>`;'
)

NEW = (
    '  // V2 Stage 2C: augment subline with obs presence + next-action\n'
    '  const _scSubExtra = []\n'
    '    .concat(_scRecord.observation ? [\'obs\'] : [])\n'
    '    .concat(_scRecord.nextAction && !_scRecord.isSent ? [_scRecord.nextAction] : [])\n'
    '    .join(\' \u00b7 \');\n'
    '  const _scSubline = [meta.subline || \'\', _scSubExtra].filter(Boolean).join(\' \u00b7 \');\n'
    '  return `<div class="status-stack">` +\n'
    '    `<span class="badge ${meta.badgeClass}" title="${escHtml(meta.title || meta.label)}">${escHtml(meta.label)}</span>` +\n'
    '    `<div class="status-sub ${meta.tone || \'info\'}">${escHtml(_scSubline)}</div>` +\n'
    '    (meta.detail ? `<div class="status-sub exact">${escHtml(meta.detail)}</div>` : \'\') +\n'
    '    `</div>`;'
)

if OLD in src:
    src = src.replace(OLD, NEW, 1)
    print("REPLACED: statusCellHtml return augmented with obs + next-action")
else:
    # Try LF-only variant
    OLD_LF = OLD.replace('\r\n', '\n')
    if OLD_LF in src:
        src = src.replace(OLD_LF, NEW.replace('\r\n', '\n'), 1)
        print("REPLACED (LF): statusCellHtml return augmented")
    else:
        print("MISS: exact return block not found")
        # Print context around _scRecord to help debug
        idx = src.find('const _scRecord = _leadRecord(row);')
        if idx >= 0:
            print(f"  _scRecord found at char {idx}")
            print(f"  Following 400 chars: {src[idx:idx+400]!r}")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)
