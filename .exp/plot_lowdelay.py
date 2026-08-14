#!/usr/bin/env python3
import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
def p99(n):
    h=H.get(n,{}); t=sum(h.values())
    if not t: return 0
    c=0
    for b in sorted(h):
        c+=h[b]
        if c>=0.99*t: return b
    return max(h)
def maxq(n):
    x=Q.get(n,{}); return (max(x.values()) if x else 0)/1000
Ns=[2,8,32]
schemes=[("dcqcn","DCQCN","#8172B2"),("hpcc","HPCC","#4C72B0"),("de","dual-ECN(m13)","#CCB974"),("ml","multi-level(m14)","#55A868")]
fig,axes=plt.subplots(1,3,figsize=(17,5))
for sch,l,c in schemes:
    axes[0].plot(Ns,[util("%s_ld_N%d"%(sch,N)) for N in Ns],"o-",color=c,label=l)
    axes[1].plot(Ns,[p99("%s_ld_N%d"%(sch,N)) for N in Ns],"o-",color=c,label=l)
    axes[2].plot(Ns,[maxq("%s_ld_N%d"%(sch,N)) for N in Ns],"o-",color=c,label=l)
axes[0].set_title("Utilization vs N"); axes[0].set_ylabel("util %"); axes[0].set_ylim(0,105)
axes[1].set_title("p99 queuing latency vs N"); axes[1].set_ylabel("p99 latency (us)"); axes[1].set_yscale("log")
axes[2].set_title("max queue vs N"); axes[2].set_ylabel("max queue (KB)"); axes[2].set_yscale("log")
for a in axes: a.set_xlabel("incast degree N"); a.set_xticks(Ns); a.grid(alpha=0.3,which="both"); a.legend(fontsize=8)
fig.suptitle("LOW-DELAY regime (~2us feedback, 2us NIC): on/off vs DCQCN/HPCC",fontsize=13)
fig.tight_layout(); fig.savefig(ART+"/lowdelay_incast.png",dpi=110); print("saved lowdelay_incast.png")

# high vs low delay for on/off at N=8 (shows the delay was the bottleneck)
fig2,ax=plt.subplots(figsize=(9,5))
pairs=[("de_N8","m13 high-delay"),("de_ld_N8","m13 low-delay"),("ml_N8","m14 high-delay"),("ml_ld_N8","m14 low-delay"),("dcqcn_ld_N8","DCQCN(ref)"),("hpcc_ld_N8","HPCC(ref)")]
import numpy as np
x=np.arange(len(pairs)); 
p=[p99(n) for n,_ in pairs]
b=ax.bar(x,p,color=["#CCB974","#B8860B","#55A868","#2E7D32","#8172B2","#4C72B0"])
for i in x: ax.text(i,p[i],"%.0f"%p[i],ha="center",va="bottom",fontsize=9)
ax.set_xticks(x); ax.set_xticklabels([l for _,l in pairs],rotation=20,ha="right",fontsize=8)
ax.set_ylabel("p99 queuing latency (us)"); ax.set_title("N=8: cutting the loop delay is what unlocks on/off (p99 latency)")
fig2.tight_layout(); fig2.savefig(ART+"/lowdelay_beforeafter.png",dpi=110); print("saved lowdelay_beforeafter.png")
