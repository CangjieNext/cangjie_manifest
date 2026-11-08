#!/usr/bin/env python3
"""Count public API surface of Rust library/ (std distribution crates)."""
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1])
KINDS = ['fn', 'struct', 'enum', 'union', 'trait', 'type', 'const', 'static', 'mod', 'use', 'macro']
MODS = r'(?:unsafe\s+)?(?:const\s+)?(?:async\s+)?(?:extern\s+"[^"]*"\s+)?(?:default\s+)?'

TOP_RE = re.compile(r'^pub\s+' + MODS + r'(fn|struct|enum|union|trait|type|const|static|mod|use|macro)\b', re.M)
MEMBER_RE = re.compile(r'^\s+pub\s+' + MODS + r'(fn|struct|enum|union|trait|type|const|static|mod|use|macro)\b', re.M)

# crates that are implementation deps / tests / build shims, not user-facing std API
SKIP_CRATES = {'coretests', 'alloctests', 'sysroot', 'rustc-std-workspace-core',
               'rustc-std-workspace-alloc', 'rustc-std-workspace-std',
               'compiler-builtins', 'windows-sys', 'windows_link'}
STD_CRATES = {'core', 'alloc', 'std', 'proc_macro', 'test', 'std_detect', 'portable-simd',
              'panic_abort', 'panic_unwind', 'unwind', 'rtstartup', 'backtrace', 'stdarch'}

def strip_comments(src):
    # keep it simple: remove /* */ and // (strings rarely contain these at line start)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    src = re.sub(r'//[^\n]*', '', src)
    return src

per_pkg, total = {}, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0)
std_only = dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0)
for f in sorted(root.rglob('*.rs')):
    rel = f.relative_to(root)
    parts = rel.parts
    crate = parts[0]
    if crate in SKIP_CRATES:
        continue
    # skip crate-level tests/benches dirs
    rest = parts[1:]
    if rest and rest[0] in ('tests', 'benches'):
        continue
    try:
        src = f.read_text(encoding='utf-8', errors='replace')
    except Exception:
        continue
    s = strip_comments(src)
    d = per_pkg.setdefault(crate, dict(files=0, loc=0, top={k: 0 for k in KINDS}, members=0))
    d['files'] += 1; d['loc'] += len(s.split('\n'))
    for m in TOP_RE.finditer(s):
        d['top'][m.group(1)] += 1
    d['members'] += len(MEMBER_RE.findall(s))
for name, d in per_pkg.items():
    total['files'] += d['files']; total['loc'] += d['loc']; total['members'] += d['members']
    for k in KINDS:
        total['top'][k] += d['top'][k]
    if name in STD_CRATES:
        std_only['files'] += d['files']; std_only['loc'] += d['loc']; std_only['members'] += d['members']
        for k in KINDS:
            std_only['top'][k] += d['top'][k]
total['top_total'] = sum(v for k, v in total['top'].items() if k != 'use')
std_only['top_total'] = sum(v for k, v in std_only['top'].items() if k != 'use')
out = dict(total=total, std_crates_only=std_only, per_pkg=per_pkg)
print(json.dumps(out, ensure_ascii=False, indent=1))
