#ifndef RDMA_HW_H
#define RDMA_HW_H

#include <ns3/rdma.h>
#include <ns3/rdma-queue-pair.h>
#include <ns3/node.h>
#include <ns3/custom-header.h>
#include "qbb-net-device.h"
#include <unordered_map>
#include <map>
#include "pint.h"

namespace ns3 {

struct RdmaInterfaceMgr{
	Ptr<QbbNetDevice> dev;
	Ptr<RdmaQueuePairGroup> qpGrp;

	RdmaInterfaceMgr() : dev(NULL), qpGrp(NULL) {}
	RdmaInterfaceMgr(Ptr<QbbNetDevice> _dev){
		dev = _dev;
	}
};

class RdmaHw : public Object {
public:

	static TypeId GetTypeId (void);
	RdmaHw();

	Ptr<Node> m_node;
	DataRate m_minRate;		//< Min sending rate
	uint32_t m_mtu;
	uint32_t m_cc_mode;
	double m_nack_interval;
	uint32_t m_chunk;
	uint32_t m_ack_interval;
	bool m_backto0;
	bool m_var_win, m_fast_react;
	bool m_rateBound;
	std::vector<RdmaInterfaceMgr> m_nic; // list of running nic controlled by this RdmaHw
	std::unordered_map<uint64_t, Ptr<RdmaQueuePair> > m_qpMap; // mapping from uint64_t to qp
	std::unordered_map<uint64_t, Ptr<RdmaRxQueuePair> > m_rxQpMap; // mapping from uint64_t to rx qp
	std::unordered_map<uint32_t, std::vector<int> > m_rtTable; // map from ip address (u32) to possible ECMP port (index of dev)

	// qp complete callback
	typedef Callback<void, Ptr<RdmaQueuePair> > QpCompleteCallback;
	QpCompleteCallback m_qpCompleteCallback;

	void SetNode(Ptr<Node> node);
	void Setup(QpCompleteCallback cb); // setup shared data and callbacks with the QbbNetDevice
	static uint64_t GetQpKey(uint32_t dip, uint16_t sport, uint16_t pg); // get the lookup key for m_qpMap
	Ptr<RdmaQueuePair> GetQp(uint32_t dip, uint16_t sport, uint16_t pg); // get the qp
	uint32_t GetNicIdxOfQp(Ptr<RdmaQueuePair> qp); // get the NIC index of the qp
	void AddQueuePair(uint64_t size, uint16_t pg, Ipv4Address _sip, Ipv4Address _dip, uint16_t _sport, uint16_t _dport, uint32_t win, uint64_t baseRtt, Callback<void> notifyAppFinish); // add a new qp (new send)
	void DeleteQueuePair(Ptr<RdmaQueuePair> qp);

	Ptr<RdmaRxQueuePair> GetRxQp(uint32_t sip, uint32_t dip, uint16_t sport, uint16_t dport, uint16_t pg, bool create); // get a rxQp
	uint32_t GetNicIdxOfRxQp(Ptr<RdmaRxQueuePair> q); // get the NIC index of the rxQp
	void DeleteRxQp(uint32_t dip, uint16_t pg, uint16_t dport);

	int ReceiveUdp(Ptr<Packet> p, CustomHeader &ch);
	int ReceiveCnp(Ptr<Packet> p, CustomHeader &ch);
	int ReceiveAck(Ptr<Packet> p, CustomHeader &ch); // handle both ACK and NACK
	int Receive(Ptr<Packet> p, CustomHeader &ch); // callback function that the QbbNetDevice should use when receive packets. Only NIC can call this function. And do not call this upon PFC

	void CheckandSendQCN(Ptr<RdmaRxQueuePair> q);
	int ReceiverCheckSeq(uint32_t seq, Ptr<RdmaRxQueuePair> q, uint32_t size);
	void AddHeader (Ptr<Packet> p, uint16_t protocolNumber);
	static uint16_t EtherToPpp (uint16_t protocol);

	void RecoverQueue(Ptr<RdmaQueuePair> qp);
	void QpComplete(Ptr<RdmaQueuePair> qp);
	void SetLinkDown(Ptr<QbbNetDevice> dev);

	// call this function after the NIC is setup
	void AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx);
	void ClearTable();
	void RedistributeQp();

	Ptr<Packet> GetNxtPacket(Ptr<RdmaQueuePair> qp); // get next packet to send, inc snd_nxt
	void PktSent(Ptr<RdmaQueuePair> qp, Ptr<Packet> pkt, Time interframeGap);
	void UpdateNextAvail(Ptr<RdmaQueuePair> qp, Time interframeGap, uint32_t pkt_size);
	void ChangeRate(Ptr<RdmaQueuePair> qp, DataRate new_rate);
	/******************************
	 * Mellanox's version of DCQCN
	 *****************************/
	double m_g; //feedback weight
	double m_rateOnFirstCNP; // the fraction of line rate to set on first CNP
	bool m_EcnClampTgtRate;
	double m_rpgTimeReset;
	double m_rateDecreaseInterval;
	uint32_t m_rpgThreshold;
	double m_alpha_resume_interval;
	DataRate m_rai;		//< Rate of additive increase
	DataRate m_rhai;		//< Rate of hyper-additive increase

	// the Mellanox's version of alpha update:
	// every fixed time slot, update alpha.
	void UpdateAlphaMlx(Ptr<RdmaQueuePair> q);
	void ScheduleUpdateAlphaMlx(Ptr<RdmaQueuePair> q);

	// Mellanox's version of CNP receive
	void cnp_received_mlx(Ptr<RdmaQueuePair> q);

	// Mellanox's version of rate decrease
	// It checks every m_rateDecreaseInterval if CNP arrived (m_decrease_cnp_arrived).
	// If so, decrease rate, and reset all rate increase related things
	void CheckRateDecreaseMlx(Ptr<RdmaQueuePair> q);
	void ScheduleDecreaseRateMlx(Ptr<RdmaQueuePair> q, uint32_t delta);

	// Mellanox's version of rate increase
	void RateIncEventTimerMlx(Ptr<RdmaQueuePair> q);
	void RateIncEventMlx(Ptr<RdmaQueuePair> q);
	void FastRecoveryMlx(Ptr<RdmaQueuePair> q);
	void ActiveIncreaseMlx(Ptr<RdmaQueuePair> q);
	void HyperIncreaseMlx(Ptr<RdmaQueuePair> q);

	/***********************
	 * High Precision CC
	 ***********************/
	double m_targetUtil;
	double m_utilHigh;
	uint32_t m_miThresh;
	bool m_multipleRate;
	bool m_sampleFeedback; // only react to feedback every RTT, or qlen > 0
	void HandleAckHp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch);
	void UpdateRateHp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch, bool fast_react);
	void UpdateRateHpTest(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch, bool fast_react);
	void FastReactHp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch);

	/**********************
	 * TIMELY
	 *********************/
	double m_tmly_alpha, m_tmly_beta;
	uint64_t m_tmly_TLow, m_tmly_THigh, m_tmly_minRtt;
	void HandleAckTimely(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch);
	void UpdateRateTimely(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch, bool us);
	void FastReactTimely(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch);

	/**********************
	 * DCTCP
	 *********************/
	DataRate m_dctcp_rai;
	void HandleAckDctcp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch);

	/*********************
	 * HPCC-PINT
	 ********************/
	uint32_t pint_smpl_thresh;
	void SetPintSmplThresh(double p);
	void HandleAckHpPint(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch);
	void UpdateRateHpPint(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch, bool fast_react);

	/**********************
	 * On/Off CC (mode 12) -- controlled per destination IP (DIP), not per QP.
	 * Binary rate: full line rate (on) or a fixed low rate (m_minRate, e.g. 250Mbps).
	 *  - OFF: switch marks ECN when the egress queue exceeds a threshold; the
	 *    receiver echoes it as CNP in the ACK. Any CNP for a DIP throttles ALL
	 *    QPs to that DIP. While OFF, if no CNP arrives for m_onoff_off_timeout,
	 *    the source exits OFF and resumes full rate (avoids the stuck-OFF
	 *    deadlock when congestion clears and no notification is generated).
	 *  - ON : the switch sends a rate-limited "back to sender" notification
	 *    (triggered when a packet's queuing delay exceeds a threshold) carrying
	 *    the current 16-level queue level. The source resumes full rate ONLY if
	 *    the carried level is below m_onoff_on_level. A high level is NOT used as
	 *    OFF (OFF is exclusively the CNP path). A received signal takes effect
	 *    after a jittered NIC processing delay.
	 *********************/
	uint64_t m_onoff_t_nic_min, m_onoff_t_nic_max; // NIC processing delay jitter range (ns)
	uint32_t m_onoff_on_level;      // BTS -> ON only if carried queue level < this
	uint64_t m_onoff_off_timeout;   // ns; resume if no CNP for this long while OFF (0=disabled)
	uint32_t m_onoff_on_confirm;    // dual-ECN: # consecutive unmarked ACKs (queue<Klow) before ON
	// multi-level (mode 14): light decrease factor, resume floor, probe step/interval (percent, ns)
	uint32_t m_ml_light_pct;   // light decrease: R <- R * light_pct/100 (on 01)
	uint32_t m_ml_resume_pct;  // fast-recovery floor as % of line (on first unmarked)
	uint32_t m_ml_probe_pct;   // additive probe step as % of line (on sustained unmarked)
	uint64_t m_ml_probe_intvl; // ns between probe steps
	struct OnOffCtx {
		bool applied; bool target; bool pending; EventId timeout; uint32_t unmarked;
		DataRate tgtRate, appRate; bool ratePending; EventId probe; // mode 14 (multi-level)
		OnOffCtx() : applied(false), target(false), pending(false), unmarked(0), ratePending(false) {}
	};
	std::map<uint32_t, OnOffCtx> m_onoffCtx;                          // per-DIP control state
	std::map<uint32_t, std::vector<Ptr<RdmaQueuePair> > > m_onoffQps; // per-DIP QP list
	void HandleAckOnOff(Ptr<RdmaQueuePair> qp, bool congested); // OFF via ECN->CNP (per DIP)
	void HandleAckDualEcn(Ptr<RdmaQueuePair> qp, bool high, bool low); // dual-watermark on/off (mode 13)
	void HandleAckMultiLevel(Ptr<RdmaQueuePair> qp, bool high, bool low); // multi-level rate (mode 14)
	void OnOffSetRate(uint32_t dip, DataRate rate);   // schedule a rate change after NIC delay
	void OnOffApplyRate(uint32_t dip);                // apply latest target rate to all QPs to DIP
	void OnOffProbe(uint32_t dip);                    // additive probe upward while uncongested
	void OnOffSignal(uint32_t dip, bool congested);            // latch latest signal for a DIP
	void OnOffApply(uint32_t dip);                             // apply latest state after NIC delay
	void OnOffTimeout(uint32_t dip);                           // OFF watchdog -> resume
	void OnOffBtsOn(uint32_t dip, uint16_t sport, uint16_t pg, uint32_t qlevel); // ON from switch BTS
	// registry so a SwitchNode can deliver a back-to-sender ON to the source NIC
	static std::map<uint32_t, Ptr<RdmaHw> > m_rdmaHwMap; // node id -> RdmaHw
	static void DeliverBtsOn(uint32_t srcNodeId, uint32_t dip, uint16_t sport, uint16_t pg, uint32_t qlevel);
};

} /* namespace ns3 */

#endif /* RDMA_HW_H */
