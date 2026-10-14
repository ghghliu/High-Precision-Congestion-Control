#!/usr/bin/env python3
"""Generate PrfaaS cross-cluster RDMA workloads and ns-3 configs.

Traffic matches the case study in arXiv:2604.15039 section 4:
truncated lognormal uncached length, only L > 19.4K on the inter-cluster
link, KV size fit to Table 5, uniform arrivals at 1.61 req/s.

The simulator is RDMA, so each KV is one or more queue pairs. PFC stays on
(USE_DYNAMIC_PFC_THRESHOLD 1). CC parameters follow simulation/run.py at
100 Gbps, PD-side NICs are 400 Gbps, the fastest INT-encodable rate above the WAN.
"""

import argparse
import json
import math
import os
import random

MU = 9.90
SIGMA = 1.00
LEN_LO = 128.0
LEN_HI = 131072.0
THRESHOLD = 19400.0
# Table 5 least-squares fit, MiB = A + B * tokens. Residual < 7 MiB.
KV_A_MIB = 172.003409
KV_B_MIB = 0.0163489643
ARRIVAL_RATE = 1.61  # offloaded requests per second

SENDERS = [0, 1, 2, 3]
RECEIVERS = [4, 5, 6, 7, 8]
SW_SEND = 9
SW_RECV = 10

DISTANCES_KM = [5, 10, 20, 50]
# One-way fiber delay, 5 us/km.
NS_PER_KM = 5000

# run.py formulas at bw=100, plus 800 Gbps scaled by the same KB-per-Gbps.
# PD-side NICs are 400 Gbps, the fastest rate this simulator's INT header
# can encode (25/50/100/200/400). The paper's 800 Gbps access is above the
# 100 Gbps WAN, and 400 Gbps keeps that inequality without a bogus INT rate.
KMIN_100G = 400
KMAX_100G = 1600
KMIN_400G = 1600
KMAX_400G = 6400
DCTCP_K_100G = 300
DCTCP_K_400G = 1200


def kv_bytes(tokens):
    mib = KV_A_MIB + KV_B_MIB * tokens
    return int(round(mib * 1024 * 1024))


def sample_long(rng):
    while True:
        length = rng.lognormvariate(MU, SIGMA)
        if LEN_LO <= length <= LEN_HI and length > THRESHOLD:
            return length


def one_way_delay(km):
    return "%dns" % (km * NS_PER_KM)


def write_topology(path, km):
    delay = one_way_delay(km)
    lines = [
        "11 2 10",
        str(SW_SEND),
        str(SW_RECV),
    ]
    for host in SENDERS:
        lines.append("%d %d 100Gbps 1000ns 0" % (host, SW_SEND))
    lines.append("%d %d 100Gbps %s 0" % (SW_SEND, SW_RECV, delay))
    for host in RECEIVERS:
        lines.append("%d %d 400Gbps 1000ns 0" % (host, SW_RECV))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def write_trace(path):
    with open(path, "w") as f:
        f.write("0\n")


def generate_requests(n_req, n_conn, seed):
    rng = random.Random(seed)
    interval = 1.0 / ARRIVAL_RATE
    requests = []
    for i in range(n_req):
        tokens = sample_long(rng)
        total = kv_bytes(tokens)
        base = total // n_conn
        extra = total % n_conn
        sizes = [base + (1 if c < extra else 0) for c in range(n_conn)]
        requests.append({
            "request_id": i,
            "src": SENDERS[i % len(SENDERS)],
            "dst": RECEIVERS[i % len(RECEIVERS)],
            "start": i * interval,
            "tokens": tokens,
            "total_bytes": total,
            "conn_bytes": sizes,
        })
    return requests


def write_flows(path, requests):
    rows = []
    for req in requests:
        for conn, size in enumerate(req["conn_bytes"]):
            # pg 3 matches the simulator's example flows. dport distinguishes QPs.
            rows.append("%d %d 3 %d %d %.9f" % (
                req["src"], req["dst"], 100 + conn, size, req["start"]))
    with open(path, "w") as f:
        f.write("%d\n" % len(rows))
        f.write("\n".join(rows) + "\n")


def cc_params(cc):
    """Parameters copied from simulation/run.py --bw 100."""
    if cc == "dcqcn":
        return dict(mode=1, ai=20, hai=200, dctcp_ai=1000, has_win=0, vwin=0,
                    us=0, u_tgt=0.95, int_multi=1, ack_prio=1, g=0.00390625,
                    pint_log_base=1.05, pint_prob=1.0, ecn="dcqcn")
    if cc == "hp":
        return dict(mode=3, ai=40, hai=40, dctcp_ai=1000, has_win=1, vwin=1,
                    us=1, u_tgt=0.95, int_multi=4, ack_prio=0, g=0.00390625,
                    pint_log_base=1.05, pint_prob=1.0, ecn="std")
    if cc == "timely":
        return dict(mode=7, ai=100, hai=500, dctcp_ai=1000, has_win=0, vwin=0,
                    us=0, u_tgt=0.95, int_multi=1, ack_prio=1, g=0.00390625,
                    pint_log_base=1.05, pint_prob=1.0, ecn="std")
    if cc == "dctcp":
        return dict(mode=8, ai=10, hai=10, dctcp_ai=615, has_win=1, vwin=1,
                    us=0, u_tgt=0.95, int_multi=1, ack_prio=0, g=0.0625,
                    pint_log_base=1.05, pint_prob=1.0, ecn="dctcp")
    if cc == "hpccPint":
        return dict(mode=10, ai=40, hai=40, dctcp_ai=1000, has_win=1, vwin=1,
                    us=1, u_tgt=0.95, int_multi=4, ack_prio=0, g=0.00390625,
                    pint_log_base=1.05, pint_prob=1.0, ecn="std")
    raise ValueError(cc)


def ecn_maps(kind):
    if kind == "dctcp":
        kmin = "2 100000000000 %d 400000000000 %d" % (DCTCP_K_100G, DCTCP_K_400G)
        pmax = "2 100000000000 1.0 400000000000 1.0"
        return kmin, kmin, pmax
    kmin = "2 100000000000 %d 400000000000 %d" % (KMIN_100G, KMIN_400G)
    kmax = "2 100000000000 %d 400000000000 %d" % (KMAX_100G, KMAX_400G)
    pmax = "2 100000000000 0.2 400000000000 0.2"
    return kmin, kmax, pmax


def write_config(path, topo, flow, trace, out_dir, tag, cc, stop_s):
    p = cc_params(cc)
    kmin, kmax, pmax = ecn_maps(p["ecn"])
    text = """ENABLE_QCN 1
USE_DYNAMIC_PFC_THRESHOLD 1

PACKET_PAYLOAD_SIZE 1000

TOPOLOGY_FILE {topo}
FLOW_FILE {flow}
TRACE_FILE {trace}
TRACE_OUTPUT_FILE {out}/trace_{tag}.tr
FCT_OUTPUT_FILE {out}/fct_{tag}.txt
PFC_OUTPUT_FILE {out}/pfc_{tag}.txt

SIMULATOR_STOP_TIME {stop:.3f}

CC_MODE {mode}
ALPHA_RESUME_INTERVAL 1
RATE_DECREASE_INTERVAL 4
CLAMP_TARGET_RATE 0
RP_TIMER 300
EWMA_GAIN {g}
FAST_RECOVERY_TIMES 1
RATE_AI {ai}Mb/s
RATE_HAI {hai}Mb/s
MIN_RATE 1000Mb/s
DCTCP_RATE_AI {dctcp_ai}Mb/s

ERROR_RATE_PER_LINK 0.0000
L2_CHUNK_SIZE 4000
L2_ACK_INTERVAL 1
L2_BACK_TO_ZERO 0

HAS_WIN {has_win}
GLOBAL_T 1
VAR_WIN {vwin}
FAST_REACT {us}
U_TARGET {u_tgt}
MI_THRESH 0
INT_MULTI {int_multi}
MULTI_RATE 0
SAMPLE_FEEDBACK 0
PINT_LOG_BASE {pint_log_base}
PINT_PROB {pint_prob}

RATE_BOUND 1

ACK_HIGH_PRIO {ack_prio}

LINK_DOWN 0 0 0

ENABLE_TRACE 0

KMAX_MAP {kmax}
KMIN_MAP {kmin}
PMAX_MAP {pmax}
BUFFER_SIZE 32
QLEN_MON_FILE {out}/qlen_{tag}.txt
QLEN_MON_START 0
QLEN_MON_END {qend}
""".format(
        topo=topo, flow=flow, trace=trace, out=out_dir, tag=tag, stop=stop_s,
        mode=p["mode"], g=p["g"], ai=p["ai"], hai=p["hai"], dctcp_ai=p["dctcp_ai"],
        has_win=p["has_win"], vwin=p["vwin"], us=p["us"], u_tgt=p["u_tgt"],
        int_multi=p["int_multi"], pint_log_base=p["pint_log_base"],
        pint_prob=p["pint_prob"], ack_prio=p["ack_prio"],
        kmax=kmax, kmin=kmin, pmax=pmax,
        qend=int(stop_s * 1e9),
    )
    with open(path, "w") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-req", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--conns", default="1,4,8,16")
    ap.add_argument("--distances", default="5,10,20,50")
    ap.add_argument("--ccs", default="dcqcn,hp,timely,dctcp,hpccPint")
    ap.add_argument("--stop-margin", type=float, default=1.0,
                    help="seconds after the last start, enough for a 2.3 GiB line-rate send")
    args = ap.parse_args()

    out = args.out
    os.makedirs(out, exist_ok=True)
    trace = os.path.join(out, "trace.txt")
    write_trace(trace)

    conns = [int(x) for x in args.conns.split(",") if x]
    distances = [int(x) for x in args.distances.split(",") if x]
    ccs = [x for x in args.ccs.split(",") if x]
    interval = 1.0 / ARRIVAL_RATE
    stop_s = (args.n_req - 1) * interval + args.stop_margin

    jobs = []
    for n_conn in conns:
        requests = generate_requests(args.n_req, n_conn, args.seed)
        flow = os.path.join(out, "flow_c%d.txt" % n_conn)
        manifest = os.path.join(out, "manifest_c%d.json" % n_conn)
        write_flows(flow, requests)
        with open(manifest, "w") as f:
            json.dump({
                "seed": args.seed,
                "n_conn": n_conn,
                "arrival_rate": ARRIVAL_RATE,
                "requests": requests,
            }, f)
        for km in distances:
            topo = os.path.join(out, "topo_%dkm.txt" % km)
            write_topology(topo, km)
            for cc in ccs:
                tag = "%s_c%d_%dkm" % (cc, n_conn, km)
                cfg = os.path.join(out, "config_%s.txt" % tag)
                write_config(cfg, topo, flow, trace, out, tag, cc, stop_s)
                jobs.append({"tag": tag, "config": cfg, "cc": cc, "n_conn": n_conn, "km": km})

    with open(os.path.join(out, "jobs.json"), "w") as f:
        json.dump({"stop_s": stop_s, "jobs": jobs}, f, indent=2)
    print("jobs %d stop %.3f s" % (len(jobs), stop_s))


if __name__ == "__main__":
    main()
