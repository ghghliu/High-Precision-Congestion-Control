#!/bin/bash
set -e
cd /home/ubuntu/repo/simulation
echo "[build]"; CC=gcc CXX=g++ ./waf build -j$(nproc) >/tmp/build.log 2>&1 && echo ok || { tail -30 /tmp/build.log; exit 1; }
OUT=/home/ubuntu/repo/.exp/out
RUNS="pfc_C dcqcn_C hpcc_C timely_C onoff_ideal_C onoff_nic4_C onoff_nic4_32_C onoff_nic4_100_C onoff_s1_C onoff_s4_C onoff_s16_C onoff_g4_C onoff_g16_C onoff_to64_C onoff_to460_C onoff_lvl2_C onoff_lvl8_C"
for name in $RUNS; do
  echo "[run] $name"
  ./waf --run "scratch/third /home/ubuntu/repo/.exp/config_${name}.txt" >$OUT/log_${name}.txt 2>&1
done
echo "[done]"
