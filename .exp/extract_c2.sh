#!/bin/bash
set -e
cd /home/ubuntu/repo/analysis
make trace_reader >/dev/null 2>&1
OUT=/home/ubuntu/repo/.exp/out
RUNS="pfc_C dcqcn_C hpcc_C timely_C onoff_ideal_C onoff_nic4_C onoff_nic4_32_C onoff_nic4_100_C onoff_s1_C onoff_s4_C onoff_s16_C onoff_g4_C onoff_g16_C onoff_to64_C onoff_to460_C onoff_lvl2_C onoff_lvl8_C"
> $OUT/C2_data.csv
for name in $RUNS; do
  echo "[extract] $name"
  ./trace_reader $OUT/mix_${name}.tr 'dip=0x0b000001' 2>/dev/null | awk -v n=$name '
    $2=="n:64" && $8=="0b000001" && $5=="Enqu" {
      q=$4; qb=int(($1-2000000000)/10000); if(q>qm[qb])qm[qb]=q;
      lat=int(q/50000); if(lat>5000)lat=5000; H[lat]++; slat+=q/50000.0; nen++;
    }
    $2=="n:64" && $8=="0b000001" && $5=="Dequ" && $11=="U" {
      split($15,a,"("); pl=a[2]; sub(/\)/,"",pl); tb=int(($1-2000000000)/200000); T[tb]+=pl;
    }
    END{
      for(k in qm) print "Q",n,k,qm[k];
      for(k in T)  print "T",n,k,T[k];
      for(k in H)  print "H",n,k,H[k];
      print "S",n,slat,nen;
    }
  ' >> $OUT/C2_data.csv
done
wc -l $OUT/C2_data.csv
