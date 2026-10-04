#include "mesh_frame.h"

#include <cstring>

#include "mesh_crypto.h"

namespace mesh {

namespace {

const uint8_t kZeroKey[16] = {0};

struct Reader {
  const uint8_t* p;
  size_t n;
  size_t i = 0;
  bool ok = true;
  Reader(const uint8_t* p_, size_t n_) : p(p_), n(n_) {}
  uint8_t u8() {
    if (i + 1 > n) { ok = false; return 0; }
    return p[i++];
  }
  uint16_t u16() {
    const uint16_t a = u8();
    return static_cast<uint16_t>(a | (uint16_t(u8()) << 8));
  }
  uint32_t u32() {
    uint32_t v = 0;
    for (int s = 0; s < 32; s += 8) v |= uint32_t(u8()) << s;
    return v;
  }
  void bytes(uint8_t* dst, size_t len) {
    if (i + len > n) { ok = false; std::memset(dst, 0, len); return; }
    std::memcpy(dst, p + i, len);
    i += len;
  }
  bool ascii(char* dst, size_t len) {  // printable ASCII only, NUL terminates dst
    if (i + len > n) { ok = false; dst[0] = 0; return false; }
    for (size_t k = 0; k < len; k++) {
      const uint8_t c = p[i + k];
      if (c < 0x20 || c > 0x7E) ok = false;
      dst[k] = static_cast<char>(c);
    }
    dst[len] = 0;
    i += len;
    return ok;
  }
  bool done() const { return ok && i == n; }
};

struct Writer {
  uint8_t* p;
  size_t cap;
  size_t i = 0;
  bool ok = true;
  Writer(uint8_t* p_, size_t cap_) : p(p_), cap(cap_) {}
  void u8(uint8_t v) {
    if (i + 1 > cap) { ok = false; return; }
    p[i++] = v;
  }
  void u16(uint16_t v) { u8(uint8_t(v)); u8(uint8_t(v >> 8)); }
  void u32(uint32_t v) { for (int s = 0; s < 32; s += 8) u8(uint8_t(v >> s)); }
  void bytes(const uint8_t* src, size_t len) {
    if (i + len > cap) { ok = false; return; }
    std::memcpy(p + i, src, len);
    i += len;
  }
};

bool parse_payload(FrameType t, Reader& r, Frame& f) {
  switch (t) {
    case FrameType::Hello: {
      HelloPayload& h = f.hello;
      h.caps = r.u8(); h.role = r.u8(); h.rank = r.u8(); h.conflict = r.u8();
      h.master_id = r.u32();
      h.fw[0] = r.u8(); h.fw[1] = r.u8(); h.fw[2] = r.u8();
      h.name_len = r.u8();
      if (h.name_len > kMaxNameLen) return false;
      r.ascii(h.name, h.name_len);
      return r.done();
    }
    case FrameType::Timer: {
      TimerPayload& m = f.timer;
      m.master_id = r.u32();
      m.session = r.u32();
      m.rank = r.u8(); m.lights = r.u8(); m.flags = r.u8(); m.mode = r.u8(); m.phase = r.u8();
      m.remaining_ms = r.u32();
      m.end_no = r.u8(); m.total_ends = r.u8(); m.group = r.u8(); m.round = r.u8();
      m.total_rounds = r.u8(); m.session_rev = r.u8();
      m.sound_seq = r.u8(); m.sound_count = r.u8(); m.sound_blast = r.u8(); m.sound_gap = r.u8();
      m.sound_age = r.u16();
      return r.done();
    }
    case FrameType::Sound: {
      SoundPayload& s = f.sound;
      s.master_id = r.u32(); s.session = r.u32(); s.sound_seq = r.u8(); s.count = r.u8(); s.blast = r.u8(); s.gap = r.u8();
      return r.done();
    }
    case FrameType::Cmd: {
      f.cmd.counter = r.u32();
      f.cmd.action = r.u8();
      if (f.cmd.action < kActionPrimary || f.cmd.action > kActionEmergency) return false;
      return r.done();
    }
    case FrameType::CmdAck: {
      r.bytes(f.cmd_ack.target_mac, kMacLen);
      f.cmd_ack.counter = r.u32();
      f.cmd_ack.result = r.u8();
      if (f.cmd_ack.result > kAckUnknownRemote) return false;
      return r.done();
    }
    case FrameType::Session: {
      SessionPayload& s = f.session;
      s.master_id = r.u32();
      s.rev = r.u8(); s.flags = r.u8(); s.total_ends = r.u8(); s.practice_ends = r.u8();
      s.prep_ms = r.u32(); s.shoot_ms = r.u32(); s.warn_ms = r.u32(); s.auto_delay_ms = r.u32();
      s.seq_len = r.u8();
      if (s.seq_len > kMaxSeqIdLen) return false;
      r.ascii(s.sequence_id, s.seq_len);
      s.groups_n = r.u8();
      if (s.groups_n > kMaxGroups) return false;
      for (uint8_t g = 0; g < s.groups_n && r.ok; g++) {
        s.group_len[g] = r.u8();
        if (s.group_len[g] > kMaxGroupLen) return false;
        r.ascii(s.groups[g], s.group_len[g]);
      }
      return r.done();
    }
    case FrameType::PairOpen: {
      f.pair_open.master_id = r.u32();
      f.pair_open.seconds_left = r.u8();
      r.bytes(f.pair_open.master_pub, 32);
      return r.done();
    }
    case FrameType::PairReq: {
      PairReqPayload& q = f.pair_req;
      q.caps = r.u8();
      q.name_len = r.u8();
      if (q.name_len > kMaxNameLen) return false;
      r.ascii(q.name, q.name_len);
      r.bytes(q.remote_pub, 32);
      return r.done();
    }
    case FrameType::PairAcc: {
      r.bytes(f.pair_acc.target_mac, kMacLen);
      r.bytes(f.pair_acc.blob, 32);
      return r.done();
    }
    case FrameType::Revoke: {
      r.bytes(f.revoke.target_mac, kMacLen);
      return r.done();
    }
  }
  return false;
}

bool write_payload(const Frame& f, Writer& w) {
  switch (f.type) {
    case FrameType::Hello: {
      const HelloPayload& h = f.hello;
      if (h.name_len > kMaxNameLen) return false;
      w.u8(h.caps); w.u8(h.role); w.u8(h.rank); w.u8(h.conflict);
      w.u32(h.master_id);
      w.u8(h.fw[0]); w.u8(h.fw[1]); w.u8(h.fw[2]);
      w.u8(h.name_len);
      w.bytes(reinterpret_cast<const uint8_t*>(h.name), h.name_len);
      return w.ok;
    }
    case FrameType::Timer: {
      const TimerPayload& m = f.timer;
      w.u32(m.master_id);
      w.u32(m.session);
      w.u8(m.rank); w.u8(m.lights); w.u8(m.flags); w.u8(m.mode); w.u8(m.phase);
      w.u32(m.remaining_ms);
      w.u8(m.end_no); w.u8(m.total_ends); w.u8(m.group); w.u8(m.round);
      w.u8(m.total_rounds); w.u8(m.session_rev);
      w.u8(m.sound_seq); w.u8(m.sound_count); w.u8(m.sound_blast); w.u8(m.sound_gap);
      w.u16(m.sound_age);
      return w.ok;
    }
    case FrameType::Sound: {
      const SoundPayload& s = f.sound;
      w.u32(s.master_id); w.u32(s.session); w.u8(s.sound_seq); w.u8(s.count); w.u8(s.blast); w.u8(s.gap);
      return w.ok;
    }
    case FrameType::Cmd:
      w.u32(f.cmd.counter);
      w.u8(f.cmd.action);
      return w.ok;
    case FrameType::CmdAck:
      w.bytes(f.cmd_ack.target_mac, kMacLen);
      w.u32(f.cmd_ack.counter);
      w.u8(f.cmd_ack.result);
      return w.ok;
    case FrameType::Session: {
      const SessionPayload& s = f.session;
      if (s.seq_len > kMaxSeqIdLen || s.groups_n > kMaxGroups) return false;
      w.u32(s.master_id);
      w.u8(s.rev); w.u8(s.flags); w.u8(s.total_ends); w.u8(s.practice_ends);
      w.u32(s.prep_ms); w.u32(s.shoot_ms); w.u32(s.warn_ms); w.u32(s.auto_delay_ms);
      w.u8(s.seq_len);
      w.bytes(reinterpret_cast<const uint8_t*>(s.sequence_id), s.seq_len);
      w.u8(s.groups_n);
      for (uint8_t g = 0; g < s.groups_n; g++) {
        if (s.group_len[g] > kMaxGroupLen) return false;
        w.u8(s.group_len[g]);
        w.bytes(reinterpret_cast<const uint8_t*>(s.groups[g]), s.group_len[g]);
      }
      return w.ok;
    }
    case FrameType::PairOpen:
      w.u32(f.pair_open.master_id);
      w.u8(f.pair_open.seconds_left);
      w.bytes(f.pair_open.master_pub, 32);
      return w.ok;
    case FrameType::PairReq: {
      const PairReqPayload& q = f.pair_req;
      if (q.name_len > kMaxNameLen) return false;
      w.u8(q.caps); w.u8(q.name_len);
      w.bytes(reinterpret_cast<const uint8_t*>(q.name), q.name_len);
      w.bytes(q.remote_pub, 32);
      return w.ok;
    }
    case FrameType::PairAcc:
      w.bytes(f.pair_acc.target_mac, kMacLen);
      w.bytes(f.pair_acc.blob, 32);
      return w.ok;
    case FrameType::Revoke:
      w.bytes(f.revoke.target_mac, kMacLen);
      return w.ok;
  }
  return false;
}

}  // namespace

void compute_tag(const uint8_t* key, size_t key_len, const uint8_t* frame_no_tag, size_t len,
                 const uint8_t src_mac[kMacLen], uint8_t tag[kTagLen]) {
  const Part parts[2] = {{frame_no_tag, len}, {src_mac, kMacLen}};
  uint8_t full[32];
  hmac_sha256(key, key_len, parts, 2, full);
  std::memcpy(tag, full, kTagLen);
}

DecodeResult decode(const uint8_t* buf, size_t len, const uint8_t src_mac[kMacLen], const KeyRing& keys,
                    Frame& out) {
  if (len < kHeaderLen + kTagLen || len > kMaxFrame) return DecodeResult::Length;
  if (buf[0] != kMagic) return DecodeResult::Magic;
  if (buf[1] != kVersion) return DecodeResult::Version;
  const uint8_t type = buf[2];
  if (type < 1 || type > 10) return DecodeResult::Type;
  if (buf[3] != 0) return DecodeResult::Flags;  // hop 0 only in the first release, reserved bits 0

  const uint8_t* key = nullptr;
  size_t key_len = 16;
  switch (static_cast<FrameType>(type)) {
    case FrameType::Cmd:
      if (keys.remote_lookup) key = keys.remote_lookup(keys.remote_ctx, src_mac);
      break;
    case FrameType::PairReq:
      if (keys.pairing_open) key = kZeroKey;
      break;
    case FrameType::PairAcc:
      key = keys.pair_key;
      key_len = 32;
      break;
    default:
      key = keys.mesh_key;
      break;
  }
  if (!key) return DecodeResult::NoKey;

  const size_t body = len - kTagLen;
  uint8_t tag[kTagLen];
  compute_tag(key, key_len, buf, body, src_mac, tag);
  if (!ct_equal(tag, buf + body, kTagLen)) return DecodeResult::Tag;

  std::memset(&out, 0, sizeof out);
  out.type = static_cast<FrameType>(type);
  out.epoch = static_cast<uint16_t>(buf[4] | (buf[5] << 8));
  out.seq = static_cast<uint16_t>(buf[6] | (buf[7] << 8));
  Reader r(buf + kHeaderLen, body - kHeaderLen);
  if (!parse_payload(out.type, r, out)) return DecodeResult::Payload;
  return DecodeResult::Ok;
}

size_t encode(const Frame& f, const uint8_t* key, size_t key_len, const uint8_t src_mac[kMacLen], uint8_t* out,
              size_t cap) {
  if (cap < kHeaderLen + kTagLen) return 0;
  Writer w(out, cap - kTagLen);
  w.u8(kMagic); w.u8(kVersion); w.u8(static_cast<uint8_t>(f.type)); w.u8(0);
  w.u16(f.epoch); w.u16(f.seq);
  if (!write_payload(f, w)) return 0;
  if (f.type == FrameType::Cmd && (f.cmd.action < kActionPrimary || f.cmd.action > kActionEmergency)) return 0;
  if (w.i + kTagLen > kMaxFrame) return 0;
  compute_tag(key, key_len, out, w.i, src_mac, out + w.i);
  return w.i + kTagLen;
}

}  // namespace mesh
