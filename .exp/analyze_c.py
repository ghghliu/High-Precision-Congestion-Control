#!/usr/bin/env python3
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OUT = "/workspace/.exp/out"; ART = "/opt/cursor/artifacts"
os.makedirs(ART, exist_ok=True)

# load
Q = {}   # name -> {tbin(10us): max_qlen_bytes}
T = {}   # name -> {tbin(200us): bytes}
for line in open(OUT + "/C_data.csv"):
    p = line.split()
    if len(p) != 4: continue
    kind, name, b, v = p[0], p[1], int(p[2]), float(p[3])
    if kind == "Q": Q.setdefault(name, {})[b] = v
    else: T.setdefault(name, {})[b] = v

def qseries(name, dt=10e-6, tmax=0.010):
    n = int(tmax/dt); d = Q.get(name, {})
    return [ (i*dt*1000) for i in range(n)], [ d.get(i,0)/1000.0 for i in range(n)]  # ms, KB
def tseries(name, dt=200e-6, tmax=0.010):
    n = int(tmax/dt); d = T.get(name, {})
    return [ (i*dt*1000) for i in range(n)], [ d.get(i,0)*8/dt/1e9 for i in range(n)]  # ms, Gbps

def stats(name):
    qs = [v/1000.0 for v in Q.get(name, {}).values()]           # KB
    # steady window: throughput bins with t in [3ms,10ms]
    tb = T.get(name, {})
    ss = [tb.get(i,0) for i in range(15,50)]
    util = (sum(ss)*8/(len(ss)*200e-6))/400e9 if ss else 0
    return dict(qmax=max(qs) if qs else 0, qavg=sum(qs)/len(qs) if qs else 0, util=util)

def npause(name):
    pf = "%s/pfc_%s.txt" % (OUT, name); c = 0
    if os.path.exists(pf):
        for _ in open(pf): c += 1
    return c

# ---- Plot 1: baselines vs on/off queue at bottleneck ----
fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5.5))
for name, lab in [("dcqcn_C","DCQCN"),("hpcc_C","HPCC"),("timely_C","TIMELY"),("pfc_C","PFC-only"),("onoff_ideal_C","on/off ideal(0 delay)"),("onoff_s8g8_C","on/off s8g8 (nic16-100)")]:
    x, y = qseries(name); a1.plot(x, y, lw=1.3, label=lab)
a1.set_title("Bottleneck queue length (leaf0->host0), 8:1 incast"); a1.set_xlabel("time (ms)"); a1.set_ylabel("queue (KB)")
a1.grid(alpha=0.3); a1.legend(fontsize=8)
for name, lab in [("onoff_ideal_C","ideal (0,0)"),("onoff_s4g4_C","sense4+sig4"),("onoff_s8g8_C","sense8+sig8"),("onoff_s16g16_C","sense16+sig16")]:
    x, y = qseries(name); a2.plot(x, y, lw=1.3, label=lab)
a2.set_title("On/Off queue vs switch delay (NIC jitter 16-100us)"); a2.set_xlabel("time (ms)"); a2.set_ylabel("queue (KB)")
a2.grid(alpha=0.3); a2.legend(fontsize=8)
fig.tight_layout(); fig.savefig(ART+"/expC_queue.png", dpi=110); print("saved expC_queue.png")

# ---- Plot 2: on/off delay-sweep tradeoff (util vs max queue) + throughput ----
fig2, (b1, b2) = plt.subplots(1, 2, figsize=(15, 5.5))
grid = [("onoff_ideal_C","ideal")] + [("onoff_s%dg%d_C"%(s,g), "s%d g%d"%(s,g)) for s in (4,8,16) for g in (4,8,16)]
xs = [stats(n)["qmax"] for n,_ in grid]; ys = [stats(n)["util"]*100 for n,_ in grid]
b1.scatter(xs, ys, s=60)
for (n,lab),x,y in zip(grid,xs,ys): b1.annotate(lab,(x,y),fontsize=8,xytext=(4,3),textcoords="offset points")
b1.set_xlabel("max bottleneck queue overshoot (KB)"); b1.set_ylabel("throughput utilization (%)")
b1.set_title("On/Off tradeoff: larger HW delay -> bigger queue + lower throughput"); b1.grid(alpha=0.3)
for name, lab in [("onoff_ideal_C","ideal"),("onoff_s8g8_C","s8g8"),("onoff_s16g16_C","s16g16"),("hpcc_C","HPCC(ref)")]:
    x, y = tseries(name); b2.plot(x, y, lw=1.3, label=lab)
b2.axhline(400, color="gray", ls=":"); b2.set_ylim(0,460)
b2.set_title("Aggregate throughput at bottleneck"); b2.set_xlabel("time (ms)"); b2.set_ylabel("Gbps"); b2.grid(alpha=0.3); b2.legend(fontsize=8)
fig2.tight_layout(); fig2.savefig(ART+"/expC_onoff_tradeoff.png", dpi=110); print("saved expC_onoff_tradeoff.png")

# ---- text summary ----
L = []
L.append("=========== Scenario C: clean last-hop incast (8 senders -> 1 x 400G receiver) ===========")
L.append("%-26s %10s %12s %12s %10s" % ("scheme/config","util(%)","q_avg(KB)","q_max(KB)","PFC"))
def row(name, lab):
    s = stats(name); return "%-26s %10.1f %12.0f %12.0f %10d" % (lab, s["util"]*100, s["qavg"], s["qmax"], npause(name))
for n,l in [("pfc_C","PFC-only"),("dcqcn_C","DCQCN"),("hpcc_C","HPCC"),("timely_C","TIMELY")]:
    L.append(row(n,l))
L.append("-"*74)
L.append("On/Off CC (mode 12), off-rate=250Mbps, threshold K=100KB:")
L.append(row("onoff_ideal_C","  ideal (no HW delay)"))
for s in (4,8,16):
    for g in (4,8,16):
        L.append(row("onoff_s%dg%d_C"%(s,g), "  sense=%dus sig=%dus nic16-100"%(s,g)))
L.append(row("onoff_s8g8_nic16_C","  sense8 sig8 nic=16us"))
L.append(row("onoff_s8g8_nic100_C","  sense8 sig8 nic=100us"))
txt = "\n".join(L); print("\n"+txt)
open(ART+"/onoff_results.txt","w").write(txt+"\n"); print("\nsaved onoff_results.txt")
