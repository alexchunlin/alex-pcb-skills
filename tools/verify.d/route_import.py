"""Check run_engine import outcomes with controlled dependencies."""
import argparse
import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def function_code(source_path):
    source_path = source_path.resolve()
    source = source_path.read_bytes()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "run_engine")
    metadata = {"source_path": str(source_path), "source_sha256": sha(source)}
    return compile(ast.Module(body=[node], type_ignores=[]), str(source_path), "exec"), metadata, source


def run_case(root, import_ok, code, stale=False):
    name = "import-true" if import_ok else "import-false"
    case = root / (name + "-stale" if stale else name)
    case.mkdir()
    board = case / "input.kicad_pcb"
    board.write_text("CONTROL TEXT ONLY; not KiCad geometry\n")
    jar, java = case / "fake.jar", case / "fake.java"
    jar.write_text("not executable\n")
    java.write_text("not executable\n")
    output, log = case / "output", case / "route.log"
    events = []
    stale_text = "PREEXISTING OUTPUT CONTROL; must remain untouched on false import\n"
    if stale:
        output.mkdir()
        (output / board.name).write_text(stale_text)

    def event(call, **details):
        events.append({"sequence": len(events) + 1, "call": call, **details})

    def load_board(path):
        event("pcbnew.LoadBoard", path=path)
        return {"source": path, "imported": False}

    def export_dsn(value, path):
        event("pcbnew.ExportSpecctraDSN", board=dict(value), path=path, returns=True)
        Path(path).write_text("FAKE DSN; no geometry\n")
        return True

    def run_java(argv, **kwargs):
        event("subprocess.run", argv=argv, kwargs=kwargs, returncode=0)
        ses = Path(argv[argv.index("-do") + 1])
        ses.write_text("FAKE SES; no geometry\n")
        event("fake_java.created_ses", path=str(ses))
        return SimpleNamespace(returncode=0, stdout="controlled Java success; never launched", stderr="controlled Java stderr")

    def import_ses(value, path):
        event("pcbnew.ImportSpecctraSES", board_before=dict(value), path=path, returns=import_ok)
        if import_ok:
            value["imported"] = True
        return import_ok

    def unfill_and_save(value, path):
        # Deliberately a fake dependency: observes whether run_engine calls its
        # save helper after a false importer result, without implementing CAD.
        event("unfill_and_save", board=dict(value), path=path)
        write(Path(path), {"fake_saved_board": True, "imported": value["imported"], "source": value["source"]})
        event("fake_helper.saved_output", path=path, imported=value["imported"])

    namespace = {"__name__": "controlled_run_engine", "os": os, "sys": sys,
                 "pcbnew": SimpleNamespace(LoadBoard=load_board, ExportSpecctraDSN=export_dsn, ImportSpecctraSES=import_ses),
                 "subprocess": SimpleNamespace(run=run_java), "unfill_and_save": unfill_and_save,
                 "FR_JAR": str(jar), "JAVA": str(java),
                 "FR_ARGS": ["-mt", "4", "-da", "--gui.enabled=false", "--logging.file.enabled=false"]}
    exec(code, namespace)
    result = namespace["run_engine"]("freerouting", str(board), str(output), 1, str(log))
    routed = output / board.name
    record = {"importer_return": import_ok, "preexisting_output": stale, "events": events,
              "returned_tuple": list(result), "returned_tuple_repr": repr(result),
              "output_exists": routed.exists(), "output_path": str(routed),
              "output_content": routed.read_text() if routed.exists() else None,
              "log_content": log.read_text(),
              "save_called_after_false_import": not import_ok and any(e["call"] == "unfill_and_save" for e in events),
              "reported_routed_path_with_rc_zero": result[0] == str(routed) and result[2] == 0,
              "fake_helper_boundary": "helper records invocation and writes control JSON; no native UnFill/SaveBoard was called"}
    write(case / "trace.json", record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    code, metadata, source = function_code(args.source)
    output = args.output.resolve()
    output.mkdir()
    (output / "pcbroute.tested.py").write_bytes(source)
    records = [run_case(output, True, code), run_case(output, False, code),
               run_case(output, False, code, stale=True)]
    prefix = ["pcbnew.LoadBoard", "pcbnew.ExportSpecctraDSN", "subprocess.run",
              "fake_java.created_ses", "pcbnew.LoadBoard", "pcbnew.ImportSpecctraSES"]
    checks = []
    for record in records:
        calls = [event["call"] for event in record["events"]]
        log = record["log_content"]
        if record["importer_return"]:
            assert calls == prefix + ["unfill_and_save", "fake_helper.saved_output"]
            assert record["reported_routed_path_with_rc_zero"] and record["output_exists"]
            assert json.loads(record["output_content"])["imported"] is True
            assert "ImportSpecctraSES failed" not in log
        else:
            assert calls == prefix
            assert record["returned_tuple"][0] is None and record["returned_tuple"][2] == 1
            assert not record["save_called_after_false_import"]
            assert "ImportSpecctraSES failed for " in log
            if record["preexisting_output"]:
                assert record["output_content"] == "PREEXISTING OUTPUT CONTROL; must remain untouched on false import\n"
                assert record["output_exists"]
            else:
                assert not record["output_exists"]
        assert "rc=0 wall=" in log  # Java's result is retained separately from import failure.
        assert "controlled Java success; never launched" in log and "controlled Java stderr" in log
        checks.append({"importer_return": record["importer_return"],
                       "preexisting_output": record["preexisting_output"], "passed": True})
    result = {"source": metadata, "python": sys.version, "native_invocations": 0,
              "java_invocations": 0, "checks": checks, "all_passed": True,
              "limits": "Exact modified Python function with controlled native/helper dependencies; no native failure or PCB acceptance claim."}
    write(output / "summary.json", result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
