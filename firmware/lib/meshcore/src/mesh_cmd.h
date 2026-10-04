// CMD logic of docs/mesh.md sections 2 and 4. CmdGate runs on the master node (permission, counter, ACK
// cache); CmdSender runs on a remote (counter, 15 ms retransmit until CMD_ACK, 250 ms limit).
#pragma once
#include <cstddef>
#include <cstdint>

#include "mesh_frame.h"

namespace mesh {

constexpr size_t kMaxRemotes = 8;
constexpr size_t kAckCache = 8;

struct RemoteEntry {
  bool used;
  uint8_t mac[kMacLen];
  uint8_t key[16];
  uint8_t mask;           // bit n-1 allows action n; emergency (bit 6) is always allowed
  uint32_t last_counter;  // last accepted; the owner persists it
};

struct CmdDecision {
  enum Kind : uint8_t {
    Ignore,   // host dead, or nothing to do (stale or duplicate of a pending command): send nothing
    Forward,  // new command: forward `$P,cmd` to the host, ACK later via onHostAck
    SendAck,  // send CMD_ACK with `result` now (denied, unknown remote, or re-ACK of a cached result)
  } kind = Ignore;
  uint8_t result = 0;
};

class CmdGate {
 public:
  bool addRemote(const uint8_t mac[kMacLen], const uint8_t key[16], uint8_t mask, uint32_t last_counter = 0);
  bool removeRemote(const uint8_t mac[kMacLen]);
  const RemoteEntry* find(const uint8_t mac[kMacLen]) const;

  // KeyRing hook: 16-byte key of a paired remote or nullptr. ctx is the CmdGate.
  static const uint8_t* lookupKey(void* ctx, const uint8_t mac[kMacLen]);

  // `mac` is the receive-callback source. For an authenticated CMD (decode succeeded with the remote key).
  // A CMD from a MAC that is not paired fails its tag in decode and is dropped; unknown() lets a caller that
  // still wants to answer result 2 (for example from a HELLO-less probe) build the decision.
  CmdDecision onCmd(const uint8_t mac[kMacLen], uint32_t counter, uint8_t action, bool host_alive);
  static CmdDecision unknown() { return CmdDecision{CmdDecision::SendAck, kAckUnknownRemote}; }

  // The host answered `$P,ack`. Returns true if a CMD_ACK for (mac, counter) must be sent now.
  bool onHostAck(const uint8_t mac[kMacLen], uint32_t counter, uint8_t result);

 private:
  struct CacheEntry {
    bool used, done;
    uint8_t mac[kMacLen];
    uint32_t counter;
    uint8_t result;
  };
  CacheEntry* findCache(const uint8_t mac[kMacLen], uint32_t counter);
  CacheEntry& putCache(const uint8_t mac[kMacLen], uint32_t counter, bool done, uint8_t result);
  RemoteEntry* findMut(const uint8_t mac[kMacLen]);

  RemoteEntry remotes_[kMaxRemotes] = {};
  CacheEntry cache_[kAckCache] = {};
  size_t next_cache_ = 0;
};

class CmdSender {
 public:
  explicit CmdSender(uint32_t last_counter = 0) : counter_(last_counter) {}
  // Starts a command: returns its counter (strictly increasing). The caller persists it BEFORE sending.
  uint32_t begin(uint32_t now_ms, uint8_t action);
  // True when a (re)transmission of the current command is due: at once, then every 15 ms, until the ACK
  // arrives or 250 ms have passed. Use a new frame seq for each retransmission, the same counter.
  bool due(uint32_t now_ms);
  // Returns true if the ACK belongs to the pending command.
  bool onAck(uint32_t counter, uint8_t result);
  bool pending() const { return pending_; }
  uint8_t action() const { return action_; }
  uint32_t counter() const { return counter_; }
  bool acked() const { return acked_; }
  uint8_t result() const { return result_; }

 private:
  uint32_t counter_;
  uint32_t start_ = 0, next_ = 0;
  uint8_t action_ = 0, result_ = 0;
  bool pending_ = false, acked_ = false;
};

}  // namespace mesh
