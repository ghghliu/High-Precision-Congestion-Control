#!/bin/bash
set -e
cd /home/ubuntu/repo/analysis
make trace_reader >/dev/null 2>&1
OUT=/home/ubuntu/repo/.exp/out
RUNS="pfc_C dcqcn_C hpcc_C timely_C onoff_ideal_C onoff_s4g4_C onoff_s4g8_C onoff_s4g16_C onoff_s8g4_C onoff_s8g8_C onoff_s8g16_C onoff_s16g4_C onoff_s16g8_C onoff_s16g16_C onoff_s8g8_nic16_C onoff_s8g8_nic100_C"
> $OUT/C_data.csv
for name in $RUNS; do
  echo "[extract] $name"
  ./trace_reader $OUT/mix_${name}.tr 'dip=0x0b000001' 2>/dev/null | awk -v n=$name '
    $2=="n:64" && $8=="0b000001" && $5=="Enqu" { qb=int(($1-2000000000)/10000); if($4>qm[qb])qm[qb]=$4 }
    $2=="n:64" && $8=="0b000001" && $5=="Dequ" && $11=="U" { split($15,a,"("); pl=a[2]; sub(/\)/,"",pl); tb=int(($1-2000000000)/200000); b[tb]+=pl }
    END{ for(k in qm) print "Q",n,k,qm[k]; for(k in b) print "T",n,k,b[k] }
  ' >> $OUT/C_data.csv
done
wc -l $OUT/C_data.csv
