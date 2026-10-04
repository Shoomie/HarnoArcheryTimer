#include "mesh_arbiter.h"

#include <cstring>

#include "mesh_config.h"

namespace mesh {

namespace {
inline uint32_t age(uint32_t now, uint32_t then) { return static_cast<uint32_t>(now - then); }
}  // namespace

Arbiter::Arbiter(const ArbiterConfig& cfg, SessionStore* store) : cfg_(cfg), store_(store) {}

bool Arbiter::acceptSession(uint32_t id, uint32_t session) {
  SessionSlot* slot = nullptr;
  for (auto& s : sessions_)
    if (s.used && s.id == id) { slot = &s; break; }
  if (!slot) {  // cache miss: ask the store (NVS), then remember
    uint32_t saved = 0;
    const bool have = store_ && store_->load(id, &saved);
    for (auto& s : sessions_)
      if (!s.used) { slot = &s; break; }
    if (!slot) { slot = &sessions_[session_next_]; session_next_ = (session_next_ + 1) % kSessionCache; }
    *slot = SessionSlot{true, id, saved};
    if (!have) {  // first frame ever seen from this master: accept and record
      slot->session = session;
      if (store_) store_->save(id, session);
      return true;
    }
  }
  if (session < slot->session) return false;
  if (session > slot->session) {
    slot->session = session;
    if (store_) store_->save(id, session);
  }
  return true;
}

void Arbiter::setHostAlive(bool alive, uint32_t) { host_alive_ = alive; }
void Arbiter::setHostLights(uint8_t lights) { host_lights_ = lights & 7; }

bool Arbiter::live(const Master& m, uint32_t now) const { return m.used && age(now, m.last_ms) < kMasterLiveMs; }

// Highest rank, then lowest master_id.
bool Arbiter::better(const Master& a, const Master& b) {
  if (a.rank != b.rank) return a.rank > b.rank;
  return a.id < b.id;
}

Arbiter::Master* Arbiter::find(uint32_t id) {
  for (auto& m : masters_)
    if (m.used && m.id == id) return &m;
  return nullptr;
}

Arbiter::Master* Arbiter::insert(uint32_t id, uint32_t now) {
  Master* slot = nullptr;
  for (size_t i = 0; i < kMaxMasters; i++) {
    Master& m = masters_[i];
    if (!m.used) { slot = &m; break; }
    if (static_cast<int>(i) == followed_) continue;  // never evict the followed master
    if (!slot || age(now, m.last_ms) > age(now, slot->last_ms)) slot = &m;
  }
  if (!slot) return nullptr;  // unreachable: kMaxMasters > 1
  std::memset(slot, 0, sizeof *slot);
  slot->used = true;
  slot->id = id;
  slot->first_ms = now;
  return slot;
}

void Arbiter::follow(Master& m) {
  followed_ = static_cast<int>(&m - masters_);
  m.snd_known = false;  // the next TIMER from it only records sound_seq
}

void Arbiter::select(uint32_t now) {
  if (!radioRole()) return;
  Master* best = nullptr;  // best live candidate other than the followed one
  Master* cur = followed_ >= 0 ? &masters_[followed_] : nullptr;
  for (auto& m : masters_) {
    if (&m == cur || !live(m, now)) continue;
    if (!best || better(m, *best)) best = &m;
  }
  if (!cur) {
    if (best) follow(*best);
    return;
  }
  if (!live(*cur, now) || age(now, cur->last_ms) >= kSwitchSilenceMs) {
    if (best) follow(*best);  // followed master silent for 600 ms and another is live
    return;
  }
  Master* up = nullptr;  // live master of higher rank heard for 400 ms
  for (auto& m : masters_) {
    if (&m == cur || !live(m, now) || m.rank <= cur->rank) continue;
    if (age(now, m.first_ms) < kSwitchHigherRankMs) continue;
    if (!up || better(m, *up)) up = &m;
  }
  if (up) follow(*up);
}

void Arbiter::startSound(uint32_t now, uint8_t seq, uint8_t count, uint8_t blast, uint8_t gap, uint16_t age_ms) {
  last_sound_ = SoundStart{seq, count, blast, gap, age_ms};
  sound_starts_++;
  // Pattern timeline (blast and gap in x10 ms; the firmware falls back to its defaults for 0, so do the same here).
  const uint32_t b = (blast ? blast : 50) * 10u, g = (gap ? gap : 50) * 10u;
  pat_total_ms_ = count * b + (count - 1u) * g;
  pat_start_ms_ = now - age_ms;
  pat_active_ = true;
}

void Arbiter::stopSound() {
  sound_stops_++;  // safe direction: always counted, even if nothing runs, so the glue silences the outputs
  pat_active_ = false;
}

bool Arbiter::soundActive(uint32_t now) const {
  return pat_active_ && age(now, pat_start_ms_) < pat_total_ms_;
}

void Arbiter::onTimer(uint32_t now, const TimerPayload& t, const uint8_t* src_mac) {
  if (t.master_id == 0 || t.rank > 2) return;
  if ((cfg_.role == HostRole::M || cfg_.role == HostRole::F) && t.master_id == cfg_.own_master_id) return;
  if (!acceptSession(t.master_id, t.session)) return;  // replay of an older session: no effect at all
  Master* m = find(t.master_id);
  if (!m) {
    m = insert(t.master_id, now);
    if (!m) return;
  } else {
    if (age(now, m->last_ms) >= kMasterLiveMs) m->first_ms = now;  // was gone: presence restarts
    m->prev_ms = m->last_ms;
    m->has_prev = true;
  }
  m->last_ms = now;
  m->rank = t.rank;
  m->timer = t;
  if (src_mac) {
    std::memcpy(m->mac, src_mac, kMacLen);
    m->has_mac = true;
  }
  select(now);
  if (followed_ >= 0 && m == &masters_[followed_] && radioRole()) {
    if (!m->snd_known) {
      m->snd_known = true;  // first TIMER of a newly followed master: record only
      m->snd_seq = t.sound_seq;
    } else if (t.sound_seq != m->snd_seq) {
      m->snd_seq = t.sound_seq;
      if (t.sound_count == 0)
        stopSound();  // a stop is the safe direction: no replay guard
      else if (t.sound_age != kSoundAgeNone && t.sound_age < kSoundReplayGuardMs)
        startSound(now, t.sound_seq, t.sound_count, t.sound_blast, t.sound_gap, t.sound_age);
    }
  }
}

void Arbiter::onSound(uint32_t now, const SoundPayload& s) {
  if (!radioRole() || followed_ < 0) return;
  Master& m = masters_[followed_];
  if (m.id != s.master_id) return;
  if (!acceptSession(s.master_id, s.session)) return;
  if (m.snd_known && m.snd_seq == s.sound_seq) return;  // repeat or already seen in a TIMER
  m.snd_known = true;
  m.snd_seq = s.sound_seq;
  if (s.count > 0) startSound(now, s.sound_seq, s.count, s.blast, s.gap, 0);
  else stopSound();
}

void Arbiter::tick(uint32_t now) {
  for (size_t i = 0; i < kMaxMasters; i++) {
    Master& m = masters_[i];
    if (m.used && age(now, m.last_ms) >= kPeerExpiryMs) {
      m.used = false;
      if (static_cast<int>(i) == followed_) followed_ = -1;
    }
  }
  select(now);
}

ArbiterOutput Arbiter::output(uint32_t now) const {
  ArbiterOutput o = {};
  o.lights = kLightR;
  o.failsafe = true;

  // Conflict: two different rank-2 masters active (second most recent frame no older than 600 ms).
  int active = (cfg_.role == HostRole::M && host_alive_) ? 1 : 0;
  for (const auto& m : masters_)
    if (m.used && m.rank == 2 && m.has_prev && age(now, m.prev_ms) <= kConflictActiveMs) active++;
  o.conflict = active >= 2;

  if (followed_ >= 0) {
    o.has_follow = true;
    o.follow_id = masters_[followed_].id;
  }

  if (!radioRole()) {  // M and F are driven by the host
    if (host_alive_) {
      o.failsafe = false;
      o.lights = host_lights_;
      o.tx_rank = cfg_.role == HostRole::M ? 2 : 1;
      o.tx_master_id = cfg_.own_master_id;
    }
    return o;
  }

  if (followed_ >= 0 && live(masters_[followed_], now)) {
    const Master& f = masters_[followed_];
    o.failsafe = false;
    o.has_timer = true;
    o.timer = f.timer;
    o.emergency = (f.timer.flags & kTimerEmergency) != 0;
    o.paused = (f.timer.flags & kTimerPaused) != 0;
    o.buzzer = (f.timer.flags & kTimerBuzzer) != 0;
    o.lights = o.emergency ? kLightR : (f.timer.lights & 7);
  }
  return o;
}

}  // namespace mesh
