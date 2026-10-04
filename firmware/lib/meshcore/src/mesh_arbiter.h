// Arbiter of docs/mesh.md section 4: master table, stickiness, switch rule, conflict, fail-safe, transmit
// rank, sound handling, emergency latch. Pure logic: the clock is the `now_ms` argument of every call
// (wrap-safe uint32 milliseconds); inputs are explicit calls; outputs are read with output().
// firmware/arbiter_scenarios.txt is the executable definition.
#pragma once
#include <cstddef>
#include <cstdint>

#include "mesh_frame.h"
#include "mesh_session.h"

namespace mesh {

enum class HostRole : uint8_t { M, F, E, N };  // master, mirror (follower of a host leader), radio-fed host, node

constexpr size_t kMaxMasters = 8;

struct ArbiterConfig {
  HostRole role = HostRole::N;
  uint32_t own_master_id = 0;  // role M: own id; role F: the leader's id given by $R
};

struct SoundStart {
  uint8_t seq, count, blast, gap;  // blast and gap in x10 ms
  uint16_t age_ms;                 // how long ago the pattern began (0 for a SOUND frame)
};

struct ArbiterOutput {
  bool failsafe;             // RED, silent, fault LED blinking
  uint8_t lights;            // kLight* mask to apply
  bool emergency;            // latch of the followed master is set
  bool buzzer;               // buzzer flag of the followed master (false in fail-safe)
  bool paused;
  bool conflict;             // for HELLO and $O
  uint8_t tx_rank;           // 0 = do not transmit TIMER, else rank to send
  uint32_t tx_master_id;     // master id to put in the transmitted TIMER
  bool has_follow;
  uint32_t follow_id;        // followed master (also while it is silent, until it expires)
  bool has_timer;            // `timer` holds the latest TIMER of the followed master
  TimerPayload timer;
};

class Arbiter {
 public:
  // `store` (may be null: sessions then live in RAM only) must outlive the Arbiter; it is how the highest accepted
  // session per master_id survives a reboot.
  explicit Arbiter(const ArbiterConfig& cfg, SessionStore* store = nullptr);

  // Host input (roles M, F matter for outputs; E and N only use the radio).
  void setHostAlive(bool alive, uint32_t now_ms);
  void setHostLights(uint8_t lights);  // what the host says (kLight* mask), default RED

  // Radio input, only for frames that passed decode and the PeerTable dedupe.
  void onTimer(uint32_t now_ms, const TimerPayload& t, const uint8_t* src_mac = nullptr);
  void onSound(uint32_t now_ms, const SoundPayload& s);

  // Call regularly (a few ms) and before reading output(): applies silence-based switching and expiry.
  void tick(uint32_t now_ms);

  ArbiterOutput output(uint32_t now_ms) const;

  uint32_t soundStartCount() const { return sound_starts_; }  // cumulative patterns started
  const SoundStart& lastSound() const { return last_sound_; }
  uint32_t soundStopCount() const { return sound_stops_; }  // cumulative stops received (count == 0 with a new sound_seq)
  // True while the pattern the arbiter started runs (blast or gap), until it ends or a stop arrives.
  bool soundActive(uint32_t now_ms) const;

 private:
  struct Master {
    bool used;
    uint32_t id;
    uint8_t rank;
    uint8_t mac[kMacLen];
    bool has_mac;
    uint32_t last_ms;    // most recent TIMER
    uint32_t prev_ms;    // the one before
    bool has_prev;
    uint32_t first_ms;   // start of the current continuous presence
    bool snd_known;
    uint8_t snd_seq;
    TimerPayload timer;
  };

  bool radioRole() const { return cfg_.role == HostRole::N || cfg_.role == HostRole::E; }
  bool live(const Master& m, uint32_t now) const;
  static bool better(const Master& a, const Master& b);
  Master* find(uint32_t id);
  Master* insert(uint32_t id, uint32_t now);
  void select(uint32_t now);  // may change the followed master
  void follow(Master& m);
  // Session rule: false = drop the frame completely. Equal accepted, higher accepted and saved at once.
  bool acceptSession(uint32_t master_id, uint32_t session);
  void stopSound();
  void startSound(uint32_t now, uint8_t seq, uint8_t count, uint8_t blast, uint8_t gap, uint16_t age);

  struct SessionSlot {
    bool used;
    uint32_t id, session;
  };
  static constexpr size_t kSessionCache = 8;

  ArbiterConfig cfg_;
  SessionStore* store_;
  SessionSlot sessions_[kSessionCache] = {};
  size_t session_next_ = 0;
  bool host_alive_ = false;
  uint8_t host_lights_ = kLightR;
  Master masters_[kMaxMasters] = {};
  int followed_ = -1;  // index into masters_
  uint32_t sound_starts_ = 0;
  SoundStart last_sound_ = {};
  uint32_t sound_stops_ = 0;
  bool pat_active_ = false;
  uint32_t pat_start_ms_ = 0, pat_total_ms_ = 0;
};

}  // namespace mesh
