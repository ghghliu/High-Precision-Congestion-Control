#!/bin/bash
set -e
cd /home/ubuntu/repo/simulation
echo "[build]"; CC=gcc CXX=g++ ./waf build -j$(nproc) >/tmp/build.log 2>&1 && echo ok || { tail -30 /tmp/build.log; exit 1; }
OUT=/home/ubuntu/repo/.exp/out
RUNS="pfc_C dcqcn_C hpcc_C timely_C onoff_nic4_C onoff_nic4_32_C onoff_nic4_100_C onoff_hu_t16_l8_C onoff_hu_t16_l16_C onoff_hu_t32_l8_C onoff_hu_t32_l16_C onoff_hu_t64_l8_C onoff_hu_t64_l16_C onoff_hu_best_nic4_C onoff_hu_best_nic32_C onoff_hu_best_nic100_C"
for name in $RUNS; do
  echo "[run] $name"
  ./waf --run "scratch/third /home/ubuntu/repo/.exp/config_${name}.txt" >$OUT/log_${name}.txt 2>&1
done
echo "[done]"
