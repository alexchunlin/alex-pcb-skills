"""Filesystem-only negative controls; never launch CAD or a regeneration command."""
import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('pcbcli', root / 'skills/kicad-design/scripts/pcbcli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
failed = 0
for case in ('equal', 'ancestor', 'nested', 'symlink-nested', 'symlink-project', 'sibling', 'default'):
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / 'project'
        project.mkdir()
        sentinel = project / 'source.txt'
        sentinel.write_text('preserve me')
        alias = base / 'alias'
        alias.symlink_to(project, target_is_directory=True)
        output = {'equal': project, 'ancestor': base, 'nested': project / 'results',
                  'symlink-nested': alias / 'results', 'symlink-project': alias,
                  'sibling': base / 'project-output', 'default': None}[case]
        args = argparse.Namespace(project=str(project), out=str(output) if output else None,
                                  cmd='true', board='test.kicad_pcb', generated=None)
        rejected = False
        measured = False
        # Stop a valid run at its first measurement, before any external program.
        with patch.object(cli.tempfile, 'gettempdir', return_value=str(base)), \
             patch.object(cli, 'gui_pids', return_value=[]), \
             patch.object(cli, 'measure_tree', side_effect=RuntimeError('measurement reached')):
            try:
                cli.cmd_regen_check(args)
            except SystemExit as exc:
                rejected = 'output directory must not overlap' in str(exc)
            except RuntimeError:
                measured = True
            except OSError:
                pass
        safe = case in ('sibling', 'default')
        passed = sentinel.exists() and sentinel.read_text() == 'preserve me' and (measured if safe else rejected)
        print(('PASS' if passed else 'FAIL') + ' regen output ' + case)
        failed += not passed
for case in ('absolute', 'traversal', 'symlink-parent', 'root', 'safe-file', 'safe-dir', 'missing'):
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        project = base / 'project'
        project.mkdir()
        sentinel = project / 'source.txt'
        sentinel.write_text('preserve me')
        (project / 'first.txt').write_text('validate all before deleting any')
        (project / 'generated').mkdir()
        (project / 'generated/artifact').write_text('generated')
        (project / 'alias').symlink_to(project, target_is_directory=True)
        target = {'absolute': str(sentinel), 'traversal': '../../project/source.txt',
                  'symlink-parent': 'alias/source.txt', 'root': '.', 'safe-file': 'source.txt',
                  'safe-dir': 'generated', 'missing': 'not-created'}[case]
        out = base / 'output'
        args = argparse.Namespace(project=str(project), out=str(out), cmd='true',
                                  board='test.kicad_pcb', generated=['first.txt', target], timeout=1)
        rejected = False
        ran = False
        with patch.object(cli, 'gui_pids', return_value=[]), \
             patch.object(cli, 'measure_tree', return_value={}), \
             patch.object(cli.subprocess, 'run', side_effect=RuntimeError('regen reached')):
            try:
                cli.cmd_regen_check(args)
            except SystemExit as exc:
                rejected = 'generated path must stay inside' in str(exc)
            except RuntimeError:
                ran = True
            except OSError:
                pass
        safe = case in ('safe-file', 'safe-dir', 'missing')
        preserved = sentinel.exists() and sentinel.read_text() == 'preserve me'
        if safe:
            passed = preserved and ran and not (out / 'fresh/first.txt').exists()
        else:
            passed = preserved and rejected and (out / 'fresh/first.txt').exists()
        print(('PASS' if passed else 'FAIL') + ' regen generated ' + case)
        failed += not passed
sys.exit(bool(failed))
