#!/bin/bash
# Mouse joining an existing 8:1 incast: sweep probe size vs CC.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 scripts/gen_fattree_400g.py --mix mix

BW=400
STOP=2.08
BUF=32
TOPO=ft2_4l2s
TRACE_NODES=trace_ft2
CCS=(pfc dcqcn hp timely)
TAGS=(32k 64k 128k 400k 1m 2m 5m 20m)

run_one() {
  local cc="$1" trace="$2"
  echo ">>> ${trace}  cc=${cc}"
  python2 run.py --cc "$cc" --topo "$TOPO" --trace "$trace" \
    --bw "$BW" --stop "$STOP" --buffer "$BUF" --enable_tr 0 \
    --trace_nodes "$TRACE_NODES"
}

for tag in "${TAGS[@]}"; do
  for cc in "${CCS[@]}"; do
    run_one "$cc" "ft_probe_${tag}_flow"
  done
done

python3 ../analysis/analyze_probe.py --mix mix --ccs pfc,dcqcn,hp,timely
echo "Done."
