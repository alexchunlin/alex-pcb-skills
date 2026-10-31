"""Cases for tools/verify_select.py (verify_all.sh --changed). Plain python3; prints PASS/FAIL lines.
    python3 -I tools/verify.d/verify_select_cases.py <repo root>
1. The map: every section guarded with a non-empty watch, unique IDs, no code outside sections and plumbing, every
   pattern matches a tracked file, every tracked file maps somewhere (a watch or none:).
2. Fake changed-file lists -> the exact plan.
3. The real `--dry-run` parses and selects ALL with no --changed.
"""
import importlib.util, os, re, subprocess, sys

ROOT = os.path.abspath(sys.argv[1])
spec = importlib.util.spec_from_file_location("verify_select", os.path.join(ROOT, "tools", "verify_select.py"))
VS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VS)


def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "verify_select: " + msg)


M = VS.load(ROOT)
IDS = M["ids"]
FILES = subprocess.run(["git", "-C", ROOT, "ls-files", "--cached", "--others", "--exclude-standard"],
                       capture_output=True, text=True, check=True).stdout.split()
VA_LINES = open(os.path.join(ROOT, VS.VA)).read().split("\n")
REGION = M["region"]
SECTIONS = [u for u in M["units"] if u["kind"] == "section"]
SCRIPTS = [u for u in M["units"] if u["kind"] == "script"]
S = "skills/kicad-design/scripts/"
SELF = "verify_select.sh"

code = lambda l: l.strip() and not l.strip().startswith("#")
first = SECTIONS[0]["start"]
loose = [n for n in range(first, len(VA_LINES) + 1) if REGION[n] == ("global",) and code(VA_LINES[n - 1])]
say(not loose and len(set(IDS)) == len(IDS), "%d sections, unique IDs, no code outside sections/plumbing after the first section: %s" % (len(SECTIONS), loose or "ok"))
empty = [u["id"] for u in SECTIONS if not [p for p in u["watch"] if not p.startswith("!")]]
say(not empty, "every section's watch: is non-empty: %s" % (empty or "all"))
nohdr = [u["id"] for u in SCRIPTS if not u["has_watch"]]
say(not nohdr, "every tools/verify.d/*.sh has a # watch: header (%d scripts)" % len(SCRIPTS))
dead = ["%s: %s" % (u["id"], p) for u in M["units"] for p in u["pats"].pats if not p.startswith("!") and not any(VS.glob_re(p).match(f) for f in FILES)]
say(not dead, "every watch pattern matches a tracked file: %s" % (dead or "all"))
unmapped = [f for f in FILES if not any(u["pats"].match(f) for u in M["units"]) and not M["none"].match(f)]
say(not unmapped, "every tracked file is watched or none: (%d files): %s" % (len(FILES), unmapped[:8] or "all"))


def sel(paths):
    p = VS.plan(M, {x: None for x in paths})
    return "ALL" if p["all"] else set(p["run"])


def fmt(s):
    return s if s == "ALL" else " ".join(sorted(s, key=str))


CASES = [
    ("docs only", ["docs/STATUS.md", "README.md", "docs/upstream/01-symbol-fields.md", "bench/design/REVIEW.md"], set()),
    ("FINDINGS.md (section 20 reads it)", ["docs/FINDINGS.md"], {"20"}),
    ("a review-skill doc (section 20)", ["skills/pcb-design-review/rubric.md"], {"20"}),
    ("pcbsch.py (the bench does not run schfix)", [S + "pcbsch.py"], {"19", "16"}),
    ("the skidl checks.json", ["examples/rung1-skidl-a1/checks.json"], {"14", "20", "bench.sh"}),
    ("bench labels", ["tools/bench/labels.json"], {"bench.sh"}),
    ("the selector", ["tools/verify_select.py"], set()),
    ("a new unmapped tools dir", ["tools/newtool/run.py"], "ALL"),
    ("pcblib (the bench runs drc, check, fab only)", [S + "pcblib/board.py"], {"17", "18", "19", "16"}),
    ("a plink archive", ["examples/plink/v1-fb32540.tar.gz"], {"bench.sh"}),
]
for name, paths, want in CASES:
    want = want if want == "ALL" else want | {SELF}
    got = sel(paths)
    say(got == want, "%s -> %s" % (name, fmt(got)) if got == want else "%s -> got %s, want %s" % (name, fmt(got), fmt(want)))
p = VS.plan(M, {"tools/newtool/run.py": None})
say(p["all"] == ["unmapped: tools/newtool/run.py"], "an unmapped path says why: %s" % p["all"])
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--dry-run"], capture_output=True, text=True)
say(r.returncode == 0 and "every section and script runs" in r.stdout, "verify_all.sh --dry-run without --changed selects everything")
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--changed", "--dry-run", "--files", "docs/STATUS.md"], capture_output=True, text=True)
say(r.returncode == 0 and "no tests affected" in r.stdout, "verify_all.sh --changed --dry-run --files docs/STATUS.md: no tests affected")
