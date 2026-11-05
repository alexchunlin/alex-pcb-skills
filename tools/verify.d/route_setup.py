"""Check c_auto postpass settings and selected output with controlled measurements."""
import argparse
import ast
import builtins
import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
ORIGINAL = {"track_width": 0.2, "clearance": 0.2}
CHANGED = {"track_width": 0.1, "clearance": 0.2}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def code():
    path = ROOT.parents[1] / "skills/kicad-design/scripts/pcbroute.py"
    source = path.read_bytes()
    names = {"opt", "new_errors", "c_auto"}
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    provenance = {"source_path": str(path), "source_sha256": sha(source)}
    return compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), provenance


def run_case(root, name, route_settings, postpass=None, restore=False, post_airwires=0):
    case = root / name
    case.mkdir()
    events, emitted = [], []
    measurements = [{"parent": "pass0", "settings": ORIGINAL, "airwires": 1},
                    {"parent": "pass1", "settings": route_settings, "airwires": 1 if postpass == "stitch" else 0}]
    post_settings = ORIGINAL if restore else route_settings
    if postpass:
        measurements.append({"parent": postpass, "settings": post_settings, "airwires": post_airwires})
    consumed = []

    def event(call, **details):
        events.append({"sequence": len(events) + 1, "call": call, **details})

    def fake_board(path, settings, airwires, reason):
        value = {"CONTROL_JSON_NOT_KICAD": True, "settings": settings, "airwires": airwires}
        write(path, value)
        write(path.with_suffix(".kicad_pro"), {"CONTROL_JSON_NOT_KICAD": True, "settings": settings})
        event("fake_output_write", path=str(path), reason=reason, content=value,
              project_path=str(path.with_suffix('.kicad_pro')))

    board = case / "input.kicad_pcb"
    fake_board(board, ORIGINAL, 1, "initial control")
    destination = case / "result.kicad_pcb"
    work = case / "work"
    arguments = [str(board), "--engine", "krt", "--max-pass", "1", "--work", str(work), "--out", str(destination)]
    if postpass != "islands":
        arguments.append("--no-islands")
    invocation = list(arguments)

    def canonical(path):
        event("canonical", path=path, effect="controlled no-op")

    def measure(args):
        index = len(consumed)
        if index >= len(measurements):
            raise AssertionError("unexpected extra measurement")
        frame = measurements[index]
        path = Path(args[0])
        actual = json.loads(path.read_text())
        assert path.parent.name == frame["parent"], (path, frame)
        assert actual["settings"] == frame["settings"] and actual["airwires"] == frame["airwires"]
        result = {"settings": copy.deepcopy(frame["settings"]), "ratsnest": {"airwires": frame["airwires"]},
                  "open": {"CONTROL_NET": frame["airwires"]} if frame["airwires"] else {},
                  "vias": 1, "tracks": 1, "length_mm": 1.0, "min_width_mm": 0.2,
                  "clusters": {}, "length_per_layer_mm": {"F.Cu": 1.0},
                  "drc": {"plain_errors": 0, "packed_errors": 0, "plain_by_type": {}}}
        consumed.append(copy.deepcopy(frame))
        event("c_measure", args=args, measurement_index=index, result=result)
        return result

    def run_engine(engine, source, out_dir, pass_no, log, inner_tracks):
        event("run_engine", engine=engine, source=source, out_dir=out_dir, pass_no=pass_no,
              log=log, inner_tracks=inner_tracks, effect="fake route; no process")
        path = Path(out_dir) / Path(source).name
        fake_board(path, route_settings, measurements[1]["airwires"], "fake routing result")
        return str(path), 0.0, 0

    class FakeBoard:
        def __init__(self, path):
            self.path = path

        def fill(self):
            event("Board.fill", path=self.path, effect="controlled no-op; no native fill")

        @staticmethod
        def load(path):
            event("Board.load", path=path, effect="fake object only")
            return FakeBoard(path)

    def stitch(path, drc_path, clusters, settings):
        assert postpass == "stitch"
        event("stitch", path=path, drc_path=drc_path, clusters=clusters, settings=settings)
        fake_board(Path(path), post_settings, post_airwires, "fake stitch candidate")
        return [{"action": "CONTROL_STITCH"}]

    def islands(args):
        assert postpass == "islands"
        event("c_ground_islands", args=args)
        fake_board(Path(args[0]), post_settings, post_airwires, "fake islands candidate")
        return {"placed": ["CONTROL_PLACEMENT"], "skipped": []}

    def say(*args):
        event("say", args=args)
        emitted.append(" ".join(str(value) for value in args))

    def traced_copy(source, target, *args, **kwargs):
        result = shutil.copy(source, target, *args, **kwargs)
        event("shutil.copy", source=str(source), target=str(target),
              resulting_sha256=sha(Path(result).read_bytes()))
        return result

    def traced_open(path, mode="r", *args, **kwargs):
        event("open", path=str(path), mode=mode)
        return builtins.open(path, mode, *args, **kwargs)

    namespace = {"__name__": "controlled_c_auto", "os": os, "json": json, "OUT": emitted, "say": say,
                 "canonical": canonical, "c_measure": measure, "run_engine": run_engine, "Board": FakeBoard,
                 "stitch": stitch, "c_ground_islands": islands, "open": traced_open}
    extracted, provenance = code()
    exec(extracted, namespace)
    original_shutil = sys.modules["shutil"]
    sys.modules["shutil"] = SimpleNamespace(copy=traced_copy)
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            returned = namespace["c_auto"](arguments)
    finally:
        sys.modules["shutil"] = original_shutil
    assert consumed == measurements, "measurement sequence was not consumed exactly"
    assert sum(e["call"] == "run_engine" for e in events) == 1
    assert sum(e["call"] == "stitch" for e in events) == (postpass == "stitch")
    assert sum(e["call"] == "c_ground_islands" for e in events) == (postpass == "islands")
    saved_route = json.loads((case / "route.json").read_text())
    serialized_return = json.loads(json.dumps(returned))
    assert all(saved_route[k] == value for k, value in serialized_return.items() if k != "exit")
    record = {"case": name, "argv": invocation, "source_sha256": provenance["source_sha256"],
              "expected_measurements": measurements, "consumed_measurements": consumed,
              "events": events, "emitted_lines": emitted, "stdout": stdout.getvalue(), "returned": serialized_return,
              "effective_exit": returned.get("exit", 0), "output_content": json.loads(destination.read_text()),
              "output_project": json.loads(destination.with_suffix('.kicad_pro').read_text()),
              "route_json": saved_route,
              "stipulation": "Synthetic control JSON and measurements; routing/Board/fill/canonical/stitch/islands are fakes; real filesystem copies and c_auto decisions only."}
    (case / "stdout.log").write_text(stdout.getvalue())
    write(case / "trace.json", record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir()
    records = [run_case(root, "unchanged-no-postpass", ORIGINAL),
               run_case(root, "changed-no-postpass", CHANGED),
               run_case(root, "changed-retained-islands", CHANGED, "islands"),
               run_case(root, "changed-retained-stitch", CHANGED, "stitch"),
               run_case(root, "restored-original-islands", CHANGED, "islands", restore=True),
               run_case(root, "unchanged-islands", ORIGINAL, "islands"),
               run_case(root, "unchanged-stitch", ORIGINAL, "stitch"),
               run_case(root, "restored-original-stitch", CHANGED, "stitch", restore=True),
               run_case(root, "discarded-islands", CHANGED, "islands", restore=True, post_airwires=1),
               run_case(root, "discarded-stitch", CHANGED, "stitch", restore=True, post_airwires=2)]
    expected_clean = [True, False, False, False, True, True, True, True, False, False]
    for record, clean in zip(records, expected_clean):
        assert record["returned"]["clean"] == clean
        assert record["effective_exit"] == (0 if clean else 1)
        selected = record["output_content"]["settings"]
        expected_delta = {key: [ORIGINAL[key], value] for key, value in selected.items() if ORIGINAL[key] != value} or False
        assert record["returned"]["final"]["setup_changed"] == expected_delta
        assert record["output_project"]["settings"] == selected
        discarded = record["case"].startswith("discarded-")
        if discarded:
            assert record["returned"]["passes"][-1]["discarded"] is True
            assert selected == CHANGED and record["consumed_measurements"][-1]["settings"] == ORIGINAL
            assert record["returned"]["final"]["airwires"] == (1 if record["case"] == "discarded-stitch" else 0)
    summary = {"source": code()[1], "native_invocations": 0,
               "python": sys.version, "all_passed": True, "cases": [{"name": r["case"], "clean": r["returned"]["clean"],
                   "exit": r["effective_exit"], "pass_setup_changed": [p["setup_changed"] for p in r["returned"]["passes"]],
                   "last_measured_settings": r["consumed_measurements"][-1]["settings"],
                   "selected_output_settings": r["output_content"]["settings"],
                   "postpass_discarded": r["returned"]["passes"][-1].get("discarded", False),
                   "final_reported_setup_changed": r["returned"]["final"]["setup_changed"],
                   "measurements_consumed": len(r["consumed_measurements"])} for r in records]}
    write(root / "summary.json", summary)
    print(json.dumps(summary["cases"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
