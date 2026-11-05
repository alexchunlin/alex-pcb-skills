# Filesystem-only coverage: output isolation, provenance, explicit-out locking and relative paths.
# watch: skills/kicad-design/scripts/pcbir.py skills/kicad-design/scripts/pcbcheck.py tools/verify.d/irdrop_paths.py tools/verify.d/irdrop_paths.sh
if python3 -I "$ROOT/tools/verify.d/irdrop_paths.py" > "$V/irdrop-paths.txt" 2>&1; then
    ok "irdrop filesystem controls: isolated defaults, relative paths, exclusive explicit output and failure recovery"
else
    cat "$V/irdrop-paths.txt"
    bad "irdrop filesystem controls"
fi
