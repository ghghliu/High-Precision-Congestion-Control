#!/bin/bash
# 400G 2-tier fat-tree: PFC / DCQCN / HPCC / TIMELY
set -euo pipefail
cd "$(dirname "$0")/.."

python3 scripts/gen_fattree_400g.py --mix mix

BW=400
STOP=2.05
BUF=32
TOPO=ft2_4l2s
TRACE_NODES=trace_ft2
CCS=(pfc dcqcn hp timely)

run_one() {
  local cc="$1" trace="$2"
  echo ">>> ${trace}  cc=${cc}"
  python2 run.py --cc "$cc" --topo "$TOPO" --trace "$trace" \
    --bw "$BW" --stop "$STOP" --buffer "$BUF" --enable_tr 0 \
    --trace_nodes "$TRACE_NODES"
}

echo "== pair2 sanity (routing / 1:1) =="
for cc in "${CCS[@]}"; do
  run_one "$cc" ft_pair2_flow
done

echo "== HoL (16:1 incast + victim) =="
for cc in "${CCS[@]}"; do
  run_one "$cc" ft_hol_flow
done

echo "== incast8 (DCQCN slow recovery) =="
for cc in "${CCS[@]}"; do
  run_one "$cc" ft_incast8_flow
done

echo "== incast16 (degree trend) =="
for cc in "${CCS[@]}"; do
  run_one "$cc" ft_incast16_flow
done

echo "== Analyze =="
python3 ../analysis/analyze_ft.py --mix mix --ccs pfc,dcqcn,hp,timely
echo "Done."
