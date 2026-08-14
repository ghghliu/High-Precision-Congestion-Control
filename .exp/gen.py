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
ONOFF_BTS_DELAY_THRESH {bts_thresh}
ONOFF_BTS_LEVEL_UNIT {bts_unit}
ONOFF_ON_LEVEL_THRESH {on_level}
ONOFF_OFF_TIMEOUT {off_timeout}
ONOFF_BTS_RESUME_LEVEL {resume_level}
ONOFF_BTS_RECENT_WINDOW {recent_window}
ONOFF_ON_CONFIRM {on_confirm}
ML_LIGHT_PCT {ml_light}
ML_RESUME_PCT {ml_resume}
ML_PROBE_PCT {ml_probe}
ML_PROBE_INTERVAL {ml_probe_intvl}
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
             bts_thresh=5000, bts_unit=30000, on_level=4, off_timeout=128000,
             resume_level=2, recent_window=40000, on_confirm=1,
             ml_light=50, ml_resume=50, ml_probe=25, ml_probe_intvl=40000,
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

# ---------------- On/Off CC (mode 12) hardware sweep on scenario C ----------------
# sense = switch queue-table update period; sig = switch->source signaling delay;
# nic = jittered NIC processing delay (the 3 cases the user asked for).
def onoff_cfg(name, t_sense, t_sig, t_nic_min, t_nic_max, on_level=4, off_timeout=128000, bts_thresh=5000):
    sc = scen["C"]
    write_cfg("onoff_%s_C" % name, flow=sc["flow"], trace=sc["trace"], stop=sc["stop"], tr=sc["tr"],
              qcn=1, mode=12, ai=0, hai=0, has_win=0, vwin=0, fr=0, ack=1, int_multi=1,
              min_rate="250Mb/s", kmax=KMAX_ON, kmin=KMIN_ON, pmax=PMAX_ON,
              t_sense=t_sense, t_sig=t_sig, t_nic_min=t_nic_min, t_nic_max=t_nic_max,
              on_level=on_level, off_timeout=off_timeout, bts_thresh=bts_thresh)

onoff_runs = []
# Context: default-tuned cases (on_level=4, off_timeout=128us) across the 3 NIC cases.
onoff_cfg("nic4",    8000, 8000, 4000, 4000);   onoff_runs.append("nic4")
onoff_cfg("nic4_32", 8000, 8000, 4000, 32000);  onoff_runs.append("nic4_32")
onoff_cfg("nic4_100",8000, 8000, 4000, 100000); onoff_runs.append("nic4_100")

# ---- Anti-under-throughput exploration of the CONTROLLABLE params ----
# util is driven up by: short OFF-timeout, higher ON-level threshold, fresh sense.
# Grid over off_timeout x on_level (sense=4us, sig=8us, NIC=4-32us).
for T in (16000, 32000, 64000):
    for L in (8, 16):
        nm = "hu_t%d_l%d" % (T//1000, L)
        onoff_cfg(nm, 4000, 8000, 4000, 32000, on_level=L, off_timeout=T); onoff_runs.append(nm)
# Robustness of an aggressive high-util setting (T=32us, L=16, sense=1us) across NIC cases.
onoff_cfg("hu_best_nic4",   1000, 8000, 4000, 4000,   on_level=16, off_timeout=32000); onoff_runs.append("hu_best_nic4")
onoff_cfg("hu_best_nic32",  1000, 8000, 4000, 32000,  on_level=16, off_timeout=32000); onoff_runs.append("hu_best_nic32")
onoff_cfg("hu_best_nic100", 1000, 8000, 4000, 100000, on_level=16, off_timeout=32000); onoff_runs.append("hu_best_nic100")
# PFC-free high-util candidate (L<8, off_timeout=64us): robustness across NIC + timeout knee
onoff_cfg("pf_nic4",   4000, 8000, 4000, 4000,   on_level=8, off_timeout=64000); onoff_runs.append("pf_nic4")
onoff_cfg("pf_nic100", 4000, 8000, 4000, 100000, on_level=8, off_timeout=64000); onoff_runs.append("pf_nic100")
onoff_cfg("pf_t48", 4000, 8000, 4000, 32000, on_level=8, off_timeout=48000); onoff_runs.append("pf_t48")
onoff_cfg("pf_t80", 4000, 8000, 4000, 32000, on_level=8, off_timeout=80000); onoff_runs.append("pf_t80")
onoff_cfg("pf_t96", 4000, 8000, 4000, 32000, on_level=8, off_timeout=96000); onoff_runs.append("pf_t96")
# fast-NIC (4us) is hardest to keep utilized: does a shorter timeout recover util w/o PFC?
onoff_cfg("pf2_nic4_t32", 4000, 8000, 4000, 4000, on_level=8, off_timeout=32000); onoff_runs.append("pf2_nic4_t32")
onoff_cfg("pf2_nic4_t16", 4000, 8000, 4000, 4000, on_level=8, off_timeout=16000); onoff_runs.append("pf2_nic4_t16")
onoff_cfg("pf2_nic4_t8",  4000, 8000, 4000, 4000, on_level=8, off_timeout=8000);  onoff_runs.append("pf2_nic4_t8")

# ---- ON as the PRIMARY anti-under-throughput mechanism (off-timeout DISABLED) ----
# Lower BtsDelayThresh so ON notifications keep coming during the queue drain, so
# ON (not the timeout) resumes flows. Grid BtsDelayThresh x ON-level, nic=4-32, no timeout.
for d in (1000, 2000, 5000):
    for l in (2, 4):
        nm = "onpri_d%d_l%d" % (d//1000, l)
        onoff_cfg(nm, 4000, 8000, 4000, 32000, on_level=l, off_timeout=0, bts_thresh=d); onoff_runs.append(nm)
# best ON-only candidate across NIC cases (BtsDelayThresh=1us, ON-level<2, no timeout)
onoff_cfg("onpri_nic4",   4000, 8000, 4000, 4000,   on_level=2, off_timeout=0, bts_thresh=1000); onoff_runs.append("onpri_nic4")
onoff_cfg("onpri_nic100", 4000, 8000, 4000, 100000, on_level=2, off_timeout=0, bts_thresh=1000); onoff_runs.append("onpri_nic100")

# ---- Dual-watermark on/off (mode 13): resume rides the guaranteed per-flow ACK ----
# Klow/Khigh in KB. queue>Khigh -> OFF; Klow<=q<Khigh -> hold (hysteresis); q<Klow -> ON.
def dualecn_cfg(name, klow, khigh, t_nic_min, t_nic_max, on_confirm=1, off_timeout=460000):
    sc = scen["C"]
    KMIN = "2 400000000000 %d 3200000000000 %d" % (klow, klow)
    KMAX = "2 400000000000 %d 3200000000000 %d" % (khigh, khigh)
    write_cfg("de_%s_C" % name, flow=sc["flow"], trace=sc["trace"], stop=sc["stop"], tr=sc["tr"],
              qcn=1, mode=13, ai=0, hai=0, has_win=0, vwin=0, fr=0, ack=1, int_multi=1,
              min_rate="250Mb/s", kmax=KMAX, kmin=KMIN, pmax=PMAX_ON,
              t_nic_min=t_nic_min, t_nic_max=t_nic_max, off_timeout=off_timeout, on_confirm=on_confirm)

de_runs = []
# watermark grid (nic=4-32us, 460us backstop, confirm=1)
for (kl, kh) in [(20,100),(20,200),(50,200),(100,200),(50,400),(100,400)]:
    nm = "l%d_h%d" % (kl, kh); dualecn_cfg(nm, kl, kh, 4000, 32000); de_runs.append(nm)
# ON-confirm (state debounce) sweep on a mid watermark
dualecn_cfg("l50_h200_c4", 50, 200, 4000, 32000, on_confirm=4); de_runs.append("l50_h200_c4")
# pure dual-ECN ON (backstop DISABLED) -> does ON alone avoid under-throughput?
dualecn_cfg("l50_h200_noto", 50, 200, 4000, 32000, off_timeout=0); de_runs.append("l50_h200_noto")
# NIC robustness of a mid watermark
dualecn_cfg("nic4",   50, 200, 4000, 4000);   de_runs.append("nic4")
dualecn_cfg("nic100", 50, 200, 4000, 100000); de_runs.append("nic100")

# ---- Incast-degree scenarios (validate 50%-resume theory) + multi-level (mode 14) ----
# N senders spread across leaves 1..3 -> host0 (single bottleneck leaf0->host0).
def make_incast(N):
    pool = [host_of_leaf(1,k) for k in range(16)] + [host_of_leaf(2,k) for k in range(16)] + [host_of_leaf(3,k) for k in range(16)]
    snd = pool[:N]
    with open(HROOT + "/inc%d_flow.txt" % N, "w") as f:
        f.write("%d\n" % len(snd))
        for s in snd:
            f.write("%d %d 3 100 %d %.9f\n" % (s, rcv, 200000000, 2.000))
    open(HROOT + "/inc%d_trace.txt" % N, "w").write("1\n64\n")

KMIN_DE = "2 400000000000 50 3200000000000 50"    # Klow=50KB
KMAX_DE = "2 400000000000 200 3200000000000 200"  # Khigh=200KB

def scheme_cfg(name, N, scheme, **extra):
    flow="inc%d_flow.txt"%N; trace="inc%d_trace.txt"%N
    base=dict(flow=flow, trace=trace, stop=2.010, tr=1)
    if scheme=="dcqcn":
        base.update(qcn=1, mode=1, ai=5*BW//25, hai=50*BW//25, has_win=0, vwin=0, fr=0, ack=1, int_multi=1)
    elif scheme=="hpcc":
        base.update(qcn=1, mode=3, ai=10*BW//25, hai=10*BW//25, has_win=1, vwin=1, fr=1, ack=0, int_multi=1)
    elif scheme=="de":   # dual-ECN binary (mode 13)
        base.update(qcn=1, mode=13, ai=0, hai=0, has_win=0, vwin=0, fr=0, ack=1, int_multi=1,
                    min_rate="250Mb/s", kmax=KMAX_DE, kmin=KMIN_DE, pmax=PMAX_ON,
                    t_nic_min=4000, t_nic_max=32000, off_timeout=460000)
    elif scheme=="ml":   # multi-level (mode 14)
        base.update(qcn=1, mode=14, ai=0, hai=0, has_win=0, vwin=0, fr=0, ack=1, int_multi=1,
                    min_rate="250Mb/s", kmax=KMAX_DE, kmin=KMIN_DE, pmax=PMAX_ON,
                    t_nic_min=4000, t_nic_max=32000, off_timeout=460000)
    base.update(extra)
    write_cfg(name, **base)

inc_runs=[]
for N in (2, 8, 32):
    make_incast(N)
    for sch in ("dcqcn","hpcc","de","ml"):
        nm="%s_N%d"%(sch,N); scheme_cfg(nm,N,sch); inc_runs.append(nm)
# mode-14 param sweep on N=8: light decrease factor, resume floor, probe step
scheme_cfg("ml_l75_N8", 8, "ml", ml_light=75); inc_runs.append("ml_l75_N8")
scheme_cfg("ml_l25_N8", 8, "ml", ml_light=25); inc_runs.append("ml_l25_N8")
scheme_cfg("ml_r25_N8", 8, "ml", ml_resume=25); inc_runs.append("ml_r25_N8")
scheme_cfg("ml_r100_N8", 8, "ml", ml_resume=100); inc_runs.append("ml_r100_N8")  # resume straight to 100%
scheme_cfg("ml_p50_N8", 8, "ml", ml_probe=50); inc_runs.append("ml_p50_N8")
# finer, DCQCN-like control: no 50% jump, additive increase from R_min
scheme_cfg("ml_ai_N8",  8, "ml", ml_resume=0, ml_probe=5,  ml_probe_intvl=10000); inc_runs.append("ml_ai_N8")
scheme_cfg("ml_ai2_N8", 8, "ml", ml_resume=0, ml_probe=10, ml_probe_intvl=20000); inc_runs.append("ml_ai2_N8")
scheme_cfg("ml_ai3_N8", 8, "ml", ml_resume=0, ml_probe=5,  ml_probe_intvl=10000, ml_light=75); inc_runs.append("ml_ai3_N8")
scheme_cfg("ml_ai4_N8", 8, "ml", ml_resume=0, ml_probe=3,  ml_probe_intvl=8000,  ml_light=75); inc_runs.append("ml_ai4_N8")
print("topology: %d nodes, %d links" % (nnode, len(links)))
print("dual-ECN(mode13) configs: %s" % ", ".join("de_%s_C" % r for r in de_runs))
print("incast comparison configs: %s" % ", ".join(inc_runs))
print("Scenario C incast: %d senders -> host%d (single bottleneck leaf0->host0 400G)" % (len(sendersC), rcv))
print("baseline configs: %s on A,B,C" % ",".join(presets))
print("on/off configs: %s" % ", ".join("onoff_%s_C" % r for r in onoff_runs))
