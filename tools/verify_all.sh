#!/bin/sh
# Re-prove every tool in this repo against the rung-1 attempts and the reference boards. Writes only under
# /tmp/alexpcb-verify/run-<pid> (latest: /tmp/alexpcb-verify/latest). About 6 minutes (sections 11 and 12 regenerate the attempts twice each).
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

if want 13 "pcbcheck on rung1-zener-a1 with examples/rung1-zener-a1/checks.json: exactly the review's C3 and refdes findings"; then
if [ -f "$ZB" ]; then
  $PCB check "$ZB" "$ROOT/examples/rung1-zener-a1/checks.json" --out "$V/zcheck.json" > "$V/zcheck.txt"; rc=$?
  [ "$rc" = 1 ] && ok "zener check exits 1" || bad "zener check rc $rc"
  [ "$(jq_ "$V/zcheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['decoupling:U1.8:C3', 'silk:refdes']" ] && ok "zener fails are exactly C3 decoupling and silk refdes (R1-Z1-F3, R1-Z1-F4)" || bad "zener fails $(jq_ "$V/zcheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
  [ "$(jq_ "$V/zcheck.json" "[r['value'] for r in d['rows'] if r['id']=='decoupling:U1.8:C3'][0]")" = 2.639 ] && ok "zener C3 row carries 2.639 mm (review: 2.639)" || bad "zener C3 value"
  [ "$(jq_ "$V/zcheck.json" "[r['value'] for r in d['rows'] if r['id']=='silk:refdes'][0]")" = 10 ] && ok "zener 10 hidden refdes named in BRINGUP.md" || bad "zener silk $(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['id']=='silk:refdes']")"
  [ "$(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['id']=='addresses:I2C:U1'][0]")" = "U1 strap pin 1 (SA0) resolves high through ['JP1'] -> 0x6b; declared 0x6b" ] && ok "zener address strap resolves 0x6B through JP1" || bad "zener address $(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['check']=='addresses']")"
  [ "$(jq_ "$V/zcheck.json" "[r['value'] for r in d['rows'] if r['id']=='pullups:I2C:sda'][0]")" = 3.0 ] && ok "zener pull-up chain: 2 boards = 3.0 mA, at the limit (review R1-S1-F2 arithmetic)" || bad "zener pullups $(jq_ "$V/zcheck.json" "[r['msg'] for r in d['rows'] if r['check']=='pullups']")"
  [ "$(jq_ "$V/zcheck.json" "sum(1 for r in d['rows'] if r['check']=='connectors' and r['status']=='pass')")" = 3 ] && ok "zener J1/J2/J3 pin maps pass" || bad "zener connectors"
  [ "$(jq_ "$V/zcheck.json" "d['summary']['passes']")" = 22 ] && ok "zener 22 passes" || bad "zener passes $(jq_ "$V/zcheck.json" "d['summary']")"
else echo "NOTE no $ZB"; fi
fi

if want 14 "pcbcheck on rung1-skidl-a1: the 'four boards' and '2x the floor' claims fail as rows (R1-S1-F2)"; then
if [ -f "$KB" ]; then
  $PCB check "$KB" "$ROOT/examples/rung1-skidl-a1/checks.json" --out "$V/scheck.json" > "$V/scheck.txt"; rc=$?
  [ "$(jq_ "$V/scheck.json" "sorted(r['id'] for r in d['rows'] if r['status']=='fail')")" = "['margin:edge_clearance', 'margin:hole_clearance', 'margin:via_diameter', 'pullups:I2C:scl', 'pullups:I2C:sda', 'silk:refdes']" ] && ok "skidl fails: pull-up chain x2, margin x3, silk" || bad "skidl fails $(jq_ "$V/scheck.json" "[r['id'] for r in d['rows'] if r['status']=='fail']")"
  [ "$(jq_ "$V/scheck.json" "[r['value'] for r in d['rows'] if r['id']=='pullups:I2C:sda'][0]")" = 6.0 ] && ok "skidl 4 boards = 6.0 mA against 3.0 (the 'up to four boards' claim)" || bad "skidl pullup value"
  [ "$(jq_ "$V/scheck.json" "[r['value'] for r in d['rows'] if r['id']=='margin:via_diameter'][0]")" = 1.33 ] && ok "skidl via diameter 1.33x the floor (the '2x every feature' claim)" || bad "skidl margin value"
  [ "$(jq_ "$V/scheck.json" "sum(1 for r in d['rows'] if r['check']=='decoupling' and r['status']=='pass')")" = 5 ] && ok "skidl decoupling: all 5 rows within 2 mm (review: 1.69 to 1.98 mm)" || bad "skidl decoupling $(jq_ "$V/scheck.json" "[r['msg'] for r in d['rows'] if r['check']=='decoupling']")"
else echo "NOTE no $KB"; fi
fi

if want 15 "pcbcheck planted misdeclarations: swapped Qwiic pins, undeclared jumper, wrong address, undeclared rail, unknown key"; then
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
else echo "NOTE no $ZB"; fi
fi

if want 17 "pcblib.board: the ported Zener layout on a board fresh from Diode pcb layout gives the designer's copper (P1-T14, P1-T15)"; then
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
else echo "NOTE no $Z or no Diode pcb"; fi
fi

if want 18 "pcblib.board.from_netlist builds the SKiDL board from its kicadxml with pad nets and fields"; then
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
else echo "NOTE no $K"; fi
fi

if want 19 "pcb schfix on a raw Diode schematic without the test-point power hack: fields, labels, symlib, PWR_FLAGs; ERC 2/32 -> 0/1 (P1-T16)"; then
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
else echo "NOTE no $Z or no Diode pcb"; fi
fi

if want 20 "skills: every FINDINGS ID cited in skills/ and examples/ exists; templates and reference files present"; then
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
fi

if want 16 "every script compiles under python3 and under KiCad's Python 3.9 (P1-T13)"; then
  KPY="${KICAD_PY:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3}"
  for py in python3 "$KPY"; do
    "$py" -I -m py_compile "$ROOT"/skills/kicad-design/scripts/*.py "$ROOT"/skills/kicad-design/scripts/pcblib/*.py "$ROOT"/examples/*/*.py 2> "$V/compile.txt" && ok "compiles under $("$py" -c 'import sys; print(sys.version.split()[0])')" || bad "compile: $(cat "$V/compile.txt")"
  done
fi

echo; echo "verify_all: $pass passed, $fail failed  ($V)"
[ "$fail" = 0 ]
