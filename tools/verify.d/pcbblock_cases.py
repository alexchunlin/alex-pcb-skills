"""Pure-Python gate controls; no KiCad process or installed pcbnew required."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / 'skills/kicad-design/scripts/pcbblock.py'
sys.modules['pcbnew'] = types.SimpleNamespace(ToMM=lambda x: x)
spec = importlib.util.spec_from_file_location('pcbblock', SCRIPT)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = str(self.root / 'blocks.json')
        self.cfg = str(self.root / 'checks.json')
        Path(self.cfg).write_text('{}')
        self.data = {'order': ['A', 'B'], 'groups': [
            {'name': 'A', 'refs': ['U1'], 'region': [1, 1, 9, 9]},
            {'name': 'B', 'refs': ['U2'], 'region': [11, 1, 19, 9]}]}
        Path(self.path).write_text(json.dumps(self.data))
        self.positions = {'U1': [5, 5], 'U2': [30, 30]}
        self.f = {r: types.SimpleNamespace(
            GetPosition=lambda r=r: types.SimpleNamespace(x=self.positions[r][0], y=self.positions[r][1]),
            GetOrientationDegrees=lambda: 0, GetLayer=lambda: 0) for r in self.positions}
        for name, value in [('fps', lambda b: self.f), ('outline', lambda b: (0, 0, 20, 20)),
                            ('box', lambda f: (f.GetPosition().x - .1, f.GetPosition().x + .1, f.GetPosition().y - .1, f.GetPosition().y + .1)),
                            ('overlaps', lambda a, b: a is b)]:
            ctx = patch.object(p, name, value)
            ctx.start(); self.addCleanup(ctx.stop)
        ctx = patch.object(p.pcbnew, 'LoadBoard', lambda b: object(), create=True)
        ctx.start(); self.addCleanup(ctx.stop)
        p.write_log(self.path, {'cmd': 'plan', 'ok': True, 'plan_signature': p.plan_signature('board', p.load(self.path))})

    def call(self, fn, args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exc:
            fn(args)
        return exc.exception.code, out.getvalue()

    def checker(self, rows=None, rc=0, output=True, stderr='', raw=None):
        def run(args, **kwargs):
            if output:
                Path(args[args.index('--out') + 1]).write_text(raw if raw is not None else json.dumps({
                    'rows': rows or [], 'summary': {'fails': sum(r['status'] == 'fail' for r in rows or [])}}))
            return types.SimpleNamespace(returncode=rc, stderr=stderr, stdout='')
        return patch.object(p.subprocess, 'run', run)

    def gate(self, name='A'):
        return self.call(p.c_gate, ['board', self.path, name, '--config', self.cfg])

    def test_checker_success(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)

    def test_missing_netlist(self):
        with self.checker(rc=1, output=False, stderr='pcbcheck: no netlist at board.xml; export netlist'):
            rc, out = self.gate()
        self.assertEqual(rc, 1)
        self.assertIn('netlist', out)

    def test_missing_and_stale_output(self):
        for stale in [False, True]:
            with self.subTest(stale=stale):
                if stale:
                    (self.root / 'blocks-gate-check.json').write_text('{"rows": []}')
                with self.checker(output=False):
                    self.assertEqual(self.gate()[0], 1)

    def test_crash_exit_with_json(self):
        with self.checker(rc=2):
            self.assertEqual(self.gate()[0], 1)

    def test_malformed_report(self):
        for raw in ['{', '{}', 'null', '{"rows": [null]}', '{"rows": [], "summary": {"fails": 1}}']:
            with self.subTest(raw=raw), self.checker(raw=raw):
                self.assertEqual(self.gate()[0], 1)

    def test_fail_rows(self):
        for objs, expected in [([], 1), (['U1.1'], 1), (['U2.1'], 0), (['U1.1', 'U2.1'], 1), (['unknown'], 1)]:
            with self.subTest(objects=objs), self.checker([{'status': 'fail', 'id': 'decoupling:failure', 'msg': 'bad', 'objects': objs}], rc=1):
                self.assertEqual(self.gate()[0], expected)

    def test_failed_regate_revokes_pass(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)
            self.positions['U1'] = [0, 0]
            self.assertEqual(self.gate()[0], 1)
        self.positions['U1'] = [5, 5]
        rc, out = self.call(p.c_report, ['board', self.path, '--json'])
        self.assertEqual(rc, 1)
        self.assertNotIn('A', json.loads(out)['gates_passed'])
        self.assertEqual(len(p.read_log(self.path)), 3)

    def test_regate_earlier_invalidates_suffix(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)
            self.positions['U2'] = [15, 5]
            self.assertEqual(self.gate('B')[0], 0)
            self.positions['U2'] = [30, 30]
            self.assertEqual(self.gate('A')[0], 0)
        _, out = self.call(p.c_report, ['board', self.path, '--json'])
        self.assertEqual(json.loads(out)['gates_passed'], ['A'])
        self.assertEqual(len(p.read_log(self.path)), 4)

    def test_latest_failed_plan_blocks_gate(self):
        p.write_log(self.path, {'cmd': 'plan', 'ok': False})
        with self.checker():
            self.assertEqual(self.gate()[0], 1)

    def test_edge_skip_refs(self):
        Path(self.cfg).write_text('{"edge_margin": {"skip_refs": ["U1"]}}')
        self.positions['U1'] = [.5, 5]
        self.data['groups'][0]['region'] = [0, 0, 9, 9]
        Path(self.path).write_text(json.dumps(self.data))
        p.write_log(self.path, {"cmd": "plan", "ok": True, "plan_signature": p.plan_signature("board", p.load(self.path))})
        with self.checker():
            self.assertEqual(self.gate()[0], 0)

    def test_missing_footprint_fails(self):
        del self.f['U1']
        with self.checker():
            self.assertEqual(self.gate()[0], 1)

    def test_mechanical_ref_not_compared_to_itself(self):
        self.data['groups'][0]['refs'].append('H1')
        self.positions['H1'] = [5, 5]
        self.f['H1'] = self.f['U1']
        # Distinct objects for U1 and H1; overlap stub reports identity only.
        self.f['H1'] = types.SimpleNamespace(**vars(self.f['U1']))
        Path(self.path).write_text(json.dumps(self.data))
        p.write_log(self.path, {"cmd": "plan", "ok": True, "plan_signature": p.plan_signature("board", p.load(self.path))})
        with self.checker():
            self.assertEqual(self.gate()[0], 0)

    def test_skip_refs_does_not_skip_region_or_checker(self):
        Path(self.cfg).write_text('{"edge_margin": {"skip_refs": ["U1"]}}')
        self.positions['U1'] = [0, 0]
        with self.checker():
            self.assertEqual(self.gate()[0], 1)
        self.positions['U1'] = [5, 5]
        with self.checker([{'status': 'fail', 'id': 'decoupling:U1', 'msg': 'bad', 'objects': ['U1']}], rc=1):
            self.assertEqual(self.gate()[0], 1)

    def test_move_requires_regating_before_successor(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)
            self.positions['U1'] = [6, 5]
            self.positions['U2'] = [15, 5]
            self.assertEqual(self.gate('B')[0], 1)
        rc, out = self.call(p.c_report, ['board', self.path, '--json'])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)['gates_passed'], [])

    def test_rotation_and_layer_change_invalidate_gate(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)
        for method, value in [('GetOrientationDegrees', 90), ('GetLayer', 31)]:
            with self.subTest(method=method), patch.object(self.f['U1'], method, lambda: value):
                rc, out = self.call(p.c_report, ['board', self.path, '--json'])
                self.assertEqual(rc, 1)
                self.assertIn('U1', json.loads(out)['moved_after_gate'])
                self.assertEqual(json.loads(out)['gates_passed'], [])

    def test_report_success_and_replan_reset(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)
            self.positions['U2'] = [15, 5]
            self.assertEqual(self.gate('B')[0], 0)
        self.assertEqual(self.call(p.c_report, ['board', self.path, '--json'])[0], 0)
        p.write_log(self.path, {'cmd': 'plan', 'ok': True, 'plan_signature': p.plan_signature('board', p.load(self.path))})
        rc, out = self.call(p.c_report, ['board', self.path, '--json'])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out)['gates_passed'], [])

    def test_plan_area_separate_layers(self):
        self.data['groups'] = [{'name': 'A', 'refs': ['U1', 'U2'], 'region': [0, 0, 10, 10]}]
        self.data['order'] = ['A']
        Path(self.path).write_text(json.dumps(self.data))
        with patch.object(p, 'courtyard', lambda f: types.SimpleNamespace(Area=lambda: 60e12)), patch.dict(p.os.environ, {'KRT_PY': '/nonexistent-krt-python'}):
            self.f['U2'].GetLayer = lambda: 31
            self.assertEqual(self.call(p.c_plan, ['board', self.path])[0], 0)
            self.f['U2'].GetLayer = lambda: 0
            self.assertEqual(self.call(p.c_plan, ['board', self.path])[0], 1)

    def test_launch_error(self):
        with patch.object(p.subprocess, 'run', side_effect=OSError('cannot execute checker')):
            rc, out = self.gate()
        self.assertEqual(rc, 1)
        self.assertIn('cannot execute checker', out)


    def test_bad_config_fails_even_if_checker_succeeds(self):
        for content in ['{', 'null', '{"edge_margin": {"skip_refs": "U1"}}']:
            Path(self.cfg).write_text(content)
            with self.subTest(config=content), self.checker():
                self.assertEqual(self.gate()[0], 1)

    def test_exit_one_without_failure_rows_is_error(self):
        with self.checker(rc=1):
            self.assertEqual(self.gate()[0], 1)

    def test_out_of_order(self):
        self.positions['U2'] = [15, 5]
        with self.checker():
            rc, out = self.gate('B')
        self.assertEqual(rc, 1)
        self.assertIn('out of order: the next block is A', out)


    def test_changed_plan_revokes_history(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)
            self.positions['U2'] = [15, 5]
            self.assertEqual(self.gate('B')[0], 0)
            for group in self.data['groups']:
                group['refs'] = []
            Path(self.path).write_text(json.dumps(self.data))
            self.assertEqual(self.gate()[0], 1)
        rc, out = self.call(p.c_report, ['board', self.path, '--json'])
        self.assertEqual(rc, 1)
        self.assertFalse(json.loads(out)['plan_valid'])
        self.assertEqual(json.loads(out)['gates_passed'], [])

    def test_changed_config_revokes_history(self):
        with self.checker():
            self.assertEqual(self.gate()[0], 0)
        Path(self.cfg).write_text('{"decoupling": {"max_mm": 1}}')
        _, out = self.call(p.c_report, ['board', self.path, '--json'])
        self.assertEqual(json.loads(out)['gates_passed'], [])

    def test_legacy_plan_requires_replan(self):
        p.write_log(self.path, {'cmd': 'plan', 'ok': True})
        with self.checker():
            rc, out = self.gate()
        self.assertEqual(rc, 1)
        self.assertIn('legacy logs require re-planning', out)

    def test_other_board_cannot_borrow_plan(self):
        rc, out = self.call(p.c_report, ['another-board', self.path, '--json'])
        self.assertEqual(rc, 1)
        self.assertFalse(json.loads(out)['plan_valid'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
