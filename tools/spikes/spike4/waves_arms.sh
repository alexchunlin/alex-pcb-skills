#!/bin/sh
# Spike #4 (H2 inside the waves): the rules plan of plan_bench.py under each KRT net order, scored with the SIG judges.
#   sh tools/spikes/spike4/waves_arms.sh [boards]        (default: opus sonnet opus2; one board at a time, sequential)
# Plans go to /tmp/spike4/plans/, rows to tools/bench/results/plan.jsonl with tag spike4-h2-waves.
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PB="$ROOT/tools/bench/plan_bench.py"
P=/tmp/spike4/plans; mkdir -p "$P"
for b in ${*:-opus sonnet opus2}; do
  python3 -I "$PB" rules --board "$b" > "$P/$b-rules.json"
  python3 -I "$PB" orders --board "$b" --plan "$P/$b-rules.json" --out "$P" > /dev/null
  for arm in mps original rand1 rand2 rand3 rand4 rand5; do
    python3 -I "$PB" score --board "$b" --plan "$P/$b-$arm.json" --arm "$arm" --tag spike4-h2-waves | cut -c1-200
  done
  for o in planar share contended; do
    python3 -I "$PB" score --board "$b" --plan "$P/$b-mps.json" --arm "gp_$o" --tag spike4-h2-waves --env KICAD_GLOBAL_PLAN=1 KICAD_GLOBAL_PLAN_ORDER=$o | cut -c1-200
  done
done
