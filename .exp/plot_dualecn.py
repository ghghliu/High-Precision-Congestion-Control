#!/usr/bin/env python3
import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
OUT="/workspace/.exp/out"; ART="/opt/cursor/artifacts"; os.makedirs(ART,exist_ok=True)
Q={};T={};H={};S={}
for line in open(OUT+"/C2_data.csv"):
    p=line.split()
    if len(p)<4: continue
    d={"Q":Q,"T":T,"H":H}.get(p[0])
    if d is not None: d.setdefault(p[1],{})[int(p[2])]=float(p[3])
    elif p[0]=="S": S[p[1]]=(float(p[2]),float(p[3]))
def util(n):
    tb=T.get(n,{}); ss=[tb.get(i,0) for i in range(5,50)]; return sum(ss)*8/(len(ss)*200e-6)/400e9*100
def maxq(n):
    x=Q.get(n,{}); return (max(x.values()) if x else 0)/1000
def p99(n):
    h=H.get(n,{}); t=sum(h.values());
    if not t: return 0
    c=0
    for b in sorted(h):
        c+=h[b]
        if c>=0.99*t: return b
    return max(h)
def pfc(n):
    f="%s/pfc_%s.txt"%(OUT,n); return sum(1 for _ in open(f)) if os.path.exists(f) else 0

# Panel 1: scheme comparison
comp=[("hpcc_C","HPCC"),("dcqcn_C","DCQCN"),("onoff_hu_t64_l8_C","mode12\nproactiveON+to64"),
      ("de_l50_h200_C","mode13 dual-ECN\n(Klow50,Khigh200)"),("de_l50_h200_noto_C","mode13 dual-ECN\nNO timeout")]
# Panel 2: watermark insensitivity
wm=[("de_l20_h100_C","20/100"),("de_l20_h200_C","20/200"),("de_l50_h200_C","50/200"),
    ("de_l100_h200_C","100/200"),("de_l50_h400_C","50/400"),("de_l100_h400_C","100/400")]
fig,axes=plt.subplots(1,2,figsize=(15,5.5))
x=np.arange(len(comp)); w=0.4
u=[util(n) for n,_ in comp]; q=[p99(n) for n,_ in comp]
ax=axes[0]; ax2=ax.twinx()
b1=ax.bar(x-w/2,u,w,color="#4C72B0",label="utilization %")
b2=ax2.bar(x+w/2,q,w,color="#C44E52",label="p99 latency us")
ax.set_xticks(x); ax.set_xticklabels([l for _,l in comp],fontsize=8)
ax.set_ylabel("utilization (%)",color="#4C72B0"); ax2.set_ylabel("p99 queuing latency (us)",color="#C44E52")
ax.set_title("Scheme comparison (8:1 incast, 400G; all 0 PFC except none here)")
for i,(n,_) in enumerate(comp):
    ax.text(x[i]-w/2,u[i],"%.0f"%u[i],ha="center",va="bottom",fontsize=8)
    ax2.text(x[i]+w/2,q[i],"%.0f"%q[i],ha="center",va="bottom",fontsize=8)
ax=axes[1]; xr=np.arange(len(wm))
uu=[util(n) for n,_ in wm]; qq=[maxq(n) for n,_ in wm]
ax3=ax.twinx()
ax.bar(xr-w/2,uu,w,color="#55A868",label="util %")
ax3.bar(xr+w/2,qq,w,color="#CCB974",label="maxQ KB")
ax.set_xticks(xr); ax.set_xticklabels([l for _,l in wm]); ax.set_ylim(0,100)
ax.set_xlabel("Klow/Khigh (KB)"); ax.set_ylabel("utilization (%)"); ax3.set_ylabel("max queue (KB)")
ax.set_title("Dual-ECN is insensitive to watermark choice (all ~96%, 0 PFC)")
for i in range(len(wm)):
    ax.text(xr[i]-w/2,uu[i],"%.0f"%uu[i],ha="center",va="bottom",fontsize=8)
fig.tight_layout(); fig.savefig(ART+"/dualecn_comparison.png",dpi=110); print("saved dualecn_comparison.png")
