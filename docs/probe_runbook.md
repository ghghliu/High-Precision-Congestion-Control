# 已有 incast 上加入小流：服务器执行说明

把下面这段需求做成可复现实验，在服务器上跑即可。

> 已有 incast 正在跑时，新加入一条小流，验证它受 CC 影响欠吞吐。  
> 遍历不同小流长度：  
> - 特别小：一个 RTT 内发完，CC 还未生效，不欠吞吐  
> - 超过一个 RTT：受 CC 影响大，来不及收敛就完成，欠吞吐  
> - 比较大：CC 收敛后影响相对较小  
> 统计：完成时间、slowdown、PFC 计数、小流生命周期内 CC 速率变化

对照算法：`--cc pfc|dcqcn|hp|timely`。`--cc pfc` 只关 QCN（`ENABLE_QCN 0`），PFC 仍开。

代码在分支 `cursor/rocev2-pfc-dcqcn-bench-adc2`（未合入 `master` 前请用这个分支）。

---

## 0. 实验定义

拓扑：400G、2 级 1:1 fat-tree（4 leaf × 2 spine，每 leaf 16 条下行 + 每 spine 8 条上行）。  
`maxRtt ≈ 8080 ns`，`maxBdp ≈ 404 KB`。

```
t=2.000s  hosts 0-7  --8:1, 各 80MB-->  dest host 16
t=2.001s  host 8     --mouse, 大小 S-->  同一 dest     dport=100
```

| tag | 字节 | 预期档位 |
|-----|------|----------|
| `32k` `64k` | 32/64 KB | 亚 RTT：CC 未砍速 |
| `128k` | 128 KB | 接近 1 RTT |
| `400k` | 400 KB | ~1 BDP |
| `1m` `2m` | 1/2 MB | 几 RTT：CC 已砍、未收敛 |
| `5m` `20m` | 5/20 MB | 较大：有时间 FR/AI |

探测流用 **dport=100** 从 FCT / rate 日志里筛出来。9 路公平份额 400/9 ≈ 44.4 Gbps。  
`slowdown = FCT / 空网 standalone FCT`。亚 RTT 流的 goodput 被 RTT 主导，不要用 `vs_fair` 判断欠吞吐。

实测上 DCQCN 第一次 `mlx_dec` 约在探测流启动后 **+37 µs**（不是传播 RTT 8 µs）。≤400KB 都在这次降速前结束。

---

## 1. 环境

```bash
# ns-3.17 的 waf / run.py 必须是 Python 2
python2 -V          # 2.7.x
python3 -V          # 3.x，只用于 gen_fattree / analyze_probe

# 编译器：gcc 5+ 均可；gcc-13 已在本分支修过 ParameterLogger
g++ -dumpversion
```

缺 Python 2 时（Debian/Ubuntu 示例）：

```bash
sudo apt-get install -y python2 g++ python3
```

---

## 2. 取代码并编译（只需一次）

```bash
git clone https://github.com/ghghliu/High-Precision-Congestion-Control.git
cd High-Precision-Congestion-Control
git checkout cursor/rocev2-pfc-dcqcn-bench-adc2

cd simulation
./waf configure --enable-modules=core,network,internet,point-to-point,applications,config-store,tools,mpi,stats,bridge
./waf build
# 成功应看到 simulation/build/scratch/third
```

不要用 `python3` 跑 `waf` 或 `run.py`。

---

## 3. 跑完整扫描（推荐）

32 组：8 个长度 × 4 个 CC。单组 fat-tree 大约 1–2 分钟墙钟；`JOBS=4` 时整轮大约 15–25 分钟。

```bash
cd simulation

# 并行度按核数改，内存够可用 4
export JOBS=4

# 已有结果会跳过；要强制重跑：
# export SKIP_EXISTING=0

bash scripts/run_probe_400g.sh
```

脚本会：

1. `python3 scripts/gen_fattree_400g.py` 写出拓扑和 `mix/ft_probe_*_flow.txt`
2. 对每个 `(size, cc)` 调 `python2 run.py ... --stop 2.25 --bw 400 --buffer 32`
3. `python3 ../analysis/analyze_probe.py` 打表

只冒烟（确认环境，约 2 分钟）：

```bash
cd simulation
python3 scripts/gen_fattree_400g.py --mix mix
python2 run.py --cc dcqcn --topo ft2_4l2s --trace ft_probe_32k_flow \
  --bw 400 --stop 2.25 --buffer 32 --enable_tr 0 --trace_nodes trace_ft2
# 期望：dport 100 的 FCT ≈ 9µs，rate 日志只有 start/done 且 400G
```

只跑 DCQCN（仍扫 8 个长度）：把 `scripts/run_probe_400g.sh` 里的 `CCS=(pfc dcqcn hp timely)` 改成 `CCS=(dcqcn)`，或循环：

```bash
cd simulation
python3 scripts/gen_fattree_400g.py --mix mix
for tag in 32k 64k 128k 400k 1m 2m 5m 20m; do
  python2 run.py --cc dcqcn --topo ft2_4l2s --trace ft_probe_${tag}_flow \
    --bw 400 --stop 2.25 --buffer 32 --enable_tr 0 --trace_nodes trace_ft2
done
python3 ../analysis/analyze_probe.py --mix mix --ccs dcqcn
```

`--stop` 必须 ≥ `2.25`：20MB 若落到 DCQCN `MIN_RATE=1Gbps` 需要约 160ms。

---

## 4. 输出文件

均在 `simulation/mix/`。`--cc hp` 的文件名 tag 是 `hp95`。

| 文件 | 内容 |
|------|------|
| `fct_ft2_4l2s_ft_probe_<tag>_flow_<cc>.txt` | `sip dip sport dport size start_ns fct_ns standalone_ns` |
| `pfc_ft2_4l2s_ft_probe_<tag>_flow_<cc>.txt` | `t_ns node node_type ifindex type`（1=pause，0=resume） |
| `rate_ft2_4l2s_ft_probe_<tag>_flow_<cc>.txt` | `t_ns sip dip sport dport rate_bps why` |
| `docs/probe_table_400g.md` | 汇总表（分析脚本写） |

`why`：`start` `done` `mlx_first_cnp` `mlx_dec` `mlx_fr` `mlx_ai` `mlx_hai` `cc`（HPCC）`tmly_inc` `tmly_dec`。

手工看探测流：

```bash
# FCT：第 4 列 dport=100
awk '$4==100 {printf "fct_us=%.1f slow=%.2f\n",$7/1e3,$7/$8}' \
  mix/fct_ft2_4l2s_ft_probe_1m_flow_dcqcn.txt

# 速率：第 5 列 dport=100
awk '$5==100 {print}' mix/rate_ft2_4l2s_ft_probe_1m_flow_dcqcn.txt
```

分析脚本表头：

```
size regime cc fct_us slow gp_G vs_fair pfc rate0 rate_min rate_mean rate_end n_ev cut_us
```

- `slow`：相对空网 FCT  
- `pfc`：探测流存活窗口内 pause 次数  
- `rate0 / min / mean / end`：该 QP 的 `m_rate`（Gbps）  
- `cut_us`：相对 start，速率降到 90% 以下的时刻；`-` 表示从未砍  

PFC/TIMELY 的 `m_rate` 常停在 400G，真正限速是 pause，看 `fct_us` 和 `pfc` 列。

---

## 5. 怎么判断三档是否成立（看 DCQCN）

| 档 | 看什么 | 先前一次实测 |
|----|--------|----------------|
| 不欠吞吐 | `cut_us=-`，`rate0=rate_min=400`，`slow≈1.0–1.7` | 32k–400k |
| 欠吞吐、未收敛 | 有 `mlx_dec`，结束时 `rate_end` 很低（1–8G），流在第一次 `mlx_fr` 前结束 | 1m / 2m |
| 收敛后影响变小 | 先 MD 到 1G，之后出现 `mlx_fr` / `mlx_ai`，`slow` 不再随长度明显变差 | 5m / 20m，slow ≈ 5.6 |

HPCC：INT 从约 +8µs 开始砍，但 32k 结束时只降到 ~360G（slow 1.07），没有 1G 谷底。  
PFC：小流会被 pause 地板卡住（32k slow ~28×）；大流摊薄到 ~54G。和 CC 欠吞吐方向相反。

解读说明：`docs/probe_results_400g.md`。

---

## 6. 常见问题

- `python: can't open file waf` / 语法错误：用的是 python3。改 `python2 ./waf`、`python2 run.py`。
- `hp` 结果找不到：文件名是 `*_hp95.txt`。
- 20MB FCT 缺失或等于 stop：`--stop` 太短，用 `2.25`。
- 并行时日志交错：正常；结果按文件名分开。
- 重跑仍 skip：`SKIP_EXISTING=0 bash scripts/run_probe_400g.sh`。
