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
def pfc(n):
    f="%s/pfc_%s.txt"%(OUT,n); return sum(1 for _ in open(f)) if os.path.exists(f) else 0
Ns=[2,8,32]
schemes=[("dcqcn","DCQCN","#8172B2"),("hpcc","HPCC","#4C72B0"),("de","dual-ECN(m13)","#CCB974"),("ml","multi-level(m14)","#55A868")]
fig,axes=plt.subplots(1,3,figsize=(17,5))
for sch,l,c in schemes:
    axes[0].plot(Ns,[util("%s_N%d"%(sch,N)) for N in Ns],"o-",color=c,label=l)
    axes[1].plot(Ns,[p99("%s_N%d"%(sch,N)) for N in Ns],"o-",color=c,label=l)
    axes[2].plot(Ns,[pfc("%s_N%d"%(sch,N)) for N in Ns],"o-",color=c,label=l)
axes[0].set_title("Utilization vs incast degree"); axes[0].set_ylabel("util %"); axes[0].set_ylim(0,105)
axes[1].set_title("p99 queuing latency vs incast degree"); axes[1].set_ylabel("p99 latency (us)"); axes[1].set_yscale("log")
axes[2].set_title("PFC pause frames vs incast degree"); axes[2].set_ylabel("PFC frames")
for a in axes: a.set_xlabel("incast degree N"); a.set_xticks(Ns); a.grid(alpha=0.3); a.legend(fontsize=8)
fig.suptitle("Incast comparison (400G): multi-level(m14) vs dual-ECN(m13) vs DCQCN/HPCC",fontsize=13)
fig.tight_layout(); fig.savefig(ART+"/multilevel_incast.png",dpi=110); print("saved multilevel_incast.png")

# resume-floor sweep (N=8)
fig2,ax=plt.subplots(figsize=(8,5))
sw=[("ml_r25_N8","resume=25%"),("ml_N8","resume=50%"),("ml_r100_N8","resume=100%")]
x=range(len(sw)); u=[util(n) for n,_ in sw]; q=[p99(n) for n,_ in sw]
ax2=ax.twinx()
ax.bar([i-0.2 for i in x],u,0.4,color="#55A868",label="util %")
ax2.bar([i+0.2 for i in x],q,0.4,color="#C44E52",label="p99 latency us")
ax.set_xticks(list(x)); ax.set_xticklabels([l for _,l in sw]); ax.set_ylim(0,100)
ax.set_ylabel("util %",color="#55A868"); ax2.set_ylabel("p99 latency us",color="#C44E52")
ax.set_title("mode14: resume floor is the main util<->latency knob (N=8)")
for i in x: ax.text(i-0.2,u[i],"%.0f"%u[i],ha="center",va="bottom",fontsize=9); ax2.text(i+0.2,q[i],"%.0f"%q[i],ha="center",va="bottom",fontsize=9)
fig2.tight_layout(); fig2.savefig(ART+"/multilevel_resume_sweep.png",dpi=110); print("saved multilevel_resume_sweep.png")
