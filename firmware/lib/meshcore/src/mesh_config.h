// Timing constants shared by every mesh implementation (docs/mesh.md section 3). Times are milliseconds.
#pragma once
#include <cstdint>

namespace mesh {

constexpr uint32_t kTimerHeartbeatMs = 200;
constexpr uint32_t kRepeatOffsetsMs[4] = {0, 3, 15, 40};  // TIMER / SOUND / CMD first send, then repeats
constexpr uint32_t kCmdRetransmitMs = 15;
constexpr uint32_t kCmdGiveUpMs = 250;
constexpr uint32_t kHelloMs = 2000;
constexpr uint32_t kHelloJitterMs = 250;
constexpr uint32_t kSessionMs = 2000;
constexpr uint32_t kPairOpenMs = 1000;
constexpr uint32_t kPairWindowDefaultS = 60;
constexpr uint32_t kPeerExpiryMs = 6000;
constexpr uint32_t kMasterLiveMs = 1000;       // a TIMER heard less than this ago
constexpr uint32_t kSwitchSilenceMs = 600;     // followed master silent this long and another is live
constexpr uint32_t kSwitchHigherRankMs = 400;  // live master of higher rank heard this long
constexpr uint32_t kFailsafeMs = 1000;         // equals kMasterLiveMs: no live master for this long
constexpr uint32_t kSoundReplayGuardMs = 400;  // TIMER sound starts only if sound_age is below this
constexpr uint32_t kConflictActiveMs = 600;    // second most recent frame no older than this
constexpr uint32_t kSafetyRepeatStepMs = 50;   // safety-direction TIMER resends: every 50 ms ...
constexpr uint32_t kSafetyRepeatSpanMs = 500;  // ... for 500 ms

// Sends one frame at offsets 0, 3, 15, 40 ms (same frame, same seq). Explicit calls, no timers inside.
class RepeatSender {
 public:
  void begin(uint32_t now_ms) {
    start_ = now_ms;
    idx_ = 0;
    active_ = true;
  }
  // True each time a copy is due; call again until it returns false (several may be overdue).
  bool poll(uint32_t now_ms) {
    if (!active_) return false;
    if (static_cast<uint32_t>(now_ms - start_) < kRepeatOffsetsMs[idx_]) return false;
    if (++idx_ >= 4) active_ = false;
    return true;
  }
  bool active() const { return active_; }

 private:
  uint32_t start_ = 0;
  uint8_t idx_ = 0;
  bool active_ = false;
};

// After a change toward the safe state (lights to RED, emergency latch set, sound stopped) the sender resends the
// current TIMER (same seq) every 50 ms for 500 ms, on top of the RepeatSender copies. Usage: call observe() with the
// outgoing state whenever it is computed (or trigger() directly), then loop `while (poll(now)) sendTimerCopy();`.
class SafetyRepeater {
 public:
  void trigger(uint32_t now_ms) {  // restarts the 500 ms window
    start_ = now_ms;
    n_ = 0;
    active_ = true;
  }
  // Detects the safe-direction transitions against the previous observed state. The first call only records.
  // Returns true if it triggered.
  bool observe(uint32_t now_ms, uint8_t lights, bool emergency, bool sound_active) {
    bool toward_safe = false;
    if (known_) {
      const bool red_now = (lights & kLightMaskR) != 0 && (lights & kLightMaskGY) == 0;
      const bool red_before = (lights_ & kLightMaskR) != 0 && (lights_ & kLightMaskGY) == 0;
      toward_safe = (red_now && !red_before) || (emergency && !emergency_) || (!sound_active && sound_);
    }
    known_ = true;
    lights_ = lights;
    emergency_ = emergency;
    sound_ = sound_active;
    if (toward_safe) trigger(now_ms);
    return toward_safe;
  }
  // True each time a resend is due (at +50, +100 ... +500 ms); call again until false (several may be overdue).
  bool poll(uint32_t now_ms) {
    if (!active_) return false;
    const uint32_t due = (n_ + 1) * kSafetyRepeatStepMs;
    if (static_cast<uint32_t>(now_ms - start_) < due) return false;
    if (++n_ * kSafetyRepeatStepMs >= kSafetyRepeatSpanMs) active_ = false;
    return true;
  }
  bool active() const { return active_; }

 private:
  static constexpr uint8_t kLightMaskR = 4, kLightMaskGY = 3;  // kLightR, kLightG|kLightY
  uint32_t start_ = 0;
  uint32_t n_ = 0;
  uint8_t lights_ = 0;
  bool active_ = false, known_ = false, emergency_ = false, sound_ = false;
};

}  // namespace mesh
