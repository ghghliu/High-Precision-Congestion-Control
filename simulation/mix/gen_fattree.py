#!/usr/bin/env python3
"""Generate a 2-level or 3-level k-ary fat-tree for the HPCC packet simulator.

Level 3 is the Al-Fares fat-tree: k pods, k/2 edge and aggregation switches
per pod, (k/2)^2 core switches, k/2 hosts per edge (k^3/4 hosts).

Level 2 is the two-tier fabric used in Ofan Fig. 10: k edge switches, k/2
core switches, k/2 hosts per edge (k^2/2 hosts).

The written config turns congestion control and ECN off (CC_MODE 0,
ENABLE_QCN 0) and leaves dynamic PFC on. Forwarding stays the simulator's
current ECMP hash until a load-balancing mode is selected.
"""

import argparse
import os


def fat_tree(level, k):
    if k < 2 or k % 2:
        raise SystemExit("k must be an even integer >= 2")
    if level not in (2, 3):
        raise SystemExit("level must be 2 or 3")
    w = k // 2
    if level == 2:
        n_edge, n_agg, n_core = k, 0, w
        n_hosts = n_edge * w
    else:
        n_edge = k * w
        n_agg = k * w
        n_core = w * w
        n_hosts = n_edge * w
    n_switches = n_edge + n_agg + n_core
    base = n_hosts
    edge = list(range(base, base + n_edge))
    agg = list(range(base + n_edge, base + n_edge + n_agg))
    core = list(range(base + n_edge + n_agg, base + n_switches))

    links = []
    for h in range(n_hosts):
        e = edge[h // w]
        links.append((h, e))
    if level == 2:
        for e in edge:
            for c in core:
                links.append((e, c))
    else:
        for pod in range(k):
            edges = edge[pod * w:(pod + 1) * w]
            aggs = agg[pod * w:(pod + 1) * w]
            for e in edges:
                for a in aggs:
                    links.append((e, a))
        for a_i, a in enumerate(agg):
            agg_in_pod = a_i % w
            for c in core[agg_in_pod * w:(agg_in_pod + 1) * w]:
                links.append((a, c))
    switches = edge + agg + core
    return {
        "level": level,
        "k": k,
        "w": w,
        "n_hosts": n_hosts,
        "switches": switches,
        "edge": edge,
        "agg": agg,
        "core": core,
        "links": links,
    }


def write_topology(topo, path, bw, delay):
    nodes = topo["n_hosts"] + len(topo["switches"])
    lines = ["%d %d %d" % (nodes, len(topo["switches"]), len(topo["links"]))]
    lines.append(" ".join(str(s) for s in topo["switches"]))
    for src, dst in topo["links"]:
        lines.append("%d %d %s %s 0.000000" % (src, dst, bw, delay))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def write_flows(topo, path, nbytes):
    n = topo["n_hosts"]
    # Shift by one edge (2-level) or one pod (3-level) so every flow is northbound.
    shift = topo["w"] if topo["level"] == 2 else topo["w"] * topo["w"]
    flows = []
    for src in range(n):
        dst = (src + shift) % n
        # src dst pg dport size_bytes start_time
        flows.append("%d %d 3 100 %d 0" % (src, dst, nbytes))
    with open(path, "w") as f:
        f.write("%d\n" % len(flows))
        f.write("\n".join(flows) + "\n")


def write_trace(topo, path):
    with open(path, "w") as f:
        f.write("%d\n" % len(topo["switches"]))
        f.write(" ".join(str(s) for s in topo["switches"]) + "\n")


def write_config(directory, bw_bps):
    # Paths are absolute so `waf --run` can be launched from simulation/.
    d = os.path.abspath(directory)
    # One map entry: every link in this generator uses the same rate.
    kmap = "1 %d 400" % bw_bps
    kmin = "1 %d 100" % bw_bps
    pmax = "1 %d 0.2" % bw_bps
    text = """ENABLE_QCN 0
USE_DYNAMIC_PFC_THRESHOLD 1

PACKET_PAYLOAD_SIZE 1000

TOPOLOGY_FILE {d}/topology.txt
FLOW_FILE {d}/flow.txt
TRACE_FILE {d}/trace.txt
TRACE_OUTPUT_FILE {d}/mix.tr
FCT_OUTPUT_FILE {d}/fct.txt
PFC_OUTPUT_FILE {d}/pfc.txt

SIMULATOR_STOP_TIME 0.01

CC_MODE 0
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
L2_CHUNK_SIZE 4000
L2_ACK_INTERVAL 1
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

KMAX_MAP {kmap}
KMIN_MAP {kmin}
PMAX_MAP {pmax}
BUFFER_SIZE 16
QLEN_MON_FILE {d}/qlen.txt
QLEN_MON_START 20000000000
QLEN_MON_END 20000000000
""".format(d=d, kmap=kmap, kmin=kmin, pmax=pmax)
    with open(os.path.join(directory, "config.txt"), "w") as f:
        f.write(text)


def bw_to_bps(bw):
    units = [("Gbps", 10 ** 9), ("Mbps", 10 ** 6), ("Kbps", 10 ** 3), ("bps", 1)]
    for suffix, scale in units:
        if bw.endswith(suffix):
            return int(float(bw[: -len(suffix)]) * scale)
    raise SystemExit("bandwidth must end with Gbps, Mbps, Kbps, or bps")


def main():
    p = argparse.ArgumentParser(description="Generate a 2- or 3-level fat-tree scenario")
    p.add_argument("--level", type=int, choices=(2, 3), required=True)
    p.add_argument("--k", type=int, required=True, help="switch radix, even")
    p.add_argument("--bw", default="100Gbps")
    p.add_argument("--delay", default="1000ns")
    p.add_argument("--bytes", type=int, default=10000, help="payload bytes per flow")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)
    topo = fat_tree(args.level, args.k)
    write_topology(topo, os.path.join(args.out, "topology.txt"), args.bw, args.delay)
    write_flows(topo, os.path.join(args.out, "flow.txt"), args.bytes)
    write_trace(topo, os.path.join(args.out, "trace.txt"))
    write_config(args.out, bw_to_bps(args.bw))
    print(
        "level=%d k=%d hosts=%d switches=%d links=%d -> %s"
        % (args.level, args.k, topo["n_hosts"], len(topo["switches"]), len(topo["links"]), os.path.abspath(args.out))
    )


if __name__ == "__main__":
    main()
