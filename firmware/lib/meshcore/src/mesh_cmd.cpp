#include "mesh_cmd.h"

#include <cstring>

#include "mesh_config.h"

namespace mesh {

RemoteEntry* CmdGate::findMut(const uint8_t mac[kMacLen]) {
  for (auto& r : remotes_)
    if (r.used && std::memcmp(r.mac, mac, kMacLen) == 0) return &r;
  return nullptr;
}

const RemoteEntry* CmdGate::find(const uint8_t mac[kMacLen]) const {
  for (const auto& r : remotes_)
    if (r.used && std::memcmp(r.mac, mac, kMacLen) == 0) return &r;
  return nullptr;
}

bool CmdGate::addRemote(const uint8_t mac[kMacLen], const uint8_t key[16], uint8_t mask, uint32_t last_counter) {
  RemoteEntry* r = findMut(mac);
  if (!r) {
    for (auto& e : remotes_)
      if (!e.used) { r = &e; break; }
  }
  if (!r) return false;
  r->used = true;
  std::memcpy(r->mac, mac, kMacLen);
  std::memcpy(r->key, key, 16);
  r->mask = mask;
  r->last_counter = last_counter;
  return true;
}

bool CmdGate::removeRemote(const uint8_t mac[kMacLen]) {
  RemoteEntry* r = findMut(mac);
  if (!r) return false;
  std::memset(r, 0, sizeof *r);
  for (auto& c : cache_)
    if (c.used && std::memcmp(c.mac, mac, kMacLen) == 0) c.used = false;
  return true;
}

const uint8_t* CmdGate::lookupKey(void* ctx, const uint8_t mac[kMacLen]) {
  const RemoteEntry* r = static_cast<const CmdGate*>(ctx)->find(mac);
  return r ? r->key : nullptr;
}

CmdGate::CacheEntry* CmdGate::findCache(const uint8_t mac[kMacLen], uint32_t counter) {
  for (auto& c : cache_)
    if (c.used && c.counter == counter && std::memcmp(c.mac, mac, kMacLen) == 0) return &c;
  return nullptr;
}

CmdGate::CacheEntry& CmdGate::putCache(const uint8_t mac[kMacLen], uint32_t counter, bool done, uint8_t result) {
  CacheEntry* c = findCache(mac, counter);
  if (!c) {
    c = &cache_[next_cache_];
    next_cache_ = (next_cache_ + 1) % kAckCache;
  }
  c->used = true;
  c->done = done;
  std::memcpy(c->mac, mac, kMacLen);
  c->counter = counter;
  c->result = result;
  return *c;
}

CmdDecision CmdGate::onCmd(const uint8_t mac[kMacLen], uint32_t counter, uint8_t action, bool host_alive) {
  if (!host_alive) return CmdDecision{};  // only a master with a live host accepts CMD
  RemoteEntry* r = findMut(mac);
  if (!r) return unknown();
  if (action < kActionPrimary || action > kActionEmergency) return CmdDecision{};
  if (counter <= r->last_counter) {
    const CacheEntry* c = findCache(mac, counter);
    if (c && c->done) return CmdDecision{CmdDecision::SendAck, c->result};  // duplicate: re-ACK, never forward
    return CmdDecision{};                                                  // pending or stale: stay quiet
  }
  r->last_counter = counter;
  const bool allowed = action == kActionEmergency || (r->mask & (1u << (action - 1))) != 0;
  if (!allowed) {
    putCache(mac, counter, true, kAckDenied);
    return CmdDecision{CmdDecision::SendAck, kAckDenied};
  }
  putCache(mac, counter, false, 0);
  return CmdDecision{CmdDecision::Forward, 0};
}

bool CmdGate::onHostAck(const uint8_t mac[kMacLen], uint32_t counter, uint8_t result) {
  CacheEntry* c = findCache(mac, counter);
  if (!c || c->done) return false;
  c->done = true;
  c->result = result > kAckUnknownRemote ? kAckDenied : result;
  return true;
}

uint32_t CmdSender::begin(uint32_t now_ms, uint8_t action) {
  counter_++;
  action_ = action;
  start_ = next_ = now_ms;
  pending_ = true;
  acked_ = false;
  result_ = 0;
  return counter_;
}

bool CmdSender::due(uint32_t now_ms) {
  if (!pending_) return false;
  if (static_cast<uint32_t>(now_ms - start_) > kCmdGiveUpMs) {
    pending_ = false;
    return false;
  }
  if (static_cast<int32_t>(now_ms - next_) < 0) return false;
  next_ = now_ms + kCmdRetransmitMs;
  return true;
}

bool CmdSender::onAck(uint32_t counter, uint8_t result) {
  if (!pending_ || counter != counter_) return false;
  pending_ = false;
  acked_ = true;
  result_ = result;
  return true;
}

}  // namespace mesh
