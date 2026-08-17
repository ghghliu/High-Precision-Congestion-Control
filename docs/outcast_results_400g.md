# Outcast HoL results @ 400G 1:1 fat-tree

Topology: 4 leaf × 2 spine, 16×400G down + 8×400G to each spine.

## Pattern

```
leaf0 hosts 0..N-1  --N:1 incast-->  leaf1 dest C (host 16)
leaf0 host 0        --victim----->  leaf2 dest V (host 32, idle rack)
```

Both QPs on host 0 use PG 3. PFC pause is per-PG on the NIC, so the flow to V is backpressured even though V is idle.

Victim starts at t+200µs so the incast PFC is already active. `1/N` of 400G is 100G (N=4) or 50G (N=8).

## Outcast N=4 (expect victim ~100G under PFC)

| CC | Victim goodput | vs 1/N | Incast per-flow | Dest util | PFC on host 0 |
|----|----------------|--------|-----------------|-----------|---------------|
| **pfc** | **100.7 Gbps** | **1.01×** | 99.7 Gbps | 99% | **68** |
| dcqcn | 375.8 Gbps | 3.76× | 68.1 Gbps | 67% | 0 |
| hp | 185.2 Gbps | 1.85× | 88.0 Gbps | 87% | 0 |
| timely | 366.0 Gbps | 3.66× | 79.2 Gbps | 77% | 0 |

## Outcast N=8 (expect victim ~50G under PFC)

| CC | Victim goodput | vs 1/N | Incast per-flow | Dest util | PFC on host 0 |
|----|----------------|--------|-----------------|-----------|---------------|
| **pfc** | **66.6 Gbps** | **1.33×** | 58.2 Gbps | 100% | **96** |
| dcqcn | 383.6 Gbps | 7.67× | 38.0 Gbps | 74% | 0 |
| hp | 183.2 Gbps | 3.66× | 46.0 Gbps | 87% | 0 |
| timely | 232.7 Gbps | 4.65× | 42.6 Gbps | 79% | 14 |

N=8 victim is a bit above 50G because the probe starts after some unpaused bytes; it is still ~1/N, not line rate.

## Takeaway

- **PFC outcast:** innocent flow on the same source NIC is throttled to **~1/N**. Pause count on host 0 is the direct evidence.
- **DCQCN:** no NIC pause for the victim (~380G), but the incast **under-utilizes** the 400G dest (67–74%) — slow rate recovery after CNP.
- **HPCC:** no PFC; victim not stuck at 1/N (window-limited ~185G on this 400G param set).
- **TIMELY:** mostly protects the victim; some residual PFC at N=8.

Run: `cd simulation && bash scripts/run_outcast_400g.sh`
