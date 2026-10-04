// Session counter store (docs/mesh.md section 4, replay protection). The arbiter keeps, per master_id, the highest
// `session` it has accepted and drops TIMER/SOUND frames with a lower one. The device backs this interface with
// NVS (write only when the value rises: save() is called exactly then); tests use MemorySessionStore.
#pragma once
#include <cstddef>
#include <cstdint>

namespace mesh {

class SessionStore {
 public:
  virtual ~SessionStore() = default;
  // True and *session set if a value was saved for this master_id.
  virtual bool load(uint32_t master_id, uint32_t* session) = 0;
  // Persist the new highest session for this master_id (called only when it rises).
  virtual void save(uint32_t master_id, uint32_t session) = 0;
};

// RAM-only store for tests and host builds. Survives an Arbiter being destroyed and recreated (a "reboot").
class MemorySessionStore : public SessionStore {
 public:
  bool load(uint32_t master_id, uint32_t* session) override {
    for (size_t i = 0; i < n_; i++)
      if (id_[i] == master_id) { *session = val_[i]; return true; }
    return false;
  }
  void save(uint32_t master_id, uint32_t session) override {
    writes_++;
    for (size_t i = 0; i < n_; i++)
      if (id_[i] == master_id) { val_[i] = session; return; }
    if (n_ < kCap) { id_[n_] = master_id; val_[n_++] = session; }
    else { id_[next_] = master_id; val_[next_] = session; next_ = (next_ + 1) % kCap; }
  }
  uint32_t writes() const { return writes_; }  // number of save() calls (tests: writes only when it rises)

 private:
  static constexpr size_t kCap = 32;
  uint32_t id_[kCap] = {};
  uint32_t val_[kCap] = {};
  size_t n_ = 0, next_ = 0;
  uint32_t writes_ = 0;
};

}  // namespace mesh
