#!/bin/bash
# Outcast HoL only: N:1 incast + victim QP on sender 0.
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

for n in 4 8; do
  echo "== outcast${n} =="
  for cc in "${CCS[@]}"; do
    run_one "$cc" "ft_outcast${n}_flow"
  done
done

python3 ../analysis/analyze_ft.py --mix mix --ccs pfc,dcqcn,hp,timely 2>&1 | sed -n '/=== outcast/,$p'
echo "Done."
