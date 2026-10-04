#include "hostcore.h"

#include <cstdio>
#include <cstring>

namespace hostcore {

namespace {

constexpr uint32_t kU32Max = 0xFFFFFFFFu;

bool isUpperHex(char c) { return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F'); }
uint8_t hexNibble(char c) { return static_cast<uint8_t>(c <= '9' ? c - '0' : c - 'A' + 10); }

bool allUpperHex(const char* s, size_t n) {
  for (size_t i = 0; i < n; i++)
    if (!isUpperHex(s[i])) return false;
  return true;
}

bool hasLen(const char* s, size_t n) { return std::strlen(s) == n; }

bool isNameChar(char c) {
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-';
}

// [A-Za-z0-9_-]{1,max}
bool nameOk(const char* s, size_t max) {
  const size_t n = std::strlen(s);
  if (n < 1 || n > max) return false;
  for (size_t i = 0; i < n; i++)
    if (!isNameChar(s[i])) return false;
  return true;
}

// [A-Z0-9]{1,8}
bool groupOk(const char* s, size_t n) {
  if (n < 1 || n > 8) return false;
  for (size_t i = 0; i < n; i++)
    if (!((s[i] >= 'A' && s[i] <= 'Z') || (s[i] >= '0' && s[i] <= '9'))) return false;
  return true;
}

bool lightsOk(const char* s) {
  if (std::strcmp(s, "O") == 0) return true;
  if (!*s) return false;
  bool seen[3] = {false, false, false};
  for (; *s; ++s) {
    const int i = *s == 'G' ? 0 : *s == 'Y' ? 1 : *s == 'R' ? 2 : -1;
    if (i < 0 || seen[i]) return false;
    seen[i] = true;
  }
  return true;
}

// Every letter of `s` is in `allowed`, no repeats (empty is fine).
bool capsSubset(const char* s, const char* allowed) {
  bool seen[128] = {};
  for (; *s; ++s) {
    const unsigned char c = static_cast<unsigned char>(*s);
    if (c >= 128 || !std::strchr(allowed, *s) || seen[c]) return false;
    seen[c] = true;
  }
  return true;
}

bool rosterCapsOk(const char* s) { return std::strcmp(s, "-") == 0 || (*s && capsSubset(s, "LSBKR")); }
bool rosterNameOk(const char* s) { return std::strcmp(s, "-") == 0 || nameOk(s, 12); }

bool flagOk(const char* s) { return (s[0] == '0' || s[0] == '1') && !s[1]; }

bool uintOk(const char* s, uint32_t max) {
  uint32_t v;
  return parseUint(s, max, v);
}

bool rangedOk(const char* s, uint32_t lo, uint32_t hi) {
  uint32_t v;
  return parseUint(s, hi, v) && v >= lo;
}

bool macOk(const char* s) { return hasLen(s, 12) && allUpperHex(s, 12); }

bool blastOk(const char* s) {
  uint32_t v;
  return parseUint(s, 2000, v) && v >= 10 && v % 10 == 0;
}

// Even number of uppercase hex digits, at least one byte; exact (bytes) or any when exact == 0.
bool payloadOk(const char* s, size_t exact) {
  const size_t n = std::strlen(s);
  if (n == 0 || n % 2 || !allUpperHex(s, n)) return false;
  return exact == 0 || n / 2 == exact;
}

bool configValueOk(const char* key, const char* v) {
  if (std::strcmp(key, "name") == 0) return nameOk(v, 12);
  if (std::strcmp(key, "lights") == 0 || std::strcmp(key, "sound") == 0 || std::strcmp(key, "radio") == 0 ||
      std::strcmp(key, "remote") == 0)
    return flagOk(v);
  if (std::strcmp(key, "chan") == 0) return rangedOk(v, 1, 13);
  if (std::strcmp(key, "mkey") == 0) return hasLen(v, 32) && allUpperHex(v, 32);
  if (std::strlen(key) == 4 && std::strncmp(key, "btn", 3) == 0 && key[3] >= '1' && key[3] <= '4') return uintOk(v, 7);
  return false;  // unknown key
}

bool semverOk(const char* s) {
  int dots = 0;
  bool digit = false;
  for (; *s; ++s) {
    if (*s >= '0' && *s <= '9') digit = true;
    else if (*s == '.' && digit && dots < 2) { dots++; digit = false; }
    else return false;
  }
  return dots == 2 && digit;
}

bool fwOk(const char* s) {
  const size_t n = std::strlen(s);
  if (n < 1 || n > 16) return false;
  for (size_t i = 0; i < n; i++) {
    const char c = s[i];
    if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '_' ||
          c == '+' || c == '-'))
      return false;
  }
  return true;
}

bool roleOk(const char* s) { return s[0] && !s[1] && std::strchr("MFEN", s[0]); }

bool validateRole(const Command& c) {
  if (c.argc != 1 && c.argc != 3) return false;
  if (!roleOk(c.arg(0))) return false;
  const bool needsId = c.arg(0)[0] == 'M' || c.arg(0)[0] == 'F';
  if (needsId != (c.argc == 3)) return false;
  if (!needsId) return true;
  uint32_t id, session;
  if (!parseHexU32(c.arg(1), id) || id == 0) return false;
  return parseUint(c.arg(2), kU32Max, session) && session >= 1;
}

bool validateSession(const Command& c) {
  if (c.argc != 10) return false;
  uint32_t v;
  if (!parseUint(c.arg(0), 255, v)) return false;
  if (!parseUint(c.arg(1), 3, v)) return false;
  if (!parseUint(c.arg(2), 255, v) || !parseUint(c.arg(3), 255, v)) return false;
  for (int i = 4; i <= 7; i++)
    if (!parseUint(c.arg(i), kU32Max, v)) return false;
  if (!nameOk(c.arg(8), 16)) return false;
  // groups: AB:CD:..., 1..8 of [A-Z0-9]{1,8}
  const char* g = c.arg(9);
  int n = 0;
  for (;;) {
    const char* end = std::strchr(g, ':');
    const size_t len = end ? static_cast<size_t>(end - g) : std::strlen(g);
    if (!groupOk(g, len)) return false;
    if (++n > 8) return false;
    if (!end) break;
    g = end + 1;
  }
  return true;
}

bool validatePair(const Command& c) {
  if (c.argc < 1) return false;
  const char* sub = c.arg(0);
  const int rest = c.argc - 1;
  auto is = [&](const char* s) { return std::strcmp(sub, s) == 0; };
  if (is("open")) return rest == 1 && rangedOk(c.arg(1), 1, 120);
  if (is("close")) return rest == 0;
  if (is("accept")) {
    if (rest != 2 || !macOk(c.arg(1))) return false;
    const char* m = c.arg(2);
    if (!hasLen(m, 2) || !allUpperHex(m, 2)) return false;
    return ((hexNibble(m[0]) << 4) | hexNibble(m[1])) <= 0x7F;
  }
  if (is("reject") || is("del") || is("paired")) return rest == 1 && macOk(c.arg(1));
  if (is("ack")) return rest == 3 && macOk(c.arg(1)) && uintOk(c.arg(2), kU32Max) && uintOk(c.arg(3), 1);
  if (is("tx")) return rest == 1 && rangedOk(c.arg(1), 1, 7);
  if (is("req")) return rest == 3 && macOk(c.arg(1)) && rosterNameOk(c.arg(2)) && rosterCapsOk(c.arg(3));
  if (is("cmd")) return rest == 3 && macOk(c.arg(1)) && rangedOk(c.arg(2), 1, 7) && uintOk(c.arg(3), kU32Max);
  if (is("state")) return rest == 2 && flagOk(c.arg(1)) && uintOk(c.arg(2), 120);
  return false;
}

bool validateRoster(const Command& c) {
  if (c.argc == 2 && std::strcmp(c.arg(1), "gone") == 0) return macOk(c.arg(0));
  if (c.argc != 6) return false;
  const char* k = c.arg(1);
  if (!(k[0] && !k[1] && std::strchr("NRMFE", k[0]))) return false;
  if (!semverOk(c.arg(4))) return false;
  return macOk(c.arg(0)) && rosterCapsOk(c.arg(2)) && uintOk(c.arg(3), 127) && rosterNameOk(c.arg(5));
}

bool validate(const Command& c) {
  const int n = c.argc;
  uint32_t v;
  switch (c.cmd) {
    case 'L': return n == 1 && lightsOk(c.arg(0));
    case 'S': {
      if (n != 1 && n != 2 && n != 4) return false;
      if (n >= 2 && !(parseUint(c.arg(1), 255, v) && v != 0)) return false;
      if (n == 4 && !(blastOk(c.arg(2)) && blastOk(c.arg(3)))) return false;
      return uintOk(c.arg(0), 99);
    }
    case 'B': return n == 1 && flagOk(c.arg(0));
    case 'G': return n == 1 && groupOk(c.arg(0), std::strlen(c.arg(0)));
    case 'T': return n == 1 && uintOk(c.arg(0), kU32Max);
    case 'H':
      return n == 3 && uintOk(c.arg(0), kU32Max) && lightsOk(c.arg(1)) &&
             (c.arg(2)[0] == 0 || groupOk(c.arg(2), std::strlen(c.arg(2))));
    case 'V': return n == 0;
    case 'I': return n == 3 && uintOk(c.arg(0), 255) && fwOk(c.arg(1)) && capsSubset(c.arg(2), "LSBGTKNWR");
    case 'A': return n == 1 && uintOk(c.arg(0), kU32Max);
    case 'K': return n == 2 && parseUint(c.arg(0), 99, v) && v >= 1 && flagOk(c.arg(1));
    case 'M': return n == 1 && uintOk(c.arg(0), 3);
    case 'N':
      return n == 3 && uintOk(c.arg(0), 3) && uintOk(c.arg(1), 99) && c.arg(2)[0] && !c.arg(2)[1] &&
             std::strchr("HEN", c.arg(2)[0]);
    case 'E': {
      if (n != 1) return false;
      const char* e = c.arg(0);
      return !std::strcmp(e, "CS") || !std::strcmp(e, "UC") || !std::strcmp(e, "BA") || !std::strcmp(e, "OV");
    }
    case 'R': return validateRole(c);
    case 'C': return n == 2 && configValueOk(c.arg(0), c.arg(1));
    case 'Q': return n == 0;
    case 'U': {
      if (n != 10) return false;
      static const uint32_t max[10] = {3, 255, kU32Max, 255, 255, 255, 255, 255, 7, 255};
      for (int i = 0; i < 10; i++)
        if (!uintOk(c.arg(i), max[i])) return false;
      return true;
    }
    case 'J': return validateSession(c);
    case 'P': return validatePair(c);
    case 'O': {
      if (n != 6) return false;
      const char* r = c.arg(0);
      const char* s = c.arg(1);
      if (!roleOk(r) || !(s[0] && !s[1] && std::strchr("HEN", s[0]))) return false;
      uint32_t id;
      return uintOk(c.arg(2), 99) && flagOk(c.arg(3)) && parseHexU32(c.arg(4), id) && rangedOk(c.arg(5), 1, 13);
    }
    case 'D': return validateRoster(c);
    case 'F': return n == 1 && payloadOk(c.arg(0), 29);
    case 'W': return n == 1 && payloadOk(c.arg(0), 12);
    case 'Y': return n == 1 && payloadOk(c.arg(0), 0);
    default: return false;
  }
}

bool knownCommand(char c) { return c && std::strchr("LSBGTHVIAKMNERCQUJPODFWY", c) != nullptr; }

size_t finish(int n, size_t cap) { return (n > 0 && static_cast<size_t>(n) < cap) ? static_cast<size_t>(n) : 0; }

}  // namespace

const char* errCode(Err e) {
  switch (e) {
    case Err::OV: return "OV";
    case Err::MF: return "MF";
    case Err::CS: return "CS";
    case Err::UC: return "UC";
    case Err::BA: return "BA";
    default: return "";
  }
}

bool isLongCommand(char c) { return c && std::strchr("JFWYDP", c) != nullptr; }
size_t frameLimit(char cmd) { return isLongCommand(cmd) ? kMaxLongFrame : kMaxShortFrame; }

uint8_t checksum(const char* s, size_t n) {
  uint8_t x = 0;
  for (size_t i = 0; i < n; i++) x ^= static_cast<uint8_t>(s[i]);
  return x;
}

size_t encodeFrame(const char* body, char* out, size_t cap) {
  const size_t bl = std::strlen(body);
  const size_t total = 1 + bl + 3 + 1;  // $ body *XX \n
  if (bl == 0 || total + 1 > cap || total > frameLimit(body[0])) return 0;
  const int n = std::snprintf(out, cap, "$%s*%02X\n", body, checksum(body, bl));
  return (n > 0 && static_cast<size_t>(n) == total) ? total : 0;
}

bool LineReader::feed(char c) {
  if (done_) {
    len_ = 0;
    overflow_ = false;
    done_ = false;
  }
  if (c == '\n') {
    buf_[len_] = 0;
    done_ = true;
    return true;
  }
  if (overflow_) return false;
  if (len_ < kMaxLongFrame) buf_[len_++] = c;
  else overflow_ = true;
  return false;
}

Err parse(const char* line, size_t len, Command& out) {
  if (len > 0 && line[len - 1] == '\r') len--;
  const char letter = (len >= 2 && line[0] == '$') ? line[1] : 0;
  if (len + 1 > frameLimit(letter)) return Err::OV;
  // Framing: $ <printable body> * <two uppercase hex digits>
  if (len < 4 || line[0] != '$' || line[len - 3] != '*' || !isUpperHex(line[len - 2]) || !isUpperHex(line[len - 1]))
    return Err::MF;
  const size_t bl = len - 4;
  for (size_t i = 1; i <= bl; i++) {
    const unsigned char ch = static_cast<unsigned char>(line[i]);
    if (ch < 0x20 || ch > 0x7E) return Err::MF;
    if (ch == '$' || ch == '*') return Err::MF;  // stray delimiter
  }
  const uint8_t want = static_cast<uint8_t>((hexNibble(line[len - 2]) << 4) | hexNibble(line[len - 1]));
  if (checksum(line + 1, bl) != want) return Err::CS;

  std::memcpy(out.text, line + 1, bl);
  out.text[bl] = 0;
  out.cmd = 0;
  out.argc = 0;
  // Split on commas: text[0..first comma) is the command, the rest are the arguments (empty ones included).
  char* comma = std::strchr(out.text, ',');
  size_t total = 0;
  if (comma) {
    *comma = 0;
    char* p = comma + 1;
    for (;;) {
      if (total < kMaxArgs) out.off[total] = static_cast<uint8_t>(p - out.text);
      total++;
      char* next = std::strchr(p, ',');
      if (!next) break;
      *next = 0;
      p = next + 1;
    }
  }
  if (std::strlen(out.text) != 1 || !knownCommand(out.text[0])) return Err::UC;
  out.cmd = out.text[0];
  if (total > kMaxArgs) return Err::BA;
  out.argc = static_cast<uint8_t>(total);
  return validate(out) ? Err::None : Err::BA;
}

bool parseUint(const char* s, uint32_t max, uint32_t& out) {
  if (!*s) return false;
  if (s[0] == '0' && s[1]) return false;  // no leading zeros
  uint64_t v = 0;
  for (; *s; ++s) {
    if (*s < '0' || *s > '9') return false;
    v = v * 10 + static_cast<uint64_t>(*s - '0');
    if (v > max) return false;
  }
  out = static_cast<uint32_t>(v);
  return true;
}

bool parseHexU32(const char* s, uint32_t& out) {
  if (!hasLen(s, 8) || !allUpperHex(s, 8)) return false;
  uint32_t v = 0;
  for (int i = 0; i < 8; i++) v = (v << 4) | hexNibble(s[i]);
  out = v;
  return true;
}

bool parseMac(const char* s, uint8_t mac[6]) {
  if (!macOk(s)) return false;
  for (int i = 0; i < 6; i++) mac[i] = static_cast<uint8_t>((hexNibble(s[2 * i]) << 4) | hexNibble(s[2 * i + 1]));
  return true;
}

bool hexDecode(const char* s, uint8_t* out, size_t cap, size_t& n) {
  const size_t len = std::strlen(s);
  if (len % 2 || len / 2 > cap || !allUpperHex(s, len)) return false;
  n = len / 2;
  for (size_t i = 0; i < n; i++) out[i] = static_cast<uint8_t>((hexNibble(s[2 * i]) << 4) | hexNibble(s[2 * i + 1]));
  return true;
}

void hexEncode(const uint8_t* in, size_t n, char* out) {
  static const char d[] = "0123456789ABCDEF";
  for (size_t i = 0; i < n; i++) {
    out[2 * i] = d[in[i] >> 4];
    out[2 * i + 1] = d[in[i] & 15];
  }
  out[2 * n] = 0;
}

void macToHex(const uint8_t mac[6], char out[13]) { hexEncode(mac, 6, out); }

size_t fmtHello(char* out, size_t cap, uint32_t proto, const char* fw, const char* caps) {
  return finish(std::snprintf(out, cap, "I,%lu,%s,%s", static_cast<unsigned long>(proto), fw, caps), cap);
}
size_t fmtAck(char* out, size_t cap, uint32_t seq) {
  return finish(std::snprintf(out, cap, "A,%lu", static_cast<unsigned long>(seq)), cap);
}
size_t fmtButton(char* out, size_t cap, uint32_t id, bool down) {
  return finish(std::snprintf(out, cap, "K,%lu,%d", static_cast<unsigned long>(id), down ? 1 : 0), cap);
}
size_t fmtError(char* out, size_t cap, const char* code) { return finish(std::snprintf(out, cap, "E,%s", code), cap); }
size_t fmtEspNowStatus(char* out, size_t cap, uint32_t mode, uint32_t peers, char src) {
  return finish(std::snprintf(out, cap, "N,%lu,%lu,%c", static_cast<unsigned long>(mode),
                              static_cast<unsigned long>(peers), src),
                cap);
}
size_t fmtMeshStatus(char* out, size_t cap, char role, char src, uint32_t peers, bool conflict, uint32_t master_id,
                     uint32_t chan) {
  return finish(std::snprintf(out, cap, "O,%c,%c,%lu,%d,%08lX,%lu", role, src, static_cast<unsigned long>(peers),
                              conflict ? 1 : 0, static_cast<unsigned long>(master_id),
                              static_cast<unsigned long>(chan)),
                cap);
}
size_t fmtRoster(char* out, size_t cap, const uint8_t mac[6], char kind, const char* caps, uint32_t rssi,
                 const uint8_t fw[3], const char* name) {
  char m[13];
  macToHex(mac, m);
  return finish(std::snprintf(out, cap, "D,%s,%c,%s,%lu,%u.%u.%u,%s", m, kind, (caps && *caps) ? caps : "-",
                              static_cast<unsigned long>(rssi), fw[0], fw[1], fw[2], (name && *name) ? name : "-"),
                cap);
}
size_t fmtRosterGone(char* out, size_t cap, const uint8_t mac[6]) {
  char m[13];
  macToHex(mac, m);
  return finish(std::snprintf(out, cap, "D,%s,gone", m), cap);
}
size_t fmtFeed(char* out, size_t cap, char letter, const uint8_t* payload, size_t n) {
  if (cap < 3 + 2 * n + 1) return 0;
  out[0] = letter;
  out[1] = ',';
  hexEncode(payload, n, out + 2);
  return 2 + 2 * n;
}
size_t fmtPairRequest(char* out, size_t cap, const uint8_t mac[6], const char* name, const char* caps) {
  char m[13];
  macToHex(mac, m);
  return finish(std::snprintf(out, cap, "P,req,%s,%s,%s", m, (name && *name) ? name : "-", (caps && *caps) ? caps : "-"),
                cap);
}
size_t fmtPairCommand(char* out, size_t cap, const uint8_t mac[6], uint32_t action, uint32_t counter) {
  char m[13];
  macToHex(mac, m);
  return finish(std::snprintf(out, cap, "P,cmd,%s,%lu,%lu", m, static_cast<unsigned long>(action),
                              static_cast<unsigned long>(counter)),
                cap);
}
size_t fmtPairDone(char* out, size_t cap, const uint8_t mac[6]) {
  char m[13];
  macToHex(mac, m);
  return finish(std::snprintf(out, cap, "P,paired,%s", m), cap);
}
size_t fmtPairState(char* out, size_t cap, bool open, uint32_t seconds_left) {
  return finish(std::snprintf(out, cap, "P,state,%d,%lu", open ? 1 : 0, static_cast<unsigned long>(seconds_left)), cap);
}
size_t fmtConfig(char* out, size_t cap, const char* key, const char* value) {
  return finish(std::snprintf(out, cap, "C,%s,%s", key, value), cap);
}

}  // namespace hostcore
