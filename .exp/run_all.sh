#!/bin/bash
set -e
cd /home/ubuntu/repo/simulation
if [ ! -f build/scratch/third ]; then
  echo "[build] configuring + building ns-3 (one-time)..."
  CC=gcc CXX=g++ ./waf configure >/tmp/build.log 2>&1
  ./waf build -j$(nproc) >>/tmp/build.log 2>&1
fi
for exp in A B; do
  for sch in pfc dcqcn hpcc timely; do
    cfg=/home/ubuntu/repo/.exp/config_${sch}_${exp}.txt
    echo "[run] exp=$exp scheme=$sch"
    /usr/bin/time -v ./waf --run "scratch/third $cfg" >/home/ubuntu/repo/.exp/out/log_${sch}_${exp}.txt 2>&1 || \
      ./waf --run "scratch/third $cfg" >/home/ubuntu/repo/.exp/out/log_${sch}_${exp}.txt 2>&1
    tail -1 /home/ubuntu/repo/.exp/out/log_${sch}_${exp}.txt
  done
done
echo "[done] all runs finished"
ls -la /home/ubuntu/repo/.exp/out/ | grep -E "fct_|pfc_|mix_" | awk '{print $5, $9}'
