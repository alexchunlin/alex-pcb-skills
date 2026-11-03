#!/usr/bin/env python3
"""Spike #3, C1: add the `irdrop` row's locators to the five feed labels and one known true positive, as text (the file's
own formatting kept). Idempotent. python3 -I tools/spikes/spike3/label_irdrop.py"""
import json
from pathlib import Path

P = Path(__file__).resolve().parents[3] / "tools/bench/labels.json"
# label id -> (the existing check locator it follows, the irdrop pattern): each names the place the reviewer named
ADD = {
    "R2-S-1": ("^check fail feeds:U2\\\\.11: .*1 via\\\\(s\\\\) within 2\\\\.0 mm = 1\\\\.22 A",
               r"^check fail irdrop:VIN:(via@117\.6\d*,127\.0|neck:F\.Cu@\S+: .* by U2\.11)"),
    "R2-O-2": ("^check fail feeds:U2\\\\.11: .*total 0\\\\.00 A; a pour also reaches the pad",
               r"^check fail irdrop:VIN:neck:F\.Cu@1(2[89]|3[0-4])\.\d+,11[67]\.\d+: 0\.[23]\d* mm wide"),
    "R2-F-3": ("^check fail feeds:U1\\\\.11: .*total 1\\\\.36 A",
               r"^check fail irdrop:VIN:neck:F\.Cu@\S+: .* by U1\.11"),
    "R2A2-O-1": ("^check fail feeds:J3\\\\.1: .*total 0\\\\.00 A; a pour also reaches the pad",
                 r"^check fail irdrop:5V:neck:In2\.Cu@\S+: .* by J3\.1"),
    "R2A2-O-2": ("^check fail feeds:C17\\\\.1: .*total 0\\\\.00 A",
                 r"^check fail irdrop:VIN:via@.*\(solve: C17\.1\)"),
}
KTP = {"attempt": "rung2-zener-a2-opus", "report": "check", "pattern": r"^check fail irdrop:5V:via@13[47]\.\d+,127\.6",
       "why": "spike #3 C1: L1.2's 3 A of 5V reaches the In2 plane through two single 0.3 mm vias (1.66 + 1.35 A against "
              "1.22 A each by the feeds row's own IPC formula); the reviewer's L1.2 feeds row passed on the 1.4 mm track "
              "touching the pad, which is not where the J3 current goes"}

t = P.read_text()
for lid, (after, pat) in ADD.items():
    if json.dumps(pat) in t:
        continue
    old = f'     "pattern": "{after}"\n    }}'
    assert t.count(old) == 1, (lid, t.count(old))
    t = t.replace(old, old + ',\n    {\n     "report": "check",\n     "pattern": ' + json.dumps(pat) + "\n    }")
if json.dumps(KTP["pattern"]) not in t:
    old = ' "known_true_positives": [\n'
    assert t.count(old) == 1
    t = t.replace(old, old + "  " + json.dumps(KTP) + ",\n")
json.loads(t)
P.write_text(t)
print("labels: irdrop locators on", ", ".join(ADD), "+ 1 known true positive")
