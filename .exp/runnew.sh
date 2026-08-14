#!/bin/bash
set -e
cd /home/ubuntu/repo/simulation
OUT=/home/ubuntu/repo/.exp/out
NEW="onoff_pf2_nic4_t32_C onoff_pf2_nic4_t16_C onoff_pf2_nic4_t8_C"
for name in $NEW; do
  echo "[run] $name"; ./waf --run "scratch/third /home/ubuntu/repo/.exp/config_${name}.txt" >$OUT/log_${name}.txt 2>&1
done
echo "[extracting]"
cd /home/ubuntu/repo/analysis
for name in $NEW; do
  ./trace_reader $OUT/mix_${name}.tr 'dip=0x0b000001' 2>/dev/null | awk -v n=$name '
    $2=="n:64" && $8=="0b000001" && $5=="Enqu" { q=$4; qb=int(($1-2000000000)/10000); if(q>qm[qb])qm[qb]=q; lat=int(q/50000); if(lat>5000)lat=5000; H[lat]++; slat+=q/50000.0; nen++; }
    $2=="n:64" && $8=="0b000001" && $5=="Dequ" && $11=="U" { split($15,a,"("); p=a[2]; sub(/\)/,"",p); tb=int(($1-2000000000)/200000); T[tb]+=p; }
    END{ for(k in qm) print "Q",n,k,qm[k]; for(k in T) print "T",n,k,T[k]; for(k in H) print "H",n,k,H[k]; print "S",n,slat,nen; }' >> $OUT/C2_data.csv
done
echo "[extracted]"
