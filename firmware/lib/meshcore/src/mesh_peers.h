// Peer table: dedupe by (mac, epoch, seq) and the roster built from HELLO frames (docs/mesh.md sections 1, 3).
#pragma once
#include <cstddef>
#include <cstdint>

#include "mesh_frame.h"

namespace mesh {

constexpr size_t kMaxPeers = 16;

struct PeerInfo {
  bool used;
  uint8_t mac[kMacLen];
  uint16_t epoch;
  uint16_t last_seq;
  uint32_t last_heard_ms;
  bool has_hello;
  HelloPayload hello;
};

class PeerTable {
 public:
  // Call for every frame whose tag verified. Returns true if the frame is new and must be processed:
  // unknown peer, a new epoch (resets the peer at once), or int16(seq - last) > 0 within the same epoch.
  // Any valid frame refreshes the expiry timer, duplicates included.
  bool accept(const uint8_t mac[kMacLen], uint16_t epoch, uint16_t seq, uint32_t now_ms);

  void updateHello(const uint8_t mac[kMacLen], const HelloPayload& hello);

  // Drops peers without a valid frame for kPeerExpiryMs.
  void expire(uint32_t now_ms);

  size_t count() const;
  const PeerInfo* find(const uint8_t mac[kMacLen]) const;
  const PeerInfo& slot(size_t i) const { return peers_[i]; }  // check .used
  static constexpr size_t capacity() { return kMaxPeers; }

 private:
  PeerInfo* findMut(const uint8_t mac[kMacLen]);
  PeerInfo peers_[kMaxPeers] = {};
};

}  // namespace mesh
