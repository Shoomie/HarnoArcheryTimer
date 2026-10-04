#include "mesh_peers.h"

#include <cstring>

#include "mesh_config.h"

namespace mesh {

PeerInfo* PeerTable::findMut(const uint8_t mac[kMacLen]) {
  for (auto& p : peers_)
    if (p.used && std::memcmp(p.mac, mac, kMacLen) == 0) return &p;
  return nullptr;
}

const PeerInfo* PeerTable::find(const uint8_t mac[kMacLen]) const {
  for (const auto& p : peers_)
    if (p.used && std::memcmp(p.mac, mac, kMacLen) == 0) return &p;
  return nullptr;
}

bool PeerTable::accept(const uint8_t mac[kMacLen], uint16_t epoch, uint16_t seq, uint32_t now_ms) {
  PeerInfo* p = findMut(mac);
  if (!p) {
    // Free slot, else evict the peer that was heard longest ago.
    PeerInfo* victim = nullptr;
    for (auto& q : peers_) {
      if (!q.used) { victim = &q; break; }
      if (!victim || static_cast<uint32_t>(now_ms - q.last_heard_ms) > static_cast<uint32_t>(now_ms - victim->last_heard_ms))
        victim = &q;
    }
    std::memset(victim, 0, sizeof *victim);
    victim->used = true;
    std::memcpy(victim->mac, mac, kMacLen);
    victim->epoch = epoch;
    victim->last_seq = seq;
    victim->last_heard_ms = now_ms;
    return true;
  }
  p->last_heard_ms = now_ms;
  if (p->epoch != epoch) {  // reboot of the sender: reset its state and accept at once
    p->epoch = epoch;
    p->last_seq = seq;
    p->has_hello = false;
    return true;
  }
  if (static_cast<int16_t>(static_cast<uint16_t>(seq - p->last_seq)) > 0) {
    p->last_seq = seq;
    return true;
  }
  return false;
}

void PeerTable::updateHello(const uint8_t mac[kMacLen], const HelloPayload& hello) {
  PeerInfo* p = findMut(mac);
  if (!p) return;
  p->hello = hello;
  p->has_hello = true;
}

void PeerTable::expire(uint32_t now_ms) {
  for (auto& p : peers_)
    if (p.used && static_cast<uint32_t>(now_ms - p.last_heard_ms) >= kPeerExpiryMs) p.used = false;
}

size_t PeerTable::count() const {
  size_t n = 0;
  for (const auto& p : peers_)
    if (p.used) n++;
  return n;
}

}  // namespace mesh
