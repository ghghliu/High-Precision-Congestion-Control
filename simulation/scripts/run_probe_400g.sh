#!/bin/bash
# Mouse joining an existing 8:1 incast: sweep probe size vs CC.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 scripts/gen_fattree_400g.py --mix mix

BW=400
# 20MB at DCQCN MIN_RATE=1Gbps needs ~160ms; 8x80MB incast is ~15-30ms.
STOP=2.25
BUF=32
TOPO=ft2_4l2s
TRACE_NODES=trace_ft2
CCS=(pfc dcqcn hp timely)
TAGS=(32k 64k 128k 400k 1m 2m 5m 20m)
SKIP_EXISTING="${SKIP_EXISTING:-1}"
JOBS="${JOBS:-2}"

cctag() {
  if [ "$1" = hp ]; then echo hp95; else echo "$1"; fi
}

run_one() {
  local cc="$1" trace="$2"
  local fct="mix/fct_${TOPO}_${trace}_$(cctag "$cc").txt"
  if [ "$SKIP_EXISTING" = 1 ] && [ -f "$fct" ] && grep -q " 100 " "$fct"; then
    echo ">>> skip ${trace}  cc=${cc} (fct exists)"
    return 0
  fi
  echo ">>> ${trace}  cc=${cc}"
  python2 run.py --cc "$cc" --topo "$TOPO" --trace "$trace" \
    --bw "$BW" --stop "$STOP" --buffer "$BUF" --enable_tr 0 \
    --trace_nodes "$TRACE_NODES"
}

fail=0
pids=()
wait_oldest() {
  while [ "${#pids[@]}" -ge "$JOBS" ]; do
    local pid="${pids[0]}"
    pids=("${pids[@]:1}")
    wait "$pid" || fail=1
  done
}

for tag in "${TAGS[@]}"; do
  for cc in "${CCS[@]}"; do
    run_one "$cc" "ft_probe_${tag}_flow" &
    pids+=($!)
    wait_oldest
  done
done
for pid in "${pids[@]}"; do
  wait "$pid" || fail=1
done

python3 ../analysis/analyze_probe.py --mix mix --ccs pfc,dcqcn,hp,timely \
  --out-md ../docs/probe_table_400g.md \
  --out-svg ../docs/probe_slowdown_400g.svg
if [ "$fail" != 0 ]; then
  echo "one or more sims failed" >&2
  exit 1
fi
echo "Done."
