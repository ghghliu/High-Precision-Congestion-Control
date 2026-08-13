#!/bin/bash
# Run 400G PFC vs DCQCN microbenchmarks (HoL + small-flow).
set -euo pipefail
cd "$(dirname "$0")/.."

BW=400
STOP=2.05
CCS=(pfc dcqcn)

echo "== Dry-run configs =="
for cc in "${CCS[@]}"; do
  python2 run.py --cc "$cc" --topo bench_hol --trace bench_hol_flow \
    --bw "$BW" --stop "$STOP" --enable_tr 1 --trace_nodes trace_hol --dry_run
  python2 run.py --cc "$cc" --topo bench_sf --trace bench_sf_flow \
    --bw "$BW" --stop "$STOP" --enable_tr 1 --trace_nodes trace_sf --dry_run
done

echo "== Run HoL =="
for cc in "${CCS[@]}"; do
  echo ">>> HoL $cc"
  python2 run.py --cc "$cc" --topo bench_hol --trace bench_hol_flow \
    --bw "$BW" --stop "$STOP" --enable_tr 1 --trace_nodes trace_hol
done

echo "== Run small-flow =="
for cc in "${CCS[@]}"; do
  echo ">>> SF $cc"
  python2 run.py --cc "$cc" --topo bench_sf --trace bench_sf_flow \
    --bw "$BW" --stop "$STOP" --enable_tr 1 --trace_nodes trace_sf
done

echo "== Analyze =="
python3 ../analysis/analyze_bench.py --mix mix
echo "Done."
