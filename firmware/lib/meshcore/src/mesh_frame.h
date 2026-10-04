// Mesh v2 frame codec (docs/mesh.md sections 1-2). Pure functions, no I/O, no heap.
#pragma once
#include <cstddef>
#include <cstdint>

namespace mesh {

constexpr uint8_t kMagic = 0xA8;
constexpr uint8_t kVersion = 0x02;
constexpr size_t kHeaderLen = 8;
constexpr size_t kTagLen = 8;
constexpr size_t kMacLen = 6;
constexpr size_t kMaxFrame = 250;
constexpr size_t kMaxNameLen = 12;
constexpr size_t kMaxSeqIdLen = 32;  // not fixed by the contract: limit of this implementation
constexpr size_t kMaxGroups = 8;     // idem
constexpr size_t kMaxGroupLen = 16;  // idem
constexpr uint32_t kKeepValue = 0xFFFFFFFFu;
constexpr uint16_t kSoundAgeNone = 0xFFFF;

enum class FrameType : uint8_t {
  Hello = 1, Timer = 2, Sound = 3, Cmd = 4, CmdAck = 5, Session = 6, PairOpen = 7, PairReq = 8, PairAcc = 9,
  Revoke = 10  // the master tells one paired remote (by MAC) to forget its keys; mesh key tag
};

enum : uint8_t { kLightG = 1, kLightY = 2, kLightR = 4 };
enum : uint8_t { kTimerPaused = 1, kTimerEmergency = 2, kTimerBuzzer = 4 };
enum : uint8_t { kCapL = 1, kCapS = 2, kCapB = 4, kCapK = 8, kCapR = 16 };
enum : uint8_t { kActionPrimary = 1, kActionPause, kActionResume, kActionStopEnd, kActionNext, kActionBack,
                 kActionEmergency };
enum : uint8_t { kAckDone = 0, kAckDenied = 1, kAckUnknownRemote = 2 };

struct HelloPayload {
  uint8_t caps, role, rank, conflict;
  uint32_t master_id;
  uint8_t fw[3];
  uint8_t name_len;
  char name[kMaxNameLen + 1];  // NUL terminated copy
};

struct TimerPayload {
  uint32_t master_id;
  uint32_t session;  // replay protection counter of the master's core (mesh.md section 4)
  uint8_t rank, lights, flags, mode, phase;
  uint32_t remaining_ms;
  uint8_t end_no, total_ends, group, round, total_rounds, session_rev;
  uint8_t sound_seq, sound_count, sound_blast, sound_gap;
  uint16_t sound_age;
};

struct SoundPayload {
  uint32_t master_id;
  uint32_t session;
  uint8_t sound_seq, count, blast, gap;
};

struct CmdPayload {
  uint32_t counter;
  uint8_t action;
};

struct CmdAckPayload {
  uint8_t target_mac[kMacLen];
  uint32_t counter;
  uint8_t result;
};

struct SessionPayload {
  uint32_t master_id;
  uint8_t rev, flags, total_ends, practice_ends;  // flags: bit0 alternate order, bit1 auto-advance
  uint32_t prep_ms, shoot_ms, warn_ms, auto_delay_ms;
  uint8_t seq_len;
  char sequence_id[kMaxSeqIdLen + 1];
  uint8_t groups_n;
  uint8_t group_len[kMaxGroups];
  char groups[kMaxGroups][kMaxGroupLen + 1];
};

struct PairOpenPayload {
  uint32_t master_id;
  uint8_t seconds_left;
  uint8_t master_pub[32];
};

struct PairReqPayload {
  uint8_t caps, name_len;
  char name[kMaxNameLen + 1];
  uint8_t remote_pub[32];
};

struct PairAccPayload {
  uint8_t target_mac[kMacLen];
  uint8_t blob[32];
};

struct RevokePayload {
  uint8_t target_mac[kMacLen];
};

// One decoded (or to be encoded) frame. Only the member matching `type` is meaningful.
struct Frame {
  FrameType type;
  uint16_t epoch;
  uint16_t seq;
  HelloPayload hello;
  TimerPayload timer;
  SoundPayload sound;
  CmdPayload cmd;
  CmdAckPayload cmd_ack;
  SessionPayload session;
  PairOpenPayload pair_open;
  PairReqPayload pair_req;
  PairAccPayload pair_acc;
  RevokePayload revoke;
};

enum class DecodeResult : uint8_t { Ok, Length, Magic, Version, Type, Flags, NoKey, Tag, Payload };

using RemoteKeyLookup = const uint8_t* (*)(void* ctx, const uint8_t mac[kMacLen]);  // 16-byte key or nullptr

// The keys a receiver currently holds. Pointers must stay valid during decode.
struct KeyRing {
  const uint8_t* mesh_key = nullptr;  // 16 bytes (types 1, 2, 3, 5, 6, 7)
  RemoteKeyLookup remote_lookup = nullptr;  // type 4
  void* remote_ctx = nullptr;
  bool pairing_open = false;          // type 8 (all-zero key, integrity only) accepted only while true
  const uint8_t* pair_key = nullptr;  // 32 bytes K (type 9)
};

// Validates magic, version, type, flags (hop must be 0), key, tag and payload shape; fills `out` on Ok.
DecodeResult decode(const uint8_t* buf, size_t len, const uint8_t src_mac[kMacLen], const KeyRing& keys,
                    Frame& out);

// Serializes header + payload and appends the tag computed with `key` over frame || src_mac.
// Returns the frame length, or 0 if the payload does not fit or is invalid.
size_t encode(const Frame& f, const uint8_t* key, size_t key_len, const uint8_t src_mac[kMacLen], uint8_t* out,
              size_t cap);

// tag = first 8 bytes of HMAC-SHA256(key, frame[0 .. len-8] || src_mac)
void compute_tag(const uint8_t* key, size_t key_len, const uint8_t* frame_no_tag, size_t len,
                 const uint8_t src_mac[kMacLen], uint8_t tag[kTagLen]);

}  // namespace mesh
