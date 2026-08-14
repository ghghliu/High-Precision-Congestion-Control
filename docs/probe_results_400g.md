# Mouse joining an existing incast @ 400G

Topology: 4 leaf × 2 spine, 16×400G down + 8×400G to each spine (1:1).
`maxRtt=8080ns`, `maxBdp=404000` bytes.

## Pattern

```
leaf0 hosts 0-7  --8:1 incast 80MB-->  leaf1 dest C (host 16)   @ t=2.000s
leaf0 host 8     --mouse, size S---->  same dest C              @ t=2.001s  dport=100
```

The incast has already been running for 1ms when the mouse starts (DCQCN incast QPs are in fast-recovery around ~100G). Fair share of the 400G dest among 9 senders is **44.4 Gbps**.

| size | bytes | intended regime | empty-net FCT |
|------|------:|-----------------|---------------|
| 32k / 64k | 32/64 KB | finish inside ~1 RTT; CC should not have cut yet | 8.8 / 9.4 µs |
| 128k | 128 KB | near 1 RTT | 10.8 µs |
| 400k | 400 KB | ~1 BDP | 16.5 µs |
| 1m / 2m | 1/2 MB | a few RTTs: CC cuts, no time to converge | 29 / 50 µs |
| 5m / 20m | 5/20 MB | long enough for FR/AI after the cut | 113 / 427 µs |

`slowdown = FCT / standalone FCT`. `vs_fair = goodput / 44.4G` is **not** meaningful for sub-RTT mice (FCT is RTT-dominated). PFC/TIMELY `rate_*` stay at 400G because pause, not `m_rate`, is what throttles them.

Run: `cd simulation && bash scripts/run_probe_400g.sh`

## DCQCN: three regimes (the CC under-throughput story)

| size | fct_us | slowdown | goodput | PFC | rate 0→min→end | first cut |
|------|-------:|---------:|--------:|----:|----------------|-----------|
| 32k | 9.1 | **1.05** | 28G | 0 | 400→400→400 | none |
| 64k | 10.2 | **1.09** | 50G | 0 | 400→400→400 | none |
| 128k | 13.1 | **1.22** | 78G | 0 | 400→400→400 | none |
| 400k | 27.8 | **1.69** | 115G | 0 | 400→400→400 | none (done at 27.8µs) |
| 1m | 63.0 | **2.17** | 127G | 0 | 400→**7.7**→7.7 | 37.3µs |
| 2m | 127.9 | **2.56** | 125G | 0 | 400→**1.0**→1.0 | 37.3µs |
| 5m | 625.9 | **5.54** | 64G | 0 | 400→1.0→80 | 37.3µs; FR @ 449µs |
| 20m | 2395.5 | **5.61** | 67G | 0 | 400→1.0→119 | 37.3µs; FR+AI after 449µs |

### 1. Sub-RTT / before first CNP (32k–400k) — no DCQCN cut

First `mlx_first_cnp` on the mouse is at **+33.3µs**, first `mlx_dec` at **+37.3µs**. Every mouse that finishes before that keeps `m_rate=400G` for its whole life:

```
32k   t=+0.0us  400G start
      t=+9.1us  400G done          # slowdown 1.05
400k  t=+0.0us  400G start
      t=+27.8us 400G done          # still no CNP
```

Slowdown 1.05–1.69 is queueing/serialization on the congested dest, **not** a rate-limiter cut. This is the “CC has not taken effect yet” regime.

### 2. Few RTT, cut and finish unconverged (1m–2m) — under-throughput

```
1m  +0     400G start
    +37.3  202G mlx_dec
    +41.3  103G
    +45.3   53G
    +53.3   28G
    +57.3   15G
    +61.3    7.7G
    +63.0    7.7G done             # dies on the way down

2m  same cut, hits MIN_RATE 1G at +73µs, done at +128µs still at 1G
    (RP_TIMER / first FR is ~449µs — the mouse is gone before recovery)
```

Most bytes went out in the first ~37µs at line rate; the tail is sent at 1–8G. Slowdown **2.2–2.6×**. This is the “CC hits, no time to converge” regime.

### 3. Long enough to recover (5m–20m) — valley then FR/AI

```
5m / 20m  same 400→1G crash by +73µs
          sit at 1G until +449µs  mlx_fr → 200G
5m        second decrease to 80G, done at 626µs     slowdown 5.54
20m       FR @ 449µs, 997µs, 1917µs; AI to 119G; done at 2396µs
          slowdown 5.61, mean rate 71G, end 119G
```

Slowdown **stops getting much worse** once FR/AI has run (5.54 → 5.61). Goodput ~64–67G is above 44G fair share but far below the 125G of the 1–2MB mice that finished during the first high-rate burst. The extra bytes pay the 1G valley (~380µs × 1G ≈ 47KB) plus later MD.

## HPCC / PFC / TIMELY (same flows)

| size | dcqcn slow | hp slow | pfc slow | timely slow | pfc count (probe window) |
|------|-----------:|--------:|---------:|------------:|-------------------------:|
| 32k | 1.05 | 1.07 | **28.3** | 24.6 | 274 / 0 / 4 |
| 64k | 1.09 | 1.13 | 26.4 | 23.0 | 276 / 0 / 4 |
| 400k | 1.69 | 1.53 | 15.9 | 13.9 | 277 / 0 / 5 |
| 1m | 2.17 | 1.99 | 9.8 | 8.4 | 282 / 0 / 6 |
| 2m | 2.56 | 2.45 | 10.4 | 5.4 | 504 / 0 / 6 |
| 5m | 5.54 | 3.17 | 7.3 | 3.0 | 749 / 0 / 7 |
| 20m | 5.61 | 4.62 | 6.9 | **1.56** | 2736 / 0 / 15 |

- **HPCC:** INT starts cutting at **+8.1µs** (one RTT). 32k is done at 9.3µs with rate only 360G — same “CC barely started” signature, slowdown 1.07. Larger mice converge toward ~70–90G (20m mean 90G, end 70G) without the 1G valley, so mid-size slowdown is better than DCQCN (5m: 3.17 vs 5.54).
- **PFC:** QP rate stays 400G; the dest pauses the NIC. Tiny mice wait a whole pause epoch (~250µs floor → 28×). Larger mice amortize toward ~54G (**1.22× fair**, slowdown ~7). Hundreds to thousands of pause events in the mouse lifetime.
- **TIMELY:** small mice look like PFC (pause wait, 4–7 PFC events, rate still 400G). 20m barely cuts (one `tmly_dec` to 332G at +613µs) and finishes at **240G / 1.56×** — it does not share the dest fairly with the incast.

Full numeric table: `docs/probe_table_400g.md`. Slowdown plots: `docs/probe_slowdown_400g.svg` (all CC) and `docs/probe_slowdown_cc_400g.svg` (DCQCN/HPCC/TIMELY only).

## Takeaway

1. **Very small mice (finish before the first CNP, here ≲37µs / ≲400KB):** DCQCN `m_rate` never moves; slowdown ≈1.0–1.7 from queueing only. HPCC has started INT but the cut is a few percent. **No CC under-throughput.**
2. **Mice longer than one CNP RTT but shorter than FR (1–2MB):** DCQCN MD 400G→1G and the flow **completes on the floor**. Slowdown 2.2–2.6×; this is the under-throughput the sweep is meant to show.
3. **Larger mice (5–20MB):** DCQCN FR at ~449µs then AI; slowdown saturates ~5.6× instead of growing with size. HPCC is smoother (no 1G hole). PFC’s damage is the opposite: **worst on the smallest mice** (pause wait is a fixed tax).
