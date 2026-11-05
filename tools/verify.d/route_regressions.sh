# watch: skills/kicad-design/scripts/pcbroute.py tools/verify.d/route_*.py tools/verify.d/route_regressions.sh
mkdir -p "$V/route-regressions"
python3 -I "$ROOT/tools/verify.d/route_paths.py" --source "$ROOT/skills/kicad-design/scripts/pcbroute.py" --expect fixed --output "$V/route-regressions/paths.json" > "$V/route-regressions/paths.log" 2>&1 \
    && ok "router: eight relative/absolute input/output path controls" \
    || bad "router paths: $(tail -4 "$V/route-regressions/paths.log")"
python3 -I "$ROOT/tools/verify.d/route_import.py" --source "$ROOT/skills/kicad-design/scripts/pcbroute.py" --output "$V/route-regressions/import" > "$V/route-regressions/import.log" 2>&1 \
    && ok "router: successful import and failed import with fresh/stale output" \
    || bad "router import: $(tail -4 "$V/route-regressions/import.log")"
python3 -I "$ROOT/tools/verify.d/route_setup.py" --output "$V/route-regressions/setup" > "$V/route-regressions/setup.log" 2>&1 \
    && ok "router: ten postpass settings and selected-output controls" \
    || bad "router setup: $(tail -4 "$V/route-regressions/setup.log")"
python3 -I "$ROOT/tools/verify.d/route_groups.py" > "$V/route-regressions/groups.log" 2>&1 \
    && ok "router: group references survive canonicalization" \
    || bad "router groups: $(tail -4 "$V/route-regressions/groups.log")"
