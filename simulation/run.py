import argparse
import sys
import os

config_template="""ENABLE_QCN {enable_qcn}
USE_DYNAMIC_PFC_THRESHOLD 1

PACKET_PAYLOAD_SIZE 1000

TOPOLOGY_FILE mix/{topo}.txt
FLOW_FILE mix/{trace}.txt
TRACE_FILE mix/{trace_nodes}.txt
TRACE_OUTPUT_FILE mix/mix_{topo}_{trace}_{cc}{failure}.tr
FCT_OUTPUT_FILE mix/fct_{topo}_{trace}_{cc}{failure}.txt
PFC_OUTPUT_FILE mix/pfc_{topo}_{trace}_{cc}{failure}.txt

SIMULATOR_STOP_TIME {stop}

CC_MODE {mode}
ALPHA_RESUME_INTERVAL {t_alpha}
RATE_DECREASE_INTERVAL {t_dec}
CLAMP_TARGET_RATE 0
RP_TIMER {t_inc}
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
MI_THRESH {mi}
INT_MULTI {int_multi}
MULTI_RATE 0
SAMPLE_FEEDBACK 0
PINT_LOG_BASE {pint_log_base}
PINT_PROB {pint_prob}

RATE_BOUND 1

ACK_HIGH_PRIO {ack_prio}

LINK_DOWN {link_down}

ENABLE_TRACE {enable_tr}

KMAX_MAP {kmax_map}
KMIN_MAP {kmin_map}
PMAX_MAP {pmax_map}
BUFFER_SIZE {buffer_size}
QLEN_MON_FILE mix/qlen_{topo}_{trace}_{cc}{failure}.txt
QLEN_MON_START {qlen_start}
QLEN_MON_END {qlen_end}
"""

def make_config(**kwargs):
	defaults = dict(
		enable_qcn=1,
		trace_nodes='trace',
		stop=4.00,
		qlen_start=2000000000,
		qlen_end=3000000000,
	)
	defaults.update(kwargs)
	return config_template.format(**defaults)

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='run simulation')
	parser.add_argument('--cc', dest='cc', action='store', default='hp', help="hp/dcqcn/timely/dctcp/hpccPint/pfc")
	parser.add_argument('--trace', dest='trace', action='store', default='flow', help="the name of the flow file")
	parser.add_argument('--bw', dest="bw", action='store', default='50', help="the NIC bandwidth")
	parser.add_argument('--down', dest='down', action='store', default='0 0 0', help="link down event")
	parser.add_argument('--topo', dest='topo', action='store', default='fat', help="the name of the topology file")
	parser.add_argument('--utgt', dest='utgt', action='store', type=int, default=95, help="eta of HPCC")
	parser.add_argument('--mi', dest='mi', action='store', type=int, default=0, help="MI_THRESH")
	parser.add_argument('--hpai', dest='hpai', action='store', type=int, default=0, help="AI for HPCC")
	parser.add_argument('--pint_log_base', dest='pint_log_base', action = 'store', type=float, default=1.01, help="PINT's log_base")
	parser.add_argument('--pint_prob', dest='pint_prob', action = 'store', type=float, default=1.0, help="PINT's sampling probability")
	parser.add_argument('--enable_tr', dest='enable_tr', action = 'store', type=int, default=0, help="enable packet-level events dump")
	parser.add_argument('--stop', dest='stop', action='store', type=float, default=4.0, help="simulator stop time (seconds)")
	parser.add_argument('--trace_nodes', dest='trace_nodes', action='store', default='trace', help="trace node list file under mix/")
	parser.add_argument('--dry_run', dest='dry_run', action='store_true', default=False, help="only write config, do not run")
	parser.add_argument('--buffer', dest='buffer', action='store', type=int, default=0, help="switch buffer size in MB (0 = scale with bw)")
	args = parser.parse_args()

	topo=args.topo
	bw = int(args.bw)
	trace = args.trace
	#bfsz = 16 if bw==50 else 32
	bfsz = args.buffer if args.buffer > 0 else (16 * bw / 50)
	u_tgt=args.utgt/100.
	mi=args.mi
	pint_log_base=args.pint_log_base
	pint_prob = args.pint_prob
	enable_tr = args.enable_tr
	stop = args.stop
	# monitor queues during the interesting window after flows start (default flows @ t=2s)
	qlen_start = int(max(0.0, min(stop, 2.0) - 0.001) * 1e9)
	qlen_end = int(stop * 1e9)

	failure = ''
	if args.down != '0 0 0':
		failure = '_down'

	config_name = "mix/config_%s_%s_%s%s.txt"%(topo, trace, args.cc, failure)

	# Map NIC rate and a 4x fabric rate (common in fat-tree). Extra entries for 400G benches.
	kmax_map = "2 %d %d %d %d"%(bw*1000000000, 400*bw/25, bw*4*1000000000, 400*bw*4/25)
	kmin_map = "2 %d %d %d %d"%(bw*1000000000, 100*bw/25, bw*4*1000000000, 100*bw*4/25)
	pmax_map = "2 %d %.2f %d %.2f"%(bw*1000000000, 0.2, bw*4*1000000000, 0.2)

	common = dict(
		bw=bw, trace=trace, topo=topo, failure=failure,
		pint_log_base=pint_log_base, pint_prob=pint_prob,
		link_down=args.down, kmax_map=kmax_map, kmin_map=kmin_map, pmax_map=pmax_map,
		buffer_size=bfsz, enable_tr=enable_tr, stop=stop,
		trace_nodes=args.trace_nodes, qlen_start=qlen_start, qlen_end=qlen_end,
		enable_qcn=1,
	)

	if (args.cc.startswith("dcqcn")):
		ai = 5 * bw / 25
		hai = 50 * bw /25

		if args.cc == "dcqcn":
			config = make_config(cc=args.cc, mode=1, t_alpha=1, t_dec=4, t_inc=300, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=0, vwin=0, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=1, **common)
		elif args.cc == "dcqcn_paper":
			config = make_config(cc=args.cc, mode=1, t_alpha=50, t_dec=50, t_inc=55, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=0, vwin=0, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=1, **common)
		elif args.cc == "dcqcn_vwin":
			config = make_config(cc=args.cc, mode=1, t_alpha=1, t_dec=4, t_inc=300, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=1, vwin=1, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=0, **common)
		elif args.cc == "dcqcn_paper_vwin":
			config = make_config(cc=args.cc, mode=1, t_alpha=50, t_dec=50, t_inc=55, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=1, vwin=1, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=0, **common)
		else:
			print "unknown cc:", args.cc
			sys.exit(1)
	elif args.cc == "pfc":
		# PFC-only: no ECN/CNP rate control; rely on pause frames.
		ai = 5 * bw / 25
		hai = 50 * bw / 25
		common['enable_qcn'] = 0
		config = make_config(cc=args.cc, mode=1, t_alpha=1, t_dec=4, t_inc=300, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=0, vwin=0, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=1, **common)
	elif args.cc == "hp":
		ai = 10 * bw / 25;
		if args.hpai > 0:
			ai = args.hpai
		hai = ai # useless
		int_multi = bw / 25;
		cc = "%s%d"%(args.cc, args.utgt)
		if (mi > 0):
			cc += "mi%d"%mi
		if args.hpai > 0:
			cc += "ai%d"%ai
		config_name = "mix/config_%s_%s_%s%s.txt"%(topo, trace, cc, failure)
		config = make_config(cc=cc, mode=3, t_alpha=1, t_dec=4, t_inc=300, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=1, vwin=1, us=1, u_tgt=u_tgt, mi=mi, int_multi=int_multi, ack_prio=0, **common)
	elif args.cc == "dctcp":
		ai = 10 # ai is useless for dctcp
		hai = ai  # also useless
		dctcp_ai=615 # calculated from RTT=13us and MTU=1KB, because DCTCP add 1 MTU per RTT.
		kmax_map = "2 %d %d %d %d"%(bw*1000000000, 30*bw/10, bw*4*1000000000, 30*bw*4/10)
		kmin_map = "2 %d %d %d %d"%(bw*1000000000, 30*bw/10, bw*4*1000000000, 30*bw*4/10)
		pmax_map = "2 %d %.2f %d %.2f"%(bw*1000000000, 1.0, bw*4*1000000000, 1.0)
		common['kmax_map'] = kmax_map
		common['kmin_map'] = kmin_map
		common['pmax_map'] = pmax_map
		config = make_config(cc=args.cc, mode=8, t_alpha=1, t_dec=4, t_inc=300, g=0.0625, ai=ai, hai=hai, dctcp_ai=dctcp_ai, has_win=1, vwin=1, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=0, **common)
	elif args.cc == "timely":
		ai = 10 * bw / 10;
		hai = 50 * bw / 10;
		config = make_config(cc=args.cc, mode=7, t_alpha=1, t_dec=4, t_inc=300, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=0, vwin=0, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=1, **common)
	elif args.cc == "timely_vwin":
		ai = 10 * bw / 10;
		hai = 50 * bw / 10;
		config = make_config(cc=args.cc, mode=7, t_alpha=1, t_dec=4, t_inc=300, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=1, vwin=1, us=0, u_tgt=u_tgt, mi=mi, int_multi=1, ack_prio=1, **common)
	elif args.cc == "hpccPint":
		ai = 10 * bw / 25;
		if args.hpai > 0:
			ai = args.hpai
		hai = ai # useless
		int_multi = bw / 25;
		cc = "%s%d"%(args.cc, args.utgt)
		if (mi > 0):
			cc += "mi%d"%mi
		if args.hpai > 0:
			cc += "ai%d"%ai
		cc += "log%.3f"%pint_log_base
		cc += "p%.3f"%pint_prob
		config_name = "mix/config_%s_%s_%s%s.txt"%(topo, trace, cc, failure)
		config = make_config(cc=cc, mode=10, t_alpha=1, t_dec=4, t_inc=300, g=0.00390625, ai=ai, hai=hai, dctcp_ai=1000, has_win=1, vwin=1, us=1, u_tgt=u_tgt, mi=mi, int_multi=int_multi, ack_prio=0, **common)
	else:
		print "unknown cc:", args.cc
		sys.exit(1)

	with open(config_name, "w") as file:
		file.write(config)

	print "Wrote", config_name
	if args.dry_run:
		sys.exit(0)

	ret = os.system("./waf --run 'scratch/third %s'"%(config_name))
	sys.exit(0 if ret == 0 else 1)
