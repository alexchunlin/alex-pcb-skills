# Pure-Python controls for block gate failures, status replay, re-gating and exclusions.
# watch: skills/kicad-design/scripts/pcbblock.py tools/verify.d/pcbblock_cases.py tools/verify.d/pcbblock.sh
python3 -I "$ROOT/tools/verify.d/pcbblock_cases.py" > "$V/pcbblock-cases.txt" 2>&1 \
    && ok "block gates: checker failures, history, re-gating and placement controls" \
    || bad "block gate controls: $(tail -5 "$V/pcbblock-cases.txt")"
