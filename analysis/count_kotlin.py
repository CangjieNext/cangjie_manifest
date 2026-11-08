#!/usr/bin/env python3
"""Count public API surface of Kotlin libraries (stdlib etc.).

Kotlin default visibility is public: declarations without private/internal count.
Scope: top-level = column 0; members = indented.
"""
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
KINDS = ['class', 'object', 'interface', 'fun', 'val', 'var', 'typealias']

MOD = r'(?:public\s+)?(?:external\s+|expect\s+|actual\s+|inline\s+|suspend\s+|operator\s+|infix\s+|tailrec\s+|open\s+|final\s+|abstract\s+|sealed\s+|const\s+|lateinit\s+)*'
KIND_ALT = r'(?:(?:annotation|data|value|enum|fun)\s+)*(class|object|interface|fun|val|var|typealias)\b'

TOP_RE = re.compile(r'^' + MOD + KIND_ALT, re.M)
MEMBER_RE = re.compile(r'^\s+' + MOD + KIND_ALT, re.M)

def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    return src

def walk(root: Path, pkg_prefix=()):
    per_pkg, total = {}, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0)
    for f in sorted(root.rglob('*.kt')):
        rel = f.relative_to(root)
        parts = rel.parts
        if any(p in ('test', 'tests', 'testdata', 'samples') or p.endswith('Test') for p in parts[:-1]):
            continue
        if f.name.endswith('Test.kt') or 'Test' in f.stem:
            continue
        try:
            src = f.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        s = strip_comments(src)
        pkg = parts[0] if len(parts) > 1 else (pkg_prefix[0] if pkg_prefix else '(root)')
        d = per_pkg.setdefault(pkg, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0))
        d['files'] += 1; d['loc'] += len(s.split('\n'))
        for m in TOP_RE.finditer(s):
            k = m.group(1)
            if k in d['top']:
                d['top'][k] += 1
        d['members'] += len(MEMBER_RE.findall(s))
    for d in per_pkg.values():
        total['files'] += d['files']; total['loc'] += d['loc']; total['members'] += d['members']
        for k in KINDS:
            total['top'][k] += d['top'][k]
    total['top_total'] = sum(total['top'].values())
    return dict(total=total, per_pkg=per_pkg)

if __name__ == '__main__':
    out = walk(Path(sys.argv[1]))
    print(json.dumps(out, ensure_ascii=False, indent=1))
