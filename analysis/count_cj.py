#!/usr/bin/env python3
"""Count public API surface of Cangjie (.cj) source trees.

Top-level declarations must start at column 0 with `public`.
Members are indented `public ...` declarations inside types.
"""
import json, re, sys
from pathlib import Path

KINDS = ['class', 'struct', 'enum', 'interface', 'type', 'func', 'const', 'var', 'prop']

TOP_RE = re.compile(
    r'^public[ \t]+(?:abstract[ \t]+|open[ \t]+|sealed[ \t]+|foreign[ \t]+|unsafe[ \t]+)*'
    r'(class|struct|enum|interface|type|func|const|var|prop)\b', re.M)

MEMBER_RE = re.compile(
    r'^[ \t]+public[ \t]+(?:abstract[ \t]+|open[ \t]+|sealed[ \t]+|static[ \t]+|foreign[ \t]+|unsafe[ \t]+|operator[ \t]+)*'
    r'(func|prop|init|const|var|let|operator)\b', re.M)

def strip_comments(src: str) -> str:
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    return src

def count_tree(root: Path):
    per_pkg = {}
    total = dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0)
    files = sorted(root.rglob('*.cj'))
    for f in files:
        try:
            src = f.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        loc = src.count('\n') + 1
        s = strip_comments(src)
        rel = f.relative_to(root)
        pkg = rel.parts[0] if len(rel.parts) > 1 else '(root)'
        d = per_pkg.setdefault(pkg, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0))
        d['files'] += 1; d['loc'] += loc
        total['files'] += 1; total['loc'] += loc
        for m in TOP_RE.finditer(s):
            kind = m.group(1)
            d['top'][kind] += 1
        for m in MEMBER_RE.finditer(s):
            d['members'] += 1
    for d in per_pkg.values():
        for k in KINDS:
            total['top'][k] += d['top'][k]
        total['members'] += d['members']
    return dict(total=total, per_pkg=per_pkg)

if __name__ == '__main__':
    root = Path(sys.argv[1])
    out = count_tree(root)
    out['total']['top_total'] = sum(out['total']['top'].values())
    print(json.dumps(out, ensure_ascii=False, indent=1))
