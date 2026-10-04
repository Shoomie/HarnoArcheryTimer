// Pure serial-frame logic of docs/protocol.md (v1 and serial v2): XOR checksum, line framing with the
// 64 / 160 byte rule, command parsing and argument validation, and builders for the MCU-to-host frames.
// Mirrors src/archerytimer/hardware/protocol.py check for check (order: OV, MF, CS, UC, BA).
// No Arduino includes, no heap: replayed natively against firmware/test_vectors.txt and test_vectors_v2.txt.
// **Not verified on hardware** (native tests only).
#pragma once
#include <cstddef>
#include <cstdint>

namespace hostcore {

constexpr size_t kMaxShortFrame = 64;   // including the newline
constexpr size_t kMaxLongFrame = 160;   // J F W Y D P, including the newline
constexpr size_t kMaxArgs = 12;         // no valid command has more than 10

enum class Err : uint8_t { None, OV, MF, CS, UC, BA };

// "OV", "CS", "UC", "BA" go on the wire in $E; "MF" is never sent (silent drop).
const char* errCode(Err e);

bool isLongCommand(char cmd);           // J F W Y D P
size_t frameLimit(char cmd);            // 160 for the long commands, else 64

uint8_t checksum(const char* s, size_t n);  // XOR of the bytes

// "$<body>*XX\n" plus a NUL (uppercase hex). Returns the length without the NUL; 0 if `cap` is too small
// (needs length + 1) or the frame exceeds its 64 / 160 byte limit.
size_t encodeFrame(const char* body, char* out, size_t cap);

// Byte-wise line framing. feed() returns true when a '\n' completed a line (an empty line included); then read
// data()/size() (CR still attached) and overflowed(). The next feed() starts a new line.
class LineReader {
 public:
  bool feed(char c);
  const char* data() const { return buf_; }
  size_t size() const { return len_; }
  bool overflowed() const { return overflow_; }  // more than 160 bytes arrived before the newline

 private:
  char buf_[kMaxLongFrame + 2] = {};
  size_t len_ = 0;
  bool overflow_ = false;
  bool done_ = false;
};

struct Command {
  char cmd = 0;
  uint8_t argc = 0;
  uint8_t off[kMaxArgs] = {};
  char text[kMaxLongFrame + 2] = {};
  const char* arg(size_t i) const { return text + off[i]; }
};

// Parses one received line (without '\n'; a trailing '\r' is dropped). Every frame of docs/protocol.md is
// accepted, in both directions; the caller acts only on the ones it may receive and answers UC to the rest.
// On Err::None the arguments are valid for the command and can be converted with the helpers below.
Err parse(const char* line, size_t len, Command& out);

// --- conversion helpers (inputs already validated by parse; they re-check and return false if not) -----------
bool parseUint(const char* s, uint32_t max, uint32_t& out);  // canonical decimal, as the protocol requires
bool parseHexU32(const char* s, uint32_t& out);              // exactly 8 uppercase hex digits
bool parseMac(const char* s, uint8_t mac[6]);                // exactly 12 uppercase hex digits
bool hexDecode(const char* s, uint8_t* out, size_t cap, size_t& n);  // uppercase hex pairs
void hexEncode(const uint8_t* in, size_t n, char* out);      // writes 2n chars and a NUL
void macToHex(const uint8_t mac[6], char out[13]);

// --- MCU-to-host body builders (no '$', checksum or newline: pass to encodeFrame). Return length, 0 = no fit ---
size_t fmtHello(char* out, size_t cap, uint32_t proto, const char* fw, const char* caps);       // I
size_t fmtAck(char* out, size_t cap, uint32_t seq);                                              // A
size_t fmtButton(char* out, size_t cap, uint32_t id, bool down);                                 // K
size_t fmtError(char* out, size_t cap, const char* code);                                        // E
size_t fmtEspNowStatus(char* out, size_t cap, uint32_t mode, uint32_t peers, char src);          // N
size_t fmtMeshStatus(char* out, size_t cap, char role, char src, uint32_t peers, bool conflict,
                     uint32_t master_id, uint32_t chan);                                         // O
size_t fmtRoster(char* out, size_t cap, const uint8_t mac[6], char kind, const char* caps, uint32_t rssi,
                 const uint8_t fw[3], const char* name);                                         // D (caps/name "" = -)
size_t fmtRosterGone(char* out, size_t cap, const uint8_t mac[6]);                               // D gone
size_t fmtFeed(char* out, size_t cap, char letter, const uint8_t* payload, size_t n);            // F W Y
size_t fmtPairRequest(char* out, size_t cap, const uint8_t mac[6], const char* name, const char* caps);
size_t fmtPairCommand(char* out, size_t cap, const uint8_t mac[6], uint32_t action, uint32_t counter);
size_t fmtPairDone(char* out, size_t cap, const uint8_t mac[6]);
size_t fmtPairState(char* out, size_t cap, bool open, uint32_t seconds_left);
size_t fmtConfig(char* out, size_t cap, const char* key, const char* value);                     // C

}  // namespace hostcore
