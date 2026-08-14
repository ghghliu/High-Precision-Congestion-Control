#!/bin/bash
set -e
cd /home/ubuntu/repo/analysis
make trace_reader >/dev/null 2>&1
OUT=/home/ubuntu/repo/.exp/out
> $OUT/expA_thru.csv
for sch in pfc dcqcn hpcc timely; do
  echo "[extract] $sch"
  ./trace_reader $OUT/mix_${sch}_A.tr 'dip=0x0b000001' 2>/dev/null | awk -v sch=$sch '
    $2=="n:64" && $5=="Dequ" && $11=="U" {
      split($15,a,"("); pl=a[2]; sub(/\)/,"",pl);
      bin=int(($1-2000000000)/200000);
      key=$7"_"bin; bytes[key]+=pl; sips[$7]=1; if(bin>maxb)maxb=bin;
    }
    END{ for(s in sips) for(b=0;b<=maxb;b++){k=s"_"b; printf "%s %s %d %d\n", sch, s, b, (k in bytes?bytes[k]:0)} }
  ' >> $OUT/expA_thru.csv
done
wc -l $OUT/expA_thru.csv
