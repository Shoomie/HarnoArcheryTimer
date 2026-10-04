// Mesh v2 node: see radio.h and docs/mesh.md. All frames are ESP-NOW broadcasts on one channel, signed with the
// keys of docs/mesh.md section 1; identity is the sender MAC from the receive callback.
#include "radio.h"

#include <WiFi.h>
#include <esp_now.h>
#include <esp_random.h>
#include <esp_wifi.h>

#include "config.h"
#include "hostcore.h"
#include "mesh_cmd.h"
#include "mesh_config.h"
#include "mesh_frame.h"
#include "mesh_pair.h"
#include "mesh_peers.h"
#include "meshglue.h"
#include "version.h"
#if __has_include(<esp_mac.h>)
#include <esp_mac.h>
#endif
#include <esp_system.h>

#ifndef ESPNOW_CHANNEL
#define ESPNOW_CHANNEL 1  // default channel; a stored "chan" setting (1..13) overrides it
#endif

using namespace mesh;

#ifdef RADIO_DEBUG
#define DBG(...) Serial.printf(__VA_ARGS__)
#else
#define DBG(...) ((void)0)
#endif
namespace {

const uint8_t BCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
const uint8_t ZERO_KEY[16] = {0};
const uint32_t PAIR_REQ_PERIOD_MS = 1000;
const uint32_t PAIR_OPEN_HEARD_MS = 3000;   // a PAIR_OPEN must have been heard this recently to send PAIR_REQ
const uint32_t PAIR_FORCED_TIMEOUT_MS = 120000;
const uint32_t PAIR_FWD_REPEAT_MS = 10000;  // the same remote is shown to the operator again after this long
const uint32_t STATE_PERIOD_MS = 1000;      // $P,state while a window is open

HostFrameFn toHost = nullptr;
void hostBody(const char *b) {
  if (toHost) toHost(b);
}

// --- identity and configuration ---------------------------------------------------------------------------------
uint8_t ownMac[6] = {0};
uint16_t epoch = 1;
uint16_t txSeq = 0;
bool enabled = true;  // $C radio
uint8_t chan = ESPNOW_CHANNEL;
char nodeName[13] = "node";
uint8_t capsByte = kCapR;
uint8_t meshKey[16];
bool hasMesh = false;
uint8_t remoteKey[16];
bool hasRemote = false;
bool radioOn = false;

// --- meshcore objects -------------------------------------------------------------------------------------------
NvsSessionStore sessionStore;
CmdGate gate;
PeerTable peers;
ArbiterConfig acfg;
Arbiter arb(acfg, &sessionStore);
ArbiterOutput outp = {};
PortableX25519 x25519impl;
CmdSender sender;
SafetyRepeater safeRep;

HostRole role = HostRole::N;
char roleCh = 'N';
bool feedOn = false;
uint32_t ownId = 0, ownSession = 0;
bool hostAliveNow = false;
uint8_t hostLights = kLightR;
uint32_t soundSeen = 0, stopSeen = 0;

// host state that goes into TIMER / SESSION
HostTimer ht = {};
uint32_t htRxMs = 0;
HostSession hs = {};
bool haveHs = false, hsDirty = false;
uint32_t lastSessMs = 0;
bool hornRaw = false;
uint8_t sndSeq = 0, sndCount = 0, sndBlast = 50, sndGap = 50;
uint32_t sndStartMs = 0, sndUntil = 0;
bool sndEver = false;

// --- transmit ----------------------------------------------------------------------------------------------------
struct Burst {
  uint8_t buf[kMaxFrame];
  uint8_t len = 0;
  RepeatSender rep;
};
Burst tmrB, sndB, sessB, accB, reqB;
Burst ackB[4];
uint8_t ackNext = 0;
Frame txf;  // scratch for building frames
Frame rxf;  // scratch for decoding

uint32_t lastTimerNewMs = 0;
bool haveLastTimer = false;
TimerPayload lastTimer = {};
uint32_t nextHelloMs = 0;
uint32_t accRetryAt[2] = {0, 0};
uint8_t accRetryLeft = 0;

void sendRaw(const uint8_t *buf, size_t len) {
  if (radioOn && len) esp_now_send(BCAST, buf, len);
}

void prep(FrameType t) {
  memset(&txf, 0, sizeof txf);
  txf.type = t;
  txf.epoch = epoch;
  txf.seq = ++txSeq;
}

// Encodes `txf` into the burst and starts the 0/3/15/40 ms schedule. Returns false when the frame does not encode.
bool burstEncodeStart(Burst &b, const uint8_t *key, size_t klen, uint32_t now) {
  const size_t n = encode(txf, key, klen, ownMac, b.buf, sizeof b.buf);
  if (!n) return false;
  b.len = (uint8_t)n;
  b.rep.begin(now);
  while (b.rep.poll(now)) sendRaw(b.buf, b.len);
  return true;
}

void burstPoll(Burst &b, uint32_t now) {
  while (b.rep.poll(now)) sendRaw(b.buf, b.len);
}

// --- roster / rssi -----------------------------------------------------------------------------------------------
struct RssiEntry {
  bool used;
  uint8_t mac[6];
  uint8_t mag;
};
RssiEntry rssiTab[kMaxPeers];

void noteRssi(const uint8_t *mac, int rssi) {
  RssiEntry *slot = nullptr;
  for (auto &e : rssiTab) {
    if (e.used && memcmp(e.mac, mac, 6) == 0) { slot = &e; break; }
    if (!e.used && !slot) slot = &e;
  }
  if (!slot) slot = &rssiTab[mac[5] % kMaxPeers];
  slot->used = true;
  memcpy(slot->mac, mac, 6);
  int m = rssi < 0 ? -rssi : rssi;
  slot->mag = (uint8_t)(m > 127 ? 127 : m);
}

uint8_t rssiOf(const uint8_t *mac) {
  for (auto &e : rssiTab)
    if (e.used && memcmp(e.mac, mac, 6) == 0) return e.mag;
  return 0;
}

struct Shadow {
  bool used, seen;
  uint8_t mac[6];
  char kind;
  uint8_t caps, rssi;
  uint8_t fw[3];
  char name[13];
};
Shadow shadow[kMaxPeers];
uint32_t nextRosterMs = 0;

void capsString(uint8_t caps, char *out) {  // "LSBKR" order, as in $D and $P,req
  size_t n = 0;
  if (caps & kCapL) out[n++] = 'L';
  if (caps & kCapS) out[n++] = 'S';
  if (caps & kCapB) out[n++] = 'B';
  if (caps & kCapK) out[n++] = 'K';
  if (caps & kCapR) out[n++] = 'R';
  out[n] = 0;
}

char kindOf(const HelloPayload &h) {
  switch (h.role) {
    case 1: return 'F';
    case 2: return 'M';
    case 3: return 'E';
    default: return ((h.caps & kCapK) && !(h.caps & (kCapL | kCapS))) ? 'R' : 'N';  // a button-only node is a remote
  }
}

void sendRosterEntry(const Shadow &s) {
  char caps[8], body[hostcore::kMaxLongFrame];
  capsString(s.caps, caps);
  if (hostcore::fmtRoster(body, sizeof body, s.mac, s.kind, caps, s.rssi, s.fw, s.name)) hostBody(body);
}

void rosterPoll(uint32_t now) {
  if ((int32_t)(now - nextRosterMs) < 0) return;
  nextRosterMs = now + 250;
  peers.expire(now);
  for (auto &s : shadow) s.seen = false;
  for (size_t i = 0; i < PeerTable::capacity(); i++) {
    const PeerInfo &p = peers.slot(i);
    if (!p.used || !p.has_hello) continue;
    Shadow *s = nullptr, *freeS = nullptr;
    for (auto &c : shadow) {
      if (c.used && memcmp(c.mac, p.mac, 6) == 0) { s = &c; break; }
      if (!c.used && !freeS) freeS = &c;
    }
    Shadow cur = {};
    cur.used = cur.seen = true;
    memcpy(cur.mac, p.mac, 6);
    cur.kind = kindOf(p.hello);
    cur.caps = p.hello.caps & 0x1F;
    cur.rssi = rssiOf(p.mac);
    memcpy(cur.fw, p.hello.fw, 3);
    memcpy(cur.name, p.hello.name, sizeof cur.name);
    cur.name[12] = 0;
    if (!s) {
      s = freeS;
      if (!s) continue;
    } else {
      const int drssi = (int)cur.rssi - (int)s->rssi;
      const bool same = s->kind == cur.kind && s->caps == cur.caps && memcmp(s->fw, cur.fw, 3) == 0 &&
                        strcmp(s->name, cur.name) == 0 && drssi > -10 && drssi < 10;
      if (same) { s->seen = true; continue; }
    }
    *s = cur;
    sendRosterEntry(*s);
  }
  for (auto &s : shadow) {
    if (!s.used || s.seen) continue;
    char body[40];
    if (hostcore::fmtRosterGone(body, sizeof body, s.mac)) hostBody(body);
    s.used = false;
  }
}

// --- pairing state -----------------------------------------------------------------------------------------------
// master side
bool winOpen = false;
uint32_t winEnd = 0, nextPairOpenMs = 0, nextStateMs = 0;
uint8_t mpriv[32], mpub[32];
struct PendingReq {
  bool used;
  uint8_t mac[6];
  uint8_t pub[32];
  uint32_t lastFwdMs;
};
PendingReq pend[4];
// Remotes the operator removed: the master keeps telling them (by MAC) to forget their keys, so they pair again.
struct Revoked {
  bool used;
  uint8_t mac[6];
  uint32_t until, nextMs;
};
Revoked revoked[4];
uint8_t revokedNext = 0;
const uint32_t REVOKE_FOR_MS = 600000;  // ten minutes: a box that was off for a moment still hears it
const uint32_t REVOKE_EVERY_MS = 2000;
// remote side
bool pairMode = false, pairForced = false, pairPressed = false;
uint32_t pairUntil = 0, nextReqMs = 0;
struct OpenSeen {
  bool valid;
  uint8_t mac[6];
  uint8_t pub[32];
  uint32_t heardMs;
} openSeen;
struct PairSlot {
  bool used;
  uint8_t k[32];
};
PairSlot pairSlots[4];
uint8_t pairSlotNext = 0;

void sendPairState(bool open, uint32_t secondsLeft) {
  char b[24];
  if (hostcore::fmtPairState(b, sizeof b, open, secondsLeft)) hostBody(b);
}

void windowClose() {
  if (!winOpen) return;
  winOpen = false;
  memset(mpriv, 0, sizeof mpriv);
  memset(pend, 0, sizeof pend);
  sendPairState(false, 0);
}

uint32_t windowSecondsLeft(uint32_t now) {
  if (!winOpen) return 0;
  const int32_t left = (int32_t)(winEnd - now);
  return left <= 0 ? 0 : (uint32_t)((left + 999) / 1000);
}

// --- keyring -----------------------------------------------------------------------------------------------------
KeyRing keyring() {
  KeyRing kr;
  kr.mesh_key = hasMesh ? meshKey : nullptr;
  kr.remote_lookup = CmdGate::lookupKey;
  kr.remote_ctx = &gate;
  kr.pairing_open = winOpen;
  kr.pair_key = nullptr;
  return kr;
}

// --- arbiter plumbing --------------------------------------------------------------------------------------------
void rebuildArbiter() {
  acfg.role = role;
  acfg.own_master_id = ownId;
  arb = Arbiter(acfg, &sessionStore);
  soundSeen = 0;
  stopSeen = 0;
  haveLastTimer = false;
}

bool txActive() { return radioOn && hasMesh; }

bool sameTimer(const TimerPayload &a, const TimerPayload &b) {
  return a.master_id == b.master_id && a.session == b.session && a.remaining_ms == b.remaining_ms &&
         a.lights == b.lights && a.flags == b.flags && a.phase == b.phase && a.sound_seq == b.sound_seq &&
         a.sound_age == b.sound_age && a.end_no == b.end_no;
}

// Equal in everything that is not a pure function of time (remaining_ms and sound_age keep changing).
bool sameTimerSig(const TimerPayload &a, const TimerPayload &b) {
  return a.master_id == b.master_id && a.session == b.session && a.rank == b.rank && a.lights == b.lights &&
         a.flags == b.flags && a.mode == b.mode && a.phase == b.phase && a.end_no == b.end_no &&
         a.total_ends == b.total_ends && a.group == b.group && a.round == b.round &&
         a.total_rounds == b.total_rounds && a.session_rev == b.session_rev && a.sound_seq == b.sound_seq &&
         a.sound_count == b.sound_count && a.sound_blast == b.sound_blast && a.sound_gap == b.sound_gap;
}

// --- TIMER -------------------------------------------------------------------------------------------------------
void buildTimer(uint32_t now, const ArbiterOutput &o, TimerPayload &t) {
  memset(&t, 0, sizeof t);
  t.master_id = o.tx_master_id;
  t.session = ownSession;
  t.rank = o.tx_rank;
  t.lights = hostLights & 7;
  t.flags = (uint8_t)((ht.flags & (kTimerPaused | kTimerEmergency)) | (hornRaw ? kTimerBuzzer : 0));
  t.mode = ht.mode;
  t.phase = ht.phase;
  // remaining_ms is valid at receipt of $U: add the time since then while the clock runs. 0 unless running.
  if (ht.mode == 1) {
    uint32_t rem = ht.remainingMs;
    const bool frozen = (ht.flags & (kTimerPaused | kTimerEmergency)) != 0;
    if (!frozen) {
      const uint32_t el = now - htRxMs;
      rem = el >= rem ? 0 : rem - el;
    }
    t.remaining_ms = rem;
  }
  t.end_no = ht.endNo;
  t.total_ends = ht.totalEnds;
  t.group = ht.group;
  t.round = ht.round;
  t.total_rounds = ht.totalRounds;
  t.session_rev = ht.rev;
  t.sound_seq = sndSeq;
  t.sound_count = sndCount;
  t.sound_blast = sndBlast;
  t.sound_gap = sndGap;
  if (sndEver) {
    const uint32_t age = now - sndStartMs;
    t.sound_age = age > 0xFFFE ? 0xFFFE : (uint16_t)age;
  } else {
    t.sound_age = kSoundAgeNone;
  }
}

void timerTx(uint32_t now) {
  if (!txActive() || outp.tx_rank == 0 || (role != HostRole::M && role != HostRole::F)) {
    haveLastTimer = false;
    return;
  }
  TimerPayload t;
  buildTimer(now, outp, t);
  const bool soundActive = hornRaw || (int32_t)(sndUntil - now) > 0;
  safeRep.observe(now, t.lights, (t.flags & kTimerEmergency) != 0, soundActive);
  if (!haveLastTimer || !sameTimerSig(t, lastTimer) || now - lastTimerNewMs >= kTimerHeartbeatMs) {
    prep(FrameType::Timer);
    txf.timer = t;
    if (burstEncodeStart(tmrB, meshKey, 16, now)) {
      lastTimer = t;
      haveLastTimer = true;
      lastTimerNewMs = now;
    }
  }
  burstPoll(tmrB, now);
  while (safeRep.poll(now)) sendRaw(tmrB.buf, tmrB.len);  // same frame, same seq
}

// --- SESSION, HELLO, PAIR_OPEN -----------------------------------------------------------------------------------
void sessionTx(uint32_t now) {
  if (!txActive() || outp.tx_rank == 0 || !haveHs) return;
  if (!hsDirty && now - lastSessMs < kSessionMs) {
    burstPoll(sessB, now);
    return;
  }
  prep(FrameType::Session);
  SessionPayload &s = txf.session;
  s.master_id = outp.tx_master_id;
  s.rev = hs.rev;
  s.flags = hs.flags & 3;
  s.total_ends = hs.totalEnds;
  s.practice_ends = hs.practiceEnds;
  s.prep_ms = hs.prepMs;
  s.shoot_ms = hs.shootMs;
  s.warn_ms = hs.warnMs;
  s.auto_delay_ms = hs.delayMs;
  s.seq_len = (uint8_t)strnlen(hs.seqId, 16);
  memcpy(s.sequence_id, hs.seqId, s.seq_len);
  s.groups_n = hs.groupsN > kMaxGroups ? (uint8_t)kMaxGroups : hs.groupsN;
  for (uint8_t g = 0; g < s.groups_n; g++) {
    s.group_len[g] = (uint8_t)strnlen(hs.groups[g], 8);
    memcpy(s.groups[g], hs.groups[g], s.group_len[g]);
  }
  if (burstEncodeStart(sessB, meshKey, 16, now)) {
    hsDirty = false;
    lastSessMs = now;
  }
}

uint8_t helloRoleCode() {
  switch (role) {
    case HostRole::F: return 1;
    case HostRole::M: return 2;
    case HostRole::E: return 3;
    default: return 0;
  }
}

void helloTx(uint32_t now) {
  if (!txActive()) return;
  if ((int32_t)(now - nextHelloMs) < 0) return;
  nextHelloMs = now + kHelloMs + (esp_random() % (kHelloJitterMs + 1));
  prep(FrameType::Hello);
  HelloPayload &h = txf.hello;
  h.caps = capsByte;
  h.role = helloRoleCode();
  h.rank = role == HostRole::M ? 2 : role == HostRole::F ? 1 : 0;
  h.conflict = outp.conflict ? 1 : 0;
  h.master_id = (role == HostRole::M || role == HostRole::F) ? ownId : (outp.has_follow ? outp.follow_id : 0);
  h.fw[0] = FW_MAJOR;
  h.fw[1] = FW_MINOR;
  h.fw[2] = FW_PATCH;
  h.name_len = (uint8_t)strnlen(nodeName, kMaxNameLen);
  memcpy(h.name, nodeName, h.name_len);
  uint8_t buf[kMaxFrame];
  const size_t n = encode(txf, meshKey, 16, ownMac, buf, sizeof buf);
  sendRaw(buf, n);
}

void pairWindowTx(uint32_t now) {
  if (!winOpen) return;
  if ((int32_t)(now - winEnd) >= 0) {
    windowClose();
    return;
  }
  if ((int32_t)(now - nextStateMs) >= 0) {
    nextStateMs = now + STATE_PERIOD_MS;
    sendPairState(true, windowSecondsLeft(now));
  }
  if ((int32_t)(now - nextPairOpenMs) >= 0 && hasMesh) {
    nextPairOpenMs = now + kPairOpenMs;
    prep(FrameType::PairOpen);
    txf.pair_open.master_id = ownId;
    txf.pair_open.seconds_left = (uint8_t)windowSecondsLeft(now);
    memcpy(txf.pair_open.master_pub, mpub, 32);
    uint8_t buf[kMaxFrame];
    const size_t n = encode(txf, meshKey, 16, ownMac, buf, sizeof buf);
    sendRaw(buf, n);
  }
}

// --- remote side: PAIR_REQ, CMD ----------------------------------------------------------------------------------
void pairReqTx(uint32_t now) {
  if (!pairMode || !openSeen.valid) return;  // no button needed: the operator's accept is the control
  if (now - openSeen.heardMs > PAIR_OPEN_HEARD_MS) return;
  if ((int32_t)(now - nextReqMs) < 0) return;
  nextReqMs = now + PAIR_REQ_PERIOD_MS;
  DBG("DBG sending PAIR_REQ\n");
  // A fresh key pair for every request; the last four are kept because the operator's accept takes seconds.
  uint8_t priv[32], pub[32], shared[32];
  meshRandom(priv, 32);
  x25519impl.publicKey(pub, priv);
  x25519impl.sharedSecret(shared, priv, openSeen.pub);
  if (x25519_is_zero(shared)) return;
  PairSlot &slot = pairSlots[pairSlotNext];
  pairSlotNext = (pairSlotNext + 1) & 3;
  slot.used = true;
  derive_pair_key(shared, ownMac, openSeen.mac, slot.k);
  memset(priv, 0, sizeof priv);
  memset(shared, 0, sizeof shared);
  prep(FrameType::PairReq);
  txf.pair_req.caps = capsByte;
  txf.pair_req.name_len = (uint8_t)strnlen(nodeName, kMaxNameLen);
  memcpy(txf.pair_req.name, nodeName, txf.pair_req.name_len);
  memcpy(txf.pair_req.remote_pub, pub, 32);
  burstEncodeStart(reqB, ZERO_KEY, 16, now);
}

void revokeTx(uint32_t now) {
  if (role != HostRole::M || !hasMesh) return;
  for (auto &r : revoked) {
    if (!r.used) continue;
    if ((int32_t)(now - r.until) >= 0) { r.used = false; continue; }
    if ((int32_t)(now - r.nextMs) < 0) continue;
    r.nextMs = now + REVOKE_EVERY_MS;
    prep(FrameType::Revoke);
    memcpy(txf.revoke.target_mac, r.mac, 6);
    uint8_t buf[kMaxFrame];
    const size_t n = encode(txf, meshKey, 16, ownMac, buf, sizeof buf);
    sendRaw(buf, n);
  }
}

void cmdPump(uint32_t now) {
  if (!sender.due(now) || !hasRemote) return;
  prep(FrameType::Cmd);  // a NEW seq for every retransmit, the same counter
  txf.cmd.counter = sender.counter();
  txf.cmd.action = sender.action();
  uint8_t buf[kMaxFrame];
  const size_t n = encode(txf, remoteKey, 16, ownMac, buf, sizeof buf);
  sendRaw(buf, n);
}

// --- receive -----------------------------------------------------------------------------------------------------
struct RxItem {
  uint8_t mac[6];
  int8_t rssi;
  uint8_t len;
  uint8_t data[kMaxFrame];
};
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
RxItem ring[12];
volatile uint8_t ringHead = 0, ringTail = 0;

void ringPush(const uint8_t *mac, int rssi, const uint8_t *data, int len) {
  if (!mac || len < (int)(kHeaderLen + kTagLen) || len > (int)kMaxFrame) return;
  portENTER_CRITICAL(&mux);
  const uint8_t next = (uint8_t)((ringHead + 1) % 12);
  if (next != ringTail) {  // drop when full
    memcpy(ring[ringHead].mac, mac, 6);
    ring[ringHead].rssi = (int8_t)rssi;
    ring[ringHead].len = (uint8_t)len;
    memcpy(ring[ringHead].data, data, (size_t)len);
    ringHead = next;
  }
  portEXIT_CRITICAL(&mux);
}

#if ESP_ARDUINO_VERSION_MAJOR >= 3
void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  ringPush(info ? info->src_addr : nullptr, (info && info->rx_ctrl) ? info->rx_ctrl->rssi : 0, data, len);
}
#else
void onRecv(const uint8_t *mac, const uint8_t *data, int len) { ringPush(mac, 0, data, len); }  // no rssi on core 2.x
#endif

void forwardFeed(char letter, const uint8_t *payload, size_t n) {
  char body[hostcore::kMaxLongFrame];
  if (n && hostcore::fmtFeed(body, sizeof body, letter, payload, n)) hostBody(body);
}

void sendCmdAck(const uint8_t target[6], uint32_t counter, uint8_t result, uint32_t now) {
  prep(FrameType::CmdAck);
  memcpy(txf.cmd_ack.target_mac, target, 6);
  txf.cmd_ack.counter = counter;
  txf.cmd_ack.result = result;
  Burst &b = ackB[ackNext];
  ackNext = (uint8_t)((ackNext + 1) & 3);
  burstEncodeStart(b, meshKey, 16, now);
}

void onPairReq(const uint8_t *mac, const PairReqPayload &q, uint32_t now) {
  if (!winOpen) return;
  PendingReq *slot = nullptr;
  for (auto &p : pend)
    if (p.used && memcmp(p.mac, mac, 6) == 0) { slot = &p; break; }
  bool show = false;
  if (!slot) {
    for (auto &p : pend)
      if (!p.used) { slot = &p; break; }
    if (!slot) return;  // four requests are already waiting for the operator
    slot->used = true;
    memcpy(slot->mac, mac, 6);
    show = true;
  } else if (now - slot->lastFwdMs >= PAIR_FWD_REPEAT_MS) {
    show = true;
  }
  memcpy(slot->pub, q.remote_pub, 32);  // always the latest: it matches what the remote keeps for its next ACC
  if (!show) return;
  slot->lastFwdMs = now;
  char caps[8], body[64];
  capsString(q.caps, caps);
  if (hostcore::fmtPairRequest(body, sizeof body, mac, q.name, caps)) hostBody(body);
}

void onCmdFrame(const uint8_t *mac, const CmdPayload &c, uint32_t now) {
  const CmdDecision d = gate.onCmd(mac, c.counter, c.action, role == HostRole::M && hostAliveNow);
  const RemoteEntry *r = gate.find(mac);
  if (r) keysSaveRemote(*r);  // persists the counter (no-op when unchanged)
  if (d.kind == CmdDecision::Forward) {
    char body[64];
    if (hostcore::fmtPairCommand(body, sizeof body, mac, c.action, c.counter)) hostBody(body);
  } else if (d.kind == CmdDecision::SendAck) {
    sendCmdAck(mac, c.counter, d.result, now);
  }
}

// A remote that is waiting for PAIR_ACC tries the keys of its last four requests.
bool tryPairAcc(const uint8_t *buf, size_t len, const uint8_t *mac, uint32_t now) {
  if (len != kHeaderLen + 6 + 32 + kTagLen || buf[2] != (uint8_t)FrameType::PairAcc) return false;
  for (auto &slot : pairSlots) {
    if (!slot.used) continue;
    KeyRing kr;
    kr.pair_key = slot.k;
    if (decode(buf, len, mac, kr, rxf) != DecodeResult::Ok) continue;
    if (memcmp(rxf.pair_acc.target_mac, ownMac, 6) != 0) return true;  // for another remote
    uint8_t mk[16], rk[16];
    open_blob(slot.k, rxf.pair_acc.blob, mk, rk);
    keysStoreMesh(mk);
    keysStoreRemote(rk);
    memcpy(meshKey, mk, 16);
    memcpy(remoteKey, rk, 16);
    hasMesh = hasRemote = true;
    enabled = true;  // a box that booted keyless had the radio off by default: being paired means it is wanted
    configPutU8("radio", 1);
    configPutU8("remote", 1);
    memset(pairSlots, 0, sizeof pairSlots);
    memset(mk, 0, sizeof mk);
    memset(rk, 0, sizeof rk);
    pairMode = pairForced = pairPressed = false;
    openSeen.valid = false;
    sender = CmdSender(keysCmdCounterStart());
    nextHelloMs = now;  // announce ourselves with the new mesh key
    return true;
  }
  return true;  // was a PAIR_ACC but not ours or not decodable: consumed either way
}

// While pairing, a PAIR_OPEN is taken for its public key without checking its tag: a remote without the mesh key cannot
// verify it (docs/mesh.md section 5: the key agreement is not authenticated against an active attacker; the operator's
// accept and the physical press are the countermeasures). The PAIR_ACC that follows IS authenticated, by K.
bool captureOpen(const uint8_t *buf, size_t len, const uint8_t *mac, uint32_t now) {
  if (len != kHeaderLen + 4 + 1 + 32 + kTagLen || buf[0] != kMagic || buf[1] != kVersion ||
      buf[2] != (uint8_t)FrameType::PairOpen || buf[3] != 0)
    return false;
  openSeen.valid = true;
  memcpy(openSeen.mac, mac, 6);
  memcpy(openSeen.pub, buf + kHeaderLen + 5, 32);
  openSeen.heardMs = now;
  return true;
}

void handleRx(const RxItem &it, uint32_t now) {
  const uint8_t *mac = it.mac;
  if (memcmp(mac, ownMac, 6) == 0) return;
  DBG("DBG rx type=%u len=%u pairMode=%d from %02X%02X\n", it.data[2], it.len, (int)pairMode, mac[4], mac[5]);
  if (pairMode) {
    if (captureOpen(it.data, it.len, mac, now)) return;
    if (tryPairAcc(it.data, it.len, mac, now)) return;
  }
  const KeyRing kr = keyring();
  if (decode(it.data, it.len, mac, kr, rxf) != DecodeResult::Ok) return;  // wrong key, tag or shape: drop silently
  if (!peers.accept(mac, rxf.epoch, rxf.seq, now)) return;               // a repeat
  noteRssi(mac, it.rssi);
  const uint8_t *payload = it.data + kHeaderLen;
  const size_t plen = it.len - kHeaderLen - kTagLen;
  switch (rxf.type) {
    case FrameType::Hello:
      peers.updateHello(mac, rxf.hello);
      break;
    case FrameType::Timer:
      arb.onTimer(now, rxf.timer, mac);
      if (feedOn && role == HostRole::E) {
        const ArbiterOutput o = arb.output(now);
        if (o.has_follow && o.follow_id == rxf.timer.master_id && o.has_timer && sameTimer(o.timer, rxf.timer))
          forwardFeed('F', payload, plen);
      }
      break;
    case FrameType::Sound:
      arb.onSound(now, rxf.sound);
      if (feedOn && role == HostRole::E) {
        const ArbiterOutput o = arb.output(now);
        if (o.has_follow && o.follow_id == rxf.sound.master_id && (!o.has_timer || rxf.sound.session >= o.timer.session))
          forwardFeed('W', payload, plen);
      }
      break;
    case FrameType::Session:
      if (feedOn && role == HostRole::E) {
        const ArbiterOutput o = arb.output(now);
        if (o.has_follow && o.follow_id == rxf.session.master_id) forwardFeed('Y', payload, plen);
      }
      break;
    case FrameType::Cmd:
      if (role == HostRole::M) onCmdFrame(mac, rxf.cmd, now);
      break;
    case FrameType::CmdAck:
      if (memcmp(rxf.cmd_ack.target_mac, ownMac, 6) == 0) sender.onAck(rxf.cmd_ack.counter, rxf.cmd_ack.result);
      break;
    case FrameType::PairReq:
      onPairReq(mac, rxf.pair_req, now);
      break;
    case FrameType::Revoke:
      // Only a paired remote obeys, and only for its own MAC: it forgets both keys and asks to be paired again.
      if (hasRemote && memcmp(rxf.revoke.target_mac, ownMac, 6) == 0) radioForgetKeys();
      break;
    default:
      break;  // PAIR_OPEN of another master, PAIR_ACC not for us
  }
}

void drainRx(uint32_t now) {
  for (;;) {
    RxItem it;
    bool got = false;
    portENTER_CRITICAL(&mux);
    if (ringTail != ringHead) {
      it = ring[ringTail];
      ringTail = (uint8_t)((ringTail + 1) % 12);
      got = true;
    }
    portEXIT_CRITICAL(&mux);
    if (!got) break;
    handleRx(it, now);
  }
}

// --- radio on / off ----------------------------------------------------------------------------------------------
uint8_t channelNow() {
  const uint8_t c = configGetU8("chan", ESPNOW_CHANNEL);
  return (c >= 1 && c <= 13) ? c : (uint8_t)ESPNOW_CHANNEL;
}

void radioStart() {
  if (radioOn) return;
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_ps(WIFI_PS_NONE);  // modem sleep adds milliseconds of receive latency
#ifdef RADIO_TX_POWER_QDBM
  WiFi.setTxPower((wifi_power_t)RADIO_TX_POWER_QDBM);  // quarter dBm; Super Mini boards need less than full power
#endif
  esp_wifi_set_channel(chan, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) return;
  esp_now_register_recv_cb(onRecv);
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BCAST, 6);
  peer.channel = chan;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
  radioOn = true;
  nextHelloMs = millis() + 100;
}

void radioStop() {
  if (!radioOn) return;
  esp_now_deinit();
  WiFi.mode(WIFI_OFF);
  radioOn = false;
  portENTER_CRITICAL(&mux);
  ringHead = ringTail = 0;
  portEXIT_CRITICAL(&mux);
  peers = PeerTable();
  memset(shadow, 0, sizeof shadow);
  tmrB.rep = sndB.rep = sessB.rep = accB.rep = reqB.rep = RepeatSender();
  for (auto &b : ackB) b.rep = RepeatSender();
  haveLastTimer = false;
  safeRep = SafetyRepeater();
  windowClose();
}

}  // namespace

// ============================================================================================================
// public API
// ============================================================================================================

void radioBegin(HostFrameFn f) {
  toHost = f;
  esp_read_mac(ownMac, ESP_MAC_WIFI_STA);
  do {
    epoch = (uint16_t)(esp_random() & 0xFFFF);
  } while (epoch == 0);
  char n[13];
  if (configGetStr("name", n, sizeof n) && n[0]) {
    strncpy(nodeName, n, 12);
    nodeName[12] = 0;
  } else {
    snprintf(nodeName, sizeof nodeName, "node-%02X%02X", ownMac[4], ownMac[5]);
  }
  chan = channelNow();
  hasMesh = keysLoadMesh(meshKey);
  hasRemote = keysLoadRemote(remoteKey);
  keysLoadRemotes(gate);
  sender = CmdSender(keysCmdCounterStart());
  rebuildArbiter();
}

void radioTick(uint32_t now, bool hostAlive) {
  hostAliveNow = hostAlive;
  // pairing timeouts
  if (pairMode && pairForced && (int32_t)(now - pairUntil) >= 0 && hasMesh) pairMode = false;
  // radio on/off follows configuration, keys and pairing
  const bool want = (enabled && hasMesh) || pairMode;  // pairing needs the radio even without a key
  if (want && !radioOn) radioStart();
  else if (!want && radioOn) radioStop();

  if (radioOn) drainRx(now);
  arb.setHostAlive(hostAlive, now);
  arb.setHostLights(hostLights);
  arb.tick(now);
  outp = arb.output(now);
  // Emergency closes the pairing window at once.
  if (winOpen && (ht.flags & kTimerEmergency)) windowClose();
  if (!radioOn) return;

  timerTx(now);
  burstPoll(sndB, now);
  sessionTx(now);
  burstPoll(accB, now);
  for (auto &b : ackB) burstPoll(b, now);
  burstPoll(reqB, now);
  if (accRetryLeft && (int32_t)(now - accRetryAt[2 - accRetryLeft]) >= 0 && accB.len) {
    accRetryLeft--;
    sendRaw(accB.buf, accB.len);
  }
  helloTx(now);
  pairWindowTx(now);
  revokeTx(now);
  pairReqTx(now);
  cmdPump(now);
  rosterPoll(now);
}

const ArbiterOutput &radioOutput() { return outp; }

bool radioTakeSoundStop() {
  if (arb.soundStopCount() == stopSeen) return false;
  stopSeen = arb.soundStopCount();
  return true;
}

bool radioTakeSoundStart(SoundStart &s) {
  if (arb.soundStartCount() == soundSeen) return false;
  soundSeen = arb.soundStartCount();
  s = arb.lastSound();
  return true;
}

bool radioSetRole(char r, uint32_t masterId, uint32_t session, bool feed) {
  HostRole nr;
  switch (r) {
    case 'M': nr = HostRole::M; break;
    case 'F': nr = HostRole::F; break;
    case 'E': nr = HostRole::E; break;
    case 'N': nr = HostRole::N; break;
    default: return false;
  }
  const uint32_t id = (nr == HostRole::M || nr == HostRole::F) ? masterId : 0;
  const uint32_t ses = (nr == HostRole::M || nr == HostRole::F) ? session : 0;
  const bool feedNew = (nr == HostRole::E) && feed;
  if (nr == role && id == ownId && ses == ownSession && feedNew == feedOn) return true;  // idempotent
  role = nr;
  roleCh = r;
  ownId = id;
  ownSession = ses;
  feedOn = feedNew;
  rebuildArbiter();
  return true;
}

char radioRole() { return roleCh; }
bool radioHostDrives() { return role == HostRole::M || role == HostRole::F; }

void radioLegacyIdentity(uint32_t *masterId, uint32_t *session, bool bump) {
  uint32_t id = ((uint32_t)ownMac[2] << 24 | (uint32_t)ownMac[3] << 16 | (uint32_t)ownMac[4] << 8 | ownMac[5]) ^
                0xA5C3E100u;
  if (id == 0) id = 1;
  uint32_t s = configGetU32("lcnt", 0);
  if (bump || s == 0) {
    s = s == 0xFFFFFFFFu ? 1 : s + 1;
    configPutU32("lcnt", s);
  }
  *masterId = id;
  *session = s;
}

void radioHostLights(uint8_t mask) { hostLights = mask & 7; }
void radioHostBuzz(bool on) { hornRaw = on; }

void radioHostSound(uint8_t count, uint16_t blastMs, uint16_t gapMs) {
  const uint32_t now = millis();
  const uint8_t blast = (uint8_t)(blastMs / 10 > 255 ? 255 : blastMs / 10);
  const uint8_t gap = (uint8_t)(gapMs / 10 > 255 ? 255 : gapMs / 10);
  sndSeq++;
  sndCount = count;
  sndBlast = blast;
  sndGap = gap;
  sndStartMs = now;
  sndEver = true;
  if (count == 0) {
    sndUntil = now;  // silence: the pattern is over
    return;
  }
  sndUntil = now + (uint32_t)count * blastMs + (uint32_t)(count - 1) * gapMs;
  if (!txActive() || outp.tx_rank == 0) return;
  prep(FrameType::Sound);
  txf.sound.master_id = outp.tx_master_id;
  txf.sound.session = ownSession;
  txf.sound.sound_seq = sndSeq;
  txf.sound.count = count;
  txf.sound.blast = blast;
  txf.sound.gap = gap;
  burstEncodeStart(sndB, meshKey, 16, now);
}

void radioHostTimer(const HostTimer &t, uint32_t now) {
  ht = t;
  htRxMs = now;
}

void radioHostSession(const HostSession &s) {
  if (!haveHs || s.rev != hs.rev || s.flags != hs.flags || s.totalEnds != hs.totalEnds ||
      s.practiceEnds != hs.practiceEnds || s.prepMs != hs.prepMs || s.shootMs != hs.shootMs ||
      s.warnMs != hs.warnMs || s.delayMs != hs.delayMs || strcmp(s.seqId, hs.seqId) != 0 || s.groupsN != hs.groupsN)
    hsDirty = true;
  else
    for (uint8_t g = 0; g < s.groupsN; g++)
      if (strcmp(s.groups[g], hs.groups[g]) != 0) hsDirty = true;
  hs = s;
  haveHs = true;
}

void radioSetEnabled(bool on) { enabled = on; }

void radioSetChannel(uint8_t ch) {
  if (ch < 1 || ch > 13) return;
  chan = ch;
  if (radioOn) esp_wifi_set_channel(chan, WIFI_SECOND_CHAN_NONE);
}

void radioSetName(const char *n) {
  strncpy(nodeName, n, 12);
  nodeName[12] = 0;
}

void radioSetCaps(bool lights, bool sound, bool buttons) {
  capsByte = (uint8_t)(kCapR | (lights ? kCapL : 0) | (sound ? (kCapS | kCapB) : 0) | (buttons ? kCapK : 0));
}

bool radioSetMeshKey(const uint8_t key[16]) {
  keysStoreMesh(key);
  memcpy(meshKey, key, 16);
  hasMesh = true;
  pairMode = pairForced = pairPressed = false;  // a key from the host ends the keyless search
  // New mesh key = new radio network: forget everything learned under the old one.
  peers = PeerTable();
  memset(shadow, 0, sizeof shadow);
  windowClose();
  rebuildArbiter();
  return true;
}

bool radioEnsureMeshKey() {
  if (hasMesh) return true;
  uint8_t k[16];
  meshRandom(k, 16);
  const bool ok = radioSetMeshKey(k);
  memset(k, 0, sizeof k);
  return ok;
}

const char *radioName() { return nodeName; }
uint8_t radioChannel() { return chan; }
bool radioEnabled() { return enabled; }
bool radioActive() { return radioOn; }
bool radioHasMeshKey() { return hasMesh; }
uint8_t radioPeers() {
  const size_t n = peers.count();
  return (uint8_t)(n > 99 ? 99 : n);
}
uint32_t radioStatusMasterId() {
  if (role == HostRole::M || role == HostRole::F) return ownId;
  return outp.has_follow ? outp.follow_id : 0;
}

// --- pairing, master side ---------------------------------------------------------------------------------------

bool radioPairOpen(uint8_t seconds) {
  if (!hasMesh || !radioOn || seconds < 1 || seconds > 120) return false;
  const uint32_t now = millis();
  meshRandom(mpriv, 32);
  x25519impl.publicKey(mpub, mpriv);
  memset(pend, 0, sizeof pend);
  winOpen = true;
  winEnd = now + (uint32_t)seconds * 1000;
  nextPairOpenMs = now;
  nextStateMs = now;
  return true;
}

void radioPairClose() { windowClose(); }

bool radioPairAccept(const uint8_t mac[6], uint8_t mask) {
  if (!winOpen || !hasMesh) return false;
  PendingReq *req = nullptr;
  for (auto &p : pend)
    if (p.used && memcmp(p.mac, mac, 6) == 0) req = &p;
  if (!req) return false;
  uint8_t shared[32], k[32], rk[16], blob[32];
  x25519impl.sharedSecret(shared, mpriv, req->pub);
  if (x25519_is_zero(shared)) {
    req->used = false;
    return false;
  }
  derive_pair_key(shared, mac, ownMac, k);
  meshRandom(rk, 16);
  if (!gate.addRemote(mac, rk, mask & 0x7F, 0)) {  // table full
    memset(shared, 0, sizeof shared);
    return false;
  }
  make_blob(k, meshKey, rk, blob);
  const uint32_t now = millis();
  prep(FrameType::PairAcc);
  memcpy(txf.pair_acc.target_mac, mac, 6);
  memcpy(txf.pair_acc.blob, blob, 32);
  if (burstEncodeStart(accB, k, 32, now)) {
    accRetryAt[0] = now + 300;  // the ACC is the one frame that must not be lost: two later copies, same seq
    accRetryAt[1] = now + 800;
    accRetryLeft = 2;
  }
  if (const RemoteEntry *e = gate.find(mac)) keysSaveRemote(*e);
  char body[32];
  if (hostcore::fmtPairDone(body, sizeof body, mac)) hostBody(body);
  req->used = false;
  memset(shared, 0, sizeof shared);
  memset(k, 0, sizeof k);
  memset(rk, 0, sizeof rk);
  memset(blob, 0, sizeof blob);
  return true;
}

bool radioPairReject(const uint8_t mac[6]) {
  for (auto &p : pend)
    if (p.used && memcmp(p.mac, mac, 6) == 0) p.used = false;
  return true;
}

bool radioPairDelete(const uint8_t mac[6]) {
  gate.removeRemote(mac);
  keysEraseRemote(mac);
  Revoked *slot = nullptr;
  for (auto &r : revoked)
    if (r.used && memcmp(r.mac, mac, 6) == 0) slot = &r;
  if (!slot) {
    slot = &revoked[revokedNext];
    revokedNext = (uint8_t)((revokedNext + 1) & 3);
  }
  slot->used = true;
  memcpy(slot->mac, mac, 6);
  slot->until = millis() + REVOKE_FOR_MS;
  slot->nextMs = millis();
  return true;
}

bool radioHostAck(const uint8_t mac[6], uint32_t counter, uint8_t result) {
  if (!radioOn || !hasMesh) return true;
  if (gate.onHostAck(mac, counter, result)) sendCmdAck(mac, counter, result > 1 ? 1 : result, millis());
  return true;
}

// --- remote side -------------------------------------------------------------------------------------------------

bool radioHasRemoteKey() { return hasRemote; }

bool radioRemoteSend(uint8_t action) {
  if (!hasRemote || !radioOn || pairMode || action < kActionPrimary || action > kActionEmergency) return false;
  const uint32_t now = millis();
  keysCmdCounterReserve(sender.counter() + 1);  // persisted BEFORE the counter goes on the air
  sender.begin(now, action);
  cmdPump(now);
  return true;
}

void radioEnterPairing(bool force) {
  if (pairMode) return;
  pairMode = true;
  pairForced = force;
  pairUntil = millis() + PAIR_FORCED_TIMEOUT_MS;
  pairPressed = false;
  openSeen.valid = false;
  memset(pairSlots, 0, sizeof pairSlots);
}

bool radioPairing() { return pairMode; }

// A host that wants to join a network by radio (no shared network needed) clears the keys: the box is keyless again and
// asks the master to pair, exactly like a freshly flashed one.
void radioForgetKeys() {
  keysClearMesh();
  keysClearRemote();
  memset(meshKey, 0, sizeof meshKey);
  memset(remoteKey, 0, sizeof remoteKey);
  hasMesh = hasRemote = false;
  peers = PeerTable();
  memset(shadow, 0, sizeof shadow);
  windowClose();
  rebuildArbiter();
  pairMode = false;  // so radioEnterPairing starts a fresh search
  radioEnterPairing(false);
}
bool radioPairBlink() { return pairMode && pairForced; }  // only the deliberate boot hold blinks; a keyless box just waits quietly
void radioPairPress() {
  if (pairMode) pairPressed = true;
}
