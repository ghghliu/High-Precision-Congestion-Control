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


def _font():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    font_manager.fontManager.addfont("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc")
    plt.rcParams["font.family"] = "WenQuanYi Micro Hei"
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _save(fig, name):
    for folder in ("/opt/cursor/artifacts", "/cursor/stores/self/artifacts"):
        os.makedirs(folder, exist_ok=True)
        fig.savefig(os.path.join(folder, name))
    print(name)


def _series(case, rows, nbytes):
    import numpy as np

    group_rows = [r for r in rows if r["case"] == case and r["nbytes"] == nbytes]
    xs = sorted(set(r["jitter_ns"] for r in group_rows))
    q, qerr, rate = [], [], []
    for x in xs:
        g = [r for r in group_rows if r["jitter_ns"] == x]
        ratios = [r["down_qmax"] / float(r["nbytes"]) for r in g]
        mean = float(np.mean(ratios))
        q.append(mean)
        qerr.append([mean - min(ratios), max(ratios) - mean])
        rate.append(float(np.mean([20.0 / r["mean_gap_ns"] for r in g])))
    err = np.array(qerr).T if qerr else None
    return xs, q, err, rate


def _queue_ax(ax, title):
    ax.set_xlabel("每个包的抖动 J（ns）")
    ax.set_ylabel("热下行最大队列 / 消息大小")
    ax.set_ylim(-0.05, 1.35)
    ax.set_title(title)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")


def plot(path):
    import matplotlib.pyplot as plt

    _font()
    data = json.load(open(path))
    short, long_rows = data["short"], data["long"]

    fig, ax = plt.subplots(figsize=(7.6, 5.0), dpi=140)
    fig.subplots_adjust(left=0.12, right=0.96, bottom=0.20, top=0.88)
    xs, q, err, rate = _series("pair2", short, 160000)
    ax.errorbar(xs, q, yerr=err, color="#c2410c", marker="o", lw=2, ms=7, capsize=3, label="160 KB")
    lxs, lq, _, _ = _series("pair2", long_rows, 1600000)
    ax.plot(lxs, lq, color="#1d4ed8", marker="s", lw=2, ms=7, label="1.6 MB")
    _queue_ax(ax, "400 Gbps，每个 leaf 2 台服务器")
    fig.text(
        0.54,
        0.04,
        "只画队列。  " + "  ".join("J=%d  %.0f%%" % (x, 100 * r) for x, r in zip(xs, rate)),
        ha="center",
        fontsize=8.5,
        color="#344054",
    )
    _save(fig, "fattree-400-queue-2.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.6, 5.0), dpi=140)
    fig.subplots_adjust(left=0.12, right=0.96, bottom=0.20, top=0.88)
    xs, q, err, rate = _series("ring", short, 160000)
    ax.errorbar(xs, q, yerr=err, color="#0f766e", marker="o", lw=2, ms=7, capsize=3, label="打对面，160 KB")
    xs, q, err, _ = _series("collide", short, 160000)
    ax.errorbar(xs, q, yerr=err, color="#1d4ed8", marker="s", lw=2, ms=7, capsize=3, label="两条 leaf 对齐，160 KB")
    lxs, lq, _, _ = _series("collide", long_rows, 1600000)
    ax.plot(lxs, lq, color="#c2410c", marker="D", lw=2, ms=6.5, label="两条 leaf 对齐，1.6 MB")
    _queue_ax(ax, "400 Gbps，每个 leaf 16 台服务器")
    fig.text(
        0.54,
        0.04,
        "打对面的 1.6 MB 也是 0。  " + "  ".join("J=%d  %.0f%%" % (x, 100 * r) for x, r in zip(xs, rate)),
        ha="center",
        fontsize=8.5,
        color="#344054",
    )
    _save(fig, "fattree-400-queue-16.png")
    plt.close(fig)
    draw_diagrams()


def _box(ax, x, y, w, h, text, fc, ec, fs=8, weight="regular", tc="#111827"):
    from matplotlib.patches import FancyBboxPatch

    ax.add_patch(
        FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            facecolor=fc,
            edgecolor=ec,
            linewidth=1.3,
            zorder=4,
        )
    )
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, zorder=5, fontweight=weight, color=tc)


def _tag(ax, x, y, text, color, fs=8):
    ax.text(
        x,
        y,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color=color,
        zorder=7,
        fontweight="medium",
        bbox=dict(boxstyle="round,pad=0.16", fc="white", ec=color, lw=0.8, alpha=0.96),
    )


def _arrow(ax, a, b, color, lw=2.2, rad=0.0):
    from matplotlib.patches import FancyArrowPatch

    ax.add_patch(
        FancyArrowPatch(
            a,
            b,
            arrowstyle="-|>",
            mutation_scale=11,
            color=color,
            lw=lw,
            zorder=3,
            connectionstyle="arc3,rad=%s" % rad,
            shrinkA=2,
            shrinkB=2,
        )
    )


def _blank(ax, title):
    ax.set_axis_off()
    ax.set_title(title, fontsize=14, pad=8, color="#111827")


def draw_diagrams():
    import matplotlib.pyplot as plt

    _font()
    _draw_topo_2(plt)
    _draw_traffic_2(plt)
    _draw_topo_16(plt)
    _draw_traffic_16(plt)
    _draw_traffic_align(plt)


def _draw_topo_2(plt):
    fig, ax = plt.subplots(figsize=(11.2, 6.2), dpi=140)
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.08, top=0.88)
    ax.set_xlim(-0.4, 12.6)
    ax.set_ylim(-1.15, 6.2)
    ax.set_aspect("equal")
    _blank(ax, "组网：400 Gbps，每个 leaf 2 台服务器")
    edge_x = [1.2, 4.2, 7.2, 10.2]
    core_x = [2.7, 8.7]
    for ei in range(4):
        for ci in range(2):
            ax.plot([edge_x[ei], core_x[ci]], [1.7, 4.6], color="#d1d5db", lw=1.6, zorder=1, solid_capstyle="round")
        for side, label in ((-0.7, 0), (0.7, 1)):
            hx = edge_x[ei] + side
            ax.plot([edge_x[ei], hx], [1.7, 0.15], color="#d1d5db", lw=1.6, zorder=1)
            _box(ax, hx, 0.15, 1.05, 0.42, "H%d" % (ei * 2 + label), "#ffffff", "#64748b", fs=9)
        _box(ax, edge_x[ei], 1.7, 1.15, 0.5, "E%d" % ei, "#f8fafc", "#334155", fs=12, weight="bold")
    _box(ax, core_x[0], 4.6, 1.2, 0.52, "C0", "#f8fafc", "#334155", fs=12, weight="bold")
    _box(ax, core_x[1], 4.6, 1.2, 0.52, "C1", "#f8fafc", "#334155", fs=12, weight="bold")
    ax.text(6.1, -0.75, "4 个 leaf，2 个 core。每条链路 400 Gbps。每个 leaf 2 条下联、2 条上联，上行不收敛。", ha="center", fontsize=10, color="#344054")
    _save(fig, "fattree-400-topo-2.png")
    plt.close(fig)


def _draw_traffic_2(plt):
    fig, ax = plt.subplots(figsize=(11.2, 6.4), dpi=140)
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.10, top=0.88)
    ax.set_xlim(-0.4, 12.6)
    ax.set_ylim(-1.35, 6.3)
    ax.set_aspect("equal")
    _blank(ax, "流量：每个 leaf 2 台，400 Gbps")
    edge_x = [1.2, 4.2, 7.2, 10.2]
    core_x = [2.7, 8.7]
    colors = {0: "#c2410c", 1: "#1d4ed8", 2: "#7c3aed", 3: "#047857"}
    flows = [(0, 6, 0), (2, 7, 0), (1, 4, 1), (3, 5, 1)]

    def epos(i):
        return (edge_x[i], 1.85)

    def cpos(i):
        return (core_x[i], 4.7)

    def hpos(i):
        return (edge_x[i // 2] + (-0.72 if i % 2 == 0 else 0.72), 0.2)

    for ei in range(4):
        for ci in range(2):
            ax.plot([epos(ei)[0], cpos(ci)[0]], [epos(ei)[1], cpos(ci)[1]], color="#e5e7eb", lw=1.4, zorder=1)
        for s in (0, 1):
            hp = hpos(ei * 2 + s)
            ax.plot([epos(ei)[0], hp[0]], [epos(ei)[1], hp[1]], color="#e5e7eb", lw=1.4, zorder=1)
    for src, dst, core in flows:
        color = colors[src]
        _arrow(ax, hpos(src), epos(src // 2), color, lw=2.3)
        _arrow(ax, epos(src // 2), cpos(core), color, lw=2.4)
        _arrow(ax, cpos(core), epos(dst // 2), color, lw=2.4)
        _arrow(ax, epos(dst // 2), hpos(dst), color, lw=2.3)
    _tag(ax, 1.85, 3.55, "H0→H6", colors[0])
    _tag(ax, 3.35, 3.55, "H2→H7", colors[2])
    _tag(ax, 4.7, 3.85, "H1→H4", colors[1])
    _tag(ax, 6.55, 2.45, "H3→H5", colors[3])
    _tag(ax, 6.9, 3.85, "H0→H6、H2→H7\n同走 C0→E3", "#9a3412", fs=8)
    _tag(ax, 9.7, 3.35, "H1→H4、H3→H5\n同走 C1→E2", "#1e3a8a", fs=8)
    for i in range(4):
        _box(ax, edge_x[i], 1.85, 1.05, 0.48, "E%d" % i, "#f8fafc", "#334155", fs=11, weight="bold")
    _box(ax, core_x[0], 4.7, 1.15, 0.5, "C0", "#fff7ed", "#c2410c", fs=12, weight="bold")
    _box(ax, core_x[1], 4.7, 1.15, 0.5, "C1", "#eff6ff", "#1d4ed8", fs=12, weight="bold")
    for i in range(8):
        src = {0: 0, 1: 1, 2: 2, 3: 3, 4: 1, 5: 3, 6: 0, 7: 2}[i]
        _box(ax, hpos(i)[0], hpos(i)[1], 1.15, 0.42, "H%d" % i, "#ffffff", colors[src], fs=8, tc=colors[src])
    ax.text(6.1, -0.85, "J=0：H0、H2 先发，都进 C0；H1、H3 晚 1 ns，都进 C1。两条热下行各叠了两条流。", ha="center", fontsize=10, color="#344054")
    _save(fig, "fattree-400-traffic-2.png")
    plt.close(fig)


def _draw_topo_16(plt):
    fig, ax = plt.subplots(figsize=(14.6, 6.4), dpi=140)
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.08, top=0.88)
    ax.set_xlim(-0.3, 16.3)
    ax.set_ylim(-1.05, 6.3)
    _blank(ax, "组网：400 Gbps，每个 leaf 16 台服务器")
    core_x = [0.55 + i * 1.0 for i in range(16)]
    leaf_x = [2.05, 6.05, 10.05, 14.05]
    for lx in leaf_x:
        for cx in core_x:
            ax.plot([lx, cx], [2.15, 4.55], color="#e5e7eb", lw=0.7, zorder=1, solid_capstyle="round")
        ax.plot([lx, lx], [2.15, 0.55], color="#d1d5db", lw=1.8, zorder=1)
        _box(ax, lx, 0.55, 2.35, 0.55, "16 台服务器", "#ffffff", "#64748b", fs=9)
        _box(ax, lx, 2.15, 1.15, 0.5, "E%d" % leaf_x.index(lx), "#f8fafc", "#334155", fs=12, weight="bold")
    for i, cx in enumerate(core_x):
        _box(ax, cx, 4.55, 0.82, 0.46, "C%d" % i, "#f8fafc", "#334155", fs=7.5, weight="bold")
    ax.text(8.0, -0.55, "4 个 leaf，16 个 core，两两相连。每条链路 400 Gbps。每个 leaf 16 条下联、16 条上联，上行不收敛。", ha="center", fontsize=10, color="#344054")
    _save(fig, "fattree-400-topo-16.png")
    plt.close(fig)


def _band(ax, x, y, w, h, text):
    from matplotlib.patches import FancyBboxPatch

    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.1",
            facecolor="#f8fafc",
            edgecolor="#94a3b8",
            linewidth=1.2,
            zorder=1,
        )
    )
    ax.text(x + w / 2, y + h + 0.22, text, ha="center", va="bottom", fontsize=12, fontweight="bold", color="#334155", zorder=5)


def _through(ax, y, color):
    _arrow(ax, (2.75, y), (4.15, y), color, lw=2.1)
    ax.plot([4.25, 7.75], [y, y], color=color, lw=2.2, zorder=2, solid_capstyle="round")
    _arrow(ax, (7.85, y), (9.25, y), color, lw=2.1)


def _draw_traffic_16(plt):
    fig, ax = plt.subplots(figsize=(12.2, 8.0), dpi=140)
    fig.subplots_adjust(left=0.04, right=0.96, bottom=0.06, top=0.90)
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.35, 9.7)
    _blank(ax, "流量：每个 leaf 的 16 台打到对面 leaf 的 16 台")
    colors = ["#c2410c", "#1d4ed8", "#7c3aed", "#047857"]
    pairs = [(0, 3), (1, 0), (2, 1), (3, 2)]
    front_y = [8.15, 7.15, 6.15, 5.15]
    back_y = [3.45, 2.45, 1.45, 0.45]
    _band(ax, 4.05, 4.75, 3.9, 3.8, "C0 – C7")
    _band(ax, 4.05, 0.05, 3.9, 3.8, "C8 – C15")
    for i, (src, dst) in enumerate(pairs):
        color = colors[src]
        _box(ax, 1.45, front_y[i], 2.35, 0.62, "E%d 前 8" % src, "#ffffff", color, fs=12, tc=color, weight="bold")
        _box(ax, 10.55, front_y[i], 2.35, 0.62, "E%d 前 8" % dst, "#ffffff", color, fs=12, tc=color, weight="bold")
        _through(ax, front_y[i], color)
        _box(ax, 1.45, back_y[i], 2.35, 0.62, "E%d 后 8" % src, "#ffffff", color, fs=12, tc=color, weight="bold")
        _box(ax, 10.55, back_y[i], 2.35, 0.62, "E%d 后 8" % dst, "#ffffff", color, fs=12, tc=color, weight="bold")
        _through(ax, back_y[i], color)
    ax.text(6.0, 9.35, "同一行是一组 8 条流。J=0 时前 8 台占 C0–C7，后 8 台占 C8–C15，每条下行只有一条流。", ha="center", fontsize=10, color="#344054")
    _save(fig, "fattree-400-traffic-16.png")
    plt.close(fig)


def _draw_traffic_align(plt):
    fig, ax = plt.subplots(figsize=(12.2, 6.4), dpi=140)
    fig.subplots_adjust(left=0.04, right=0.96, bottom=0.07, top=0.88)
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.45, 6.5)
    _blank(ax, "流量：E0 和 E1 的相同时隙打到同一个 leaf")
    rows = [
        (5.35, "E0 前 8", "E3 前 8", "#c2410c"),
        (4.35, "E1 前 8", "E3 后 8", "#7c3aed"),
        (2.15, "E0 后 8", "E2 前 8", "#c2410c"),
        (1.15, "E1 后 8", "E2 后 8", "#7c3aed"),
    ]
    _band(ax, 4.05, 3.9, 3.9, 1.9, "C0 – C7，下行都去 E3")
    _band(ax, 4.05, 0.7, 3.9, 1.9, "C8 – C15，下行都去 E2")
    for y, left, right, color in rows:
        _box(ax, 1.45, y, 2.35, 0.58, left, "#ffffff", color, fs=12, tc=color, weight="bold")
        _box(ax, 10.55, y, 2.35, 0.58, right, "#ffffff", color, fs=12, tc=color, weight="bold")
        _through(ax, y, color)
    ax.text(6.0, -0.2, "J=0：两边的第 i 台都进 Ci。上面 8 条下联各有两条流，下面 8 条下联也各有两条流。", ha="center", fontsize=10, color="#344054")
    _save(fig, "fattree-400-traffic-align.png")
    plt.close(fig)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--plot":
        plot(sys.argv[2] if len(sys.argv) > 2 else "/tmp/rr-wide/results.json")
    elif len(sys.argv) > 1 and sys.argv[1] == "--draw":
        _font()
        draw_diagrams()
    else:
        main()
