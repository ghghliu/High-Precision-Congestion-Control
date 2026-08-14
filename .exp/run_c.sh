#!/bin/bash
set -e
cd /home/ubuntu/repo/simulation
echo "[build] rebuilding ns-3 with on/off CC (mode 12)..."
CC=gcc CXX=g++ ./waf configure >/tmp/build.log 2>&1
./waf build -j$(nproc) >>/tmp/build.log 2>&1 && echo "[build] ok" || { tail -30 /tmp/build.log; exit 1; }
OUT=/home/ubuntu/repo/.exp/out
RUNS="pfc_C dcqcn_C hpcc_C timely_C onoff_ideal_C onoff_s4g4_C onoff_s4g8_C onoff_s4g16_C onoff_s8g4_C onoff_s8g8_C onoff_s8g16_C onoff_s16g4_C onoff_s16g8_C onoff_s16g16_C onoff_s8g8_nic16_C onoff_s8g8_nic100_C"
for name in $RUNS; do
  echo "[run] $name"
  ./waf --run "scratch/third /home/ubuntu/repo/.exp/config_${name}.txt" >$OUT/log_${name}.txt 2>&1
done
echo "[done]"
