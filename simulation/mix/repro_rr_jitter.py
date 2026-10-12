#!/usr/bin/env python3
"""Start-time perturbation of the 4-flow Simple RR case.

Same k=4 2-level tree and the same four flows (H0->H6, H1->H4, H2->H7,
H3->H5). Every host still sends the whole message at line rate. Only the
start time moves, and the offset is a few packet times, so the four flows
overlap for almost the whole transfer and the offered load stays full.

Flows are written in start-time order. The simulator schedules the next
flow from the next line, so an unsorted file would arm that event in the past.
"""

import json
import os
import random
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_fattree import fat_tree, write_topology, write_trace
from repro_rr_l2 import port_neighbors, write_config

SIM = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WAF = "/usr/local/bin/python2.7"
TRACE_READER = os.path.join(SIM, "..", "analysis", "trace_reader")

BW_BPS = 100000000000
PKT_NS = 83  # measured enqueue spacing of one flow at 100 Gbps
WIRE_BYTES = 1048
PAIRS = [(0, 6), (1, 4), (2, 7), (3, 5)]


def write_flows(path, flows, nbytes):
    flows = sorted(flows, key=lambda item: (item[2], item[0]))
    lines = ["%d" % len(flows)]
    for src, dst, start in flows:
        lines.append("%d %d 3 100 %d %.12f" % (src, dst, nbytes, start))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def one_sender(delta_ns):
    """H0 at 0, H1 and H3 at 1 ns, only H2 moves."""
    ns = {0: 0, 1: 1, 2: delta_ns, 3: 1}
    return [(src, dst, ns[src] * 1e-9) for src, dst in PAIRS]


def edge_slip(delta_ns):
    """E1's two hosts slip together, keeping the 1 ns local stagger."""
    ns = {0: 0, 1: 1, 2: delta_ns, 3: delta_ns + 1}
    return [(src, dst, ns[src] * 1e-9) for src, dst in PAIRS]


def random_starts(window_ns, seed):
    rng = random.Random(seed)
    ns = {src: rng.uniform(0, window_ns) for src, _dst in PAIRS}
    return [(src, dst, ns[src] * 1e-9) for src, dst in PAIRS]


def parse_trace(text_path):
    rx = re.compile(
        r"^(\d+) n:(\d+) (\d+):(\d+) (\d+) (\w+) ecn:\w+ ([0-9a-f]+) ([0-9a-f]+) \d+ \d+ U (\d+)"
    )
    rows = []
    with open(text_path) as f:
        for line in f:
            m = rx.match(line)
            if not m or m.group(6) not in ("Enqu", "Dequ"):
                continue
            rows.append(
                {
                    "time": int(m.group(1)),
                    "node": int(m.group(2)),
                    "intf": int(m.group(3)),
                    "qlen": int(m.group(5)),
                    "event": m.group(6),
                    "sip": (int(m.group(7), 16) >> 8) & 0xFFFF,
                    "dip": (int(m.group(8), 16) >> 8) & 0xFFFF,
                    "seq": int(m.group(9)),
                }
            )
    return rows


def run_case(out, flows, nbytes):
    os.makedirs(out, exist_ok=True)
    topo = fat_tree(2, 4)
    write_topology(topo, os.path.join(out, "topology.txt"), "100Gbps", "1000ns")
    write_flows(os.path.join(out, "flow.txt"), flows, nbytes)
    write_trace(topo, os.path.join(out, "trace.txt"))
    write_config(out, BW_BPS, 1, nbytes, 0.01)
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
    summary = analyze(rows, port_neighbors(topo), edges, cores, topo)
    summary["nbytes"] = nbytes
    pfc = os.path.join(out, "pfc.txt")
    summary["pfc"] = sum(1 for _ in open(pfc)) if os.path.exists(pfc) else 0
    return summary


def analyze(rows, neigh, edges, cores, topo):
    """Count the first time each data packet leaves its source edge.

    A later copy of the same sequence is a NACK retransmission after two
    paths reorder that flow. It is not another RR decision for the original
    packet, so it does not enter the stickiness count.
    """
    core_of = {node: i for i, node in enumerate(topo["core"])}
    edge_of = {node: i for i, node in enumerate(topo["edge"])}
    first = {}
    link_qmax = {}
    dequ = []
    n_enqu = 0
    for r in rows:
        nbr = neigh.get((r["node"], r["intf"]))
        if nbr is None:
            continue
        if r["event"] == "Enqu":
            link_qmax[(r["node"], nbr)] = max(link_qmax.get((r["node"], nbr), 0), r["qlen"])
            if r["node"] in edges and nbr in cores:
                src_edge = topo["edge"][r["sip"] // topo["w"]]
                if r["node"] != src_edge:
                    continue
                n_enqu += 1
                key = (r["sip"], r["dip"], r["seq"])
                prev = first.get(key)
                if prev is None or r["time"] < prev[0]:
                    first[key] = (r["time"], nbr)
        elif r["event"] == "Dequ" and r["node"] in edges and nbr in cores:
            dequ.append(r)

    per_flow = {}
    flow_times = {}
    for (sip, dip, _seq), (time, nbr) in first.items():
        flow = (sip, dip)
        per_flow.setdefault(flow, {}).setdefault(nbr, 0)
        per_flow[flow][nbr] += 1
        flow_times.setdefault(flow, []).append(time)

    counts = {}
    fracs = {}
    for flow, cores_n in per_flow.items():
        total = sum(cores_n.values())
        counts["%d-%d" % flow] = {core_of.get(k, k): v for k, v in cores_n.items()}
        fracs[flow] = max(cores_n.values()) / float(total)

    first_t = {flow: min(times) for flow, times in flow_times.items()}
    last_t = {flow: max(times) for flow, times in flow_times.items()}
    t0 = max(first_t.values())
    t1 = min(last_t.values())
    span = max(last_t.values()) - min(first_t.values())
    overlap = (t1 - t0) / float(span) if span > 0 and t1 > t0 else 0.0

    down_qmax = 0
    down_link = None
    up_qmax = 0
    for (node, nbr), q in link_qmax.items():
        if node in cores and nbr in edges and q >= down_qmax:
            down_qmax = q
            down_link = [core_of.get(node, node), edge_of.get(nbr, nbr)]
        if node in edges and nbr in cores:
            up_qmax = max(up_qmax, q)

    up_rates = []
    if t1 > t0:
        window = t1 - t0
        n_by = {}
        for r in dequ:
            if t0 <= r["time"] <= t1:
                nbr = neigh[(r["node"], r["intf"])]
                n_by[(r["node"], nbr)] = n_by.get((r["node"], nbr), 0) + 1
        for n in n_by.values():
            up_rates.append(round(n * WIRE_BYTES * 8 / (window * 1e-9) / 1e9, 1))

    gaps = []
    for times in flow_times.values():
        ordered = sorted(set(times))
        gaps.extend(b - a for a, b in zip(ordered, ordered[1:]) if 0 < b - a < 500)

    return {
        "stick_min": round(min(fracs.values()), 4),
        "cores": counts,
        "down_qmax": down_qmax,
        "down_link": down_link,
        "up_qmax": up_qmax,
        "overlap_frac": round(overlap, 4),
        "up_gbps": sorted(up_rates),
        "gap_ns": sorted(gaps)[len(gaps) // 2] if gaps else PKT_NS,
        "mean_gap_ns": round(sum(gaps) / float(len(gaps)), 2) if gaps else PKT_NS,
        "n_enqu": n_enqu,
        "n_first": len(first),
        "t0": t0,
        "t1": t1,
    }


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/rr-jitter"
    os.makedirs(root, exist_ok=True)
    deltas = [0, 21, 42, 83, 124, 166, 249, 415, 830]
    results = {"pkt_ns": PKT_NS, "one": [], "edge": [], "random": [], "long": []}

    for delta in deltas:
        for kind, maker in (("one", one_sender), ("edge", edge_slip)):
            print("run", kind, delta, flush=True)
            summary = run_case(
                os.path.join(root, "%s-%d" % (kind, delta)),
                maker(delta),
                160000,
            )
            summary["delta_ns"] = delta
            summary["kind"] = kind
            results[kind].append(summary)
            print(
                "  qmax", summary["down_qmax"],
                "stick", summary["stick_min"],
                "overlap", summary["overlap_frac"],
                "up", summary["up_gbps"],
                "cores", summary["cores"],
                flush=True,
            )

    for delta in (0, 83, 166):
        print("run long", delta, flush=True)
        summary = run_case(
            os.path.join(root, "long-%d" % delta),
            one_sender(delta),
            1600000,
        )
        summary["delta_ns"] = delta
        summary["kind"] = "long"
        results["long"].append(summary)
        print("  qmax", summary["down_qmax"], "stick", summary["stick_min"], "cores", summary["cores"], flush=True)

    for window in (PKT_NS, 10 * PKT_NS):
        for seed in range(8):
            print("run random", window, seed, flush=True)
            summary = run_case(
                os.path.join(root, "rand-%d-%d" % (window, seed)),
                random_starts(window, seed),
                160000,
            )
            summary["window_ns"] = window
            summary["seed"] = seed
            results["random"].append(summary)
            print(
                "  qmax", summary["down_qmax"],
                "stick", summary["stick_min"],
                "overlap", summary["overlap_frac"],
                "cores", summary["cores"],
                flush=True,
            )

    path = os.path.join(root, "results.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print("WROTE", path)
    plot(path)


def plot(path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import numpy as np

    font_manager.fontManager.addfont("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc")
    plt.rcParams["font.family"] = "WenQuanYi Micro Hei"
    plt.rcParams["axes.unicode_minus"] = False

    results = json.load(open(path))
    fig, (ax, axr) = plt.subplots(1, 2, figsize=(13.2, 5.6), dpi=140)
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.24, top=0.82, wspace=0.28)

    def kb(rows):
        order = sorted(rows, key=lambda item: item["delta_ns"])
        x = [item["delta_ns"] / float(PKT_NS) for item in order]
        y = [item["down_qmax"] / 1000.0 for item in order]
        return x, y

    x, y = kb(results["one"])
    ax.plot(x, y, color="#c2410c", marker="o", lw=2.0, ms=7, label="只推迟 H2")
    x, y = kb(results["edge"])
    ax.plot(x, y, color="#64748b", marker="s", lw=1.8, ms=6, label="E1 两个主机一起推迟")
    ax.axhline(167.68, color="#c2410c", lw=0.6, ls="--", alpha=0.5)
    ax.set_xlabel("起步比 H0 晚多少（包）")
    ax.set_ylabel("热下行最大队列 (KB)")
    ax.set_title("错开开始时间后，碰撞还在不在")
    ax.set_ylim(-8, 210)
    ax.set_xlim(-0.4, 10.6)
    ax.legend(frameon=False, fontsize=9, loc="center")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.text(1.05, 22, "拆开了", color="#c2410c", fontsize=8, ha="center")
    ax.text(1.85, 192, "又叠回去", color="#c2410c", fontsize=8, ha="center")

    seeds = np.arange(8)
    w = 0.36
    y1 = [item["down_qmax"] / 1000.0 for item in results["random"] if item["window_ns"] == PKT_NS]
    y10 = [item["down_qmax"] / 1000.0 for item in results["random"] if item["window_ns"] == 10 * PKT_NS]
    axr.bar(seeds - w / 2, y1, w, color="#1d4ed8", label="随机窗口 1 个包")
    axr.bar(seeds + w / 2, y10, w, color="#0f766e", label="随机窗口 10 个包")
    axr.set_xticks(seeds)
    axr.set_xticklabels([str(i) for i in seeds])
    axr.set_xlabel("随机种子")
    axr.set_ylabel("热下行最大队列 (KB)")
    axr.set_title("四个开始时间各自随机", pad=22)
    axr.set_ylim(-8, 210)
    axr.legend(
        frameon=False,
        fontsize=9,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.0),
        ncol=2,
    )
    axr.spines["top"].set_visible(False)
    axr.spines["right"].set_visible(False)

    fig.text(
        0.5,
        0.04,
        "主机始终线速发完 160 KB。错开 1 个包时，四条流有 99% 的时间同时在发，四条上行都打满且队列为 0。\n"
        "只把 H2 错开约 1 个包，热下行消失；错开约 2 个包又锁回同一个核。E1 两个主机一起晚，则第一个包仍走 C0，碰撞拆不开。",
        ha="center",
        va="center",
        fontsize=9,
        color="#344054",
    )
    out = "/opt/cursor/artifacts/fattree-rr-jitter.png"
    store = "/cursor/stores/self/artifacts/fattree-rr-jitter.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.makedirs(os.path.dirname(store), exist_ok=True)
    fig.savefig(out)
    fig.savefig(store)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--plot":
        plot(sys.argv[2] if len(sys.argv) > 2 else "/tmp/rr-jitter/results.json")
    else:
        main()
