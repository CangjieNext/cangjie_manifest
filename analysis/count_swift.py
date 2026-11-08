#!/usr/bin/env python3
"""Count public API surface of Swift stdlib/public (and swift-corelibs Sources)."""
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
pkg_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 1  # path components forming pkg name
KINDS = ['class', 'struct', 'enum', 'protocol', 'func', 'typealias', 'var', 'let', 'actor', 'macro']

TOP_RE = re.compile(
    r'^public\s+(?:final\s+|open\s+|indirect\s+|nonisolated\s+|static\s+)*(class|struct|enum|protocol|func|typealias|var|let|actor|macro)\b', re.M)
MEMBER_RE = re.compile(
    r'^\s+public\s+(?:static\s+|class\s+|final\s+|override\s+|nonisolated\s+|required\s+|mutating\s+)*(func|var|let|init|subscript)\b', re.M)

def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    return src

per_pkg, total = {}, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0)
for f in sorted(root.rglob('*.swift')):
    rel = f.relative_to(root)
    parts = rel.parts
    if any(p == 'Tests' or p.endswith('Tests') or p.lower() == 'test' or p.lower() == 'testdata' for p in parts):
        continue
    try:
        src = f.read_text(encoding='utf-8', errors='replace')
    except Exception:
        continue
    s = strip_comments(src)
    pkg = '.'.join(parts[:pkg_depth]) if len(parts) > pkg_depth else '.'.join(parts[:-1]) or '(root)'
    d = per_pkg.setdefault(pkg, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0))
    d['files'] += 1; d['loc'] += len(s.split('\n'))
    for m in TOP_RE.finditer(s):
        d['top'][m.group(1)] += 1
    d['members'] += len(MEMBER_RE.findall(s))
for d in per_pkg.values():
    total['files'] += d['files']; total['loc'] += d['loc']; total['members'] += d['members']
    for k in KINDS:
        total['top'][k] += d['top'][k]
total['top_total'] = sum(total['top'].values())
total['pkg_count'] = len(per_pkg)
print(json.dumps(dict(total=total, per_pkg=per_pkg), ensure_ascii=False, indent=1))
