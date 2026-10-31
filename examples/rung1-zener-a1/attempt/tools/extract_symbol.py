#!/usr/bin/env python3
"""Extract one top-level (symbol "NAME" ...) block (plus any symbol it extends) from a KiCad .kicad_sym
library into a standalone library file. Usage: extract_symbol.py SRC.kicad_sym NAME [NAME...] -o OUT.kicad_sym"""
import sys, re

def blocks(text):
    """Yield (name, start, end) for every top-level (symbol "..." ...) block."""
    i = 0
    depth = 0
    n = len(text)
    in_str = False
    start = None
    while i < n:
        c = text[i]
        if in_str:
            if c == '\\':
                i += 2; continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '(':
            depth += 1
            if depth == 2 and text.startswith('(symbol ', i):
                start = i
        elif c == ')':
            if depth == 2 and start is not None:
                blk = text[start:i+1]
                m = re.match(r'\(symbol\s+"([^"]+)"', blk)
                yield m.group(1), blk
                start = None
            depth -= 1
        i += 1

args = sys.argv[1:]
out = args[args.index('-o') + 1]
src = args[0]
names = [a for a in args[1:args.index('-o')]]
text = open(src, encoding='utf-8').read()
all_blocks = dict(blocks(text))
want = []
for nm in names:
    blk = all_blocks[nm]
    m = re.search(r'\(extends\s+"([^"]+)"\)', blk)
    if m and m.group(1) not in names and m.group(1) not in want:
        want.append(m.group(1))
    want.append(nm)
header = text[:text.index('(symbol ')]
with open(out, 'w', encoding='utf-8') as f:
    f.write(header)
    for nm in want:
        f.write('\t' + all_blocks[nm].strip() + '\n')
    f.write(')\n')
print("wrote", out, "with", want)
