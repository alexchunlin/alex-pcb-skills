"""Filesystem-only IR-drop regression tests; no KiCad or numerical solver is run."""
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'skills/kicad-design/scripts'
pcbnew = ModuleType('pcbnew')
pcbnew.ToMM = pcbnew.FromMM = lambda x: x
pcbnew.LoadBoard = lambda path: SimpleNamespace(GetFileName=lambda: path)
with patch.dict(sys.modules, pcbnew=pcbnew, pcbq=ModuleType('pcbq')):
    spec = importlib.util.spec_from_file_location('pcbir', SCRIPTS / 'pcbir.py')
    ir = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ir)


class Paths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self.cwd)
        self.board = pcbnew.LoadBoard(str(Path('board.kicad_pcb').resolve()))
        self.extract = patch.object(ir, 'extract', side_effect=lambda b, *a: {'board': b.GetFileName()})
        self.extract.start()
        self.addCleanup(self.extract.stop)
        self.solver = patch.object(ir.subprocess, 'run', side_effect=self.solve)
        self.solver.start()
        self.addCleanup(self.solver.stop)

    def solve(self, cmd, **kw):
        # Resolve argv exactly as a child started with cwd=out would.
        inp = Path(kw['cwd']) / cmd[-3]
        svg = Path(kw['cwd']) / cmd[-1]
        data = json.loads(inp.read_text())
        svg.write_text(data['board'])
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(
            marker=data['board'], cells=1, power_mW=4.2, max_J_A_mm2=3,
            sinks=[], worst=[])), stderr='')

    def cli(self, board, out=None):
        argv = ['pcbir.py', board, '--net', '/VCC', '--source', 'J1.1',
                '--sink', 'J2.1=1', '--json']
        if out is not None:
            argv += ['--out', out]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as buf:
            ir.main()
        return json.loads(buf.getvalue())

    def test_default_two_same_stem_boards_keep_own_artifacts(self):
        # Put legacy /tmp defaults under the test root too.
        original_join = os.path.join
        def join(base, *rest):
            return original_join(self.tmp.name if base == '/tmp/pcb-irdrop' else base, *rest)
        temp_root = patch.object(ir.tempfile, 'tempdir', self.tmp.name) if hasattr(ir, 'tempfile') else contextlib.nullcontext()
        with patch.object(ir.os.path, 'join', side_effect=join), temp_root:
            a = self.cli('one/board.kicad_pcb')
            b = self.cli('two/board.kicad_pcb')
            c = self.cli('one/board.kicad_pcb')
        self.assertNotEqual(a['svg'], b['svg'])
        self.assertNotEqual(a['svg'], c['svg'])
        for rep in (a, b, c):
            self.assertEqual(Path(rep['svg']).read_text(), rep['board'])
            saved = json.loads(Path(rep['svg']).with_name('irdrop.json').read_text())
            self.assertEqual(saved['board'], rep['board'])
        print('EVIDENCE default: two same-stem boards retained distinct artifacts')

    def test_relative_output(self):
        rep = self.cli('board.kicad_pcb', 'relative output')
        self.assertEqual(Path(rep['svg']), Path('relative output/irdrop.svg').resolve())
        self.assertEqual(rep['power_mW'], 4.2)
        print('EVIDENCE relative: child input and SVG resolve once from caller cwd')

    def test_absolute_output_reuse_control(self):
        out = str(Path('explicit').resolve())
        a = self.cli('one.kicad_pcb', out)
        b = self.cli('two.kicad_pcb', out)
        self.assertEqual(a['svg'], b['svg'])
        self.assertEqual(Path(b['svg']).read_text(), b['board'])
        self.assertEqual(b['power_mW'], 4.2)

    def test_concurrent_explicit_output_rejected(self):
        out = str(Path('shared').resolve())
        entered, release = threading.Event(), threading.Event()
        errors = []
        def extract(b, *args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test timed out')
            return {'board': b.GetFileName()}
        def first():
            try:
                ir.run(self.board, 'VCC', 'J1.1', [], .1, {}, out)
            except Exception as e:
                errors.append(e)
        with patch.object(ir, 'extract', side_effect=extract):
            worker = threading.Thread(target=first)
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(RuntimeError, 'in use'):
                    ir.run(self.board, 'VCC', 'J1.1', [], .1, {}, out)
            finally:
                release.set()
                worker.join(6)
        self.assertFalse(errors)

    def test_concurrent_defaults_keep_matching_input_and_output(self):
        barrier = threading.Barrier(2)
        results, errors = [], []
        def solve(cmd, **kw):
            barrier.wait(5)  # both inputs have been written before either solver reads
            return self.solve(cmd, **kw)
        def worker(name):
            try:
                board = pcbnew.LoadBoard(str(Path(name, 'board.kicad_pcb').resolve()))
                results.append(ir.run(board, 'VCC', 'J1.1', [], .1, {}))
            except Exception as e:
                errors.append(e)
        with patch.object(ir.subprocess, 'run', side_effect=solve), patch.object(ir.tempfile, 'tempdir', self.tmp.name):
            workers = [threading.Thread(target=worker, args=(name,)) for name in ('one', 'two')]
            for thread in workers:
                thread.start()
            for thread in workers:
                thread.join(6)
        self.assertFalse(errors)
        self.assertEqual(len(results), 2)
        self.assertNotEqual(results[0]['out'], results[1]['out'])
        for rep in results:
            self.assertEqual(rep['marker'], rep['board'])
            self.assertEqual(Path(rep['svg']).read_text(), rep['board'])

    def test_solver_failure_releases_output(self):
        out = str(Path('failed').resolve())
        self.cli('old.kicad_pcb', out)
        with patch.object(ir.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='controlled failure')):
            with self.assertRaisesRegex(RuntimeError, 'controlled failure'):
                ir.run(self.board, 'VCC', 'J1.1', [], .1, {}, out)
        self.assertFalse(Path(out, 'irdrop.json').exists())
        self.assertFalse(Path(out, 'irdrop.svg').exists())
        self.cli('board.kicad_pcb', out)

    def test_check_default_and_relative_explicit_out(self):
        # Load only the integration function; the rest of pcbcheck needs native CAD.
        tree = ast.parse((SCRIPTS / 'pcbcheck.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'check_irdrop')
        ns = dict(os=os, re=re, NOT_CHECKED=[], COVERAGE=[], row=lambda *a, **kw: None,
                  pcbq=SimpleNamespace(fp_map=lambda b: {}, pad_of=lambda *a: SimpleNamespace(GetNetname=lambda: 'VCC')))
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'pcbcheck.py', 'exec'), ns)
        cfg = {'irdrop': {'sources': {'VCC': 'J1.1'}}, 'feeds': [{'pad': 'J2.1', 'amps': 1}]}
        with patch.dict(sys.modules, pcbir=ir), patch.object(ir.tempfile, 'tempdir', self.tmp.name):
            ns['check_irdrop'](cfg, None, self.board)
            ns['check_irdrop'](cfg, None, self.board)
            self.assertEqual(len(list(Path('.').glob('pcb-irdrop-check-*/VCC-J2.1/irdrop.json'))), 2)
            cfg['irdrop']['out'] = 'check relative'
            ns['check_irdrop'](cfg, None, self.board)
            self.assertTrue(Path('check relative/VCC-J2.1/irdrop.json').is_file())


if __name__ == '__main__':
    unittest.main()
