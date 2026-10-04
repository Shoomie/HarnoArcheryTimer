// Native test runner for firmware/lib/meshcore. Plain C++17, no framework.
// Usage: test_mesh <firmware dir>   (the directory that holds mesh_vectors.txt and arbiter_scenarios.txt)
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include "mesh_arbiter.h"
#include "mesh_cmd.h"
#include "mesh_config.h"
#include "mesh_crypto.h"
#include "mesh_frame.h"
#include "mesh_pair.h"
#include "mesh_peers.h"

using namespace mesh;
using Bytes = std::vector<uint8_t>;
using Fields = std::vector<std::pair<std::string, std::string>>;

static int g_checks = 0, g_fails = 0;
#define CHECK(cond, ...)                                  \
  do {                                                    \
    g_checks++;                                           \
    if (!(cond)) {                                        \
      g_fails++;                                          \
      std::printf("FAIL %s:%d: ", __FILE__, __LINE__);    \
      std::printf(__VA_ARGS__);                           \
      std::printf("\n");                                  \
    }                                                     \
  } while (0)

static Bytes fromHex(const std::string& s) {
  Bytes b;
  for (size_t i = 0; i + 1 < s.size(); i += 2) b.push_back(static_cast<uint8_t>(std::stoi(s.substr(i, 2), nullptr, 16)));
  return b;
}

static std::string toHex(const uint8_t* p, size_t n) {
  static const char* d = "0123456789ABCDEF";
  std::string s;
  for (size_t i = 0; i < n; i++) {
    s += d[p[i] >> 4];
    s += d[p[i] & 15];
  }
  return s;
}

static std::string trim(const std::string& s) {
  size_t a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
  return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

static std::vector<std::string> lines(const std::string& path) {
  std::ifstream f(path);
  std::vector<std::string> out;
  std::string l;
  while (std::getline(f, l)) out.push_back(trim(l));
  if (out.empty()) std::printf("FAIL cannot read %s\n", path.c_str()), g_fails++;
  return out;
}

static std::vector<std::string> split(const std::string& s) {
  std::istringstream is(s);
  std::vector<std::string> t;
  std::string w;
  while (is >> w) t.push_back(w);
  return t;
}

// "a=1 b=Line 1" -> [(a,1),(b,Line 1)]: a token without '=' continues the previous value.
static Fields parseFields(const std::vector<std::string>& tok, size_t from) {
  Fields f;
  for (size_t i = from; i < tok.size(); i++) {
    size_t eq = tok[i].find('=');
    if (eq == std::string::npos) {
      if (!f.empty()) f.back().second += " " + tok[i];
    } else {
      f.emplace_back(tok[i].substr(0, eq), tok[i].substr(eq + 1));
    }
  }
  return f;
}

static std::string num(unsigned long long v) { return std::to_string(v); }

static const char* typeName(FrameType t) {
  switch (t) {
    case FrameType::Hello: return "HELLO";
    case FrameType::Timer: return "TIMER";
    case FrameType::Sound: return "SOUND";
    case FrameType::Cmd: return "CMD";
    case FrameType::CmdAck: return "CMD_ACK";
    case FrameType::Session: return "SESSION";
    case FrameType::PairOpen: return "PAIR_OPEN";
    case FrameType::PairReq: return "PAIR_REQ";
    case FrameType::PairAcc: return "PAIR_ACC";
  }
  return "?";
}

static Fields frameFields(const Frame& f) {
  Fields o = {{"epoch", num(f.epoch)}, {"seq", num(f.seq)}};
  auto add = [&](const char* k, const std::string& v) { o.emplace_back(k, v); };
  switch (f.type) {
    case FrameType::Hello: {
      const auto& h = f.hello;
      add("caps", num(h.caps)); add("role", num(h.role)); add("rank", num(h.rank)); add("conflict", num(h.conflict));
      add("master_id", num(h.master_id));
      add("fw", num(h.fw[0]) + "." + num(h.fw[1]) + "." + num(h.fw[2]));
      add("name", std::string(h.name, h.name_len));
      break;
    }
    case FrameType::Timer: {
      const auto& t = f.timer;
      add("master_id", num(t.master_id)); add("session", num(t.session)); add("rank", num(t.rank)); add("lights", num(t.lights));
      add("flags", num(t.flags)); add("mode", num(t.mode)); add("phase", num(t.phase));
      add("remaining_ms", num(t.remaining_ms)); add("end_no", num(t.end_no)); add("total_ends", num(t.total_ends));
      add("group", num(t.group)); add("round", num(t.round)); add("total_rounds", num(t.total_rounds));
      add("session_rev", num(t.session_rev)); add("sound_seq", num(t.sound_seq));
      add("sound_count", num(t.sound_count)); add("sound_blast", num(t.sound_blast));
      add("sound_gap", num(t.sound_gap)); add("sound_age", num(t.sound_age));
      break;
    }
    case FrameType::Sound:
      add("master_id", num(f.sound.master_id)); add("session", num(f.sound.session)); add("sound_seq", num(f.sound.sound_seq));
      add("count", num(f.sound.count)); add("blast", num(f.sound.blast)); add("gap", num(f.sound.gap));
      break;
    case FrameType::Cmd:
      add("counter", num(f.cmd.counter)); add("action", num(f.cmd.action));
      break;
    case FrameType::CmdAck:
      add("target_mac", toHex(f.cmd_ack.target_mac, 6)); add("counter", num(f.cmd_ack.counter));
      add("result", num(f.cmd_ack.result));
      break;
    case FrameType::Session: {
      const auto& s = f.session;
      add("master_id", num(s.master_id)); add("rev", num(s.rev)); add("flags", num(s.flags));
      add("total_ends", num(s.total_ends)); add("practice_ends", num(s.practice_ends));
      add("prep_ms", num(s.prep_ms)); add("shoot_ms", num(s.shoot_ms)); add("warn_ms", num(s.warn_ms));
      add("auto_delay_ms", num(s.auto_delay_ms)); add("sequence_id", std::string(s.sequence_id, s.seq_len));
      std::string g;
      for (int i = 0; i < s.groups_n; i++) g += (i ? "," : "") + std::string(s.groups[i], s.group_len[i]);
      add("groups", g);
      break;
    }
    case FrameType::PairOpen:
      add("master_id", num(f.pair_open.master_id)); add("seconds_left", num(f.pair_open.seconds_left));
      add("master_pub", toHex(f.pair_open.master_pub, 32));
      break;
    case FrameType::PairReq:
      add("caps", num(f.pair_req.caps)); add("name", std::string(f.pair_req.name, f.pair_req.name_len));
      add("remote_pub", toHex(f.pair_req.remote_pub, 32));
      break;
    case FrameType::PairAcc:
      add("target_mac", toHex(f.pair_acc.target_mac, 6)); add("blob", toHex(f.pair_acc.blob, 32));
      break;
  }
  return o;
}

// ---------------------------------------------------------------- crypto unit checks

static void testCrypto() {
  uint8_t out[32];
  Sha256 s;
  s.update(reinterpret_cast<const uint8_t*>("abc"), 3);
  s.finish(out);
  CHECK(toHex(out, 32) == "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD", "sha256 abc");
  // RFC 4231 test case 1
  Bytes key(20, 0x0b);
  const char* msg = "Hi There";
  hmac_sha256(key.data(), key.size(), reinterpret_cast<const uint8_t*>(msg), 8, out);
  CHECK(toHex(out, 32) == "B0344C61D8DB38535CA8AFCEAF0BF12B881DC200C9833DA726E9376C2E32CFF7", "hmac rfc4231 #1");
  // RFC 4231 test case 6: key longer than the block size
  Bytes key6(131, 0xaa);
  const char* m6 = "Test Using Larger Than Block-Size Key - Hash Key First";
  hmac_sha256(key6.data(), key6.size(), reinterpret_cast<const uint8_t*>(m6), std::strlen(m6), out);
  CHECK(toHex(out, 32) == "60E431591EE0B67F0D8A26AACBF5B77F8E0BC6213728C5140546040F0EE37F54", "hmac rfc4231 #6");
}

// ---------------------------------------------------------------- vectors

static int g_vecOk = 0, g_vecErr = 0;

static void testVectors(const std::string& dir) {
  std::map<std::string, Bytes> keys;
  uint8_t pairK[32] = {0};
  bool haveK = false;
  uint8_t pairMeshKey[16], pairRemoteKey[16];
  for (const auto& l : lines(dir + "/mesh_vectors.txt")) {
    if (l.empty() || l[0] == '#') continue;
    auto tok = split(l);
    if (tok[0] == "key") {
      keys[tok[1]] = fromHex(tok[2]);
    } else if (tok[0] == "pairkey") {
      Fields f = parseFields(tok, 1);
      std::map<std::string, std::string> m(f.begin(), f.end());
      Bytes shared = fromHex(m["shared"]), rm = fromHex(m["remote_mac"]), mm = fromHex(m["master_mac"]);
      derive_pair_key(shared.data(), rm.data(), mm.data(), pairK);
      CHECK(toHex(pairK, 32) == m["K"], "pairkey K: got %s", toHex(pairK, 32).c_str());
      Bytes rk = fromHex(m["remote_key"]);
      uint8_t blob[32];
      make_blob(pairK, keys["mesh"].data(), rk.data(), blob);
      CHECK(toHex(blob, 32) == m["blob"], "pairkey blob: got %s", toHex(blob, 32).c_str());
      open_blob(pairK, blob, pairMeshKey, pairRemoteKey);
      CHECK(std::memcmp(pairMeshKey, keys["mesh"].data(), 16) == 0 && std::memcmp(pairRemoteKey, rk.data(), 16) == 0,
            "open_blob round trip");
      haveK = true;
    } else if (tok[0] == "frame") {
      // frame src=<mac> key=<name> hex=<hex> => OK <TYPE> fields | ERR
      std::string mac, keyname, hex;
      size_t arrow = 0;
      for (size_t i = 1; i < tok.size(); i++) {
        if (tok[i] == "=>") { arrow = i; break; }
        if (tok[i].rfind("src=", 0) == 0) mac = tok[i].substr(4);
        else if (tok[i].rfind("key=", 0) == 0) keyname = tok[i].substr(4);
        else if (tok[i].rfind("hex=", 0) == 0) hex = tok[i].substr(4);
      }
      CHECK(arrow != 0, "malformed vector line: %s", l.c_str());
      if (!arrow) continue;
      Bytes src = fromHex(mac), frame = fromHex(hex);

      // The key ring a receiver would hold for this vector.
      Bytes remoteKey;
      struct Ctx { const uint8_t* mac; const uint8_t* key; } ctx{src.data(), nullptr};
      KeyRing ring;
      if (keyname == "mesh") ring.mesh_key = keys["mesh"].data();
      if (keyname == "remote") {
        ctx.key = keys["remote"].data();
        ring.remote_lookup = [](void* c, const uint8_t m[6]) -> const uint8_t* {
          auto* x = static_cast<Ctx*>(c);
          return std::memcmp(x->mac, m, 6) == 0 ? x->key : nullptr;
        };
        ring.remote_ctx = &ctx;
      }
      if (keyname == "zero") ring.pairing_open = true;
      if (keyname == "K") { CHECK(haveK, "K before pairkey"); ring.pair_key = pairK; }

      Frame f;
      const DecodeResult r = decode(frame.data(), frame.size(), src.data(), ring, f);
      if (tok[arrow + 1] == "ERR") {
        g_vecErr++;
        CHECK(r != DecodeResult::Ok, "ERR vector decoded: %s", l.c_str());
        continue;
      }
      g_vecOk++;
      CHECK(r == DecodeResult::Ok, "OK vector dropped (code %d): %s", int(r), l.c_str());
      if (r != DecodeResult::Ok) continue;
      CHECK(tok[arrow + 2] == typeName(f.type), "type %s vs %s", tok[arrow + 2].c_str(), typeName(f.type));
      Fields want = parseFields(tok, arrow + 3), got = frameFields(f);
      std::map<std::string, std::string> gm(got.begin(), got.end());
      for (const auto& kv : want)
        CHECK(gm.count(kv.first) && gm[kv.first] == kv.second, "%s: field %s want '%s' got '%s'",
              typeName(f.type), kv.first.c_str(), kv.second.c_str(), gm.count(kv.first) ? gm[kv.first].c_str() : "<none>");

      // Round trip: encode must reproduce the vector byte for byte.
      const uint8_t* k = keyname == "mesh" ? keys["mesh"].data() : keyname == "remote" ? keys["remote"].data()
                         : keyname == "zero" ? keys["zero"].data() : pairK;
      const size_t kl = keyname == "K" ? 32 : 16;
      uint8_t out[kMaxFrame];
      const size_t n = encode(f, k, kl, src.data(), out, sizeof out);
      CHECK(n == frame.size() && std::memcmp(out, frame.data(), n) == 0, "encode round trip: %s", l.c_str());

      // Pairing frames must be refused when the matching condition does not hold.
      if (keyname == "zero") {
        KeyRing closed;
        closed.mesh_key = keys["mesh"].data();
        CHECK(decode(frame.data(), frame.size(), src.data(), closed, f) != DecodeResult::Ok, "PAIR_REQ with window closed");
      }
    }
  }
  CHECK(g_vecOk >= 12 && g_vecErr >= 15, "vector counts ok=%d err=%d", g_vecOk, g_vecErr);
}

// ---------------------------------------------------------------- units

static void testPeers() {
  PeerTable t;
  const uint8_t a[6] = {1, 2, 3, 4, 5, 6};
  CHECK(t.accept(a, 100, 10, 0), "new peer");
  CHECK(!t.accept(a, 100, 10, 3), "same seq (repeat) dropped");
  CHECK(!t.accept(a, 100, 9, 5), "older seq dropped");
  CHECK(t.accept(a, 100, 11, 10), "next seq");
  CHECK(t.accept(a, 100, 0x7FFF + 11, 20), "int16 delta +32767 accepted");
  CHECK(!t.accept(a, 100, 11, 30), "int16 delta behind dropped");
  CHECK(t.accept(a, 200, 1, 40), "new epoch accepted at once");
  CHECK(!t.accept(a, 200, 1, 50), "same epoch, same seq dropped");
  PeerTable w;
  CHECK(w.accept(a, 5, 0xFFFE, 0) && w.accept(a, 5, 0xFFFF, 1) && w.accept(a, 5, 0, 2), "seq wraps");
  CHECK(w.count() == 1, "one peer");
  w.expire(5999);
  CHECK(w.count() == 1, "not yet expired");
  w.expire(6002);
  CHECK(w.count() == 0, "expired after 6000 ms");
  PeerTable full;
  for (uint8_t i = 0; i < kMaxPeers + 4; i++) {
    const uint8_t m[6] = {9, 9, 9, 9, 9, i};
    CHECK(full.accept(m, 1, 1, i), "peer %d", i);
  }
  CHECK(full.count() == kMaxPeers, "capacity respected");
}

// Full pairing handshake through the X25519 interface (both sides derive K, the blob decrypts to the keys).
static void testPairHandshake(X25519& x, const char* label) {
  uint8_t mpriv[32], rpriv[32], mpub[32], rpub[32], s1[32], s2[32];
  for (int i = 0; i < 32; i++) { mpriv[i] = uint8_t(i); rpriv[i] = uint8_t(100 + i); }
  x.publicKey(mpub, mpriv);
  x.publicKey(rpub, rpriv);
  x.sharedSecret(s1, mpriv, rpub);
  x.sharedSecret(s2, rpriv, mpub);
  CHECK(std::memcmp(s1, s2, 32) == 0, "%s x25519 symmetric", label);
  const uint8_t rm[6] = {1, 1, 1, 1, 1, 1}, mm[6] = {2, 2, 2, 2, 2, 2};
  uint8_t k1[32], k2[32];
  derive_pair_key(s1, rm, mm, k1);
  derive_pair_key(s2, rm, mm, k2);
  CHECK(std::memcmp(k1, k2, 32) == 0, "both sides derive the same K");
  uint8_t mesh[16], rk[16], blob[32], mesh2[16], rk2[16];
  for (int i = 0; i < 16; i++) { mesh[i] = uint8_t(i); rk[i] = uint8_t(0x40 + i); }
  make_blob(k1, mesh, rk, blob);
  open_blob(k2, blob, mesh2, rk2);
  CHECK(!std::memcmp(mesh, mesh2, 16) && !std::memcmp(rk, rk2, 16), "blob round trip");
  // Wrong order of macs gives another K.
  uint8_t k3[32];
  derive_pair_key(s1, mm, rm, k3);
  CHECK(std::memcmp(k1, k3, 32) != 0, "mac order matters");

  // PAIR_ACC signed with K accepted, with a wrong K dropped.
  Frame f = {};
  f.type = FrameType::PairAcc; f.epoch = 7; f.seq = 1;
  std::memcpy(f.pair_acc.target_mac, rm, 6);
  std::memcpy(f.pair_acc.blob, blob, 32);
  uint8_t buf[kMaxFrame];
  size_t n = encode(f, k1, 32, mm, buf, sizeof buf);
  KeyRing ring;
  ring.pair_key = k2;
  Frame g;
  CHECK(decode(buf, n, mm, ring, g) == DecodeResult::Ok, "PAIR_ACC with K");
  ring.pair_key = k3;
  CHECK(decode(buf, n, mm, ring, g) == DecodeResult::Tag, "PAIR_ACC with wrong K");
}

static void testX25519() {
  uint8_t out[32];
  auto run = [&](const char* sc, const char* u) {
    Bytes a = fromHex(sc), b = fromHex(u);
    x25519(out, a.data(), b.data());
    return toHex(out, 32);
  };
  // RFC 7748 section 5.2
  CHECK(run("A546E36BF0527C9D3B16154B82465EDD62144C0AC1FC5A18506A2244BA449AC4",
            "E6DB6867583030DB3594C1A424B15F7C726624EC26B3353B10A903A6D0AB1C4C") ==
            "C3DA55379DE9C6908E94EA4DF28D084F32ECCF03491C71F754B4075577A28552", "rfc7748 5.2 #1");
  CHECK(run("4B66E9D4D1B4673C5AD22691957D6AF5C11B6421E0EA01D42CA4169E7918BA0D",
            "E5210F12786811D3F4B7959D0538AE2C31DBE7106FC03C3EFC4CD549C715A493") ==
            "95CBDE9476E8907D7AADE45CB4B873F88B595A68799FA152E6F8F7647AAC7957", "rfc7748 5.2 #2");
  // RFC 7748 section 5.2 iterated: k = u = 9; 1 and 1000 iterations
  uint8_t k[32] = {9}, u[32] = {9};
  for (int i = 1; i <= 1000; i++) {
    uint8_t r[32];
    x25519(r, k, u);
    std::memcpy(u, k, 32);
    std::memcpy(k, r, 32);
    if (i == 1) CHECK(toHex(k, 32) == "422C8E7A6227D7BCA1350B3E2BB7279F7897B87BB6854B783C60E80311AE3079", "rfc7748 iter 1");
  }
  CHECK(toHex(k, 32) == "684CF59BA83309552800EF566F2F4D3C1C3887C49360E3875F2EB94D99532C51", "rfc7748 iter 1000");
  // RFC 7748 section 6.1 Diffie-Hellman
  PortableX25519 x;
  Bytes ap = fromHex("77076D0A7318A57D3C16C17251B26645DF4C2F87EBC0992AB177FBA51DB92C2A");
  Bytes bp = fromHex("5DAB087E624A8A4B79E17F8B83800EE66F3BB1292618B6FD1C2F8B27FF88E0EB");
  uint8_t apub[32], bpub[32], s1[32], s2[32];
  x.publicKey(apub, ap.data());
  x.publicKey(bpub, bp.data());
  CHECK(toHex(apub, 32) == "8520F0098930A754748B7DDCB43EF75A0DBF3A0D26381AF4EBA4A98EAA9B4E6A", "rfc7748 6.1 alice pub");
  CHECK(toHex(bpub, 32) == "DE9EDB7D7B7DC1B4D35B61C2ECE435373F8343C85B78674DADFC7E146F882B4F", "rfc7748 6.1 bob pub");
  x.sharedSecret(s1, ap.data(), bpub);
  x.sharedSecret(s2, bp.data(), apub);
  CHECK(toHex(s1, 32) == "4A5D9D5BA4CE2DE1728E3BF480350F25E07E21C947D19E3376F09B3C1E161742" && !std::memcmp(s1, s2, 32),
        "rfc7748 6.1 shared secret");
  // Low-order point (u = 0) gives an all-zero secret, which callers must reject.
  uint8_t zero[32] = {0};
  x25519(out, ap.data(), zero);
  CHECK(x25519_is_zero(out) && !x25519_is_zero(s1), "all-zero shared secret detectable");
}

static void testSession() {
  // Store: writes only when the value rises; lower dropped; equal accepted.
  MemorySessionStore store;
  ArbiterConfig cfg;
  Arbiter a(cfg, &store);
  TimerPayload t = {};
  t.master_id = 7; t.rank = 2; t.lights = kLightG; t.session = 5;
  a.onTimer(0, t);
  CHECK(store.writes() == 1, "first session saved");
  a.onTimer(10, t);
  CHECK(store.writes() == 1, "equal session: no write");
  t.session = 4; t.lights = kLightR;
  a.onTimer(20, t);
  CHECK(a.output(20).lights == kLightG && store.writes() == 1, "lower session ignored");
  t.session = 9;
  a.onTimer(30, t);
  uint32_t v = 0;
  CHECK(store.load(7, &v) && v == 9 && store.writes() == 2, "higher session saved at once");
  // SOUND with lower session dropped, higher accepted (and saved).
  a.onTimer(40, t);
  SoundPayload s = {};
  s.master_id = 7; s.session = 8; s.sound_seq = 1; s.count = 2; s.blast = 50; s.gap = 50;
  a.onSound(50, s);
  CHECK(a.soundStartCount() == 0, "SOUND with lower session dropped");
  s.session = 10;
  a.onSound(60, s);
  CHECK(a.soundStartCount() == 1 && store.load(7, &v) && v == 10, "SOUND with higher session starts and is saved");
  // Another master has its own counter.
  t.master_id = 8; t.session = 1;
  a.onTimer(70, t);
  CHECK(store.load(8, &v) && v == 1 && store.load(7, &v) && v == 10, "sessions are per master_id");
  // A fresh arbiter on the same store (reboot) still rejects the old session.
  Arbiter b(cfg, &store);
  t.master_id = 7; t.session = 9;
  b.onTimer(100, t);
  CHECK(!b.output(100).has_follow, "after reboot an old session is rejected");
  // More masters than cache slots: the store stays authoritative.
  for (uint32_t id = 100; id < 120; id++) { t.master_id = id; t.session = 3; b.onTimer(200, t); }
  t.master_id = 100; t.session = 2;
  const size_t before = store.writes();
  b.onTimer(210, t);
  CHECK(store.writes() == before && store.load(100, &v) && v == 3, "cache eviction does not lose the highest session");
}

static void testSafetyRepeater() {
  SafetyRepeater r;
  CHECK(!r.observe(0, kLightG, false, false), "first observe only records");
  CHECK(!r.observe(10, kLightG | kLightY, false, true), "no safe-direction change");
  CHECK(!r.poll(1000) && !r.active(), "idle");
  CHECK(r.observe(100, kLightR, false, true), "lights to RED triggers");
  std::vector<uint32_t> at;
  for (uint32_t t = 100; t < 800; t++)
    while (r.poll(t)) at.push_back(t - 100);
  bool ok = at.size() == 10;
  for (size_t i = 0; ok && i < at.size(); i++) ok = at[i] == 50 * (i + 1);
  CHECK(ok && !r.active(), "resends every 50 ms for 500 ms (n=%d)", int(at.size()));
  CHECK(!r.observe(900, kLightR, false, true), "RED to RED is no change");
  CHECK(r.observe(910, kLightG, true, true), "emergency latch set triggers");
  CHECK(r.poll(960) && !r.poll(960), "first resend at +50");
  CHECK(r.observe(970, kLightG, true, false), "sound stopped triggers (restarts the window)");
  CHECK(!r.poll(1010) && r.poll(1020), "window restarted at 970");
  CHECK(!r.observe(1100, kLightG, false, false), "emergency cleared is not toward safe");
  CHECK(!r.observe(1110, kLightG, false, true), "sound starting is not toward safe");
  // Overdue polls fire in a burst, in count.
  SafetyRepeater q;
  q.trigger(0);
  int n = 0;
  while (q.poll(10000)) n++;
  CHECK(n == 10 && !q.active(), "overdue resends are all reported (n=%d)", n);
  // Wrap-safe.
  SafetyRepeater w;
  w.trigger(0xFFFFFFF0u);
  CHECK(w.poll(0xFFFFFFF0u + 50), "wrap-safe");
}

static void testCmd() {
  CmdGate gate;
  const uint8_t r1[6] = {1, 2, 3, 4, 5, 6}, r2[6] = {6, 5, 4, 3, 2, 1};
  const uint8_t key[16] = {7};
  gate.addRemote(r1, key, 0x01 /* primary only */, 10);
  CHECK(CmdGate::lookupKey(&gate, r1) != nullptr && CmdGate::lookupKey(&gate, r2) == nullptr, "key lookup");
  CHECK(gate.onCmd(r1, 11, kActionPrimary, false).kind == CmdDecision::Ignore, "host dead: ignore");
  CHECK(gate.onCmd(r1, 10, kActionPrimary, true).kind == CmdDecision::Ignore, "counter == last: stale");
  CHECK(gate.onCmd(r1, 5, kActionPrimary, true).kind == CmdDecision::Ignore, "counter < last: stale");
  CmdDecision d = gate.onCmd(r1, 11, kActionPrimary, true);
  CHECK(d.kind == CmdDecision::Forward, "allowed new command is forwarded");
  CHECK(gate.onCmd(r1, 11, kActionPrimary, true).kind == CmdDecision::Ignore, "duplicate while pending: quiet");
  CHECK(gate.onHostAck(r1, 11, kAckDone), "host ack produces CMD_ACK");
  d = gate.onCmd(r1, 11, kActionPrimary, true);
  CHECK(d.kind == CmdDecision::SendAck && d.result == kAckDone, "duplicate re-ACKed from cache, not forwarded");
  CHECK(!gate.onHostAck(r1, 11, kAckDone), "second host ack ignored");
  d = gate.onCmd(r1, 12, kActionNext, true);
  CHECK(d.kind == CmdDecision::SendAck && d.result == kAckDenied, "permission denied");
  d = gate.onCmd(r1, 12, kActionNext, true);
  CHECK(d.kind == CmdDecision::SendAck && d.result == kAckDenied, "denied re-ACKed");
  CHECK(gate.onCmd(r1, 13, kActionEmergency, true).kind == CmdDecision::Forward, "emergency always allowed");
  CHECK(gate.onCmd(r2, 1, kActionPrimary, true).result == kAckUnknownRemote, "unknown remote");
  CHECK(gate.find(r1)->last_counter == 13, "last counter tracked for persistence");
  CHECK(gate.removeRemote(r1) && gate.find(r1) == nullptr, "remove remote");

  CmdSender s(41);
  const uint32_t c = s.begin(1000, kActionEmergency);
  CHECK(c == 42 && s.pending(), "sender counter increments");
  CHECK(s.due(1000), "first send at once");
  CHECK(!s.due(1014), "not before 15 ms");
  CHECK(s.due(1015), "retransmit at 15 ms");
  CHECK(!s.onAck(41, 0), "ack of another counter ignored");
  CHECK(s.onAck(42, 0) && !s.pending() && s.acked(), "ack stops retransmission");
  CHECK(!s.due(1030), "no send after ack");
  s.begin(2000, kActionPrimary);
  int sends = 0;
  for (uint32_t t = 2000; t <= 2400; t++) sends += s.due(t) ? 1 : 0;
  CHECK(sends >= 16 && sends <= 18 && !s.pending(), "gives up after 250 ms (sends=%d)", sends);

  RepeatSender rs;
  rs.begin(100);
  int copies = 0;
  uint32_t at[8] = {0};
  for (uint32_t t = 100; t < 200; t++)
    while (rs.poll(t)) at[copies++] = t - 100;
  CHECK(copies == 4 && at[0] == 0 && at[1] == 3 && at[2] == 15 && at[3] == 40, "repeat offsets 0,3,15,40");
}

// ---------------------------------------------------------------- scenarios

struct Event {
  uint32_t t;
  int order;
  std::string kind;  // rx_timer, rx_sound, host_alive, host_dead, host_lights, expect
  std::map<std::string, std::string> kv;
  std::string text;
};

static uint8_t lightsFromLetters(const std::string& s) {
  uint8_t m = 0;
  if (s == "O") return 0;
  for (char c : s) m |= c == 'G' ? kLightG : c == 'Y' ? kLightY : c == 'R' ? kLightR : 0;
  return m;
}

static std::string lettersFromLights(uint8_t m) {
  std::string s;
  if (m & kLightG) s += 'G';
  if (m & kLightY) s += 'Y';
  if (m & kLightR) s += 'R';
  return s.empty() ? "O" : s;
}

static uint32_t hex8(const std::string& s) { return static_cast<uint32_t>(std::stoul(s, nullptr, 16)); }

static void runScenario(const std::string& name, const std::vector<std::string>& cfgTok, std::vector<Event>& ev) {
  ArbiterConfig cfg;
  bool hostAlive = false;
  for (const auto& kv : parseFields(cfgTok, 1)) {
    if (kv.first == "role") cfg.role = kv.second == "M" ? HostRole::M : kv.second == "F" ? HostRole::F
                                      : kv.second == "E" ? HostRole::E : HostRole::N;
    else if (kv.first == "host") hostAlive = kv.second == "alive";
    else if (kv.first == "master_id") cfg.own_master_id = hex8(kv.second);
  }
  bool hostAliveNow = hostAlive;
  MemorySessionStore store;  // survives the scenario "reboot" (RAM state of the arbiter is rebuilt)
  auto arbp = std::make_unique<Arbiter>(cfg, &store);
  arbp->setHostAlive(hostAlive, 0);
  std::stable_sort(ev.begin(), ev.end(), [](const Event& a, const Event& b) { return a.t < b.t; });
  uint32_t last = ev.empty() ? 0 : ev.back().t;
  size_t i = 0;
  int fails0 = g_fails;
  for (uint32_t now = 0; now <= last; now++) {
    for (; i < ev.size() && ev[i].t == now; i++) {
      const Event& e = ev[i];
      auto get = [&](const char* k, const char* d) { auto it = e.kv.find(k); return it == e.kv.end() ? std::string(d) : it->second; };
      if (e.kind == "rx_timer") {
        TimerPayload t = {};
        t.master_id = hex8(get("master", "0"));
        t.rank = uint8_t(std::stoi(get("rank", "0")));
        t.lights = lightsFromLetters(get("lights", "O"));
        t.flags = uint8_t(std::stoi(get("flags", "0")));
        t.sound_seq = uint8_t(std::stoi(get("sound_seq", "0")));
        t.sound_count = uint8_t(std::stoi(get("sound_count", "0")));
        t.sound_blast = 50; t.sound_gap = 50;
        t.sound_age = uint16_t(std::stoi(get("sound_age", "65535")));
        t.session = uint32_t(std::stoul(get("session", "1")));
        arbp->onTimer(now, t);
      } else if (e.kind == "rx_sound") {
        SoundPayload s = {};
        s.master_id = hex8(get("master", "0"));
        s.sound_seq = uint8_t(std::stoi(get("seq", "0")));
        s.count = uint8_t(std::stoi(get("count", "0")));
        s.blast = 50; s.gap = 50;
        s.session = uint32_t(std::stoul(get("session", "1")));
        arbp->onSound(now, s);
      } else if (e.kind == "reboot") {
        // RAM state lost, store kept; the host link state comes back as configured (fail-safe, nobody followed).
        arbp = std::make_unique<Arbiter>(cfg, &store);
        hostAliveNow = hostAlive;
        arbp->setHostAlive(hostAliveNow, now);
      } else if (e.kind == "host_alive") { hostAliveNow = true; arbp->setHostAlive(true, now); }
      else if (e.kind == "host_dead") { hostAliveNow = false; arbp->setHostAlive(false, now); }
      else if (e.kind == "host_lights") arbp->setHostLights(lightsFromLetters(get("lights", "O")));
      else if (e.kind == "expect") {
        // Expects see only the events that precede them in the file at the same ms (see contract gap note).
        arbp->tick(now);
        const ArbiterOutput o = arbp->output(now);
        const Event* pe = &e;
      for (const auto& kv : pe->kv) {
        std::string got;
        if (kv.first == "follow") { char b[16]; std::snprintf(b, sizeof b, "%08X", o.follow_id); got = o.has_follow ? b : "none"; }
        else if (kv.first == "lights") got = lettersFromLights(o.lights);
        else if (kv.first == "sound_started") got = num(arbp->soundStartCount());
        else if (kv.first == "sound_active") got = arbp->soundActive(now) ? "1" : "0";
        else if (kv.first == "conflict") got = o.conflict ? "1" : "0";
        else if (kv.first == "failsafe") got = o.failsafe ? "1" : "0";
        else if (kv.first == "tx_rank") got = num(o.tx_rank);
        else { CHECK(false, "[%s] unknown expect key %s", name.c_str(), kv.first.c_str()); continue; }
        std::string want = kv.second;
        if (kv.first == "follow" && want != "none") { char b[16]; std::snprintf(b, sizeof b, "%08X", hex8(want)); want = b; }
        CHECK(got == want, "[%s] t=%u expect %s=%s got %s", name.c_str(), now, kv.first.c_str(), want.c_str(), got.c_str());
      }
      }
    }
    arbp->tick(now);
  }
  std::printf("  scenario %-32s %s\n", name.c_str(), g_fails == fails0 ? "ok" : "FAILED");
}

static void testScenarios(const std::string& dir) {
  std::string name;
  std::vector<std::string> cfgTok;
  std::vector<Event> ev;
  int order = 0, count = 0;
  auto flush = [&]() {
    if (!name.empty()) { runScenario(name, cfgTok, ev); count++; }
    ev.clear();
    cfgTok.clear();
  };
  for (const auto& l : lines(dir + "/arbiter_scenarios.txt")) {
    if (l.empty() || l[0] == '#') continue;
    auto tok = split(l);
    if (tok[0] == "scenario") { flush(); name = tok[1]; continue; }
    if (tok[0] == "config") { cfgTok = tok; continue; }
    if (tok[0] != "at") { CHECK(false, "unparsed scenario line: %s", l.c_str()); continue; }
    uint32_t t = uint32_t(std::stoul(tok[1]));
    size_t p = 2;
    uint32_t step = 0, until = t;
    if (tok[p] == "every") { step = uint32_t(std::stoul(tok[p + 1])); CHECK(tok[p + 2] == "until", "bad every"); until = uint32_t(std::stoul(tok[p + 3])); p += 4; }
    Event e;
    e.order = order++;
    e.text = l;
    if (tok[p] == "rx") { e.kind = tok[p + 1] == "TIMER" ? "rx_timer" : "rx_sound"; p += 2; }
    else if (tok[p] == "host") { if (tok[p + 1] == "alive") e.kind = "host_alive"; else if (tok[p + 1] == "dead") e.kind = "host_dead"; else { e.kind = "host_lights"; } p += 1; if (e.kind != "host_lights") p += 1; }
    else if (tok[p] == "expect") { e.kind = "expect"; p += 1; }
    else if (tok[p] == "reboot") { e.kind = "reboot"; p += 1; }
    else { CHECK(false, "unparsed event: %s", l.c_str()); continue; }
    for (const auto& kv : parseFields(tok, p)) e.kv[kv.first] = kv.second;
    for (uint32_t x = t; x <= until; x += (step ? step : 1)) { e.t = x; ev.push_back(e); if (!step) break; }
  }
  flush();
  CHECK(count >= 12, "scenario count %d", count);
}

// REVOKE: signed with the mesh key, names one MAC; a wrong key or a short payload is refused.
static void testRevoke() {
  uint8_t mk[16], other[16], src[6] = {9, 8, 7, 6, 5, 4};
  for (int i = 0; i < 16; i++) { mk[i] = uint8_t(i); other[i] = uint8_t(0x80 + i); }
  Frame f;
  std::memset(&f, 0, sizeof f);
  f.type = FrameType::Revoke;
  f.epoch = 7;
  f.seq = 3;
  const uint8_t target[6] = {1, 2, 3, 4, 5, 6};
  std::memcpy(f.revoke.target_mac, target, 6);
  uint8_t buf[kMaxFrame];
  const size_t n = encode(f, mk, 16, src, buf, sizeof buf);
  CHECK(n == kHeaderLen + 6 + kTagLen, "revoke frame length");
  KeyRing kr;
  kr.mesh_key = mk;
  Frame out;
  CHECK(decode(buf, n, src, kr, out) == DecodeResult::Ok && out.type == FrameType::Revoke, "revoke decodes");
  CHECK(std::memcmp(out.revoke.target_mac, target, 6) == 0, "revoke target round trip");
  KeyRing bad;
  bad.mesh_key = other;
  CHECK(decode(buf, n, src, bad, out) == DecodeResult::Tag, "revoke with the wrong mesh key is refused");
  CHECK(decode(buf, n - 1, src, kr, out) != DecodeResult::Ok, "short revoke is refused");
}

int main(int argc, char** argv) {
  const std::string dir = argc > 1 ? argv[1] : ".";
  testCrypto();
  testVectors(dir);
  testPeers();
  { InsecureTestStubX25519 stub; testPairHandshake(stub, "stub"); }
  { PortableX25519 real; testPairHandshake(real, "portable"); }
  testX25519();
  testSession();
  testSafetyRepeater();
  testCmd();
  testRevoke();
  testScenarios(dir);
  std::printf("%d checks, %d failed (vectors: %d OK lines, %d ERR lines)\n", g_checks, g_fails, g_vecOk, g_vecErr);
  return g_fails ? 1 : 0;
}
