#!/usr/bin/env python3
# Generate the 400G 2-layer non-oversubscribed fat-tree, scenarios, and configs
# for baselines (PFC-only/DCQCN/HPCC/TIMELY) plus the new on/off CC (mode 12).
import os

CROOT = "/home/ubuntu/repo/.exp"
HROOT = "/workspace/.exp"
OUT_C = CROOT + "/out"
os.makedirs(HROOT + "/out", exist_ok=True)

# ---------------- Topology (unchanged) ----------------
NHOST = 64
LEAF = [64, 65, 66, 67]
SPINE = [68, 69]
DELAY = "0.001ms"
links = []
for h in range(NHOST):
    links.append((h, 64 + h // 16, "400Gbps"))
for L in LEAF:
    for S in SPINE:
        links.append((L, S, "3200Gbps"))
nnode = NHOST + len(LEAF) + len(SPINE)
nsw = len(LEAF) + len(SPINE)
with open(HROOT + "/topo.txt", "w") as f:
    f.write("%d %d %d\n" % (nnode, nsw, len(links)))
    f.write(" ".join(str(s) for s in (LEAF + SPINE)) + "\n")
    for (a, b, bw) in links:
        f.write("%d %d %s %s 0\n" % (a, b, bw, DELAY))

def host_of_leaf(L, k):
    return 16 * L + k

# ---------------- Scenario A: convergence (5 long flows -> 1 receiver) ----------------
rcv = host_of_leaf(0, 0)
sendersA = [host_of_leaf(1,0), host_of_leaf(1,1), host_of_leaf(2,0), host_of_leaf(2,1), host_of_leaf(3,0)]
with open(HROOT + "/expA_flow.txt", "w") as f:
    f.write("%d\n" % len(sendersA))
    for i, s in enumerate(sendersA):
        f.write("%d %d 3 100 %d %.9f\n" % (s, rcv, 200000000, 2.000 + i * 0.002))
open(HROOT + "/expA_trace.txt", "w").write("1\n64\n")

# ---------------- Scenario B: PFC head-of-line blocking ----------------
hot, cold = host_of_leaf(0, 0), host_of_leaf(0, 1)
aggr = [host_of_leaf(1,k) for k in range(4)] + [host_of_leaf(2,k) for k in range(4)] + [host_of_leaf(3,k) for k in range(1,5)]
victim_src = host_of_leaf(3, 0)
flowsB = [(s, hot, 100000000, 2.000) for s in aggr]
tv = 2.000500
for i in range(100):
    flowsB.append((victim_src, cold, 64000, tv)); tv += 0.000030
with open(HROOT + "/expB_flow.txt", "w") as f:
    f.write("%d\n" % len(flowsB))
    for (s, d, sz, t) in flowsB:
        f.write("%d %d 3 100 %d %.9f\n" % (s, d, sz, t))
open(HROOT + "/expB_trace.txt", "w").write("0\n")

# ---------------- Scenario C: clean last-hop incast (single congestion point) ----------------
# N senders spread across leaves 1..3 -> one receiver host0 on leaf0.
# Only congestion point = leaf0->host0 (400G). Long persistent flows to observe
# the bottleneck queue dynamics / throughput of each CC.
INCAST_N = 8
sendersC = [host_of_leaf(1,0), host_of_leaf(1,1), host_of_leaf(1,2),
            host_of_leaf(2,0), host_of_leaf(2,1), host_of_leaf(2,2),
            host_of_leaf(3,0), host_of_leaf(3,1)][:INCAST_N]
with open(HROOT + "/expC_flow.txt", "w") as f:
    f.write("%d\n" % len(sendersC))
    for s in sendersC:
        f.write("%d %d 3 100 %d %.9f\n" % (s, rcv, 200000000, 2.000))
open(HROOT + "/expC_trace.txt", "w").write("1\n64\n")   # trace bottleneck leaf0

# ---------------- ECN / rate maps ----------------
BW = 400
kmin4, kmax4 = 100*BW//25, 400*BW//25
kmin32, kmax32 = 100*(BW*8)//25, 400*(BW*8)//25
KMAX_STD = "2 400000000000 %d 3200000000000 %d" % (kmax4, kmax32)
KMIN_STD = "2 400000000000 %d 3200000000000 %d" % (kmin4, kmin32)
PMAX_STD = "2 400000000000 0.20 3200000000000 0.20"
# On/Off: deterministic threshold K (KB) -> KMIN==KMAX, PMAX=1.0
K_ONOFF = 100
KMAX_ON = "2 400000000000 %d 3200000000000 %d" % (K_ONOFF, K_ONOFF)
KMIN_ON = "2 400000000000 %d 3200000000000 %d" % (K_ONOFF, K_ONOFF)
PMAX_ON = "2 400000000000 1.00 3200000000000 1.00"

TMPL = """ENABLE_QCN {qcn}
USE_DYNAMIC_PFC_THRESHOLD 1
PACKET_PAYLOAD_SIZE 1000
TOPOLOGY_FILE {croot}/topo.txt
FLOW_FILE {croot}/{flow}
TRACE_FILE {croot}/{trace}
TRACE_OUTPUT_FILE {out}/mix_{name}.tr
FCT_OUTPUT_FILE {out}/fct_{name}.txt
PFC_OUTPUT_FILE {out}/pfc_{name}.txt
SIMULATOR_STOP_TIME {stop:.3f}
CC_MODE {mode}
ALPHA_RESUME_INTERVAL 1
RATE_DECREASE_INTERVAL 4
CLAMP_TARGET_RATE 0
RP_TIMER 300
EWMA_GAIN 0.00390625
FAST_RECOVERY_TIMES 1
RATE_AI {ai}Mb/s
RATE_HAI {hai}Mb/s
MIN_RATE {min_rate}
DCTCP_RATE_AI 1000Mb/s
ONOFF_T_SENSE {t_sense}
ONOFF_T_SIG {t_sig}
ONOFF_T_NIC_MIN {t_nic_min}
ONOFF_T_NIC_MAX {t_nic_max}
ERROR_RATE_PER_LINK 0.0000
L2_CHUNK_SIZE 4000
L2_ACK_INTERVAL 1
L2_BACK_TO_ZERO 0
HAS_WIN {has_win}
GLOBAL_T 1
VAR_WIN {vwin}
FAST_REACT {fr}
U_TARGET 0.95
MI_THRESH 0
INT_MULTI {int_multi}
MULTI_RATE 0
SAMPLE_FEEDBACK 0
PINT_LOG_BASE 1.05
PINT_PROB 1.0
RATE_BOUND 1
ACK_HIGH_PRIO {ack}
LINK_DOWN 0 0 0
ENABLE_TRACE {tr}
KMAX_MAP {kmax}
KMIN_MAP {kmin}
PMAX_MAP {pmax}
BUFFER_SIZE 128
QLEN_MON_FILE {out}/qlen_{name}.txt
QLEN_MON_START 2000000000
QLEN_MON_END 2000000001
"""

def write_cfg(name, **kw):
    d = dict(croot=CROOT, out=OUT_C, int_multi=1, min_rate="1000Mb/s",
             t_sense=0, t_sig=0, t_nic_min=0, t_nic_max=0,
             kmax=KMAX_STD, kmin=KMIN_STD, pmax=PMAX_STD, name=name)
    d.update(kw)
    with open("%s/config_%s.txt" % (HROOT, name), "w") as f:
        f.write(TMPL.format(**d))

# baseline presets: (qcn, mode, ai, hai, has_win, vwin, fr, ack, int_multi)
presets = {
    "pfc":    (0, 1, 5*BW//25, 50*BW//25, 0, 0, 0, 0, 1),
    "dcqcn":  (1, 1, 5*BW//25, 50*BW//25, 0, 0, 0, 1, 1),
    "hpcc":   (1, 3, 10*BW//25, 10*BW//25, 1, 1, 1, 0, 1),
    "timely": (1, 7, 10*BW//10, 50*BW//10, 0, 0, 0, 1, 1),
}
scen = {
    "A": dict(flow="expA_flow.txt", trace="expA_trace.txt", stop=2.014, tr=1),
    "B": dict(flow="expB_flow.txt", trace="expB_trace.txt", stop=2.012, tr=0),
    "C": dict(flow="expC_flow.txt", trace="expC_trace.txt", stop=2.010, tr=1),
}
for exp, sc in scen.items():
    for sch, p in presets.items():
        qcn, mode, ai, hai, hw, vw, fr, ack, im = p
        write_cfg("%s_%s" % (sch, exp), flow=sc["flow"], trace=sc["trace"], stop=sc["stop"],
                  tr=sc["tr"], qcn=qcn, mode=mode, ai=ai, hai=hai, has_win=hw, vwin=vw,
                  fr=fr, ack=ack, int_multi=im)

# ---------------- On/Off CC (mode 12) delay sweep on scenario C ----------------
def onoff_cfg(name, t_sense, t_sig, t_nic_min, t_nic_max):
    sc = scen["C"]
    write_cfg("onoff_%s_C" % name, flow=sc["flow"], trace=sc["trace"], stop=sc["stop"], tr=sc["tr"],
              qcn=1, mode=12, ai=0, hai=0, has_win=0, vwin=0, fr=0, ack=1, int_multi=1,
              min_rate="250Mb/s", kmax=KMAX_ON, kmin=KMIN_ON, pmax=PMAX_ON,
              t_sense=t_sense, t_sig=t_sig, t_nic_min=t_nic_min, t_nic_max=t_nic_max)

onoff_runs = []
onoff_cfg("ideal", 0, 0, 0, 0); onoff_runs.append("ideal")   # no hardware delay (best case)
for ts in (4000, 8000, 16000):
    for tg in (4000, 8000, 16000):
        nm = "s%dg%d" % (ts//1000, tg//1000)
        onoff_cfg(nm, ts, tg, 16000, 100000); onoff_runs.append(nm)   # NIC jitter 16-100us
# isolate NIC delay effect at fixed sense/sig = 8us
for lo, hi, tag in ((16000,16000,"nic16"), (100000,100000,"nic100")):
    onoff_cfg("s8g8_%s" % tag, 8000, 8000, lo, hi); onoff_runs.append("s8g8_%s" % tag)

print("topology: %d nodes, %d links" % (nnode, len(links)))
print("Scenario C incast: %d senders -> host%d (single bottleneck leaf0->host0 400G)" % (len(sendersC), rcv))
print("baseline configs: %s on A,B,C" % ",".join(presets))
print("on/off configs: %s" % ", ".join("onoff_%s_C" % r for r in onoff_runs))
