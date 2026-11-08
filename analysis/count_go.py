#!/usr/bin/env python3
"""Count exported API surface of Go stdlib (go/src), excluding toolchain/internal/vendor/tests."""
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
EXCLUDE_TOP = {'cmd', 'internal', 'vendor', 'testdata'}
KINDS = ['type', 'func', 'const', 'var']

RE_FUNC = re.compile(r'^func\s+([A-Z]\w*)', re.M)
RE_METHOD = re.compile(r'^func\s*\([^)]*\)\s+([A-Z]\w*)', re.M)
RE_TYPE = re.compile(r'^type\s+([A-Z]\w*)', re.M)
RE_CONST1 = re.compile(r'^const\s+([A-Z]\w*)', re.M)
RE_VAR1 = re.compile(r'^var\s+([A-Z]\w*)', re.M)
RE_BLOCK_ENTRY = re.compile(r'^\s*([A-Z]\w*)\s*[=,]')

def count_file(src):
    top = {k: 0 for k in KINDS}
    members = 0
    lines = src.split('\n')
    block = None  # 'const' | 'var'
    for ln in lines:
        s = ln.rstrip()
        if block:
            if RE_BLOCK_ENTRY.match(s):
                top[block] += 1
            if s.startswith(')'):
                block = None
            continue
        if RE_FUNC.match(s) and '(' not in s.split('func')[1][:0] :  # placeholder
            pass
        m = RE_FUNC.match(s)
        if m and not s.startswith('func ('):
            top['func'] += 1
        elif s.startswith('func ('):
            members += 1
        elif RE_TYPE.match(s):
            top['type'] += 1
        elif RE_CONST1.match(s):
            top['const'] += 1
        elif RE_VAR1.match(s):
            top['var'] += 1
        elif re.match(r'^const\s*\(', s):
            block = 'const'
        elif re.match(r'^var\s*\(', s):
            block = 'var'
    return top, members

def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    return src

per_pkg, total = {}, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0)
for f in sorted(root.rglob('*.go')):
    rel = f.relative_to(root)
    parts = rel.parts
    if parts[0] in EXCLUDE_TOP:
        continue
    if f.name.endswith('_test.go'):
        continue
    if 'testdata' in parts:
        continue
    try:
        src = f.read_text(encoding='utf-8', errors='replace')
    except Exception:
        continue
    if '\n//go:build ignore' in src or src.startswith('//go:build ignore'):
        continue
    s = strip_comments(src)
    pkg = parts[0] if len(parts) > 1 else '(root)'
    d = per_pkg.setdefault(pkg, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0))
    top, members = count_file(s)
    d['files'] += 1; d['loc'] += len(s.split('\n'))
    d['members'] += members
    for k in KINDS:
        d['top'][k] += top[k]
for d in per_pkg.values():
    total['files'] += d['files']; total['loc'] += d['loc']; total['members'] += d['members']
    for k in KINDS:
        total['top'][k] += d['top'][k]
total['top_total'] = sum(total['top'].values())
total['pkg_count'] = len(per_pkg)
print(json.dumps(dict(total=total, per_pkg=per_pkg), ensure_ascii=False, indent=1))
