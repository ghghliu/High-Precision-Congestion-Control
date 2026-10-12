#!/usr/bin/env python3
"""400 Gbps, 16 hosts per leaf, uplinks not oversubscribed.

Same 2-level shape as the k=4 demo: four leaves and a full bipartite
core. Each leaf has 16 servers and 16 uplinks, all 400 Gbps, so the
uplink capacity equals the servers' capacity.

Two traffic patterns:

ring: E0's first 8 servers send to E3's first 8, E0's last 8 send to
E3's last 8, and every other leaf does the same three leaves away.
Each destination leaf receives 16 flows and has 16 downlinks.

collide: the 2-host collision, widened. E0 and E1 each send 16 flows.
The eight hosts that leave an edge first all go to E3, so at zero
jitter those two groups share the same eight cores. Aggregate demand
on E3 is still 16 flows.

pair2 is the original four flows at 400 Gbps, for the same jitter
values. NACK stays off. A negative jitter draw cannot beat the wire.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_fattree import fat_tree, write_topology, write_trace
from repro_rr_jitter import analyze, parse_trace
from repro_rr_l2 import port_neighbors, write_config

SIM = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WAF = "/usr/local/bin/python2.7"
TRACE_READER = os.path.join(SIM, "..", "analysis", "trace_reader")
BW = 400000000000
W = 16


def wide_topo():
    n_edge, hosts = 4, W
    n_core = hosts
    n_hosts = n_edge * hosts
    edge = list(range(n_hosts, n_hosts + n_edge))
    core = list(range(n_hosts + n_edge, n_hosts + n_edge + n_core))
    links = []
    for h in range(n_hosts):
        links.append((h, edge[h // hosts]))
    for e in edge:
        for c in core:
            links.append((e, c))
    return {
        "level": 2,
        "k": n_edge * 2,
        "w": hosts,
        "n_hosts": n_hosts,
        "switches": edge + core,
        "edge": edge,
        "agg": [],
        "core": core,
        "links": links,
    }


def write_flows(path, flows, nbytes):
    flows = sorted(flows, key=lambda item: (item[2], item[0]))
    lines = ["%d" % len(flows)]
    for src, dst, start in flows:
        lines.append("%d %d 3 100 %d %.12f" % (src, dst, nbytes, start))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def ring_flows():
    """E0 -> E3 one-to-one, then the same shift on every leaf."""
    flows = []
    for edge in range(4):
        dest = (edge + 3) % 4
        for i in range(W):
            flows.append((edge * W + i, dest * W + i, i * 1e-9))
    return flows


def collide_flows():
    """Two leaves, phase-aligned, sharing cores toward E3 and E2.

    Local host i starts i ns later, so at zero jitter leaf RR gives it
    core i. E0[0:8] and E1[0:8] therefore both sit on cores 0..7 and
    both go to E3.
    """
    flows = []
    for i in range(8):
        flows.append((0 * W + i, 3 * W + i, i * 1e-9))
        flows.append((0 * W + 8 + i, 2 * W + i, (8 + i) * 1e-9))
        flows.append((1 * W + i, 3 * W + 8 + i, i * 1e-9))
        flows.append((1 * W + 8 + i, 2 * W + 8 + i, (8 + i) * 1e-9))
    return flows


def pair2_flows():
    return [
        (0, 6, 0.0),
        (1, 4, 1e-9),
        (2, 7, 0.0),
        (3, 5, 1e-9),
    ]


CASES = {
    "ring": (wide_topo, ring_flows),
    "collide": (wide_topo, collide_flows),
    "pair2": (lambda: fat_tree(2, 4), pair2_flows),
}


def run_case(out, case, nbytes, jitter_ns, seed):
    os.makedirs(out, exist_ok=True)
    topo_fn, flow_fn = CASES[case]
    topo = topo_fn()
    flows = flow_fn()
    write_topology(topo, os.path.join(out, "topology.txt"), "400Gbps", "1000ns")
    write_flows(os.path.join(out, "flow.txt"), flows, nbytes)
    write_trace(topo, os.path.join(out, "trace.txt"))
    write_config(out, BW, 1, nbytes, 0.01, jitter_ns, seed, enable_nack=0)
    with open(os.path.join(out, "run.log"), "w") as f:
        subprocess.check_call(
            [WAF, os.path.join(SIM, "waf"), "--run", "scratch/third %s/config.txt" % out],
            cwd=SIM,
            stdout=f,
            stderr=subprocess.STDOUT,
        )
    text = os.path.join(out, "trace.txt.out")
    with open(text, "w") as f:
        subprocess.check_call([TRACE_READER, os.path.join(out, "mix.tr")], stdout=f)
    summary = analyze(parse_trace(text), port_neighbors(topo), set(topo["edge"]), set(topo["core"]), topo)
    expect = len(flows) * (nbytes // 1000)
    if summary["n_first"] != expect or summary["n_enqu"] != expect:
        raise SystemExit(
            "%s expected %d packets, n_first=%s n_enqu=%s"
            % (out, expect, summary["n_first"], summary["n_enqu"])
        )
    pfc = os.path.join(out, "pfc.txt")
    summary.update({
        "case": case,
        "nbytes": nbytes,
        "jitter_ns": jitter_ns,
        "seed": seed,
        "n_flows": len(flows),
        "n_cores": len(topo["core"]),
        "pfc": sum(1 for _ in open(pfc)) if os.path.exists(pfc) else 0,
    })
    return summary


def main():
    root = "/tmp/rr-wide"
    for arg in sys.argv[1:]:
        if arg != "--pilot":
            root = arg
    pilot = "--pilot" in sys.argv
    os.makedirs(root, exist_ok=True)
    jitters = [0] if pilot else [0, 2, 4, 8, 16, 32]
    results = []
    for case in ("pair2", "collide", "ring"):
        for jitter in jitters:
            seeds = [1] if jitter == 0 else [1, 2]
            for seed in seeds:
                print("run", case, jitter, "seed", seed, flush=True)
                summary = run_case(os.path.join(root, "%s-j%d-s%d" % (case, jitter, seed)), case, 160000, jitter, seed)
                results.append(summary)
                print(
                    "  qmax", summary["down_qmax"],
                    "upq", summary["up_qmax"],
                    "stick", summary["stick_min"],
                    "gap", summary["mean_gap_ns"],
                    "pfc", summary["pfc"],
                    "link", summary["down_link"],
                    flush=True,
                )
    long_rows = []
    if not pilot:
        for case in ("pair2", "collide", "ring"):
            for jitter in (0, 4, 8):
                print("run long", case, jitter, flush=True)
                summary = run_case(os.path.join(root, "long-%s-j%d" % (case, jitter)), case, 1600000, jitter, 1)
                long_rows.append(summary)
                print(
                    "  qmax", summary["down_qmax"],
                    "stick", summary["stick_min"],
                    "gap", summary["mean_gap_ns"],
                    "pfc", summary["pfc"],
                    flush=True,
                )
    path = os.path.join(root, "results.json")
    with open(path, "w") as f:
        json.dump({"short": results, "long": long_rows}, f)
    print("WROTE", path)
    if not pilot:
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
    data = json.load(open(path))
    short = data["short"]
    base = [r["mean_gap_ns"] for r in short if r["jitter_ns"] == 0 and r["case"] == "pair2"]
    pkt = base[0] if base else 21.0

    def series(case, rows):
        group_rows = [r for r in rows if r["case"] == case]
        xs = sorted(set(r["jitter_ns"] for r in group_rows))
        q, qerr, stick, rate = [], [], [], []
        for x in xs:
            g = [r for r in group_rows if r["jitter_ns"] == x]
            ratios = [r["down_qmax"] / float(r["nbytes"]) for r in g]
            mean = float(np.mean(ratios))
            q.append(mean)
            qerr.append([mean - min(ratios), max(ratios) - mean])
            stick.append(float(np.mean([r["stick_min"] for r in g])))
            gaps = [r["mean_gap_ns"] for r in g]
            rate.append(float(np.mean([pkt / g_ns for g_ns in gaps])))
        return xs, q, np.array(qerr).T, stick, rate

    fig, ax = plt.subplots(figsize=(8.8, 5.6), dpi=140)
    fig.subplots_adjust(left=0.11, right=0.88, bottom=0.20, top=0.88)
    styles = [
        ("pair2", "#c2410c", "o", "2 台上联，400G"),
        ("collide", "#1d4ed8", "s", "16 台上联，两条 leaf 对齐"),
        ("ring", "#0f766e", "^", "16 台上联，每个 leaf 单独打对面"),
    ]
    ax2 = ax.twinx()
    for case, color, marker, label in styles:
        xs, q, qerr, stick, _rate = series(case, short)
        ax.errorbar(xs, q, yerr=qerr, color=color, marker=marker, lw=2, ms=6.5, capsize=3, label=label)
        ax2.plot(xs, [100 * s for s in stick], color=color, marker=marker, lw=1, ms=4, ls=":", alpha=0.9)
    ax.set_xlabel("每个包的抖动 J（ns）")
    ax.set_ylabel("热下行最大队列 / 消息大小")
    ax.set_ylim(-0.05, 1.35)
    ax2.set_ylabel("一条流落在同一个核上的包（%，虚线）")
    ax2.set_ylim(-5, 125)
    ax.set_title("400 Gbps：上联从 2 条加到 16 条")
    ax.spines["top"].set_visible(False)
    ax2.spines["top"].set_visible(False)
    ax.legend(frameon=False, fontsize=8.5, loc="center right")
    fig.text(
        0.5,
        0.035,
        "实线是队列。虚线是粘在同一个核上的比例。J=0 时 2 台上联会把整条消息堆在一条下行上。",
        ha="center",
        va="center",
        fontsize=8.5,
        color="#344054",
    )
    out = "/opt/cursor/artifacts/fattree-rr-wide.png"
    store = "/cursor/stores/self/artifacts/fattree-rr-wide.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.makedirs(os.path.dirname(store), exist_ok=True)
    fig.savefig(out)
    fig.savefig(store)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--plot":
        plot(sys.argv[2] if len(sys.argv) > 2 else "/tmp/rr-wide/results.json")
    else:
        main()
