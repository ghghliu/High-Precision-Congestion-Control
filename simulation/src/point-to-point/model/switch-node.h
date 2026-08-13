#ifndef SWITCH_NODE_H
#define SWITCH_NODE_H

#include <unordered_map>
#include <ns3/node.h>
#include "qbb-net-device.h"
#include "switch-mmu.h"
#include "pint.h"

namespace ns3 {

class Packet;

class SwitchNode : public Node{
	static const uint32_t pCnt = 257;	// Number of ports used
	static const uint32_t qCnt = 8;	// Number of queues/priorities used
	uint32_t m_ecmpSeed;
	std::unordered_map<uint32_t, std::vector<int> > m_rtTable; // map from ip address (u32) to possible ECMP port (index of dev)

	// monitor of PFC
	uint32_t m_bytes[pCnt][pCnt][qCnt]; // m_bytes[inDev][outDev][qidx] is the bytes from inDev enqueued for outDev at qidx
	
	uint64_t m_txBytes[pCnt]; // counter of tx bytes

	uint32_t m_lastPktSize[pCnt];
	uint64_t m_lastPktTs[pCnt]; // ns
	double m_u[pCnt];

protected:
	bool m_ecnEnabled;
	uint32_t m_ccMode;
	uint64_t m_maxRtt;

	uint32_t m_ackHighPrio; // set high priority for ACK/NACK

	// On/Off CC (mode 12): switch-generated "back to sender" ON notification.
	// The switch periodically (every m_btsSense) samples each egress port's queue
	// depth and stores it as a 16-level (4-bit) value in m_qLevel. When a data
	// packet is dequeued after experiencing a queuing delay > m_btsDelayThresh,
	// the switch sends an ON notification carrying m_qLevel back to that packet's
	// source, arriving after m_btsSig. (OFF stays on the ECN->CNP path.)
	uint64_t m_btsSense;        // queue-level table update period (ns)
	uint64_t m_btsSig;          // switch->source signaling delay (ns)
	uint64_t m_btsDelayThresh;  // per-packet queuing delay that triggers a BTS (ns)
	uint64_t m_btsLevelUnit;    // bytes per quantized queue level (16 levels)
	uint32_t m_qLevel[pCnt];    // periodically-updated quantized queue level per port
	bool m_btsStarted;
	std::unordered_map<uint64_t, uint64_t> m_lastBts; // (port,src) -> last BTS time (ns), rate-limits to 1/sense
	void BtsSampleQueues();

private:
	int GetOutDev(Ptr<const Packet>, CustomHeader &ch);
	void SendToDev(Ptr<Packet>p, CustomHeader &ch);
	static uint32_t EcmpHash(const uint8_t* key, size_t len, uint32_t seed);
	void CheckAndSendPfc(uint32_t inDev, uint32_t qIndex);
	void CheckAndSendResume(uint32_t inDev, uint32_t qIndex);
public:
	Ptr<SwitchMmu> m_mmu;

	static TypeId GetTypeId (void);
	SwitchNode();
	void SetEcmpSeed(uint32_t seed);
	void AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx);
	void ClearTable();
	bool SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch);
	void SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p);

	// for approximate calc in PINT
	int logres_shift(int b, int l);
	int log2apprx(int x, int b, int m, int l); // given x of at most b bits, use most significant m bits of x, calc the result in l bits
};

} /* namespace ns3 */

#endif /* SWITCH_NODE_H */
