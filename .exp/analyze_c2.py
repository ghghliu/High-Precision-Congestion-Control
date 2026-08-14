#!/usr/bin/env python3
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = "/workspace/.exp/out"; ART = "/opt/cursor/artifacts"
os.makedirs(ART, exist_ok=True)

Q = {}; T = {}; H = {}; S = {}
for line in open(OUT + "/C2_data.csv"):
    p = line.split()
    if len(p) < 4: continue
    if p[0] == "Q": Q.setdefault(p[1], {})[int(p[2])] = float(p[3])
    elif p[0] == "T": T.setdefault(p[1], {})[int(p[2])] = float(p[3])
    elif p[0] == "H": H.setdefault(p[1], {})[int(p[2])] = int(p[3])
    elif p[0] == "S": S[p[1]] = (float(p[2]), float(p[3]))   # sum_lat_us, n_enq

def util(name):
    tb = T.get(name, {})
    ss = [tb.get(i, 0) for i in range(5, 50)]   # 2.001..2.010
    return (sum(ss) * 8 / (len(ss) * 200e-6)) / 400e9

def maxq_kb(name):
    d = Q.get(name, {}); return (max(d.values()) if d else 0) / 1000.0

def avg_lat(name):
    s, n = S.get(name, (0, 0)); return s / n if n else 0

def avg_q_kb(name):
    return avg_lat(name) * 50.0   # us * 50000 B/us / 1000

def p99_lat(name):
    h = H.get(name, {}); tot = sum(h.values())
    if tot == 0: return 0
    c = 0
    for b in sorted(h):
        c += h[b]
        if c >= 0.99 * tot: return b
    return max(h)

def npfc(name):
    pf = "%s/pfc_%s.txt" % (OUT, name); n = 0
    if os.path.exists(pf):
        for _ in open(pf): n += 1
    return n

baselines = [("pfc_C","PFC-only"),("dcqcn_C","DCQCN"),("hpcc_C","HPCC"),("timely_C","TIMELY")]
onoff = [("onoff_ideal_C","on/off ideal(min HW delay)"),
         ("onoff_nic4_C","on/off nic=4us"),
         ("onoff_nic4_32_C","on/off nic=4-32us"),
         ("onoff_nic4_100_C","on/off nic=4-100us"),
         ("onoff_s1_C","on/off sense=1us"),
         ("onoff_s4_C","on/off sense=4us"),
         ("onoff_s16_C","on/off sense=16us"),
         ("onoff_g4_C","on/off sig=4us"),
         ("onoff_g16_C","on/off sig=16us"),
         ("onoff_to64_C","on/off off-timeout=64us"),
         ("onoff_to460_C","on/off off-timeout=460us"),
         ("onoff_lvl2_C","on/off on-level<2"),
         ("onoff_lvl8_C","on/off on-level<8")]

def rowstr(name, lab):
    return "%-26s %8.1f %11.0f %11.0f %11.1f %11.1f %10d" % (
        lab, util(name)*100, avg_q_kb(name), maxq_kb(name), avg_lat(name), p99_lat(name), npfc(name))

L = []
L.append("Scenario C: clean last-hop incast (8 senders -> one 400G receiver), all with PFC ON")
L.append("%-26s %8s %11s %11s %11s %11s %10s" % ("scheme","util(%)","avgQ(KB)","maxQ(KB)","avgLat(us)","p99Lat(us)","PFC"))
L.append("-"*94)
for n,l in baselines: L.append(rowstr(n,l))
L.append("-"*94)
for n,l in onoff: L.append(rowstr(n,l))
txt = "\n".join(L); print(txt)
open(ART+"/onoff_aligned_results.txt","w").write(txt+"\n")

# --- plot: bar charts of the 6 metrics for baselines + 3 nic cases ---
sel = [("pfc_C","PFC"),("dcqcn_C","DCQCN"),("hpcc_C","HPCC"),("timely_C","TIMELY"),
       ("onoff_ideal_C","o/o ideal"),("onoff_nic4_C","o/o nic4"),("onoff_nic4_32_C","o/o nic4-32"),("onoff_nic4_100_C","o/o nic4-100")]
labels = [l for _,l in sel]
import numpy as np
x = np.arange(len(sel))
fig, axes = plt.subplots(2, 3, figsize=(16, 8))
metrics = [("utilization (%)", lambda n: util(n)*100),
           ("avg queue (KB)", avg_q_kb),
           ("max queue (KB)", maxq_kb),
           ("avg latency (us)", avg_lat),
           ("p99 latency (us)", p99_lat),
           ("PFC pause frames", npfc)]
for ax,(title,fn) in zip(axes.flat, metrics):
    vals = [fn(n) for n,_ in sel]
    bars = ax.bar(x, vals, color=["#888","#4C72B0","#55A868","#C44E52","#8172B2","#CCB974","#64B5CD","#E377C2"])
    ax.set_title(title); ax.set_xticks(x); ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    for b,v in zip(bars, vals): ax.text(b.get_x()+b.get_width()/2, v, ("%.0f"%v), ha="center", va="bottom", fontsize=7)
fig.suptitle("Scenario C (8:1 incast, 400G): baselines vs on/off (aligned HW model)", fontsize=13)
fig.tight_layout(); fig.savefig(ART+"/onoff_aligned_metrics.png", dpi=110); print("\nsaved onoff_aligned_metrics.png")

# --- time series: throughput + queue for key cases (two on/off failure regimes) ---
def tser(name):
    d = T.get(name, {}); return [i*0.2 for i in range(50)], [d.get(i,0)*8/200e-6/1e9 for i in range(50)]
def qser(name):
    d = Q.get(name, {}); return [i*0.01 for i in range(1000)], [d.get(i,0)/1000.0 for i in range(1000)]
ts_sel = [("hpcc_C","HPCC"),("dcqcn_C","DCQCN"),("onoff_nic4_C","on/off nic=4us"),
          ("onoff_nic4_100_C","on/off nic=4-100us"),("onoff_to64_C","on/off off-timeout=64us")]
fig3, (c1, c2) = plt.subplots(1, 2, figsize=(15, 5.5))
for name, lab in ts_sel:
    x,y = tser(name); c1.plot(x, y, lw=1.3, label=lab)
c1.axhline(400, color="gray", ls=":"); c1.set_ylim(0,460); c1.set_title("Aggregate throughput at bottleneck")
c1.set_xlabel("time (ms)"); c1.set_ylabel("Gbps"); c1.grid(alpha=0.3); c1.legend(fontsize=8)
for name, lab in ts_sel:
    x,y = qser(name); c2.plot(x, y, lw=1.0, label=lab)
c2.set_title("Bottleneck queue length"); c2.set_xlabel("time (ms)"); c2.set_ylabel("queue (KB)")
c2.set_yscale("symlog"); c2.grid(alpha=0.3); c2.legend(fontsize=8)
fig3.suptitle("On/off (corrected): 0 PFC, bounded queue; util vs queue tradeoff via HW delays / timeout", fontsize=12)
fig3.tight_layout(); fig3.savefig(ART+"/onoff_aligned_timeseries.png", dpi=110); print("saved onoff_aligned_timeseries.png")
