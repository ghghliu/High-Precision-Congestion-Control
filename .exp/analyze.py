#!/usr/bin/env python3
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HROOT = "/workspace/.exp"; OUT = HROOT + "/out"; ART = "/opt/cursor/artifacts"
os.makedirs(ART, exist_ok=True)
SCHEMES = ["pfc", "dcqcn", "hpcc", "timely"]
LABEL = {"pfc": "PFC-only (no CC)", "dcqcn": "DCQCN", "hpcc": "HPCC", "timely": "TIMELY"}

def ip_hex(n): return "%08x" % (0x0b000001 + (n//256)*0x10000 + (n%256)*0x100)
HOST0, HOST1 = ip_hex(0), ip_hex(1)
SENDER = {ip_hex(16):16, ip_hex(17):17, ip_hex(32):32, ip_hex(33):33, ip_hex(48):48}

# ---------------- Exp A ----------------
BINW = 0.0002; T0 = 2.000
data = {s: {} for s in SCHEMES}       # data[sch][sip][bin]=bytes
maxbin = 0
for line in open(OUT + "/expA_thru.csv"):
    sch, sip, b, by = line.split()
    b = int(b); by = float(by); maxbin = max(maxbin, b)
    data[sch].setdefault(sip, {})[b] = by
nbins = maxbin + 1
def gbps(by): return by * 8 / BINW / 1e9

def jain(xs):
    s = sum(xs); s2 = sum(x*x for x in xs); n = len(xs)
    return (s*s)/(n*s2) if s2 > 0 else 0.0

A_stats = {}
fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True, sharey=True)
tms = [(T0 + (i+0.5)*BINW - T0)*1000 for i in range(nbins)]
for ax, sch in zip(axes.flat, SCHEMES):
    agg = [0.0]*nbins
    for sip in sorted(SENDER):
        series = [gbps(data[sch].get(sip, {}).get(b, 0.0)) for b in range(nbins)]
        for b in range(nbins): agg[b] += series[b]
        ax.plot(tms, series, lw=1.2, label="host%d" % SENDER[sip])
    ax.plot(tms, agg, "k--", lw=1.7, label="aggregate")
    ax.axhline(400, color="gray", ls=":", lw=1)
    ax.set_title(LABEL[sch]); ax.set_ylim(0, 460); ax.grid(alpha=0.3)
    ss = [b for b in range(nbins) if (T0+(b+0.5)*BINW) >= 2.011]
    util = sum(agg[b] for b in ss)/(len(ss)*400.0)
    pf_ss = [sum(gbps(data[sch].get(sip, {}).get(b, 0.0)) for b in ss)/len(ss) for sip in sorted(SENDER)]
    conv = None
    for b in range(nbins):
        if (T0+(b+0.5)*BINW) >= 2.008 and agg[b] >= 380: conv = (T0+(b+0.5)*BINW-2.008)*1000; break
    A_stats[sch] = dict(util=util, jain=jain(pf_ss), conv=conv)
axes[0,0].legend(fontsize=8, ncol=2, loc="lower right")
for ax in axes[1,:]: ax.set_xlabel("time since first flow (ms)  [flows start at 0,2,4,6,8 ms]")
for ax in axes[:,0]: ax.set_ylabel("throughput at bottleneck (Gbps)")
fig.suptitle("Exp A - 5 long flows -> one 400G receiver: bandwidth ramp & convergence", fontsize=13)
fig.tight_layout(); fig.savefig(ART+"/expA_convergence.png", dpi=110); print("saved expA_convergence.png")

# ---------------- Exp B ----------------
def parse_fct(sch):
    r = []
    for line in open("%s/fct_%s_B.txt" % (OUT, sch)):
        p = line.split()
        if len(p) >= 8: r.append((p[0], p[1], int(p[4]), int(p[5]), int(p[6]), int(p[7])))
    return r
def pctl(a, q):
    a = sorted(a); return a[min(len(a)-1, int(len(a)*q))] if a else 0

B_stats = {}
for sch in SCHEMES:
    rows = parse_fct(sch)
    vic = [r for r in rows if r[2] == 64000 and r[1] == HOST1]
    sl = [max(1.0, r[4]/r[5]) if r[5] > 0 else 1.0 for r in vic]
    span = (max(r[3]+r[4] for r in vic)-min(r[3] for r in vic))*1e-9 if vic else 1
    vg = sum(r[2] for r in vic)*8/span/1e9 if span > 0 else 0
    ptot = psp = 0
    pf = "%s/pfc_%s_B.txt" % (OUT, sch)
    if os.path.exists(pf):
        for line in open(pf):
            q = line.split()
            if len(q) >= 5:
                ptot += 1
                if q[1] in ("68", "69"): psp += 1
    B_stats[sch] = dict(n=len(vic), avg=sum(sl)/len(sl) if sl else 0, p50=pctl(sl,0.5),
                        p99=pctl(sl,0.99), mx=max(sl) if sl else 0, gbps=vg,
                        pause_total=ptot, pause_spine=psp)

fig2, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(SCHEMES)); w = 0.38
p50 = [B_stats[s]["p50"] for s in SCHEMES]; p99 = [B_stats[s]["p99"] for s in SCHEMES]
b1 = ax.bar(x-w/2, p50, w, label="p50"); b2 = ax.bar(x+w/2, p99, w, label="p99")
for i in range(len(SCHEMES)):
    ax.text(x[i]-w/2, p50[i], "%.1f"%p50[i], ha="center", va="bottom", fontsize=9)
    ax.text(x[i]+w/2, p99[i], "%.0f"%p99[i], ha="center", va="bottom", fontsize=9)
ax.set_xticks(x); ax.set_xticklabels([LABEL[s] for s in SCHEMES], fontsize=9)
ax.set_ylabel("victim-flow FCT slowdown (log)"); ax.set_yscale("log"); ax.grid(alpha=0.3, axis="y")
ax.axhline(1, color="green", ls=":", lw=1)
ax.set_title("Exp B - PFC head-of-line blocking\nvictim = 64KB flows to an IDLE host, sharing the PAUSEd spine->leaf link")
ax.legend()
fig2.tight_layout(); fig2.savefig(ART+"/expB_hol_slowdown.png", dpi=110); print("saved expB_hol_slowdown.png")

# ---------------- text summary ----------------
L = []
L.append("================ Exp A: bandwidth convergence (5x 200MB flows -> one 400G receiver) ================")
L.append("%-18s %14s %22s %14s" % ("scheme","avg_util(last3ms)","conv_time_to_95%(ms)","Jain_fairness"))
for s in SCHEMES:
    st = A_stats[s]; c = "%.2f"%st["conv"] if st["conv"] is not None else ">6 (never)"
    L.append("%-18s %13.1f%% %22s %14.3f" % (LABEL[s], st["util"]*100, c, st["jain"]))
L.append("")
L.append("================ Exp B: PFC head-of-line blocking (victim 64KB flows -> an IDLE host) ================")
L.append("%-18s %5s %8s %8s %9s %10s %12s %12s" %
         ("scheme","n","avg_sl","p99_sl","max_sl","vic_Gbps","PFC_total","PFC_spine"))
for s in SCHEMES:
    st = B_stats[s]
    L.append("%-18s %5d %8.1f %8.1f %9.1f %10.1f %12d %12d" %
             (LABEL[s], st["n"], st["avg"], st["p99"], st["mx"], st["gbps"], st["pause_total"], st["pause_spine"]))
txt = "\n".join(L); print("\n"+txt)
open(ART+"/experiment_results.txt","w").write(txt+"\n"); print("\nsaved experiment_results.txt")
