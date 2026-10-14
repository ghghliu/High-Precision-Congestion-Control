#!/usr/bin/env python3
"""Workloads for the congestion cases named in arXiv:2604.15039.

The section 4 case study (4 instances, uniform 1.61 req/s, 100 Gbps) is the
non-congested operating point. The paper says the same PrfaaS egress queues
when:

1. Several KV transfers hit the egress together (sections 3.3 and 3.4.3).
   The missing parameter is how many instances fire at once. Sweep 1, 2, 4,
   8 and 16. Two matches the section 2.3 ratio of about 170 Gbps against a
   100 Gbps link. Four is every case-study instance dumping one KV together.
   Sixteen is inside the paper's 1.8 Tbps / 100 Gbps scale example.
2. The inter-cluster bandwidth drops (introduction). Sweep 50 and 25 Gbps,
   the INT-encodable steps below the case study's 100 Gbps, with 4 senders.
3. A prefix-cache bulk transfer shares the egress (section 3.4.3). Sizes are
   Table 5 at 8K, 32K and 128K tokens, sent from an extra host together with
   4 KV flows.

Each KV is the paper's 44K-token conditional mean. Transfers start together
and are not paced, which is the unsmoothed burst the paper says the
scheduler has to prevent. PFC stays on.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_experiment import cc_params, kv_bytes, one_way_delay

CCS = ["dcqcn", "hp", "timely", "dctcp", "hpccPint"]
N_RECV = 5
# Paper: E[L | L > 19.4K] ≈ 44K tokens.
KV_TOKENS = 44000
# Table 5 measured sizes for a concurrent prefix-cache transfer.
PREFIX_MIB = {
    "8k": 308.9,
    "32k": 701.3,
    "128k": 2316.3,
}


def ecn_for(rates_gbps, dctcp):
    """kmin/kmax in KB, scaled from run.py at 100 Gbps (4 and 16 KB per Gbps)."""
    parts_min = []
    parts_max = []
    parts_p = []
    for g in rates_gbps:
        bps = int(g * 1e9)
        if dctcp:
            k = max(1, int(round(3.0 * g)))
            parts_min.append("%d %d" % (bps, k))
            parts_max.append("%d %d" % (bps, k))
            parts_p.append("%d 1.0" % bps)
        else:
            parts_min.append("%d %d" % (bps, max(1, int(round(4.0 * g)))))
            parts_max.append("%d %d" % (bps, max(1, int(round(16.0 * g)))))
            parts_p.append("%d 0.2" % bps)
    n = len(rates_gbps)
    return "%d %s" % (n, " ".join(parts_min)), "%d %s" % (n, " ".join(parts_max)), "%d %s" % (n, " ".join(parts_p))


def mib_bytes(mib):
    return int(round(mib * 1024 * 1024))


def build_scenario(spec):
    k = spec["k"]
    prefix_mib = spec["prefix_mib"]
    n_send = k + (1 if prefix_mib else 0)
    n_recv = N_RECV
    sw_s = n_send + n_recv
    sw_r = sw_s + 1
    node_num = sw_r + 1
    # host links, one WAN, receiver links
    link_num = n_send + 1 + n_recv
    delay = one_way_delay(spec["km"])
    wan = spec["wan_gbps"]
    lines = ["%d 2 %d" % (node_num, link_num), str(sw_s), str(sw_r)]
    for s in range(n_send):
        lines.append("%d %d 100Gbps 1000ns 0" % (s, sw_s))
    lines.append("%d %d %dGbps %s 0" % (sw_s, sw_r, wan, delay))
    for i in range(n_recv):
        lines.append("%d %d 400Gbps 1000ns 0" % (n_send + i, sw_r))
    # Device 0 is loopback. Host links are ifindex 1..n_send, WAN is next.
    wan_if = n_send + 1

    kv = kv_bytes(KV_TOKENS)
    requests = []
    rows = []
    for s in range(k):
        sizes = split(kv, spec["n_conn"])
        requests.append({
            "request_id": s,
            "kind": "kv",
            "src": s,
            "dst": n_send + (s % n_recv),
            "tokens": KV_TOKENS,
            "total_bytes": kv,
            "conn_bytes": sizes,
        })
        for c, size in enumerate(sizes):
            rows.append("%d %d 3 %d %d 0.000000000" % (s, n_send + (s % n_recv), 100 + c, size))
    if prefix_mib:
        pb = mib_bytes(prefix_mib)
        src = k
        dst = n_send
        requests.append({
            "request_id": k,
            "kind": "prefix",
            "src": src,
            "dst": dst,
            "tokens": None,
            "total_bytes": pb,
            "conn_bytes": [pb],
            "prefix_mib": prefix_mib,
        })
        rows.append("%d %d 3 100 %d 0.000000000" % (src, dst, pb))

    max_bytes = max(r["total_bytes"] for r in requests)
    # MIN_RATE is 1 Gbps, so a starved flow of this size finishes within this window.
    stop_s = max_bytes * 8.0 / 1e9 + 3.0
    return {
        "topo": "\n".join(lines) + "\n",
        "flows": "%d\n%s\n" % (len(rows), "\n".join(rows)),
        "requests": requests,
        "wan_sw": sw_s,
        "wan_if": wan_if,
        "stop_s": stop_s,
        "n_send": n_send,
        "kv_bytes": kv,
    }


def split(total, n):
    base, extra = divmod(total, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def config_text(built, paths, spec):
    p = cc_params(spec["cc"])
    rates = sorted(set([100, spec["wan_gbps"], 400]))
    kmin, kmax, pmax = ecn_for(rates, p["ecn"] == "dctcp")
    return """ENABLE_QCN 1
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
        topo=paths["topo"], flow=paths["flow"], trace=paths["trace"],
        out=paths["out"], tag=spec["tag"], stop=built["stop_s"],
        mode=p["mode"], g=p["g"], ai=p["ai"], hai=p["hai"], dctcp_ai=p["dctcp_ai"],
        has_win=p["has_win"], vwin=p["vwin"], us=p["us"], u_tgt=p["u_tgt"],
        int_multi=p["int_multi"], pint_log_base=p["pint_log_base"],
        pint_prob=p["pint_prob"], ack_prio=p["ack_prio"],
        kmax=kmax, kmin=kmin, pmax=pmax,
        qend=int(built["stop_s"] * 1e9),
    )


def specs():
    out = []
    def add(**kw):
        prefix = kw.pop("prefix_mib", 0.0)
        tag = "%s_%s_k%d_c%d_%dkm_%dg" % (
            kw["kind"], kw["cc"], kw["k"], kw["n_conn"], kw["km"], kw["wan_gbps"])
        if prefix:
            tag += "_p%d" % int(round(prefix))
        kw.update({"prefix_mib": prefix, "tag": tag})
        out.append(kw)

    for k in (1, 2, 4):
        for km in (10, 50):
            for n_conn in (1, 8):
                for cc in CCS:
                    add(kind="burst", cc=cc, k=k, n_conn=n_conn, km=km, wan_gbps=100)
    for k in (8, 16):
        for cc in CCS:
            add(kind="burst", cc=cc, k=k, n_conn=1, km=10, wan_gbps=100)
    for wan in (50, 25):
        for km in (10, 50):
            for cc in CCS:
                add(kind="bwdrop", cc=cc, k=4, n_conn=1, km=km, wan_gbps=wan)
    for _name, mib in PREFIX_MIB.items():
        for cc in CCS:
            add(kind="prefix", cc=cc, k=4, n_conn=1, km=10, wan_gbps=100, prefix_mib=mib)
    return out


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/prfaas-cong"
    os.makedirs(out_dir, exist_ok=True)
    trace = os.path.join(out_dir, "trace.txt")
    with open(trace, "w") as f:
        f.write("0\n")
    jobs = []
    for spec in specs():
        built = build_scenario(spec)
        topo = os.path.join(out_dir, "topo_%s.txt" % spec["tag"])
        flow = os.path.join(out_dir, "flow_%s.txt" % spec["tag"])
        cfg = os.path.join(out_dir, "config_%s.txt" % spec["tag"])
        with open(topo, "w") as f:
            f.write(built["topo"])
        with open(flow, "w") as f:
            f.write(built["flows"])
        paths = {"topo": topo, "flow": flow, "trace": trace, "out": out_dir}
        with open(cfg, "w") as f:
            f.write(config_text(built, paths, spec))
        meta = dict(spec)
        meta.update({
            "config": cfg,
            "wan_sw": built["wan_sw"],
            "wan_if": built["wan_if"],
            "stop_s": built["stop_s"],
            "kv_bytes": built["kv_bytes"],
            "requests": built["requests"],
        })
        jobs.append(meta)
    with open(os.path.join(out_dir, "jobs.json"), "w") as f:
        json.dump({"jobs": jobs}, f)
    print("jobs", len(jobs), "kv_bytes", jobs[0]["kv_bytes"])


if __name__ == "__main__":
    main()
