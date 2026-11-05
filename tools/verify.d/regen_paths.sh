# Reject overlapping regeneration scratch paths before deletion, copying or CAD.
# watch: skills/kicad-design/scripts/pcbcli.py tools/verify.d/regen_paths.py
python3 -I "$ROOT/tools/verify.d/regen_paths.py" "$ROOT" > "$V/regen-paths.txt" 2>&1
if [ "$?" = 0 ]; then
    ok "regen output path preservation (7 cases)"
else
    cat "$V/regen-paths.txt"
    bad "regen output path preservation"
fi
