#include "hostlink.h"

#include "hostcore.h"

using hostcore::Command;
using hostcore::Err;

static const int PROTO = 2;

static HostHandlers HH;
static const char *fwVersion = "";
static const char *caps = "";
static uint32_t lastValidMs = 0;
static bool everValid = false;
static hostcore::LineReader reader;
static int lastSoundId = 0;

void hostlinkSendFrame(const char *body) {
  char out[hostcore::kMaxLongFrame + 4];
  const size_t n = hostcore::encodeFrame(body, out, sizeof out);
  if (n) Serial.write(reinterpret_cast<const uint8_t *>(out), n);
}

static void sendError(const char *code) {
  char b[16];
  if (hostcore::fmtError(b, sizeof b, code)) hostlinkSendFrame(b);
}

void hostlinkSendStatus(uint8_t mode, uint8_t peers, char source) {
  char b[24];
  if (hostcore::fmtEspNowStatus(b, sizeof b, mode, peers, source)) hostlinkSendFrame(b);
}

void hostlinkSendConfig(const char *key, const char *value) {
  char b[48];
  if (hostcore::fmtConfig(b, sizeof b, key, value)) hostlinkSendFrame(b);
}

bool hostlinkAlive(uint32_t timeoutMs) { return everValid && millis() - lastValidMs <= timeoutMs; }

// Lights state already validated by hostcore: "O" or a set of G/Y/R.
static uint8_t lightsMask(const char *s) {
  uint8_t m = 0;
  for (; *s; ++s) m |= (*s == 'G') ? 1 : (*s == 'Y') ? 2 : (*s == 'R') ? 4 : 0;
  return m;
}

// $S,<n>[,<id>[,<blast_ms>,<gap_ms>]]. A repeated id is a host retransmission, already acted on.
static void handleSound(const Command &c) {
  uint32_t n = 0, id = 0, blast = 0, gap = 0;
  hostcore::parseUint(c.arg(0), 99, n);
  if (c.argc >= 2) hostcore::parseUint(c.arg(1), 255, id);
  if (c.argc == 4) {
    hostcore::parseUint(c.arg(2), 2000, blast);
    hostcore::parseUint(c.arg(3), 2000, gap);
  }
  if (id != 0 && (int)id == lastSoundId) return;
  if (id != 0) lastSoundId = (int)id;
  if (HH.onSound) HH.onSound((int)n, (uint16_t)blast, (uint16_t)gap);
}

static void handleTimer(const Command &c) {
  HostTimer t = {};
  uint32_t v[10] = {};
  for (int i = 0; i < 10; i++) hostcore::parseUint(c.arg(i), 0xFFFFFFFFu, v[i]);
  t.mode = (uint8_t)v[0];
  t.phase = (uint8_t)v[1];
  t.remainingMs = v[2];
  t.endNo = (uint8_t)v[3];
  t.totalEnds = (uint8_t)v[4];
  t.group = (uint8_t)v[5];
  t.round = (uint8_t)v[6];
  t.totalRounds = (uint8_t)v[7];
  t.flags = (uint8_t)v[8];
  t.rev = (uint8_t)v[9];
  if (HH.onTimerState) HH.onTimerState(t);
}

static void handleSession(const Command &c) {
  static HostSession s;  // large; only touched from loop()
  memset(&s, 0, sizeof s);
  uint32_t v[8] = {};
  for (int i = 0; i < 8; i++) hostcore::parseUint(c.arg(i), 0xFFFFFFFFu, v[i]);
  s.rev = (uint8_t)v[0];
  s.flags = (uint8_t)v[1];
  s.totalEnds = (uint8_t)v[2];
  s.practiceEnds = (uint8_t)v[3];
  s.prepMs = v[4];
  s.shootMs = v[5];
  s.warnMs = v[6];
  s.delayMs = v[7];
  strncpy(s.seqId, c.arg(8), 16);  // hostcore enforced 1-16 characters
  const char *g = c.arg(9);
  while (*g && s.groupsN < 8) {
    const char *end = strchr(g, ':');
    const size_t len = end ? (size_t)(end - g) : strlen(g);
    memcpy(s.groups[s.groupsN], g, len > 8 ? 8 : len);
    s.groupsN++;
    if (!end) break;
    g = end + 1;
  }
  if (HH.onSession) HH.onSession(s);
}

static uint8_t hexByte(const char *m) {
  return (uint8_t)(((m[0] <= '9' ? m[0] - '0' : m[0] - 'A' + 10) << 4) | (m[1] <= '9' ? m[1] - '0' : m[1] - 'A' + 10));
}

static void handlePair(const Command &c) {
  const char *sub = c.arg(0);
  uint8_t mac[6] = {0};
  uint32_t a = 0, b = 0;
  bool ok = true;
  if (!strcmp(sub, "open")) {
    hostcore::parseUint(c.arg(1), 120, a);
    ok = HH.onPairOpen && HH.onPairOpen((uint8_t)a);
  } else if (!strcmp(sub, "close")) {
    if (HH.onPairClose) HH.onPairClose();
  } else if (!strcmp(sub, "accept")) {
    hostcore::parseMac(c.arg(1), mac);
    ok = HH.onPairAccept && HH.onPairAccept(mac, hexByte(c.arg(2)));
  } else if (!strcmp(sub, "reject")) {
    hostcore::parseMac(c.arg(1), mac);
    ok = HH.onPairReject && HH.onPairReject(mac);
  } else if (!strcmp(sub, "del")) {
    hostcore::parseMac(c.arg(1), mac);
    ok = HH.onPairDelete && HH.onPairDelete(mac);
  } else if (!strcmp(sub, "ack")) {
    hostcore::parseMac(c.arg(1), mac);
    hostcore::parseUint(c.arg(2), 0xFFFFFFFFu, a);
    hostcore::parseUint(c.arg(3), 1, b);
    ok = HH.onPairAck && HH.onPairAck(mac, a, (uint8_t)b);
  } else if (!strcmp(sub, "tx")) {
    hostcore::parseUint(c.arg(1), 7, a);
    ok = HH.onPairTx && HH.onPairTx((uint8_t)a);
  } else {
    ok = false;  // req / cmd / paired / state travel the other way
  }
  if (!ok) sendError("BA");
}

static bool isHostCommand(char c) { return c && strchr("LSBGTHVMRCQUJP", c); }

// A validated command from the host.
static void handle(const Command &c) {
  switch (c.cmd) {
    case 'V': {
      lastSoundId = 0;  // a (re)connecting host restarts its ids; never drop its first whistle
      char b[48];
      if (hostcore::fmtHello(b, sizeof b, PROTO, fwVersion, caps)) hostlinkSendFrame(b);
      break;
    }
    case 'L':
      if (HH.onLights) HH.onLights(lightsMask(c.arg(0)));
      break;
    case 'S':
      handleSound(c);
      break;
    case 'B':
      if (HH.onBuzz) HH.onBuzz(c.arg(0)[0] == '1');
      break;
    case 'H': {
      // $H,<seq>,<lights>,<group>: re-assert lights, ACK the sequence number.
      if (HH.onLights) HH.onLights(lightsMask(c.arg(1)));
      uint32_t seq = 0;
      hostcore::parseUint(c.arg(0), 0xFFFFFFFFu, seq);
      char b[24];
      if (hostcore::fmtAck(b, sizeof b, seq)) hostlinkSendFrame(b);
      break;
    }
    case 'M': {
      uint32_t m = 0;
      hostcore::parseUint(c.arg(0), 3, m);
      if (!HH.onMode || !HH.onMode((uint8_t)m)) sendError("BA");
      break;
    }
    case 'G':
    case 'T':
      break;  // no group or time display on this rig; validated, then ignored
    case 'R': {
      uint32_t id = 0, session = 0;
      if (c.argc == 3) {
        hostcore::parseHexU32(c.arg(1), id);
        hostcore::parseUint(c.arg(2), 0xFFFFFFFFu, session);
      }
      if (!HH.onRole || !HH.onRole(c.arg(0)[0], id, session)) sendError("BA");
      break;
    }
    case 'C': {
      const char *key = c.arg(0), *value = c.arg(1);
      if (!HH.onConfig || !HH.onConfig(key, value)) {
        sendError("BA");
        break;
      }
      // The mesh key is write-only: the answer carries zeros, never the key.
      hostlinkSendConfig(key, strcmp(key, "mkey") ? value : "00000000000000000000000000000000");
      break;
    }
    case 'Q':
      if (HH.onConfigQuery) HH.onConfigQuery();
      break;
    case 'U':
      handleTimer(c);
      break;
    case 'J':
      handleSession(c);
      break;
    case 'P':
      handlePair(c);
      break;
    default:
      sendError("UC");  // a valid frame of the MCU-to-host direction ($I $A $K $E $N $O $D $F $W $Y)
  }
}

static void processLine() {
  if (reader.overflowed()) { sendError("OV"); return; }
  const size_t len = reader.size();
  const char *line = reader.data();
  if (len == 0 || (len == 1 && line[0] == '\r')) return;
  static Command cmd;  // ~180 bytes: keep it off the loop task's stack
  const Err e = hostcore::parse(line, len, cmd);
  if (e == Err::MF) return;  // malformed framing: dropped silently
  if (e != Err::None) { sendError(hostcore::errCode(e)); return; }
  if (isHostCommand(cmd.cmd)) {
    lastValidMs = millis();
    everValid = true;
  }
  handle(cmd);
}

void hostlinkBegin(const HostHandlers &handlers, const char *version, const char *capabilities) {
  HH = handlers;
  fwVersion = version;
  caps = capabilities;
  Serial.begin(115200);
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
  Serial.setTxTimeoutMs(0);  // a stand-alone box with no USB host must never block on print
#endif
}

void hostlinkPoll() {
  while (Serial.available()) {
    if (reader.feed((char)Serial.read())) processLine();
  }
}
