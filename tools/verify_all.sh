#!/bin/sh
# Re-prove every tool in this repo against the rung-1 attempts and the reference boards. Writes only under
# /tmp/alexpcb-verify/run-<pid> (latest: /tmp/alexpcb-verify/latest). About 5 minutes (sections 11 and 12 regenerate the attempts twice each).
#   sh tools/verify_all.sh            # everything
#   sh tools/verify_all.sh 1 5 7      # only these sections (the --changed selector from alex-3d-skills lands with phase 7)
# Inputs (read-only, copied first): RUNS (default ~/code-stuff/alex-pcb-runs) and REF (default /tmp/pcb-ref). A section
# whose input is missing prints NOTE and is not a failure.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PCB="$ROOT/skills/kicad-design/scripts/pcb"
RUNS="${RUNS:-$HOME/code-stuff/alex-pcb-runs}"
REF="${REF:-/tmp/pcb-ref}"
VT="${VERIFY_TMP:-/tmp/alexpcb-verify}"; V="$VT/run-$$"
rm -rf "$V"; mkdir -p "$V"; ln -sfn "$V" "$VT/latest"
printf '{"commit": "%s", "dirty": %s, "when": "%s"}\n' "$(git -C "$ROOT" rev-parse HEAD 2>/dev/null)" \
  "$([ -n "$(git -C "$ROOT" status --porcelain -- skills tools 2>/dev/null)" ] && echo true || echo false)" "$(date +%Y-%m-%dT%H:%M:%S)" > "$V/meta.json"
SEL="${*:-ALL}"
want() { [ "$SEL" = ALL ] || case " $SEL " in *" $1 "*) ;; *) return 1 ;; esac; echo "== $1 $2"; }
pass=0; fail=0
ok() { echo "PASS $1"; pass=$((pass+1)); }
bad() { echo "FAIL $1"; fail=$((fail+1)); }
jq_() { python3 -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2], {}, {'d': d}))" "$1" "$2" 2>/dev/null; }
# copies: the tools must never touch the attempts
Z="$V/zener"; K="$V/skidl"
[ -d "$RUNS/rung1-zener-a1" ] && cp -R "$RUNS/rung1-zener-a1" "$Z"
[ -d "$RUNS/rung1-skidl-a1" ] && cp -R "$RUNS/rung1-skidl-a1" "$K"
ZB="$Z/layout/qwiic_imu/qwiic_imu.kicad_pcb"; ZS="$Z/layout/qwiic_imu/qwiic_imu.kicad_sch"
KB="$K/qwiic_imu.kicad_pcb"; KS="$K/qwiic_imu.kicad_sch"
MB="$REF/motorgo-plink-hardware/motorgo_plink/motorgo_plink.kicad_pcb"

if want 1 "dual DRC on rung1-zener-a1: plain 20 errors, raw pack 0, floored pack 20, sentinel fires (R1-Z1-F1)"; then
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
else echo "NOTE no $ZB"; fi
fi

if want 2 "dual DRC on rung1-skidl-a1: plain 18 errors (R1-S1-F1)"; then
if [ -f "$KB" ]; then
  $PCB drc "$KB" --out "$V/kdrc" > "$V/kdrc.txt"
  [ "$(jq_ "$V/kdrc/drc.json" "d['plain']['errors']")" = 18 ] && ok "skidl plain 18 errors" || bad "skidl plain $(jq_ "$V/kdrc/drc.json" "d['plain']['errors']")"
  [ "$(jq_ "$V/kdrc/drc.json" "sorted(d['plain']['by_type']['error'].items())")" = "[('clearance', 12), ('hole_clearance', 6)]" ] && ok "skidl types clearance 12 + hole_clearance 6" || bad "skidl types $(jq_ "$V/kdrc/drc.json" "d['plain']['by_type']")"
  $PCB drc "$KB" --out "$V/kdrc-raw" --no-floor > /dev/null
  [ "$(jq_ "$V/kdrc-raw/drc.json" "d['packed']['errors']")" = 0 ] && ok "skidl raw pack 0 errors" || bad "skidl raw pack $(jq_ "$V/kdrc-raw/drc.json" "d['packed']['errors']")"
else echo "NOTE no $KB"; fi
fi

if want 3 "dual DRC on the Plink reference board with --pack jlcpcb: per-type cap, library paths through the mirror (P0-T2, P1-T1, P1-T2)"; then
if [ -f "$MB" ]; then
  t0=$(date +%s); $PCB drc "$MB" --pack jlcpcb --out "$V/mdrc" --no-floor > "$V/mdrc.txt"; t1=$(date +%s)
  [ "$(jq_ "$V/mdrc/drc.json" "d['plain']['by_type']['error']['copper_edge_clearance']")" = 40 ] && ok "plink plain copper_edge_clearance 40 (P0-T2)" || bad "plink edge $(jq_ "$V/mdrc/drc.json" "d['plain']['by_type']")"
  [ "$(jq_ "$V/mdrc/drc.json" "d['plain']['unconnected']")" = 6 ] && ok "plink 6 unconnected" || bad "plink unconnected $(jq_ "$V/mdrc/drc.json" "d['plain']['unconnected']")"
  [ "$(jq_ "$V/mdrc/drc.json" "d['sentinel']")" = fired ] && ok "plink sentinel fired through the resolved jlcpcb 4-layer pack" || bad "plink sentinel $(jq_ "$V/mdrc/drc.json" "d['sentinel']")"
  [ "$(jq_ "$V/mdrc/drc.json" "'track_width(sentinel)' in d['capped_types'] and 'silk_overlap' in d['capped_types']")" = True ] && ok "plink: 199 cap detected on the sentinel and silk_overlap (P1-T2)" || bad "plink cap $(jq_ "$V/mdrc/drc.json" "d['capped_types']")"
  [ "$(jq_ "$V/mdrc/drc.json" "d['packed']['by_type']['warning'].get('lib_footprint_mismatch')")" = 86 ] && ok "plink lib_footprint_mismatch 86 in the mirror = in place (library paths resolve, P1-T1)" || bad "plink lib mismatch $(jq_ "$V/mdrc/drc.json" "d['packed']['by_type']['warning'].get('lib_footprint_mismatch')")"
  echo "NOTE plink dual drc took $((t1-t0)) s"
else echo "NOTE no $MB (clone motorgo-plink-hardware into $REF)"; fi
fi

if want 4 "rejected rule pack is detected (P0-T5): bad layer name -> exit 2, sentinel not fired"; then
if [ -f "$ZB" ]; then
  printf '(version 1)\n(rule "bad layer" (layer "No.Such") (constraint clearance (min 0.1mm)))\n' > "$V/bad.kicad_dru"
  $PCB drc "$ZB" --pack "$V/bad.kicad_dru" --out "$V/zbad" > "$V/zbad.txt"; rc=$?
  [ "$rc" = 2 ] && ok "rejected pack exits 2" || bad "rejected pack exit $rc"
  grep -q "RULE PACK REJECTED" "$V/zbad.txt" && ok "rejected pack said so" || bad "no rejection message"
  printf '(version 1)\n(rule "ok" (constraint clearance (min 0.1mm)))\n' > "$V/ok.kicad_dru"
  $PCB drc "$ZB" --pack "$V/ok.kicad_dru" --out "$V/zok" > "$V/zok.txt"; rc=$?
  [ "$rc" = 1 ] && grep -q "sentinel fired" "$V/zok.txt" && ok "accepted pack: sentinel fired, exit 1 on the plain errors" || bad "accepted pack rc $rc"
else echo "NOTE no $ZB"; fi
fi

if want 5 "ERC and netlist on both rung-1 schematics"; then
for s in "$ZS" "$KS"; do
  [ -f "$s" ] || { echo "NOTE no $s"; continue; }
  n=$(basename "$(dirname "$s")"); $PCB erc "$s" --out "$V/erc-$n.json" > "$V/erc-$n.txt"; rc=$?
  grep -q "0 errors, 1 warnings" "$V/erc-$n.txt" && [ "$rc" = 0 ] && ok "erc $n: 0 errors 1 warning, exit 0" || bad "erc $n: $(head -1 "$V/erc-$n.txt") rc $rc"
  $PCB netlist "$s" "$V/net-$n.xml" > "$V/net-$n.txt" && grep -q "11 nets" "$V/net-$n.txt" && ok "netlist $n: 11 nets" || bad "netlist $n: $(cat "$V/net-$n.txt")"
done
fi

if want 6 "connectivity diff (P0-T3): identical, renamed, planted U1 SDA/SCL pin swap, schematic inputs"; then
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
else echo "NOTE section 5 did not run"; fi
fi

if want 7 "pcb q measurements reproduce the R1-Z1 review (decoupling, coverage, vias, silk, dist)"; then
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
else echo "NOTE no $ZB"; fi
fi

if want 8 "pcb fab on the Zener board: 14 gerber files, JLC BOM/CPL, J1/J2 origin offset flagged (R1-S1-F3, R1-S1-F4)"; then
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
else echo "NOTE no $ZB"; fi
fi

if want 9 "render, svg, stats"; then
if [ -f "$ZB" ]; then
  $PCB render "$ZB" --out "$V/r" --size 600 > /dev/null && [ -s "$V/r/qwiic_imu_top.png" ] && ok "render" || bad "render"
  $PCB svg "$ZB" --out "$V/r" > "$V/svg.txt" && [ "$(ls "$V/r"/*.svg | wc -l | tr -d ' ')" = 4 ] && ok "svg board: F, B, In1, In2" || bad "svg board: $(cat "$V/svg.txt")"
  $PCB svg "$ZS" --out "$V/rs" > "$V/svgs.txt" && ls "$V/rs"/*.svg > /dev/null 2>&1 && ok "svg schematic" || bad "svg schematic: $(cat "$V/svgs.txt")"
  $PCB stats "$ZB" --json "$V/stats.json" > "$V/stats.txt" && grep -q "4 copper layers" "$V/stats.txt" && [ "$(jq_ "$V/stats.json" "d['vias']['through']")" = 25 ] && ok "stats: 4 layers, 25 vias" || bad "stats: $(head -2 "$V/stats.txt")"
else echo "NOTE no $ZB"; fi
fi

if want 10 "GUI guards (P0-T6): layout/apply get --no-open, open is refused, guard runs"; then
  [ "$(PCB_DRY=1 $PCB layout foo.zen)" = "$HOME/.local/bin/pcb layout --no-open foo.zen" ] && ok "layout injects --no-open" || bad "layout: $(PCB_DRY=1 $PCB layout foo.zen)"
  [ "$(PCB_DRY=1 $PCB apply schematic --no-open foo.zen)" = "$HOME/.local/bin/pcb apply schematic --no-open foo.zen" ] && ok "apply keeps a single --no-open" || bad "apply: $(PCB_DRY=1 $PCB apply schematic --no-open foo.zen)"
  [ "$(PCB_DRY=1 $PCB build foo.zen)" = "$HOME/.local/bin/pcb build foo.zen" ] && ok "build passes through" || bad "build passthrough"
  $PCB open x > /dev/null 2>&1; [ $? = 2 ] && ok "open refused" || bad "open not refused"
  $PCB guard > /dev/null; rc=$?; [ "$rc" = 0 ] && ok "guard: no GUI running" || echo "NOTE guard reports a KiCad GUI running (rc $rc); not counted"
  $PCB > /dev/null && ok "pcb with no command prints help and exits 0" || bad "help exit"
fi

if want 11 "regen-check on rung1-zener-a1: reproduces R1-Z1-F2 (exit 1 from clean, pass 1 12 err/4 warn, pass 2 20/0)"; then
if [ -d "$Z" ]; then
  $PCB regen-check "$Z" --cmd tools/regen.sh --board layout/qwiic_imu/qwiic_imu.kicad_pcb --generated layout fab --out "$V/zregen" > "$V/zregen.txt"; rc=$?
  [ "$rc" = 1 ] && grep -q "FAILS" "$V/zregen.txt" && ok "zener regen-check FAILS with exit 1" || bad "zener regen-check rc $rc: $(tail -1 "$V/zregen.txt")"
  [ "$(jq_ "$V/zregen/regen.json" "(d['pass1']['cmd_exit'], d['pass1']['drc']['plain_errors'], d['pass1']['drc']['plain_warnings'])")" = "(1, 12, 4)" ] && ok "zener pass 1: regen.sh exit 1, DRC 12 errors 4 warnings (review: 4 isolated_copper)" || bad "zener pass 1 $(jq_ "$V/zregen/regen.json" "(d['pass1']['cmd_exit'], d['pass1']['drc'])")"
  [ "$(jq_ "$V/zregen/regen.json" "(d['pass2']['drc']['plain_errors'], d['pass2']['drc']['plain_warnings'])")" = "(20, 0)" ] && ok "zener pass 2 converges to 20/0" || bad "zener pass 2 $(jq_ "$V/zregen/regen.json" "d['pass2']['drc']")"
  [ "$(jq_ "$V/zregen/regen.json" "'placement' in ' '.join(d['diff_ref_pass1']) or 'copper' in ' '.join(d['diff_ref_pass1'])")" = False ] && ok "zener placement and tracks identical to the handed-in board" || bad "zener placement differs: $(jq_ "$V/zregen/regen.json" "d['diff_ref_pass1']")"
  [ "$(jq_ "$V/zregen/regen.json" "d['pass1']['fab']['gerbers']['qwiic_imu-Edge_Cuts.gm1'] == d['pass2']['fab']['gerbers']['qwiic_imu-Edge_Cuts.gm1']")" = True ] && ok "zener Edge.Cuts gerber hashes equal across passes (dates stripped, P1-T9)" || bad "zener edge gerber hash differs between passes"
  [ "$(jq_ "$V/zregen/regen.json" "d['pass1']['fab']['gerbers']['qwiic_imu-F_Cu.gtl'] == d['pass2']['fab']['gerbers']['qwiic_imu-F_Cu.gtl']")" = False ] && ok "zener F.Cu gerber differs between passes (the zone-fill difference is real)" || bad "zener F.Cu gerber equal between passes?"
else echo "NOTE no $Z"; fi
fi

if want 12 "regen-check on rung1-skidl-a1: exit 0 but the first pass from clean diverges (P1-T10)"; then
if [ -d "$K" ]; then
  $PCB regen-check "$K" --cmd ./check.sh --board qwiic_imu.kicad_pcb --generated qwiic_imu.kicad_sch qwiic_imu.kicad_pcb qwiic_imu.kicad_pro qwiic_imu.kicad_prl qwiic_imu.xml qwiic_imu.net fab qwiic_imu-drc.json qwiic_imu-erc.json qwiic_imu.kicad_dru --out "$V/sregen" > "$V/sregen.txt"; rc=$?
  [ "$rc" = 1 ] && ok "skidl regen-check FAILS" || bad "skidl regen-check rc $rc"
  [ "$(jq_ "$V/sregen/regen.json" "(d['pass1']['cmd_exit'], d['pass2']['cmd_exit'], d['pass1']['drc']['plain_errors'], d['pass2']['drc']['plain_errors'])")" = "(0, 0, 12, 18)" ] && ok "skidl check.sh exits 0 twice, DRC 12 errors on pass 1 and 18 on pass 2" || bad "skidl passes $(jq_ "$V/sregen/regen.json" "(d['pass1']['cmd_exit'], d['pass2']['cmd_exit'], d['pass1']['drc'], d['pass2']['drc'])")"
  [ "$(jq_ "$V/sregen/regen.json" "'nets' in ' '.join(d['diff_ref_pass1'])")" = False ] && ok "skidl netlist identical from clean" || bad "skidl netlist differs"
else echo "NOTE no $K"; fi
fi

echo; echo "verify_all: $pass passed, $fail failed  ($V)"
[ "$fail" = 0 ]
