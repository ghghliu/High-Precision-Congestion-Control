#!/usr/bin/env python3
"""Reproduce Simple RR stickiness on a standard 2-level fat-tree.

k=4: 4 edge switches, 2 cores, 2 hosts per edge (8 hosts). Every edge
connects to every core. Congestion control and ECN stay off.

The permutation sends the first host of edge 0 and the first host of edge 1
to the two hosts under edge 3. Global RR starts at the same pointer on every
edge, so those two flows stick to the same core and pile onto one
core->edge downlink. The two uplinks of each source edge stay balanced.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_fattree import fat_tree, write_topology, write_trace

SIM = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WAF = "/usr/local/bin/python2.7"
TRACE_READER = os.path.join(SIM, "..", "analysis", "trace_reader")


def write_flows(path, flows):
    lines = ["%d" % len(flows)]
    for src, dst, start in flows:
        lines.append("%d %d 3 100 %d %.9f" % (src, dst, FLOWS_BYTES, start))
    # placeholder, bytes filled by caller via global set before write
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


FLOWS_BYTES = 10000


def collision_flows():
    # 1 ns stagger inside an edge fixes which local host is RR slot 0.
    # Across edges, slot 0 is aligned, which is the Simple RR failure mode.
    return [
        (0, 6, 0.0),
        (1, 4, 1e-9),
        (2, 7, 0.0),
        (3, 5, 1e-9),
        (4, 0, 0.0),
        (5, 2, 1e-9),
        (6, 1, 0.0),
        (7, 3, 1e-9),
    ]


def write_config(directory, bw_bps, lb_mode, nbytes, stop):
    d = os.path.abspath(directory)
    text = """ENABLE_QCN 0
USE_DYNAMIC_PFC_THRESHOLD 1
PACKET_PAYLOAD_SIZE 1000
TOPOLOGY_FILE {d}/topology.txt
FLOW_FILE {d}/flow.txt
TRACE_FILE {d}/trace.txt
TRACE_OUTPUT_FILE {d}/mix.tr
FCT_OUTPUT_FILE {d}/fct.txt
PFC_OUTPUT_FILE {d}/pfc.txt
SIMULATOR_STOP_TIME {stop}
CC_MODE 0
LB_MODE {lb}
ALPHA_RESUME_INTERVAL 1
RATE_DECREASE_INTERVAL 4
CLAMP_TARGET_RATE 0
RP_TIMER 900
EWMA_GAIN 0.00390625
FAST_RECOVERY_TIMES 1
RATE_AI 50Mb/s
RATE_HAI 100Mb/s
MIN_RATE 100Mb/s
DCTCP_RATE_AI 1000Mb/s
ERROR_RATE_PER_LINK 0.0000
L2_CHUNK_SIZE 2000000000
L2_ACK_INTERVAL 2000000000
L2_BACK_TO_ZERO 0
HAS_WIN 0
GLOBAL_T 1
VAR_WIN 0
FAST_REACT 0
U_TARGET 0.95
MI_THRESH 0
INT_MULTI 1
MULTI_RATE 0
SAMPLE_FEEDBACK 0
PINT_LOG_BASE 1.05
PINT_PROB 1.0
RATE_BOUND 1
ACK_HIGH_PRIO 0
LINK_DOWN 0 0 0
ENABLE_TRACE 1
KMAX_MAP 1 {bw} 400
KMIN_MAP 1 {bw} 100
PMAX_MAP 1 {bw} 0.2
BUFFER_SIZE 64
QLEN_MON_FILE {d}/qlen.txt
QLEN_MON_START 20000000000
QLEN_MON_END 20000000000
""".format(d=d, stop=stop, lb=lb_mode, bw=bw_bps)
    with open(os.path.join(directory, "config.txt"), "w") as f:
        f.write(text)


def port_neighbors(topo):
    """Map (node, ifIndex) -> neighbor. ifIndex 0 is the IP loopback."""
    nodes = topo["n_hosts"] + len(topo["switches"])
    nxt = [1] * nodes
    neigh = {}
    for src, dst in topo["links"]:
        neigh[(src, nxt[src])] = dst
        neigh[(dst, nxt[dst])] = src
        nxt[src] += 1
        nxt[dst] += 1
    return neigh


def parse_trace(text_path):
    # time n:N if:q qlen EVENT ecn:E sip dip sport dport U seq ...
    rx = re.compile(
        r"^(\d+) n:(\d+) (\d+):(\d+) (\d+) (\w+) ecn:\w+ ([0-9a-f]+) ([0-9a-f]+) \d+ \d+ U "
    )
    rows = []
    with open(text_path) as f:
        for line in f:
            m = rx.match(line)
            if not m:
                continue
            rows.append(
                {
                    "time": int(m.group(1)),
                    "node": int(m.group(2)),
                    "intf": int(m.group(3)),
                    "qidx": int(m.group(4)),
                    "qlen": int(m.group(5)),
                    "event": m.group(6),
                    "sip": int(m.group(7), 16),
                    "dip": int(m.group(8), 16),
                }
            )
    return rows


def ip_to_host(ip):
    return (ip >> 8) & 0xFFFF


def summarize(rows, neigh, edges, cores):
    enqu = [r for r in rows if r["event"] == "Enqu"]
    by_flow_edge = {}
    link_pkts = {}
    link_qmax = {}
    for r in enqu:
        nbr = neigh.get((r["node"], r["intf"]))
        if nbr is None:
            continue
        key = (r["node"], nbr)
        link_pkts[key] = link_pkts.get(key, 0) + 1
        link_qmax[key] = max(link_qmax.get(key, 0), r["qlen"])
        if r["node"] in edges and nbr in cores:
            flow = (ip_to_host(r["sip"]), ip_to_host(r["dip"]))
            by_flow_edge.setdefault(flow, set()).add(nbr)
    return by_flow_edge, link_pkts, link_qmax


def run_case(out, lb_mode, nbytes):
    global FLOWS_BYTES
    FLOWS_BYTES = nbytes
    os.makedirs(out, exist_ok=True)
    topo = fat_tree(2, 4)
    write_topology(topo, os.path.join(out, "topology.txt"), "100Gbps", "1000ns")
    write_flows(os.path.join(out, "flow.txt"), collision_flows())
    write_trace(topo, os.path.join(out, "trace.txt"))
    # 100 Gbps, ~100 us is enough for a few hundred KB plus a queue.
    write_config(out, 100000000000, lb_mode, nbytes, 0.002)
    log = os.path.join(out, "run.log")
    with open(log, "w") as f:
        subprocess.check_call(
            [WAF, os.path.join(SIM, "waf"), "--run", "scratch/third %s/config.txt" % out],
            cwd=SIM,
            stdout=f,
            stderr=subprocess.STDOUT,
        )
    text = os.path.join(out, "trace.txt.out")
    with open(text, "w") as f:
        subprocess.check_call([TRACE_READER, os.path.join(out, "mix.tr")], stdout=f)
    rows = parse_trace(text)
    edges = set(topo["edge"])
    cores = set(topo["core"])
    flows, pkts, qmax = summarize(rows, port_neighbors(topo), edges, cores)
    pfc = os.path.join(out, "pfc.txt")
    n_pfc = sum(1 for _ in open(pfc)) if os.path.exists(pfc) else 0
    return {
        "topo": topo,
        "flows": flows,
        "pkts": pkts,
        "qmax": qmax,
        "pfc": n_pfc,
        "nbytes": nbytes,
        "lb": lb_mode,
    }


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/rr-l2"
    sizes = [40000, 160000]
    results = {}
    for n in sizes:
        results[("rr", n)] = run_case(os.path.join(root, "rr-%d" % n), 1, n)
    results[("ecmp", 160000)] = run_case(os.path.join(root, "ecmp-160000"), 0, 160000)
    report = os.path.join(root, "report.txt")
    with open(report, "w") as f:
        for key, res in results.items():
            f.write("== %s bytes=%d pfc=%d ==\n" % (key[0], key[1], res["pfc"]))
            f.write("sticky cores per flow (source edge uplink):\n")
            for flow, cores in sorted(res["flows"].items()):
                f.write("  %s -> %s\n" % (flow, sorted(cores)))
            f.write("uplink packets / max qlen:\n")
            edges, cores = set(res["topo"]["edge"]), set(res["topo"]["core"])
            for (node, nbr), cnt in sorted(res["pkts"].items()):
                if node in edges and nbr in cores:
                    f.write("  edge %d -> core %d  pkts=%d qmax=%d\n" % (node, nbr, cnt, res["qmax"][(node, nbr)]))
            f.write("downlink packets / max qlen:\n")
            for (node, nbr), cnt in sorted(res["pkts"].items()):
                if node in cores and nbr in edges:
                    f.write("  core %d -> edge %d  pkts=%d qmax=%d\n" % (node, nbr, cnt, res["qmax"][(node, nbr)]))
    print(open(report).read())
    print("REPORT", report)


if __name__ == "__main__":
    main()
