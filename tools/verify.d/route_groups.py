"""Text-only identity checks for canonicalization; no native geometry claim."""
import ast
import json
from pathlib import Path
import re
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'skills/kicad-design/scripts/pcbroute.py'
NAMES = {'top_spans', 'track_uuids', 'canonical'}
nodes = [n for n in ast.parse(SOURCE.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
assert len(nodes) == len(NAMES)
functions = {}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), functions)


def uid(number):
    return f'00000000-0000-4000-8000-{number:012d}'


def parse(text):
    """Independent recursive token parser for the controlled s-expressions."""
    tokens = iter(re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text))
    def item(token):
        if token != '(':
            return json.loads(token) if token.startswith('"') else token
        result = []
        for token in tokens:
            if token == ')':
                return result
            result.append(item(token))
        raise ValueError('unclosed expression')
    return item(next(tokens))


def fixture(footprint, duplicate):
    tracks = [f'(segment (start 1 1) (end 2 1) (uuid "{uid(1)}"))',
              f'(arc (start 2 1) (mid 3 2) (end 4 1) (uuid "{uid(2)}"))',
              f'(via (at 4 1) (uuid "{uid(3)}"))']
    members = [uid(1), uid(2), uid(3), uid(6), uid(99)]
    if duplicate:
        tracks.append(tracks[0].replace(uid(1), uid(4)))
        members.append(uid(4))
    label = 'literal ' + uid(1) + ' (members "' + uid(2) + '")'
    other = f'(gr_text {json.dumps(label)} (uuid "{uid(6)}"))'
    group = f'(group {json.dumps(label)} (uuid "{uid(7)}") (members ' + ' '.join(json.dumps(m) for m in members) + '))'
    fp = '(footprint "R" (property "Reference" "R1"))' if footprint else ''
    return '(kicad_pcb ' + ' '.join(tracks + [other, group, fp]) + ')', label


class Groups(unittest.TestCase):
    def test_references_and_idempotence(self):
        for footprint in (False, True):
            for duplicate in (False, True):
                with self.subTest(footprint=footprint, duplicate=duplicate), tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / 'board.kicad_pcb'
                    text, label = fixture(footprint, duplicate)
                    path.write_text(text)
                    functions['canonical'](path)
                    first = path.read_text()
                    board = parse(first)
                    tracks, members = [], None
                    for node in board[1:]:
                        if not isinstance(node, list):
                            continue
                        fields = {n[0]: n[1:] for n in node[1:] if isinstance(n, list)}
                        if node[0] in {'segment', 'arc', 'via'}:
                            tracks.append(fields['uuid'][0])
                        if node[0] == 'group':
                            self.assertEqual(node[1], label)
                            self.assertEqual(fields['uuid'], [uid(7)])
                            members = fields['members']
                        if node[0] == 'gr_text':
                            self.assertEqual(node[1], label)
                            self.assertEqual(fields['uuid'], [uid(6)])
                    self.assertEqual(len(tracks), len(set(tracks)))
                    self.assertEqual(set(members), set(tracks) | {uid(6), uid(99)})
                    functions['canonical'](path)
                    self.assertEqual(path.read_text(), first)


if __name__ == '__main__':
    unittest.main()
