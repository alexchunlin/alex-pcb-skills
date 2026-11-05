#!/usr/bin/env python3
"""Router path regression controls with file-I/O subprocess stubs; no CAD."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

KRT_STUB = '''import json,sys
from pathlib import Path
board,out=map(Path,sys.argv[1:3])
data=board.read_bytes()
assert board.with_suffix('.kicad_pro').read_text()=='sidecar'
out.write_bytes(data)
Path(sys.argv[sys.argv.index('--json-out')+1]).write_text(json.dumps({'input':str(board),'output':str(out)}))
'''
JAVA_STUB = '''#!/usr/bin/env python3
import sys
from pathlib import Path
dsn=Path(sys.argv[sys.argv.index('-de')+1])
ses=Path(sys.argv[sys.argv.index('-do')+1])
ses.write_bytes(dsn.read_bytes())
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--expect', choices=['original', 'fixed'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_bytes()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite control result')
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'run_engine')
    module = ast.Module(body=[function], type_ignores=[])
    original_cwd = Path.cwd()
    results = []
    with tempfile.TemporaryDirectory(prefix='s7 path control ') as temp:
        root = Path(temp)
        native = root/'native engine'
        (native/'py_router').mkdir(parents=True)
        (native/'py_router/route.py').write_text(KRT_STUB)
        java = root/'fake java'
        java.write_text(JAVA_STUB)
        java.chmod(0o755)
        jar = root/'fake.jar'
        jar.write_text('dummy')
        # These stubs perform file I/O only. No pcbnew import or CAD executable.
        pcbnew = SimpleNamespace(LoadBoard=lambda path: Path(path),
            ExportSpecctraDSN=lambda board,path: Path(path).write_bytes(board.read_bytes()),
            ImportSpecctraSES=lambda board,path: Path(path).read_bytes())
        globals_ = dict(os=os, sys=sys, subprocess=subprocess, pcbnew=pcbnew,
                        KRT_DIR=str(native), KRT_PY=sys.executable, KRT_PASSES=[[], []],
                        ROUTE_RULES=[], FR_JAR=str(jar), JAVA=str(java), FR_ARGS=[],
                        outer_only_args=lambda board: [],
                        unfill_and_save=lambda board,path: Path(path).write_bytes(board.read_bytes()))
        exec(compile(module, str(args.source), 'exec'), globals_)
        try:
            os.chdir(root)
            for engine in ('krt', 'freerouting'):
                for relative_board, relative_out in ((True,True),(False,False),(True,False),(False,True)):
                    name = f'{engine}-board-{relative_board}-out-{relative_out}'
                    case = root/name
                    (case/'input').mkdir(parents=True)
                    board = case/'input/board.kicad_pcb'
                    board.write_bytes(b'dummy board bytes\n')
                    board.with_suffix('.kicad_pro').write_text('sidecar')
                    output = case/'output'
                    board_arg = str(board.relative_to(root) if relative_board else board)
                    output_arg = str(output.relative_to(root) if relative_out else output)
                    routed, wall, rc = globals_['run_engine'](engine, board_arg, output_arg, 1,
                        str(case/'engine.log'), inner_tracks=True, timeout=3)
                    expected_success = args.expect == 'fixed' or not relative_out and (engine == 'freerouting' or not relative_board)
                    valid_output = routed is not None and Path(routed).read_bytes() == board.read_bytes()
                    valid_sidecar = (output/'board.kicad_pro').read_text() == 'sidecar'
                    passed = (rc == 0 and valid_output and valid_sidecar) if expected_success else (rc != 0 and routed is None)
                    results.append(dict(case=name, expected_success=expected_success, return_code=rc,
                                        routed=routed, wall_seconds=wall, sidecar_preserved=valid_sidecar,
                                        passed=passed, log=(case/'engine.log').read_text()))
        finally:
            os.chdir(original_cwd)
    record = dict(status='passed' if all(row['passed'] for row in results) else 'failed',
                  mode='fake subprocess path controls; no CAD', expected=args.expect,
                  source=str(args.source.resolve()), source_sha256=hashlib.sha256(source).hexdigest(),
                  cases=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'status':record['status'], 'cases':len(results)}))
    raise SystemExit(0 if record['status']=='passed' else 1)


if __name__ == '__main__':
    main()
