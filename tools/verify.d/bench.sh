# Replay bench (tools/bench/replay.py): lint, a HEAD run over the four archived boards, and the recall the current
# tools must reach on the labelled findings (the gate: recall up, false fails not up, per tools/bench/README.md).
# Sourced by tools/verify_all.sh. About 2 min (drc + check + fab per board; regen only via --from-verify).
# watch: tools/bench/replay.py tools/bench/labels.json tools/bench/corpus.json examples/*/board/** examples/plink/* examples/*/checks.json @cli @check @q
python3 -I "$ROOT/tools/bench/replay.py" lint > "$V/bench-lint.txt" 2>&1 && ok "bench lint: $(cat "$V/bench-lint.txt")" || bad "bench lint: $(cat "$V/bench-lint.txt")"
python3 -I "$ROOT/tools/bench/replay.py" --no-save > "$V/bench.txt" 2>&1; rc=$?
[ "$rc" = 0 ] && ok "bench run on HEAD" || bad "bench run rc $rc: $(tail -3 "$V/bench.txt")"
grep -q "^rung1-zener-a1 .*recall fail 3 fw 3 .*not run \['R1-Z1-F2'\]" "$V/bench.txt" && ok "bench zener: 3 of 3 labels caught as fails (F1 drc, F3 and F4 check); F2 is regen, verify-only" || bad "bench zener: $(grep '^rung1-zener-a1' "$V/bench.txt")"
grep -q "^rung1-skidl-a1 .*recall fail 4 fw 5 .*false fails 0 " "$V/bench.txt" && ok "bench skidl: 4 fails + 1 warn of 5 (F1 drc; F2a margin, F2b pull-ups, F2c GND via; F4 CPL offset as a warn), 0 false fails" || bad "bench skidl: $(grep '^rung1-skidl-a1' "$V/bench.txt")"
grep -q "^plink-v1 .*missed \['PLINK-SCHOTTKY', 'PLINK-SILK'\].*| rows: fail 1 fw 1 ff 0" "$V/bench.txt" && ok "bench plink-v1: the fabbed IMU SDA/SCL swap caught in rows scope (P1-T18); Schottky and silk are honest misses" || bad "bench plink-v1: $(grep '^plink-v1' "$V/bench.txt")"
grep -q "^plink-fixed .*recall fail 1 fw 1 .*false fails 0 " "$V/bench.txt" && ok "bench plink-fixed: edge/unconnected label caught, 0 false fails (pinmaps pass after the rework)"
grep -q "^ALL .*false fails 0 " "$V/bench.txt" && ok "bench ALL: 0 false fails" || bad "bench ALL: $(grep '^ALL' "$V/bench.txt")" || bad "bench plink-fixed: $(grep '^plink-fixed' "$V/bench.txt")"
