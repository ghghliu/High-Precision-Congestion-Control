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
	uint32_t m_lbMode; // 0: 5-tuple ECMP, 1: one RR pointer on this switch, 2: RR with a fresh host order each round
	uint32_t m_rrGroupPorts; // 0: one switch-wide RR pointer. N: one pointer per N ingress ports (pofan)
	uint32_t m_rrHoldPackets; // packets kept on the current slot before the pointer advances. 1: every packet
	uint32_t m_rrPtr[pCnt];  // next RR slot per ingress group; slot 0 is the lowest peer node id
	uint32_t m_rrRun[pCnt];  // packets already sent on the current slot of this group
	uint32_t m_roundSeed;
	uint32_t m_arrivalJitterNs;
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

private:
	int GetOutDev(Ptr<const Packet>, CustomHeader &ch);
	uint32_t PeerNodeId(uint32_t ifIndex) const;
	bool IsHostPort(uint32_t ifIndex) const;
	uint32_t HostRank(uint32_t round, uint32_t inDev) const;
	uint32_t ArrivalDelay(uint32_t seq, uint32_t sip) const;
	void SendToDev(Ptr<Packet>p, CustomHeader &ch);
	void ForwardShuffled(Ptr<Packet> p);
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
