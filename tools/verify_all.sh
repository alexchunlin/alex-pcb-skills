#!/bin/sh
# Re-prove every tool in this repo against the rung-1 attempts and the reference boards. Writes only under
# /tmp/alexpcb-verify/run-<pid> (latest: /tmp/alexpcb-verify/latest). About 14 minutes.
#   sh tools/verify_all.sh                       # everything
#   sh tools/verify_all.sh 1 5 7                 # only these sections
#   sh tools/verify_all.sh --changed [BASE] [--dry-run]   # only what the change since merge-base(BASE, HEAD) affects
#                                                # (BASE defaults to main; committed, uncommitted and untracked files)
# Each section opens with `if want ID; then  #@ watch: PATTERNS [needs: IDS]` and closes with `fi  #@ end ID`; each
# tools/verify.d/*.sh script has a `# watch:` header. tools/verify_select.py (ported from alex-3d-skills) maps the changed
# paths onto them and prints the plan first (--dry-run: only the plan). A path nothing watches runs everything, unless
# `#@ none:` says no test reads it. A unit selected under --changed that runs no check fails the run; a section whose
# input is missing on this machine says so with nochecks.
# Inputs (read-only, copied first): RUNS (default ~/code-stuff/alex-pcb-runs) and REF (default /tmp/pcb-ref).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PCB="$ROOT/skills/kicad-design/scripts/pcb"
RUNS="${RUNS:-$HOME/code-stuff/alex-pcb-runs}"
REF="${REF:-/tmp/pcb-ref}"
VT="${VERIFY_TMP:-/tmp/alexpcb-verify}"; V="$VT/run-$$"
rm -rf "$V"; mkdir -p "$V"; ln -sfn "$V" "$VT/latest"
printf '{"commit": "%s", "dirty": %s, "when": "%s"}\n' "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)" \
  "$([ -n "$(git -C "$ROOT" status --porcelain -- skills tools 2>/dev/null)" ] && echo true || echo false)" "$(date +%Y-%m-%dT%H:%M:%S)" > "$V/meta.json"
#@ plumbing
#@ group @cli = skills/kicad-design/scripts/pcb skills/kicad-design/scripts/pcbcli.py
#@ group @q = skills/kicad-design/scripts/pcb skills/kicad-design/scripts/pcbq.py
#@ group @check = skills/kicad-design/scripts/pcb skills/kicad-design/scripts/pcbcheck.py skills/kicad-design/scripts/pcbq.py skills/kicad-design/scripts/pcbcli.py
#@ group @lib = skills/kicad-design/scripts/pcb skills/kicad-design/scripts/pcblib/**
# none: paths no test reads (a watch wins: section 20 reads FINDINGS.md and every skills/**/*.md)
#@ none: docs/** README.md .gitignore bench/design/** tools/bench/README.md tools/bench/results/** tools/verify.d/README
SELECTED=ALL; EXPECT=""; CHANGED=""; RAN=""; CUR=""; CUR_N=0; CUR_OK=""
case "${1:-}" in
  --*) P=$(python3 -I "$ROOT/tools/verify_select.py" "$@") || { rc=$?; printf '%s\n' "$P"; exit $rc; }
       printf '%s\n' "$P" | grep -v -e '^SELECT' -e '^UNITS'
       SELECTED=$(printf '%s\n' "$P" | sed -n 's/^SELECT *//p')
       EXPECT=$(printf '%s\n' "$P" | sed -n 's/^UNITS *//p')
       [ "$SELECTED" = ALL ] || EXPECT="$SELECTED"
       case " $* " in *" --dry-run "*) exit 0 ;; esac
       [ -n "$SELECTED" ] || { echo "verify_all: the selector chose nothing (it always picks verify_select.sh)"; exit 2; }
       CHANGED=1 ;;
  "") ;;
  *) SELECTED="$*" ;;                       # a list of section IDs
esac
pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
# want ID: is this unit selected? Under --changed it also records the unit, and the unit before it must have run a check.
unit_end() {
  [ -n "$CUR" ] && [ -n "$CHANGED" ] && [ -z "$CUR_OK" ] && [ $((pass+fail)) = "$CUR_N" ] && bad "verify_all: $CUR was selected but ran no checks"
  CUR=""; CUR_OK=""
}
want() {
  unit_end
  [ "$SELECTED" = ALL ] || case " $SELECTED " in *" $1 "*) ;; *) return 1 ;; esac
  CUR=$1; CUR_N=$((pass+fail)); RAN="$RAN $1"; return 0
}
nochecks() { echo "NOTE $1"; CUR_OK=1; }   # a selected unit with nothing to check on this machine
#@ plumbing end
jq_() { python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {}, {'d': d}))" "$1" "$2" 2>/dev/null; }
# copies: the tools must never touch the attempts
Z="$V/zener"; K="$V/skidl"
[ -d "$RUNS/rung1-zener-a1" ] && cp -R "$RUNS/rung1-zener-a1" "$Z"
[ -d "$RUNS/rung1-skidl-a1" ] && cp -R "$RUNS/rung1-skidl-a1" "$K"
ZB="$Z/layout/qwiic_imu/qwiic_imu.kicad_pcb"; ZS="$Z/layout/qwiic_imu/qwiic_imu.kicad_sch"
KB="$K/qwiic_imu.kicad_pcb"; KS="$K/qwiic_imu.kicad_sch"
MB="$REF/motorgo-plink-hardware/motorgo_plink/motorgo_plink.kicad_pcb"

if want 1; then  #@ watch: @cli
echo "== 1 dual DRC on rung1-zener-a1: plain 20 errors, raw pack 0, floored pack 20, sentinel fires (R1-Z1-F1)"
if [ -f "$ZB" ]; then
  $PCB drc "$ZB" --out "$V/zdrc" > "$V/zdrc.txt"; rc=$?
  [ "$rc" = 1 ] && ok "zener drc exits 1 on errors" || bad "zener drc exit $rc"
  [ "$(jq_ "$V/zdrc/drc.json" "d['plain']['errors']")" = 20 ] && ok "zener plain 20 errors" || bad "zener plain errors: $(jq_ "$V/zdrc/drc.json" "d['plain']['errors']")"
  [ "$(jq_ "$V/zdrc/drc.json" "sorted(d['plain']['by_type']['error'].items())")" = "[('clearance', 12), ('hole_clearance', 8)]" ] && ok "zener plain types clearance 12 + hole_clearance 8" || bad "zener plain types $(jq_ "$V/zdrc/drc.json" "d['plain']['by_type']")"
  [ "$(jq_ "$V/zdrc/drc.json" "d['packed']['errors']")" = 20 ] && ok "zener floored pack 20 errors (setup enforced through the pack)" || bad "zener floored pack errors $(jq_ "$V/zdrc/drc.json" "d['packed']['errors']")"
  [ "$(jq_ "$V/zdrc/drc.json" "d['sentinel']")" = fired ] && ok "zener sentinel fired" || bad "zener sentinel $(jq_ "$V/zdrc/drc.json" "d['sentinel']")"
  [ "$(jq_ "$V/zdrc/drc.json" "len(d['pack_relaxes_setup'])")" = 19 ] && ok "zener pack relaxes 19 setup minimums" || bad "zener relaxes $(jq_ "$V/zdrc/drc.json" "len(d['pack_relaxes_setup'])")"
  $PCB drc "$ZB" --out "$V/zdrc-raw" --no-floor > "$V/zdrc-raw.txt"
  [ "$(jq_ "$V/zdrc-raw/drc.json" "d['packed']['errors']")" = 0 ] && ok "zener raw pack 0 errors (the designer's number)" || bad "zener raw pack $(jq_ "$V/zdrc-raw/drc.json" "d['packed']['errors']")"
  [ "$(jq_ "$V/zdrc-raw/drc.json" "len(d['masked_by_raw_pack'])")" = 20 ] && ok "zener raw pack masks all 20 plain errors" || bad "zener masked $(jq_ "$V/zdrc-raw/drc.json" "len(d['masked_by_raw_pack'])")"
  [ -z "$(cd "$RUNS" && git status --porcelain 2>/dev/null)" ] || true
  cmp -s "$ZB" "$RUNS/rung1-zener-a1/layout/qwiic_imu/qwiic_imu.kicad_pcb" && ok "zener board untouched by drc" || bad "zener board modified"
else nochecks "no $ZB"; fi
fi  #@ end 1

if want 2; then  #@ watch: @cli
echo "== 2 dual DRC on rung1-skidl-a1: plain 18 errors (R1-S1-F1)"
if [ -f "$KB" ]; then
  $PCB drc "$KB" --out "$V/kdrc" > "$V/kdrc.txt"
  [ "$(jq_ "$V/kdrc/drc.json" "d['plain']['errors']")" = 18 ] && ok "skidl plain 18 errors" || bad "skidl plain $(jq_ "$V/kdrc/drc.json" "d['plain']['errors']")"
  [ "$(jq_ "$V/kdrc/drc.json" "sorted(d['plain']['by_type']['error'].items())")" = "[('clearance', 12), ('hole_clearance', 6)]" ] && ok "skidl types clearance 12 + hole_clearance 6" || bad "skidl types $(jq_ "$V/kdrc/drc.json" "d['plain']['by_type']")"
  $PCB drc "$KB" --out "$V/kdrc-raw" --no-floor > /dev/null
  [ "$(jq_ "$V/kdrc-raw/drc.json" "d['packed']['errors']")" = 0 ] && ok "skidl raw pack 0 errors" || bad "skidl raw pack $(jq_ "$V/kdrc-raw/drc.json" "d['packed']['errors']")"
else nochecks "no $KB"; fi
fi  #@ end 2

if want 3; then  #@ watch: @cli
echo "== 3 dual DRC on the Plink reference board with --pack jlcpcb: per-type cap, library paths through the mirror (P0-T2, P1-T1, P1-T2)"
if [ -f "$MB" ]; then
  t0=$(date +%s); $PCB drc "$MB" --pack jlcpcb --out "$V/mdrc" --no-floor > "$V/mdrc.txt"; t1=$(date +%s)
  [ "$(jq_ "$V/mdrc/drc.json" "d['plain']['by_type']['error']['copper_edge_clearance']")" = 40 ] && ok "plink plain copper_edge_clearance 40 (P0-T2)" || bad "plink edge $(jq_ "$V/mdrc/drc.json" "d['plain']['by_type']")"
  [ "$(jq_ "$V/mdrc/drc.json" "d['plain']['unconnected']")" = 6 ] && ok "plink 6 unconnected" || bad "plink unconnected $(jq_ "$V/mdrc/drc.json" "d['plain']['unconnected']")"
  [ "$(jq_ "$V/mdrc/drc.json" "d['sentinel']")" = fired ] && ok "plink sentinel fired through the resolved jlcpcb 4-layer pack" || bad "plink sentinel $(jq_ "$V/mdrc/drc.json" "d['sentinel']")"
  [ "$(jq_ "$V/mdrc/drc.json" "'track_width(sentinel)' in d['capped_types'] and 'silk_overlap' in d['capped_types']")" = True ] && ok "plink: 199 cap detected on the sentinel and silk_overlap (P1-T2)" || bad "plink cap $(jq_ "$V/mdrc/drc.json" "d['capped_types']")"
  [ "$(jq_ "$V/mdrc/drc.json" "d['packed']['by_type']['warning'].get('lib_footprint_mismatch')")" = 86 ] && ok "plink lib_footprint_mismatch 86 in the mirror = in place (library paths resolve, P1-T1)" || bad "plink lib mismatch $(jq_ "$V/mdrc/drc.json" "d['packed']['by_type']['warning'].get('lib_footprint_mismatch')")"
  echo "NOTE plink dual drc took $((t1-t0)) s"
else nochecks "no $MB (clone motorgo-plink-hardware into $REF)"; fi
fi  #@ end 3

if want 4; then  #@ watch: @cli
echo "== 4 rejected rule pack is detected (P0-T5): bad layer name -> exit 2, sentinel not fired"
if [ -f "$ZB" ]; then
  printf '(version 1)\n(rule "bad layer" (layer "No.Such") (constraint clearance (min 0.1mm)))\n' > "$V/bad.kicad_dru"
  $PCB drc "$ZB" --pack "$V/bad.kicad_dru" --out "$V/zbad" > "$V/zbad.txt"; rc=$?
  [ "$rc" = 2 ] && ok "rejected pack exits 2" || bad "rejected pack exit $rc"
  grep -q "RULE PACK REJECTED" "$V/zbad.txt" && ok "rejected pack said so" || bad "no rejection message"
  printf '(version 1)\n(rule "ok" (constraint clearance (min 0.1mm)))\n' > "$V/ok.kicad_dru"
  $PCB drc "$ZB" --pack "$V/ok.kicad_dru" --out "$V/zok" > "$V/zok.txt"; rc=$?
  [ "$rc" = 1 ] && grep -q "sentinel fired" "$V/zok.txt" && ok "accepted pack: sentinel fired, exit 1 on the plain errors" || bad "accepted pack rc $rc"
else nochecks "no $ZB"; fi
fi  #@ end 4

if want 5; then  #@ watch: @cli
echo "== 5 ERC and netlist on both rung-1 schematics"
for s in "$ZS" "$KS"; do
  [ -f "$s" ] || { nochecks "no $s"; continue; }
  n=$(basename "$(dirname "$s")"); $PCB erc "$s" --out "$V/erc-$n.json" > "$V/erc-$n.txt"; rc=$?
  grep -q "0 errors, 1 warnings" "$V/erc-$n.txt" && [ "$rc" = 0 ] && ok "erc $n: 0 errors 1 warning, exit 0" || bad "erc $n: $(head -1 "$V/erc-$n.txt") rc $rc"
  $PCB netlist "$s" "$V/net-$n.xml" > "$V/net-$n.txt" && grep -q "11 nets" "$V/net-$n.txt" && ok "netlist $n: 11 nets" || bad "netlist $n: $(cat "$V/net-$n.txt")"
done
fi  #@ end 5

if want 6; then  #@ watch: @cli  needs: 5
echo "== 6 connectivity diff (P0-T3): identical, renamed, planted U1 SDA/SCL pin swap, schematic inputs"
if [ -f "$V/net-qwiic_imu.xml" ]; then
  X="$V/net-qwiic_imu.xml"
  $PCB diff "$X" "$X" > "$V/diff1.txt" && ok "diff identical exits 0" || bad "diff identical: $(head -1 "$V/diff1.txt")"
  sed 's/"SDA"/"SDX"/' "$X" > "$V/renamed.xml"
  $PCB diff "$X" "$V/renamed.xml" > "$V/diff2.txt" && grep -q "1 renamed" "$V/diff2.txt" && ok "diff rename-only exits 0 and lists the rename" || bad "diff rename: $(head -1 "$V/diff2.txt")"
  python3 -I -c "
t=open('$X').read(); a='<node ref=\"U1\" pin=\"14\"'; b='<node ref=\"U1\" pin=\"13\"'
open('$V/swapped.xml','w').write(t.replace(a,'@@').replace(b,a).replace('@@',b))"
  $PCB diff "$X" "$V/swapped.xml" --json "$V/diff3.json" > "$V/diff3.txt"; rc=$?
  [ "$rc" = 1 ] && grep -q "CONNECTIVITY CHANGED" "$V/diff3.txt" && ok "diff catches the planted SDA/SCL pin swap (exit 1)" || bad "diff swap rc $rc"
  [ "$(jq_ "$V/diff3.json" "sorted(d['only_in_a'])")" = "['SCL', 'SDA']" ] && ok "diff names the two nets" || bad "diff nets $(jq_ "$V/diff3.json" "d['only_in_a']")"
  $PCB diff "$ZS" "$X" > "$V/diff4.txt" && ok "diff accepts a .kicad_sch input" || bad "diff sch input: $(head -1 "$V/diff4.txt")"
else nochecks "section 5 did not run"; fi
fi  #@ end 6

if want 7; then  #@ watch: @q
echo "== 7 pcb q measurements reproduce the R1-Z1 review (decoupling, coverage, vias, silk, dist)"
if [ -f "$ZB" ]; then
  $PCB q "$ZB" decoupling > "$V/q-dec.txt"
  grep -q "C1(100nF) 3V3 -> U1.8: centre 1.7511" "$V/q-dec.txt" && ok "q decoupling C1 -> U1.8 1.751 mm (review: 1.751)" || bad "q decoupling C1: $(grep C1 "$V/q-dec.txt")"
  grep -q "C2(100nF) 3V3 -> U1.5: centre 1.5125" "$V/q-dec.txt" && ok "q decoupling C2 -> U1.5 1.512 mm (review: 1.512)" || bad "q decoupling C2: $(grep C2 "$V/q-dec.txt")"
  grep -q "'8': 2.6394" "$V/q-dec.txt" && ok "q decoupling C3 lists U1.8 at 2.639 mm (review: 2.639; brief: 2 mm)" || bad "q decoupling C3: $(grep C3 "$V/q-dec.txt")"
  $PCB q "$ZB" dist C3.1 U1.8 | grep -q "centre 2.6394" && ok "q dist C3.1 U1.8 2.639" || bad "q dist"
  $PCB q "$ZB" coverage U1 In1.Cu > "$V/q-cov.txt"; pct=$(sed -n 's/.*GND \([0-9.]*\)%.*/\1/p' "$V/q-cov.txt")
  python3 -I -c "import sys; sys.exit(0 if 90 <= float('$pct' or 0) <= 100 else 1)" && ok "q coverage U1 In1.Cu GND $pct% (review: 93.1% on a 40x40 grid; polygon intersection here)" || bad "q coverage: $(cat "$V/q-cov.txt")"
  $PCB q "$ZB" vias | grep -q "PCBQ vias 25 sizes(dia,drill) \[(0.6, 0.3)\]" && ok "q vias 25 x 0.6/0.3" || bad "q vias"
  $PCB q "$ZB" silk | grep -q "refdes hidden 14 of 15" && ok "q silk: 14 of 15 refdes hidden (R1-Z1-F4)" || bad "q silk"
  $PCB q "$ZB" settings | grep -q "clearance=0.2 track_width=0.2 via_diameter=0.6 through_hole=0.3 hole_clearance=0.3" && ok "q settings" || bad "q settings"
  $PCB q "$ZB" edge --json | python3 -I -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['copper_layers']==4 and d['footprints']==15 else 1)" && ok "q edge --json: 4 layers, 15 footprints" || bad "q edge json"
  $PCB q "$ZB" nets > "$V/q-nets.txt" && [ "$(grep -c '^PCBQ net' "$V/q-nets.txt")" = 11 ] && ok "q nets: 11 nets" || bad "q nets $(grep -c '^PCBQ net' "$V/q-nets.txt")"
  $PCB q "$ZB" holes | tail -1 | grep -q "6 pad holes, 25 vias" && ok "q holes" || bad "q holes"
  $PCB q "$ZB" nosuch > /dev/null 2>&1; [ $? != 0 ] && ok "q unknown command exits non-zero" || bad "q unknown command exit 0"
else nochecks "no $ZB"; fi
fi  #@ end 7

if want 8; then  #@ watch: @cli @q
echo "== 8 pcb fab on the Zener board: 14 gerber files, JLC BOM/CPL, J1/J2 origin offset flagged (R1-S1-F3, R1-S1-F4)"
if [ -f "$ZB" ]; then
  $PCB fab "$ZB" --out "$V/zfab" > "$V/zfab.txt"; rc=$?
  [ "$rc" = 0 ] && ok "fab exits 0" || bad "fab exit $rc: $(cat "$V/zfab.txt")"
  [ "$(jq_ "$V/zfab/fab.json" "len(d['files']['gerbers'])")" = 14 ] && ok "fab 14 files in the zip (11 layers, drill, map, job)" || bad "fab files $(jq_ "$V/zfab/fab.json" "len(d['files']['gerbers'])")"
  [ "$(jq_ "$V/zfab/fab.json" "(d['bom_lines'], d['bom_missing_lcsc'], d['cpl_lines'], d['dnp'])")" = "(5, [], 8, ['J3'])" ] && ok "fab BOM 5 lines all with LCSC, CPL 8 parts, J3 DNP excluded" || bad "fab bom/cpl $(jq_ "$V/zfab/fab.json" "(d['bom_lines'], d['bom_missing_lcsc'], d['cpl_lines'], d['dnp'])")"
  [ "$(jq_ "$V/zfab/fab.json" "sorted(d['cpl_origin_offsets_mm'])")" = "['J1', 'J2']" ] && ok "fab flags the JST origin offset on J1, J2 (R1-S1-F4)" || bad "fab offsets $(jq_ "$V/zfab/fab.json" "d['cpl_origin_offsets_mm']")"
  head -1 "$V/zfab/qwiic_imu_cpl_jlcpcb.csv" | grep -q "^Designator,Mid X,Mid Y,Layer,Rotation" && ok "fab CPL has JLC headers" || bad "fab CPL header"
  head -1 "$V/zfab/qwiic_imu_bom_jlcpcb.csv" | grep -q "^Comment,Designator,Footprint,LCSC Part #" && ok "fab BOM has JLC headers" || bad "fab BOM header"
  # no drill-mark flashes: the F.Cu gerber has no aperture flashed at the NPTH centres (R1-S1-F3 came from --board-plot-params)
  n=$(grep -c "D03\*" "$V/zfab/gerbers/qwiic_imu-Edge_Cuts.gm1"); [ "$n" = 0 ] && ok "fab edge-cuts gerber has no flashes" || bad "fab edge-cuts flashes $n"
  [ -s "$V/zfab/qwiic_imu_top.png" ] && [ -s "$V/zfab/qwiic_imu_bottom.png" ] && ok "fab renders both sides" || bad "fab renders"
else nochecks "no $ZB"; fi
fi  #@ end 8

if want 9; then  #@ watch: @cli
echo "== 9 render, svg, stats"
if [ -f "$ZB" ]; then
  $PCB render "$ZB" --out "$V/r" --size 600 > /dev/null && [ -s "$V/r/qwiic_imu_top.png" ] && ok "render" || bad "render"
  $PCB svg "$ZB" --out "$V/r" > "$V/svg.txt" && [ "$(ls "$V/r"/*.svg | wc -l | tr -d ' ')" = 4 ] && ok "svg board: F, B, In1, In2" || bad "svg board: $(cat "$V/svg.txt")"
  $PCB svg "$ZS" --out "$V/rs" > "$V/svgs.txt" && ls "$V/rs"/*.svg > /dev/null 2>&1 && ok "svg schematic" || bad "svg schematic: $(cat "$V/svgs.txt")"
  $PCB stats "$ZB" --json "$V/stats.json" > "$V/stats.txt" && grep -q "4 copper layers" "$V/stats.txt" && [ "$(jq_ "$V/stats.json" "d['vias']['through']")" = 25 ] && ok "stats: 4 layers, 25 vias" || bad "stats: $(head -2 "$V/stats.txt")"
else nochecks "no $ZB"; fi
fi  #@ end 9

if want 10; then  #@ watch: skills/kicad-design/scripts/pcb
echo "== 10 GUI guards (P0-T6): layout/apply get --no-open, open is refused, guard runs"
  [ "$(PCB_DRY=1 $PCB layout foo.zen)" = "$HOME/.local/bin/pcb layout foo.zen --no-open" ] && ok "layout appends --no-open" || bad "layout: $(PCB_DRY=1 $PCB layout foo.zen)"
  [ "$(PCB_DRY=1 $PCB apply schematic --no-open foo.zen)" = "$HOME/.local/bin/pcb apply schematic --no-open foo.zen" ] && ok "apply keeps a single --no-open" || bad "apply: $(PCB_DRY=1 $PCB apply schematic --no-open foo.zen)"
  [ "$(PCB_DRY=1 $PCB apply schematic foo.zen)" = "$HOME/.local/bin/pcb apply schematic foo.zen --no-open" ] && ok "apply schematic appends --no-open after the subcommand (R1-A2-T1)" || bad "apply: $(PCB_DRY=1 $PCB apply schematic --no-open foo.zen)"
  [ "$(PCB_DRY=1 $PCB build foo.zen)" = "$HOME/.local/bin/pcb build foo.zen" ] && ok "build passes through" || bad "build passthrough"
  $PCB open x > /dev/null 2>&1; [ $? = 2 ] && ok "open refused" || bad "open not refused"
  $PCB guard > /dev/null; rc=$?; [ "$rc" = 0 ] && ok "guard: no GUI running" || echo "NOTE guard reports a KiCad GUI running (rc $rc); not counted"
  $PCB > /dev/null && ok "pcb with no command prints help and exits 0" || bad "help exit"
fi  #@ end 10

if want 11; then  #@ watch: @cli @q
echo "== 11 regen-check on rung1-zener-a1: reproduces R1-Z1-F2 (exit 1 from clean, pass 1 12 err/4 warn, pass 2 20/0)"
if [ -d "$Z" ]; then
  $PCB regen-check "$Z" --cmd tools/regen.sh --board layout/qwiic_imu/qwiic_imu.kicad_pcb --generated layout fab --out "$V/zregen" > "$V/zregen.txt"; rc=$?
  [ "$rc" = 1 ] && grep -q "FAILS" "$V/zregen.txt" && ok "zener regen-check FAILS with exit 1" || bad "zener regen-check rc $rc: $(tail -1 "$V/zregen.txt")"
  [ "$(jq_ "$V/zregen/regen.json" "(d['pass1']['cmd_exit'], d['pass1']['drc']['plain_errors'], d['pass1']['drc']['plain_warnings'])")" = "(1, 12, 4)" ] && ok "zener pass 1: regen.sh exit 1, DRC 12 errors 4 warnings (review: 4 isolated_copper)" || bad "zener pass 1 $(jq_ "$V/zregen/regen.json" "(d['pass1']['cmd_exit'], d['pass1']['drc'])")"
  [ "$(jq_ "$V/zregen/regen.json" "(d['pass2']['drc']['plain_errors'], d['pass2']['drc']['plain_warnings'])")" = "(20, 0)" ] && ok "zener pass 2 converges to 20/0" || bad "zener pass 2 $(jq_ "$V/zregen/regen.json" "d['pass2']['drc']")"
  [ "$(jq_ "$V/zregen/regen.json" "'placement' in ' '.join(d['diff_ref_pass1']) or 'copper' in ' '.join(d['diff_ref_pass1'])")" = False ] && ok "zener placement and tracks identical to the handed-in board" || bad "zener placement differs: $(jq_ "$V/zregen/regen.json" "d['diff_ref_pass1']")"
  [ "$(jq_ "$V/zregen/regen.json" "d['pass1']['fab']['gerbers']['qwiic_imu-Edge_Cuts.gm1'] == d['pass2']['fab']['gerbers']['qwiic_imu-Edge_Cuts.gm1']")" = True ] && ok "zener Edge.Cuts gerber hashes equal across passes (dates stripped, P1-T9)" || bad "zener edge gerber hash differs between passes"
  [ "$(jq_ "$V/zregen/regen.json" "d['pass1']['fab']['gerbers']['qwiic_imu-F_Cu.gtl'] == d['pass2']['fab']['gerbers']['qwiic_imu-F_Cu.gtl']")" = False ] && ok "zener F.Cu gerber differs between passes (the zone-fill difference is real)" || bad "zener F.Cu gerber equal between passes?"
else nochecks "no $Z"; fi
fi  #@ end 11

if want 12; then  #@ watch: @cli @q
echo "== 12 regen-check on rung1-skidl-a1: exit 0 but the first pass from clean diverges (P1-T10)"
if [ -d "$K" ]; then
  $PCB regen-check "$K" --cmd ./check.sh --board qwiic_imu.kicad_pcb --generated qwiic_imu.kicad_sch qwiic_imu.kicad_pcb qwiic_imu.kicad_pro qwiic_imu.kicad_prl qwiic_imu.xml qwiic_imu.net fab qwiic_imu-drc.json qwiic_imu-erc.json qwiic_imu.kicad_dru --out "$V/sregen" > "$V/sregen.txt"; rc=$?
  [ "$rc" = 1 ] && ok "skidl regen-check FAILS" || bad "skidl regen-check rc $rc"
  [ "$(jq_ "$V/sregen/regen.json" "(d['pass1']['cmd_exit'], d['pass2']['cmd_exit'], d['pass1']['drc']['plain_errors'], d['pass2']['drc']['plain_errors'])")" = "(0, 0, 12, 18)" ] && ok "skidl check.sh exits 0 twice, DRC 12 errors on pass 1 and 18 on pass 2" || bad "skidl passes $(jq_ "$V/sregen/regen.json" "(d['pass1']['cmd_exit'], d['pass2']['cmd_exit'], d['pass1']['drc'], d['pass2']['drc'])")"
  [ "$(jq_ "$V/sregen/regen.json" "'nets' in ' '.join(d['diff_ref_pass1'])")" = False ] && ok "skidl netlist identical from clean" || bad "skidl netlist differs"
else nochecks "no $K"; fi
fi  #@ end 12

if want 13; then  #@ watch: @check examples/rung1-zener-a1/checks.json
echo "== 13 pcbcheck on rung1-zener-a1 with examples/rung1-zener-a1/checks.json: exactly the review's C3 and refdes findings"
if [ -f "$ZB" ]; then
  $PCB check "$ZB" "$ROOT/examples/rung1-zener-a1/checks.json" --out "$V/zcheck.json" > "$V/zcheck.txt"; rc=$?
  [ "$rc" = 1 ] && ok "zener check exits 1" || bad "zener check rc $rc"
  [ "$(jq_ "$V/zcheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['decoupling:U1.8:C3', 'silk:refdes']" ] && ok "zener fails are exactly C3 decoupling and silk refdes (R1-Z1-F3, R1-Z1-F4)" || bad "zener fails $(jq_ "$V/zcheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
  [ "$(jq_ "$V/zcheck.json" "[r['value'] for r in d['rows'] if r['id']=='decoupling:U1.8:C3'][0]")" = 2.639 ] && ok "zener C3 row carries 2.639 mm (review: 2.639)" || bad "zener C3 value"
  [ "$(jq_ "$V/zcheck.json" "[r['value'] for r in d['rows'] if r['id']=='silk:refdes'][0]")" = 10 ] && ok "zener 10 hidden refdes named in BRINGUP.md" || bad "zener silk $(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['id']=='silk:refdes']")"
  [ "$(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['id']=='addresses:I2C:U1'][0]")" = "U1 strap pin 1 (SA0) resolves high through ['JP1'] -> 0x6b; declared 0x6b" ] && ok "zener address strap resolves 0x6B through JP1" || bad "zener address $(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['check']=='addresses']")"
  [ "$(jq_ "$V/zcheck.json" "[r['value'] for r in d['rows'] if r['id']=='pullups:I2C:sda'][0]")" = 3.0 ] && ok "zener pull-up chain: 2 boards = 3.0 mA, at the limit (review R1-S1-F2 arithmetic)" || bad "zener pullups $(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['check']=='pullups']")"
  [ "$(jq_ "$V/zcheck.json" "sum(1 for r in d['rows'] if r['check']=='connectors' and r['status']=='pass')")" = 3 ] && ok "zener J1/J2/J3 pin maps pass" || bad "zener connectors"
  [ "$(jq_ "$V/zcheck.json" "d['summary']['passes']")" = 38 ] && ok "zener 38 passes (incl. 5 policy and 8 fields rows)" || bad "zener passes $(jq_ "$V/zcheck.json" "d['summary']")"
else nochecks "no $ZB"; fi
fi  #@ end 13

if want 14; then  #@ watch: @check examples/rung1-skidl-a1/checks.json
echo "== 14 pcbcheck on rung1-skidl-a1: the 'four boards' and '2x the floor' claims fail as rows (R1-S1-F2)"
if [ -f "$KB" ]; then
  $PCB check "$KB" "$ROOT/examples/rung1-skidl-a1/checks.json" --out "$V/scheck.json" > "$V/scheck.txt"; rc=$?
  [ "$(jq_ "$V/scheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['decoupling:C1:gnd_via', 'decoupling:C2:gnd_via', 'margin:edge_clearance', 'margin:hole_clearance', 'margin:via_diameter', 'pullups:I2C:scl', 'pullups:I2C:sda', 'silk:refdes']" ] && ok "skidl fails: GND via x2 (C1 1.21, C2 1.10 against the claimed 1 mm), pull-up chain x2, margin x3, silk" || bad "skidl fails $(jq_ "$V/scheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
  [ "$(jq_ "$V/scheck.json" "[r['value'] for r in d['rows'] if r['id']=='pullups:I2C:sda'][0]")" = 6.0 ] && ok "skidl 4 boards = 6.0 mA against 3.0 (the 'up to four boards' claim)" || bad "skidl pullup value"
  [ "$(jq_ "$V/scheck.json" "[r['value'] for r in d['rows'] if r['id']=='margin:via_diameter'][0]")" = 1.33 ] && ok "skidl via diameter 1.33x the floor (the '2x every feature' claim)" || bad "skidl margin value"
  [ "$(jq_ "$V/scheck.json" "sum(1 for r in d['rows'] if r['check']=='decoupling' and r['status']=='pass')")" = 6 ] && ok "skidl decoupling: 5 distance rows within 2 mm (review: 1.69 to 1.98 mm) and C3's GND via within 1 mm" || bad "skidl decoupling $(jq_ "$V/scheck.json" "[r['msg'] for r in d['rows'] if r['check']=='decoupling']")"
else nochecks "no $KB"; fi
fi  #@ end 14

if want 15; then  #@ watch: @check examples/rung1-zener-a1/checks.json
echo "== 15 pcbcheck planted misdeclarations: swapped Qwiic pins, undeclared jumper, wrong address, undeclared rail, unknown key"
if [ -f "$ZB" ]; then
  python3 -I -c "
import json; c=json.load(open('$ROOT/examples/rung1-zener-a1/checks.json'))
c['connectors']['J1']={'1':'GND','2':'3V3','3':'SCL','4':'SDA'}; del c['jumpers']['JP2']
c['buses']['I2C']['devices']['U1']['address']='0x6A'; del c['rails']['GND']; c['bogus']=1
json.dump(c, open('$V/planted.json','w'))"
  $PCB check "$ZB" "$V/planted.json" --out "$V/pcheck.json" > "$V/pcheck.txt"
  f="$(jq_ "$V/pcheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")"
  for id in connectors:J1 jumpers:JP2 addresses:I2C:U1 rails:GND; do
    case "$f" in *"'$id'"*) ok "planted: $id fails" ;; *) bad "planted: $id did not fail ($f)" ;; esac
  done
  grep -q "CONFIG unknown key 'bogus'" "$V/pcheck.txt" && ok "planted: unknown config key warned" || bad "planted: no config warn"
  grep -q "pin 3: declared SCL, netlist SDA" "$V/pcheck.txt" && ok "planted: J1 row names the swapped pin" || bad "planted: J1 message $(grep connectors:J1 "$V/pcheck.txt")"
  $PCB check "$ZB" "$ROOT/examples/rung1-zener-a1/checks.json" --out "$V/ocheck.json" --only connectors,rails > /dev/null
  [ "$(jq_ "$V/ocheck.json" "sorted({r['check'] for r in d['rows']})")" = "['connectors', 'rails']" ] && ok "--only connectors,rails runs just those" || bad "--only $(jq_ "$V/ocheck.json" "sorted({r['check'] for r in d['rows']})")"
else nochecks "no $ZB"; fi
fi  #@ end 15

if want 17; then  #@ watch: @lib @cli @q examples/rung1-zener-a1/layout_board.py examples/rung1-zener-a1/attempt/**
echo "== 17 pcblib.board: the ported Zener layout on a board fresh from Diode pcb layout gives the designer's copper (P1-T14, P1-T15)"
if [ -d "$Z" ] && [ -x "$HOME/.local/bin/pcb" ]; then
  FR="$V/zfresh"; rm -rf "$FR"; cp -R "$Z" "$FR"; rm -rf "$FR/layout" "$FR/fab" "$FR/review" "$FR/regen-check"
  (cd "$FR" && "$HOME/.local/bin/pcb" build qwiic_imu.zen > "$V/zfresh-build.txt" 2>&1 && "$HOME/.local/bin/pcb" layout --no-open qwiic_imu.zen >> "$V/zfresh-build.txt" 2>&1)
  FB="$FR/layout/qwiic_imu/qwiic_imu.kicad_pcb"
  [ -f "$FB" ] && ok "fresh board from pcb build + pcb layout --no-open" || bad "no fresh board: $(tail -3 "$V/zfresh-build.txt")"
  cp -R "$FR/layout" "$FR/layout-pristine"
  (cd "$FR" && $PCB py "$ROOT/examples/rung1-zener-a1/layout_board.py" "$FB" > "$V/port.txt" 2>&1); rc=$?
  [ "$rc" = 0 ] && grep -q "'tracks': 74, 'vias': 25, 'zones': 4" "$V/port.txt" && ok "port: 74 tracks, 25 vias, 4 zones (the designer's counts)" || bad "port rc $rc: $(tail -2 "$V/port.txt")"
  $PCB drc "$FB" --pack jlcpcb --out "$V/portdrc" --no-parity > "$V/portdrc.txt"
  [ "$(jq_ "$V/portdrc/drc.json" "(d['plain']['errors'], d['plain']['warnings'])")" = "(12, 0)" ] && ok "port on a pack-free project: 12 errors, 0 warnings (no first-fill islands: BuildConnectivity, P1-T10)" || bad "port drc $(jq_ "$V/portdrc/drc.json" "(d['plain']['errors'], d['plain']['warnings'], d['plain']['by_type'])")"
  $PCB q "$FB" fps --json > "$V/port-fps.json"; $PCB q "$ZB" fps --json > "$V/orig-fps.json"
  python3 -I -c "
import json; a=json.load(open('$V/port-fps.json'))['footprints']; b=json.load(open('$V/orig-fps.json'))['footprints']
ka={r['ref']:(r['pos'],r['rot']) for r in a}; kb={r['ref']:(r['pos'],r['rot']) for r in b}; assert ka==kb, (ka, kb)" && ok "port placement identical to the designer's board (15 refs, position and rotation)" || bad "port placement differs"
  $PCB q "$FB" nets --json > "$V/port-nets.json"; $PCB q "$ZB" nets --json > "$V/orig-nets.json"
  python3 -I -c "
import json; a={n['net']:(n['length_mm'],n['vias']) for n in json.load(open('$V/port-nets.json'))['nets']}; b={n['net']:(n['length_mm'],n['vias']) for n in json.load(open('$V/orig-nets.json'))['nets']}
assert set(a)==set(b) and all(abs(a[k][0]-b[k][0])<=0.005 and a[k][1]==b[k][1] for k in a), (a,b)" && ok "port copper identical per net (length within 5 um, vias)" || bad "port copper differs"
  # the rule pack in the project dir changes the fill: hole clearance 0.2 from the pack instead of 0.3 from the setup (P1-T14)
  rm -rf "$FR/layout"; cp -R "$FR/layout-pristine" "$FR/layout"; cp "$REF/kicad-druid/JLCPCB/JLCPCB.kicad_dru" "$FR/layout/qwiic_imu/qwiic_imu.kicad_dru"
  (cd "$FR" && $PCB py "$ROOT/examples/rung1-zener-a1/layout_board.py" "$FB" > "$V/port2.txt" 2>&1)
  $PCB drc "$FB" --out "$V/portdrc2" --no-parity > "$V/portdrc2.txt"
  [ "$(jq_ "$V/portdrc2/drc.json" "(d['plain']['errors'], d['plain']['by_type']['error'].get('hole_clearance'))")" = "(20, 8)" ] && ok "same script with the pack in the project dir: 20 errors, 8 hole_clearance (the filler read the pack, P1-T14)" || bad "pack-present fill $(jq_ "$V/portdrc2/drc.json" "d['plain']['by_type']")"
  [ "$(wc -l < "$ROOT/examples/rung1-zener-a1/layout_board.py")" -lt 120 ] && ok "port is under 120 lines (designer: 280)" || bad "port grew"
else nochecks "no $Z or no Diode pcb"; fi
fi  #@ end 17

if want 18; then  #@ watch: @lib skills/kicad-design/scripts/pcb
echo "== 18 pcblib.board.from_netlist builds the SKiDL board from its kicadxml with pad nets and fields"
if [ -d "$K" ]; then
  (cd "$K" && $PCB py -c "
from pcblib.board import Board
b = Board.from_netlist('qwiic_imu.xml', '/tmp/alexpcb-verify/fromnet.kicad_pcb', libs={'qwiic_imu': 'qwiic_imu.pretty'})
b.setup(layers=4); b.place('U1', 12.7, 12.7, 0); b.outline_rect(0, 0, 25.4, 25.4, r=2)
s = b.summary(); nets = sorted({p.GetNetname() for f in b.b.GetFootprints() for p in f.Pads() if p.GetNetname()})
print('FROMNET', s['footprints'], len(nets), b.field('U1', 'LCSC'), b.fp('J3').IsDNP(), b.pad_xy('U1', '1'))
b.save()" > "$V/fromnet.txt" 2>&1); rc=$?
  grep -q "^FROMNET 15 11 C967633 True" "$V/fromnet.txt" && ok "from_netlist: 15 footprints, 11 nets on pads, LCSC field read, J3 DNP, U1 pad 1 placed" || bad "from_netlist rc $rc: $(cat "$V/fromnet.txt")"
  [ -s /tmp/alexpcb-verify/fromnet.kicad_pcb ] && ok "from_netlist board saved" || bad "from_netlist not saved"
else nochecks "no $K"; fi
fi  #@ end 18

if want 19; then  #@ watch: skills/kicad-design/scripts/pcbsch.py @q @lib @cli examples/rung1-zener-a1/layout_board.py examples/rung1-zener-a1/attempt/**
echo "== 19 pcb schfix on a raw Diode schematic without the test-point power hack: fields, labels, symlib, PWR_FLAGs; ERC 2/32 -> 0/1 (P1-T16)"
if [ -d "$Z" ] && [ -x "$HOME/.local/bin/pcb" ]; then
  F2="$V/zfresh2"; rm -rf "$F2"; cp -R "$Z" "$F2"; rm -rf "$F2/layout" "$F2/fab" "$F2/review" "$F2/regen-check"
  sed -i '' 's/TestPoint(name="TP1", power_source=True, P1=GND)/TestPoint(name="TP1", P1=GND)/; s/TestPoint(name="TP2", power_source=True, P1=V3V3)/TestPoint(name="TP2", P1=V3V3)/' "$F2/qwiic_imu.zen"
  (cd "$F2" && "$HOME/.local/bin/pcb" build qwiic_imu.zen && "$HOME/.local/bin/pcb" layout --no-open qwiic_imu.zen && "$HOME/.local/bin/pcb" apply schematic --no-open qwiic_imu.zen) > "$V/zfresh2-build.txt" 2>&1
  S2="$F2/layout/qwiic_imu/qwiic_imu.kicad_sch"
  [ -f "$S2" ] && ok "raw schematic from pcb apply schematic --no-open" || bad "no schematic: $(tail -3 "$V/zfresh2-build.txt")"
  cp "$S2" "$V/raw2.kicad_sch"
  $PCB schfix "$S2" > "$V/schfix.txt"; rc=$?
  [ "$rc" = 0 ] && ok "schfix exits 0" || bad "schfix rc $rc: $(cat "$V/schfix.txt")"
  grep -q "fields +27, dnp 0, labels->global 20, PWR_FLAG \['GND', '3V3'\], symlib written; nets renamed 7, connectivity identical; ERC 2 errors / 32 warnings -> 0 errors / 1 warnings" "$V/schfix.txt" && ok "schfix: 27 fields, 20 labels, PWR_FLAG on GND and 3V3, 7 renames, ERC 2/32 -> 0/1" || bad "schfix line: $(cat "$V/schfix.txt")"
  $PCB schfix "$S2" > "$V/schfix2.txt"; grep -q "no change; fields +0, dnp 0, labels->global 0, PWR_FLAG none" "$V/schfix2.txt" && ok "schfix idempotent" || bad "schfix second run: $(cat "$V/schfix2.txt")"
  $PCB diff "$V/raw2.kicad_sch" "$S2" > "$V/schdiff.txt" && grep -q "identical connectivity, 7 renamed" "$V/schdiff.txt" && ok "pcb diff raw vs fixed: identical, 7 renamed (/SDA -> SDA ...)" || bad "schdiff: $(head -2 "$V/schdiff.txt")"
  grep -q '(dnp yes)' "$V/raw2.kicad_sch" && ok "Diode 0.4.95 already writes (dnp yes) for J3 (R1-Z1-T3 'ignored DNP' does not hold for the schematic)" || bad "raw schematic has no dnp yes"
  [ -f "$F2/layout/qwiic_imu/qwiic_imu_symbols.kicad_sym" ] && [ -f "$F2/layout/qwiic_imu/sym-lib-table" ] && ok "symbol library and sym-lib-table written next to the schematic" || bad "symlib files missing"
  # the real flow: the pcblib layout script upper-cases Zener's Mpn/Lcsc footprint fields, then parity compares like with like
  (cd "$F2" && $PCB py "$ROOT/examples/rung1-zener-a1/layout_board.py" layout/qwiic_imu/qwiic_imu.kicad_pcb > "$V/port3.txt" 2>&1)
  $PCB drc "$F2/layout/qwiic_imu/qwiic_imu.kicad_pcb" --pack jlcpcb --out "$V/fixdrc" > "$V/fixdrc.txt"
  [ "$(jq_ "$V/fixdrc/drc.json" "(d['plain']['parity'], d['plain']['errors'], d['plain']['unconnected'])")" = "(2, 12, 0)" ] && ok "after schfix + pcblib layout: parity 2 warnings (U1 NC pad naming only), 12 errors, 0 unconnected" || bad "parity/drc $(jq_ "$V/fixdrc/drc.json" "(d['plain']['parity'], d['plain']['errors'], d['plain']['unconnected'])")"
  $PCB erc "$S2" --out "$V/fixerc.json" --list | grep -q "FLG01 Pin 1" && ok "the one ERC warning left is SDX (bidirectional) on the flagged GND net, a datasheet tie-off to accept" || bad "unexpected ERC after schfix"
else nochecks "no $Z or no Diode pcb"; fi
fi  #@ end 19

if want 20; then  #@ watch: skills/**/*.md skills/kicad-design/templates/** docs/FINDINGS.md examples/*/checks.json examples/*/*.py
echo "== 20 skills: every FINDINGS ID cited in skills/ and examples/ exists; templates and reference files present"
  ids=$(grep -rhoIE --include='*.md' --include='*.py' --include='*.json' --include='*.sh' --include='pcb' '\b(P[0-9]-T[0-9]+|R[0-9]-[SZ][0-9]-[FTR][0-9]+)\b' "$ROOT"/skills "$ROOT"/examples/*/*.py "$ROOT"/examples/*/checks.json 2>/dev/null | sort -u)
  missing=""; n=0
  for id in $ids; do n=$((n+1)); grep -q "$id" "$ROOT/docs/FINDINGS.md" || missing="$missing $id"; done
  [ -z "$missing" ] && ok "all $n FINDINGS IDs cited in skills/ and examples/ exist in docs/FINDINGS.md" || bad "IDs cited but not in FINDINGS:$missing"
  missing=""
  for f in skills/kicad-design/SKILL.md skills/kicad-design/reference/api.md skills/kicad-design/reference/checks-config.md skills/kicad-design/reference/footguns.md skills/kicad-design/reference/front-end.md skills/kicad-design/templates/project/checks.json skills/kicad-design/templates/project/tools/regen.sh skills/kicad-design/templates/project/tools/layout_board.py skills/pcb-design-review/SKILL.md skills/pcb-design-review/rubric.md skills/pcb-design-review/checklist.md; do
    [ -s "$ROOT/$f" ] || missing="$missing $f"
  done
  [ -z "$missing" ] && ok "skill, reference, template and review files present" || bad "missing:$missing"
  python3 -I -c "import json; json.load(open('$ROOT/skills/kicad-design/templates/project/checks.json'))" && ok "template checks.json parses" || bad "template checks.json"
  head -3 "$ROOT/skills/kicad-design/SKILL.md" | grep -q "^name: kicad-design" && head -3 "$ROOT/skills/pcb-design-review/SKILL.md" | grep -q "^name: pcb-design-review" && ok "SKILL.md frontmatter names" || bad "frontmatter"
fi  #@ end 20

if want 21; then  #@ watch: @cli @check examples/rung1-zener-a1/board/** examples/rung1-zener-a1/checks.json
echo "== 21 project exception rules stay in both DRC runs; policy rows catch a lowered board setup (R1-A2-T5)"
E="$V/exc"; rm -rf "$E"; mkdir -p "$E"; cp "$ROOT"/examples/rung1-zener-a1/board/* "$E"/
printf '(version 1)\n(rule "LGA-14 pad gap on U1" (condition "A.memberOfFootprint(%sU1%s) && B.memberOfFootprint(%sU1%s)") (constraint clearance (min 0.15mm)))\n' "'" "'" "'" "'" > "$E/qwiic_imu.kicad_dru"
$PCB drc "$E/qwiic_imu.kicad_pcb" --pack jlcpcb --out "$V/excdrc" > "$V/excdrc.txt"
grep -q "project rules kept in both runs: \['LGA-14 pad gap on U1'\]" "$V/excdrc.txt" && ok "a scoped project rule is recognised as intent, not a fab pack" || bad "exception: $(head -1 "$V/excdrc.txt")"
[ "$(jq_ "$V/excdrc/drc.json" "(d['plain']['by_type']['error'], d['packed']['by_type']['error'])")" = "({'hole_clearance': 8}, {'hole_clearance': 8})" ] && ok "the U1 pad-pad exception removes the 12 clearance errors in both runs, the 8 hole errors stay" || bad "exception errors $(jq_ "$V/excdrc/drc.json" "(d['plain']['by_type'], d['packed']['by_type'])")"
cp "$REF/kicad-druid/JLCPCB/JLCPCB.kicad_dru" "$E/qwiic_imu.kicad_dru"
$PCB drc "$E/qwiic_imu.kicad_pcb" --out "$V/excdrc2" > "$V/excdrc2.txt"
grep -q "fab pack, removed from the plain run" "$V/excdrc2.txt" && [ "$(jq_ "$V/excdrc2/drc.json" "d['plain']['errors']")" = 20 ] && ok "a copied-in fab pack is dropped from the plain run (20 errors) and used as the pack" || bad "pack detection: $(head -2 "$V/excdrc2.txt")"
rm -f "$E/qwiic_imu.kicad_dru"
$PCB check "$E/qwiic_imu.kicad_pcb" "$ROOT/examples/rung1-zener-a1/checks.json" --only policy --out "$V/pol1.json" > "$V/pol1.txt" && [ "$(jq_ "$V/pol1.json" "d['summary']['passes']")" = 5 ] && ok "policy: the a1 board meets the brief's 5 numbers" || bad "policy a1: $(cat "$V/pol1.txt")"
python3 -I -c "
import json; p='$E/qwiic_imu.kicad_pro'; d=json.load(open(p)); d['board']['design_settings']['rules']['min_clearance']=0.14; d['board']['design_settings']['rules']['min_text_height']=0.8; json.dump(d, open(p,'w'), indent=1)"
$PCB check "$E/qwiic_imu.kicad_pcb" "$ROOT/examples/rung1-zener-a1/checks.json" --only policy --out "$V/pol2.json" > "$V/pol2.txt"; rc=$?
[ "$rc" = 1 ] && [ "$(jq_ "$V/pol2.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['policy:clearance_mm', 'policy:silk_text_mm']" ] && ok "policy: a board setup lowered to 0.14 mm clearance and 0.8 mm text fails both rows (what both attempt-2 designers did)" || bad "policy planted: $(cat "$V/pol2.txt")"
fi  #@ end 21

if want 22; then  #@ watch: @cli @q examples/rung1-zener-a2-sonnet/**
echo "== 22 attempt-2 Sonnet board: regen-check REGENERATES; pcbcheck with the policy block fails clearance 0.14 and 5 Datasheet fields (R1-A2S)"
A="$RUNS/rung1-zener-a2-sonnet"
if [ -d "$A" ] && [ -x "$HOME/.local/bin/pcb" ]; then
  rm -rf "$V/a2s"; cp -R "$A" "$V/a2s"; rm -rf "$V/a2s/review"
  $PCB regen-check "$V/a2s" --cmd tools/regen.sh --board layout/qwiic_imu/qwiic_imu.kicad_pcb --generated layout fab reports --out "$V/a2sregen" > "$V/a2sregen.txt"; rc=$?
  [ "$rc" = 0 ] && grep -q REGENERATES "$V/a2sregen.txt" && ok "a2 sonnet regen-check REGENERATES" || bad "a2 sonnet regen: $(tail -3 "$V/a2sregen.txt")"
else nochecks "no $A or no Diode pcb"; fi
$PCB check "$ROOT/examples/rung1-zener-a2-sonnet/board/qwiic_imu.kicad_pcb" "$ROOT/examples/rung1-zener-a2-sonnet/checks.json" --out "$V/a2scheck.json" > "$V/a2scheck.txt"
[ "$(jq_ "$V/a2scheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['fields:C1', 'fields:C2', 'fields:C3', 'fields:R1', 'fields:R2', 'policy:clearance_mm']" ] && ok "a2 sonnet pcbcheck: policy clearance 0.14 and the five empty Datasheet fields (the reviewer's one overclaim)" || bad "a2 sonnet check: $(jq_ "$V/a2scheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
fi  #@ end 22

if want 23; then  #@ watch: @cli @q examples/rung1-zener-a2-fable/**
echo "== 23 attempt-2 Fable board: regen-check REGENERATES with gerber warns (R1-A2-T2); policy fails clearance 0.15 and silk 0.8 (R1-A2F-1)"
A="$RUNS/rung1-zener-a2-fable"
if [ -d "$A" ] && [ -x "$HOME/.local/bin/pcb" ]; then
  rm -rf "$V/a2f"; cp -R "$A" "$V/a2f"; rm -rf "$V/a2f/review"
  $PCB regen-check "$V/a2f" --cmd tools/regen.sh --board layout/qwiic_imu/qwiic_imu.kicad_pcb --generated layout fab --out "$V/a2fregen" > "$V/a2fregen.txt"; rc=$?
  [ "$rc" = 0 ] && grep -q REGENERATES "$V/a2fregen.txt" && ok "a2 fable regen-check REGENERATES on netlist, DRC, placement and copper" || bad "a2 fable regen: $(tail -4 "$V/a2fregen.txt")"
  grep -q "warn: fab gerbers differ (canonical form)" "$V/a2fregen.txt" && ok "a2 fable: gerber differences reported as a warn, not the verdict (the zone filler is not bit-stable)" || echo "NOTE a2 fable: no gerber warn this run"
else nochecks "no $A or no Diode pcb"; fi
$PCB check "$ROOT/examples/rung1-zener-a2-fable/board/qwiic_imu.kicad_pcb" "$ROOT/examples/rung1-zener-a2-fable/checks.json" --out "$V/a2fcheck.json" > "$V/a2fcheck.txt"
[ "$(jq_ "$V/a2fcheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['policy:clearance_mm', 'policy:silk_text_mm']" ] && ok "a2 fable pcbcheck: policy clearance 0.15 and silk text 0.8 (the reviewer's major)" || bad "a2 fable check: $(jq_ "$V/a2fcheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
fi  #@ end 23

if want 24; then  #@ watch: @check examples/rung1-zener-a1/board/**
echo "== 24 calcs rows: IPC-2221 width vs declared current, thermal stitching vias, formula rows with netlist values (P1-T21)"
cat > "$V/calcs.json" <<'EOC'
{"currents": {"3V3": 0.005, "GND": 0.005}, "copper_oz": {"outer": 1.0, "inner": 0.5},
 "thermal_vias": {"U1": {"pad": "6", "min": 1, "within_mm": 1.5}},
 "calcs": [
  {"id": "p_ldo", "expr": "(5.0 - 3.3) * 0.5", "unit": "W", "max": 1.0},
  {"id": "tj_ldo", "expr": "40 + p_ldo * 90", "unit": "degC", "max": 125},
  {"id": "buck_ripple_pct", "expr": "100 * 5.0 * (1 - 5.0/17.0) / (500e3 * 6.8e-6) / 3.0", "unit": "%", "min": 30, "max": 40},
  {"id": "pullup_ma", "expr": "3.3 / R('R1') * 1000", "unit": "mA", "max": 3.0},
  {"id": "c_bulk", "expr": "C('C3')", "unit": "F", "min": 1e-6}]}
EOC
$PCB check "$ROOT/examples/rung1-zener-a1/board/qwiic_imu.kicad_pcb" "$V/calcs.json" --only currents,thermal_vias,calcs --out "$V/calcs1.json" > "$V/calcs1.txt"; rc=$?
[ "$rc" = 0 ] && [ "$(jq_ "$V/calcs1.json" "d['summary']['passes']")" = 8 ] && ok "calcs: 8 rows pass (widths at 5 mA, 1 GND via within 1.5 mm of U1.6, LDO 0.85 W / 116.5 degC, ripple 34.6 %, pull-up 1.5 mA from R1's value, C3 from its value)" || bad "calcs sane: $(cat "$V/calcs1.txt")"
[ "$(jq_ "$V/calcs1.json" "round([r['value'] for r in d['rows'] if r['id']=='calcs:buck_ripple_pct'][0], 1)")" = 34.6 ] && ok "calcs: buck ripple 34.6 % at 6.8 uH" || bad "calcs ripple $(jq_ "$V/calcs1.json" "[r['msg'] for r in d['rows'] if r['id']=='calcs:buck_ripple_pct']")"
python3 -I -c "
import json; d=json.load(open('$V/calcs.json')); d['currents']['3V3']=3.0; d['thermal_vias']['U1']['min']=5; d['calcs'][0]['expr']='(5.0 - 3.3) * 0.8'; d['calcs'][2]['expr']='100 * 5.0 * (1 - 5.0/17.0) / (500e3 * 4.7e-6) / 3.0'; json.dump(d, open('$V/calcs2.json','w'))"
$PCB check "$ROOT/examples/rung1-zener-a1/board/qwiic_imu.kicad_pcb" "$V/calcs2.json" --only currents,thermal_vias,calcs --out "$V/calcs2.json.out" > "$V/calcs2.txt"; rc=$?
[ "$rc" = 1 ] && [ "$(jq_ "$V/calcs2.json.out" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['calcs:buck_ripple_pct', 'calcs:p_ldo', 'calcs:tj_ldo', 'currents:3V3', 'thermal_vias:U1']" ] && ok "calcs planted: 3 A on a 0.2 mm track (needs 0.898 mm outer by IPC-2221), 5 vias wanted with 1 present, LDO 1.36 W / 162 degC, ripple 50 % all fail" || bad "calcs planted: $(cat "$V/calcs2.txt")"
grep -q "needs 0.898 mm outer (1.0 oz), 4.670 mm inner (0.5 oz)" "$V/calcs2.txt" && ok "calcs: IPC-2221 3 A at 20 degC = 0.898 mm at 1 oz outer, 4.670 mm at 0.5 oz inner" || bad "calcs width numbers: $(grep currents "$V/calcs2.txt")"
fi  #@ end 24

if want 25; then  #@ watch: @check @cli examples/rung1-zener-a1/board/**
echo "== 25 rung-2 tool fixes: feeds row, declared decoupling on any pin type, values with ratings, stale netlist re-export, regen-check output outside the project, sentinel-free packed report (R2-T4, R2-T5)"
cat > "$V/feeds.json" <<'EOC'
{"feeds": [{"pad": "U1.8", "amps": 3.0, "within_mm": 2.0}], "decoupling": [{"ic": "J1", "pin": "2", "cap": "C1", "max_mm": 20}],
 "currents": {"3V3": 0.5}, "calcs": [{"id": "c1", "expr": "C('C1')", "min": 1e-9}]}
EOC
$PCB check "$ROOT/examples/rung1-zener-a1/board/qwiic_imu.kicad_pcb" "$V/feeds.json" --only feeds,decoupling,currents,calcs --out "$V/feeds.out.json" > "$V/feeds.txt"
[ "$(jq_ "$V/feeds.out.json" "[(r['status'], round(r['value'], 2)) for r in d['rows'] if r['id']=='feeds:U1.8'][0]")" = "('fail', 1.19)" ] && ok "feeds: U1.8 at 3 A fails with 1.19 A (one 0.2 mm track, no via, pour unsized)" || bad "feeds: $(grep feeds "$V/feeds.txt")"
[ "$(jq_ "$V/feeds.out.json" "[r['status'] for r in d['rows'] if r['id']=='decoupling:J1.2:C1'][0]")" = pass ] && ok "decoupling: a declared row on a passive pin is measured (11.7 mm, limit 20)" || bad "decoupling declared: $(grep J1 "$V/feeds.txt")"
$PCB py -c "import pcbcheck as c; print('PV', *[float('%.6g' % c.parse_value(x)) for x in ('100nF 50V', '4.7uH 2A', '2k2', '0.01')])" 2>/dev/null | grep -q "^PV 1e-07 4.7e-06 2200.0 0.01" && ok "parse_value: '100nF 50V', '4.7uH 2A', '2k2', '0.01'" || bad "parse_value: $($PCB py -c "import pcbcheck as c; print(c.parse_value('100nF 50V'), c.parse_value('4.7uH 2A'), c.parse_value('2k2'), c.parse_value('0.01'))" 2>&1 | tail -1)"
N="$V/stale"; rm -rf "$N"; mkdir -p "$N"; cp "$ROOT"/examples/rung1-zener-a1/board/* "$N"/; touch -t 202001010000 "$N/qwiic_imu.xml"
$PCB check "$N/qwiic_imu.kicad_pcb" "$ROOT/examples/rung1-zener-a1/checks.json" --only rails --out "$N/pc.json" > "$N/pc.txt"
grep -q "CONFIG netlist qwiic_imu.xml was older than the schematic: re-exported" "$N/pc.txt" && [ "$(stat -f %m "$N/qwiic_imu.xml")" -gt 1600000000 ] && ok "pcb check re-exports a netlist older than the schematic (R2-T4)" || bad "stale netlist: $(grep CONFIG "$N/pc.txt")"
R="$V/regenout"; rm -rf "$R"; mkdir -p "$R"; cp -R "$ROOT/examples/rung1-zener-a1/board" "$R/board"
$PCB regen-check "$R/board" --cmd true --board qwiic_imu.kicad_pcb > "$R/regen.txt"; rc=$?
[ "$rc" = 0 ] && [ -f "$R/board/regen-check.json" ] && grep -q "/pcb-regen/board-" "$R/regen.txt" && ok "regen-check writes under /tmp/pcb-regen and copies regen-check.json into the project (R2-T4)" || bad "regen-check out: rc $rc $(tail -2 "$R/regen.txt")"
$PCB drc "$ROOT/examples/rung1-zener-a1/board/qwiic_imu.kicad_pcb" --pack jlcpcb --out "$V/sdrc" > /dev/null
[ "$(jq_ "$V/sdrc/drc-packed.json" "(d.get('sentinel_hits_removed'), sum(1 for v in d['violations'] if '99.' in v['description']))")" = "(74, 0)" ] && [ -f "$V/sdrc/drc-packed-raw.json" ] && ok "packed report carries no sentinel hits (74 removed, raw kept)" || bad "sentinel strip: $(jq_ "$V/sdrc/drc-packed.json" "(d.get('sentinel_hits_removed'), len(d['violations']))")"
fi  #@ end 25

if want 26; then  #@ watch: @check @cli examples/rung2-zener-a*/**
echo "== 26 rung-2 boards: the reviewers' majors as rows (feeds, declared decoupling, currents; drc shorts on the unfinished board) (R2-T5)"
for a in opus sonnet fable; do
  B=$(ls "$ROOT"/examples/rung2-zener-a1-$a/board/*.kicad_pcb)
  $PCB check "$B" "$ROOT/examples/rung2-zener-a1-$a/checks.json" --out "$V/r2${a:0:1}check.json" > "$V/r2$a.txt"
done
[ "$(jq_ "$V/r2ocheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['decoupling:U2.11:C10', 'decoupling:U2.11:C11', 'decoupling:U2.11:C17', 'feeds:U2.11']" ] && ok "r2 opus: feeds U2.11 0.00 A (pour neck), C11 11.76 / C17 15.47 mm (the reviewer's two electrical majors)" || bad "r2 opus: $(jq_ "$V/r2ocheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
[ "$(jq_ "$V/r2scheck.json" "[round(r['value'], 2) for r in d['rows'] if r['id']=='feeds:U2.11'][0]")" = 1.22 ] && ok "r2 sonnet: feeds U2.11 1.22 A from one 0.3 mm via (reviewer: one via, 0.34 mm finger)" || bad "r2 sonnet feeds $(grep feeds "$V/r2sonnet.txt")"
[ "$(jq_ "$V/r2scheck.json" "sum(1 for r in d['rows'] if r['check']=='decoupling' and r['status']=='fail')")" = 4 ] && ok "r2 sonnet: 4 declared VM/charge-pump caps beyond 2 mm (5.05 to 7.6 mm)" || bad "r2 sonnet decoupling"
[ "$(jq_ "$V/r2fcheck.json" "[round(r['value'], 2) for r in d['rows'] if r['id']=='feeds:U1.11'][0]")" = 1.36 ] && ok "r2 fable: feeds U1.11 1.36 A (reviewer: 1.355 A through an 0402 pad)" || bad "r2 fable feeds"
[ "$(jq_ "$V/r2fcheck.json" "d['summary']['fails']")" = 9 ] && ok "r2 fable: 9 fails (4 decoupling, 4 currents on 0.28-0.3 mm tracks, feeds)" || bad "r2 fable fails $(jq_ "$V/r2fcheck.json" "d['summary']")"
grep -q "currents:VIN_RAW: .*no tracks: carried by pours only" "$V/r2opus.txt" && ok "r2 opus: pour-only nets warn, not pass" || bad "r2 opus currents warn"
$PCB drc "$ROOT/examples/rung2-zener-a1-fable/board/motor_channel.kicad_pcb" --pack jlcpcb --out "$V/r2fdrc" > "$V/r2fdrc.txt"
# 67 here against the designer's 62: the archived board sits without its vendored footprint library (59 lib_footprint_issues), which
# moves five clearance/mask errors; the shorts, courtyards and unconnected counts are the reviewer's
# shorting_items is 20 or 21 run to run: the shorts sit on fill boundaries and the fill is multithreaded (P6-T5, seen twice in full runs)
[ "$(jq_ "$V/r2fdrc/drc.json" "(d['plain']['by_type']['error'].get('shorting_items') in (20, 21), d['plain']['by_type']['error'].get('courtyards_overlap'), d['plain']['unconnected'])")" = "(True, 14, 6)" ] && ok "r2 fable drc: 20 or 21 shorts (P6-T5), 14 courtyard overlaps, 6 unconnected (the reviewer's blockers)" || bad "r2 fable drc $(jq_ "$V/r2fdrc/drc.json" "(d['plain']['errors'], d['plain']['by_type'])")"
$PCB check "$ROOT/examples/rung2-zener-a2-opus/board/motor1.kicad_pcb" "$ROOT/examples/rung2-zener-a2-opus/checks.json" --out "$V/r2a2ocheck.json" > "$V/r2a2opus.txt"
[ "$(jq_ "$V/r2a2ocheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['feeds:C17.1', 'feeds:J3.1']" ] && ok "r2 attempt-2 opus: feeds J3.1 and C17.1 at 0.00 A (the reviewer's two electrical majors, R2A2-O-1/2); the designer's own 147 rows pass" || bad "r2a2 opus: $(jq_ "$V/r2a2ocheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
fi  #@ end 26

if want 27; then  #@ watch: @q skills/kicad-design/scripts/pcbroute.py tools/bench/route_bench.py examples/rung1-zener-a1/board/**
echo "== 27 pcb route primitives: ratsnest count, strip keeps placement, DSN export, measure (P6-T1)"
for a in opus sonnet fable; do $PCB q "$ROOT"/examples/rung2-zener-a1-$a/board/*.kicad_pcb ratsnest --json > "$V/rn-$a.json"; done
[ "$(jq_ "$V/rn-opus.json" "d['airwires']")$(jq_ "$V/rn-sonnet.json" "d['airwires']")$(jq_ "$V/rn-fable.json" "(d['airwires'], d['open_nets'], d['kicad_unconnected'])")" = "00(6, 4, 6)" ] && ok "ratsnest: opus 0, sonnet 0, fable 6 airwires on 4 nets (the R2-F reviewer's 6 unconnected), KiCad's own count agrees" || bad "ratsnest: $(jq_ "$V/rn-fable.json" "d['airwires']")"
R="$V/route"; rm -rf "$R"; mkdir -p "$R"; cp "$ROOT"/examples/rung1-zener-a1/board/qwiic_imu.kicad_p* "$R"/
$PCB route measure "$R/qwiic_imu.kicad_pcb" --ref-value LSM6 --json > "$R/m0.json"
$PCB route strip "$R/qwiic_imu.kicad_pcb" --json > "$R/strip.json"
$PCB route measure "$R/qwiic_imu.kicad_pcb" --ref-value LSM6 --json > "$R/m1.json"
[ "$(jq_ "$R/strip.json" "(d['before']['tracks'], d['before']['vias'], d['after']['tracks'], d['after']['vias'], d['after']['zones'], d['after']['footprints'])")" = "(74, 25, 0, 0, 4, 15)" ] && ok "strip: 74 tracks and 25 vias gone, 4 zones and 15 footprints kept" || bad "strip: $(cat "$R/strip.json" | cut -c1-200)"
[ "$(jq_ "$R/m0.json" "(d['ratsnest']['airwires'], d['vias'], round(d['length_mm']), d['part']['ref'])")" = "(0, 25, 145, 'U1')" ] && [ "$(jq_ "$R/m1.json" "(d['ratsnest']['airwires'], d['open']['3V3'], d['open']['GND'] if 'GND' in d['open'] else 0, d['part']['airwires'])")" = "(23, 10, 0, 21)" ] && ok "measure: designer copper 0 airwires / 25 vias / 145 mm; stripped 23 airwires (3V3 10, GND 0 through its pour), 21 on U1's nets" || bad "measure: $(cut -c1-200 "$R/m1.json")"
$PCB q "$ROOT/examples/rung1-zener-a1/board/qwiic_imu.kicad_pcb" fps --json > "$R/fps0.json"; $PCB q "$R/qwiic_imu.kicad_pcb" fps --json > "$R/fps1.json"
python3 -I -c "
import json; a=json.load(open('$R/fps0.json'))['footprints']; b=json.load(open('$R/fps1.json'))['footprints']
k=lambda f: (f['ref'], tuple(f['pos']), f['rot'], f['layer']); assert sorted(map(k,a))==sorted(map(k,b)), 'placement moved'" 2> "$R/place.txt" && ok "strip: every footprint's position, rotation and layer unchanged" || bad "strip placement: $(cat "$R/place.txt")"
$PCB route export-dsn "$R/qwiic_imu.kicad_pcb" --json > "$R/dsn.json" && grep -q "(host_cad \"KiCad's Pcbnew\")" "$R/qwiic_imu.dsn" && [ "$(grep -c '(image ' "$R/qwiic_imu.dsn")" -ge 5 ] && ok "export-dsn: a pcbnew Specctra file with images ($(grep -c '(image ' "$R/qwiic_imu.dsn")) for the router" || bad "export-dsn: $(cat "$R/dsn.json")"
python3 -I "$ROOT/tools/bench/route_bench.py" table --md > "$R/table.md" && [ "$(grep -c '^| ' "$R/table.md")" -ge 34 ] && grep -q "| opus | tracks | krt / default | 58 -> \*\*0\*\* | \*\*0\*\* / 0 | 37 |" "$R/table.md" && grep -q "| opus | tracks | freerouting / default | 58 -> \*\*21\*\* | \*\*22\*\* / 0 | 5 |" "$R/table.md" && ok "route bench results: 33 rows; opus/tracks KRT 0 airwires 0 errors 37 vias, freerouting 21 airwires 22 errors 5 vias (P6-T3)" || bad "route bench table: $(grep -c '^| ' "$R/table.md") rows"
KRT_PY="${KRT_PY:-${KRT_DIR:-$REF/KiCadRoutingTools}/.venv/bin/python}"
if [ -x "$KRT_PY" ]; then
  # the loop on the rung-1 board: 23 airwires to 0 in two KRT passes, one new starved thermal on the LGA-14's GND pad, the 20
  # inherited errors (LGA pad gap, fill at 0.2 from P1-T14) separated, stitch discarded, verdict NOT CLEAN, exit 1 (P6-T4)
  $PCB route auto "$R/qwiic_imu.kicad_pcb" --work "$R/work" > "$R/auto.txt" 2>&1; rc=$?
  [ "$rc" = 1 ] && [ "$(jq_ "$R/route.json" "(d['clean'], d['start']['airwires'], sorted(d['start']['inherited_by_type'].items()), d['final']['airwires'], d['final']['new_errors'], d['final']['setup_changed'], [p['pass'] for p in d['passes']])")" = "(False, 23, [('clearance', 12), ('hole_clearance', 8)], 0, {'starved_thermal': 1}, False, [1, 2, 'stitch'])" ] && ok "route auto (KRT): 23 airwires -> 2 after pass 1 -> 0 after pass 2, one new starved thermal named, 20 inherited errors separated, stitch tried and discarded, exit 1" || bad "route auto: rc $rc $(tail -2 "$R/auto.txt" | cut -c1-300)"
  [ "$(jq_ "$R/route.json" "d['final']['vias'] > 0 and d['final']['tracks'] > 0")" = True ] && $PCB q "$R/qwiic_imu.kicad_pcb" ratsnest --json | grep -q '"airwires": 0' && ok "route auto wrote the routed board in place (0 airwires on re-measure)" || bad "route auto output"
  # order independence (P6-T6): the same board with its footprint blocks reversed routes to the same copper through `auto`
  python3 -I -c "
import sys; sys.path.insert(0, '$ROOT/skills/kicad-design/scripts')
import re
t = open('$ROOT/examples/rung1-zener-a1/board/qwiic_imu.kicad_pcb').read()
blocks = [m.span() for m in re.finditer(r'\n\t\(footprint .*?\n\t\)', t, re.S)]
fps = [t[a:b] for a, b in blocks]
out = []; last = 0
for (a, b), f in zip(blocks, reversed(fps)): out.append(t[last:a]); out.append(f); last = b
out.append(t[last:]); open('$R/rev.kicad_pcb', 'w').write(''.join(out)); print(len(fps))" > "$R/rev.txt"
  cp "$ROOT/examples/rung1-zener-a1/board/qwiic_imu.kicad_pro" "$R/rev.kicad_pro"
  $PCB route strip "$R/rev.kicad_pcb" > /dev/null && $PCB route auto "$R/rev.kicad_pcb" --work "$R/revwork" > "$R/revauto.txt" 2>&1
  $PCB q "$R/rev.kicad_pcb" nets --json > "$R/revnets.json"; $PCB q "$R/qwiic_imu.kicad_pcb" nets --json > "$R/fwdnets.json"
  python3 -I -c "
import json; a={n['net']: (n['length_mm'], n['vias']) for n in json.load(open('$R/fwdnets.json'))['nets']}; b={n['net']: (n['length_mm'], n['vias']) for n in json.load(open('$R/revnets.json'))['nets']}
d=[k for k in a if abs(a[k][0]-b[k][0]) > 0.005 or a[k][1] != b[k][1]]; assert not d, d; print('same copper on', len(a), 'nets')" > "$R/order.txt" 2>&1 && ok "route auto: $(cat "$R/rev.txt") footprints reversed in the file give identical per-net copper (canonical order, P6-T6)" || bad "route auto order: $(cat "$R/order.txt" | tail -1)"
else nochecks "KiCadRoutingTools not installed ($KRT_PY): route auto not run (install per tools/bench/README.md)"; fi
fi  #@ end 27

if want 16; then  #@ watch: skills/kicad-design/scripts/** examples/*/*.py
echo "== 16 every script compiles under python3 and under KiCad's Python 3.9 (P1-T13)"
  KPY="${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
  for py in python3 "$KPY"; do
    "$py" -I -m py_compile "$ROOT"/skills/kicad-design/scripts/*.py "$ROOT"/skills/kicad-design/scripts/pcblib/*.py "$ROOT"/examples/*/*.py 2> "$V/compile.txt" && ok "compiles under $("$py" -c 'import sys; print(sys.version.split()[0])')" || bad "compile: $(cat "$V/compile.txt")"
  done
fi  #@ end 16

#@ plumbing
# per-feature checks: each tools/verify.d/*.sh is sourced here and calls ok/bad. Each may use $ROOT, $PCB, $V, $RUNS, $REF.
# Under --changed, each by its # watch: header.
mkdir -p "$ROOT/tools/verify.d"
for f in "$ROOT"/tools/verify.d/*.sh; do [ -f "$f" ] && want "${f##*/}" && . "$f"; done
unit_end
# --changed: every unit the plan selected must have run (a broken want() or loop ran nothing and passed)
if [ -n "$CHANGED" ]; then
  for u in $EXPECT; do case " $RAN " in *" $u "*) ;; *) bad "verify_all: $u was selected but did not run" ;; esac; done
  echo "verify_all --changed: ran$RAN"
fi
echo; echo "verify_all: $pass passed, $fail failed  ($V)"
[ "$fail" = 0 ]
#@ plumbing end
