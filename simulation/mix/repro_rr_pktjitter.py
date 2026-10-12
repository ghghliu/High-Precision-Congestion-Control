#!/usr/bin/env python3
"""Per-packet send jitter on the sticky 4-flow RR case.

The four flows still start together (H0/H2 at 0, H1/H3 at 1 ns) and each
host still aims at line rate. Every packet then draws Uniform[-J, J] ns
around that gap. A draw that would send the next packet before the wire is
free is clipped, so the NIC never exceeds line rate and the average rate
sits a little under it.
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
PKT_NS = 83
PAIRS = [(0, 6), (1, 4), (2, 7), (3, 5)]


def write_flows(path, nbytes):
    # Same lockstep as the sticky case. The file must be in start-time order.
    starts = {0: 0.0, 1: 1e-9, 2: 0.0, 3: 1e-9}
    flows = [(src, dst, starts[src]) for src, dst in PAIRS]
    lines = ["%d" % len(flows)]
    for src, dst, start in flows:
        lines.append("%d %d 3 100 %d %.12f" % (src, dst, nbytes, start))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def run_case(out, nbytes, jitter_ns, seed):
    os.makedirs(out, exist_ok=True)
    topo = fat_tree(2, 4)
    write_topology(topo, os.path.join(out, "topology.txt"), "100Gbps", "1000ns")
    write_flows(os.path.join(out, "flow.txt"), nbytes)
    write_trace(topo, os.path.join(out, "trace.txt"))
    # NACK stays on in the simulator default. Here a flow that uses both cores
    # can be reordered, and a NACK would restart the message. Turn it off so
    # the queue is only the packets each host sends once.
    write_config(out, 100000000000, 1, nbytes, 0.01, jitter_ns, seed, enable_nack=0)
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
    summary["nbytes"] = nbytes
    summary["jitter_ns"] = jitter_ns
    summary["seed"] = seed
    summary["rate_frac"] = round(PKT_NS / float(summary["mean_gap_ns"]), 4) if summary["mean_gap_ns"] else 0
    expect = 4 * (nbytes // 1000)
    if summary["n_first"] != expect or summary["n_enqu"] != expect:
        raise SystemExit(
            "expected %d first transmissions, got n_first=%s n_enqu=%s in %s"
            % (expect, summary["n_first"], summary["n_enqu"], out)
        )
    return summary


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/rr-pktjitter"
    os.makedirs(root, exist_ok=True)
    jitters = [0, 8, 16, 32, 64]
    results = []
    for jitter in jitters:
        seeds = [1] if jitter == 0 else [1, 2, 3, 4]
        for seed in seeds:
            print("run", jitter, "seed", seed, flush=True)
            summary = run_case(os.path.join(root, "j%d-s%d" % (jitter, seed)), 160000, jitter, seed)
            results.append(summary)
            print(
                "  qmax", summary["down_qmax"],
                "stick", summary["stick_min"],
                "gap", summary["mean_gap_ns"],
                "rate", summary["rate_frac"],
                "tx", summary["n_enqu"],
                "cores", summary["cores"],
                flush=True,
            )
    long_rows = []
    for jitter in (0, 16, 32, 64):
        print("run long", jitter, flush=True)
        summary = run_case(os.path.join(root, "long-%d" % jitter), 1600000, jitter, 1)
        long_rows.append(summary)
        print(
            "  qmax", summary["down_qmax"],
            "stick", summary["stick_min"],
            "rate", summary["rate_frac"],
            "cores", summary["cores"],
            flush=True,
        )
    path = os.path.join(root, "results.json")
    with open(path, "w") as f:
        json.dump({"short": results, "long": long_rows}, f, indent=2)
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
    data = json.load(open(path))

    def series(rows):
        xs = sorted(set(item["jitter_ns"] for item in rows))
        q, qerr, stick, rate = [], [], [], []
        for x in xs:
            group = [item for item in rows if item["jitter_ns"] == x]
            ratios = [item["down_qmax"] / float(item["nbytes"]) for item in group]
            mean = float(np.mean(ratios))
            q.append(mean)
            qerr.append([mean - min(ratios), max(ratios) - mean])
            stick.append(np.mean([item["stick_min"] for item in group]))
            rate.append(np.mean([item["rate_frac"] for item in group]))
        return xs, q, np.array(qerr).T if qerr else None, stick, rate

    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=140)
    fig.subplots_adjust(left=0.12, right=0.88, bottom=0.22, top=0.88)
    xs, q, qerr, stick, rate = series(data["short"])
    ax.errorbar(xs, q, yerr=qerr, color="#c2410c", marker="o", lw=2, ms=7, capsize=3, label="160 KB，队列 / 消息")
    lxs, lq, _, _, _ = series(data["long"])
    ax.plot(lxs, lq, color="#1d4ed8", marker="s", lw=2, ms=7, label="1.6 MB，队列 / 消息")
    ax.set_xlabel("每个包的抖动幅度 J（ns），间隔在线速 ±J 内均匀取值")
    ax.set_ylabel("热下行最大队列 / 消息大小")
    ax.set_ylim(-0.05, 1.25)
    ax.set_title("逐包抖动后，RR 还会不会粘住")
    ax.spines["top"].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax2 = ax.twinx()
    ax2.plot(xs, [100 * s for s in stick], color="#0f766e", marker="^", lw=1.4, ms=6, label="落在同一核的比例")
    ax2.set_ylabel("最少的那条流，落在同一核上的包 (%)")
    ax2.set_ylim(-5, 125)
    ax2.spines["top"].set_visible(False)
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, frameon=False, fontsize=8.5, loc="center right")
    rate_txt = "  ".join("J=%d 速率 %.0f%%" % (x, 100 * r) for x, r in zip(xs, rate))
    fig.text(0.5, 0.045, "间隔 = 线速间隔 + max(0, 均匀[-J, J])。负的抖动发不出去，平均速率略低于线速。乱序不重传。\n" + rate_txt, ha="center", va="center", fontsize=8.5, color="#344054")
    out = "/opt/cursor/artifacts/fattree-rr-pktjitter.png"
    store = "/cursor/stores/self/artifacts/fattree-rr-pktjitter.png"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.makedirs(os.path.dirname(store), exist_ok=True)
    fig.savefig(out)
    fig.savefig(store)
    print(out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--plot":
        plot(sys.argv[2] if len(sys.argv) > 2 else "/tmp/rr-pktjitter/results.json")
    else:
        main()
