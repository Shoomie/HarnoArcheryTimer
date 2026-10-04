// Native tests for firmware/lib/hostcore: replays firmware/test_vectors.txt (serial v1) and
// firmware/test_vectors_v2.txt (serial v2). Plain C++17, no framework.
// Usage: test_hostcore <firmware dir>   (the directory that holds the two vector files)
#define _CRT_SECURE_NO_WARNINGS
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "hostcore.h"

using namespace hostcore;

static int g_checks = 0, g_fails = 0;
#define CHECK(cond, ...)                               \
  do {                                                 \
    g_checks++;                                        \
    if (!(cond)) {                                     \
      g_fails++;                                       \
      std::printf("FAIL %s:%d: ", __FILE__, __LINE__); \
      std::printf(__VA_ARGS__);                        \
      std::printf("\n");                               \
    }                                                  \
  } while (0)

static std::string trimRight(std::string s) {
  while (!s.empty() && (s.back() == '\r' || s.back() == '\n')) s.pop_back();
  return s;
}

static std::vector<std::string> split(const std::string& s, char sep) {
  std::vector<std::string> out;
  std::string cur;
  std::istringstream is(s);
  while (std::getline(is, cur, sep)) out.push_back(cur);
  return out;
}

static Err parseStr(const std::string& frame, Command& c) { return parse(frame.c_str(), frame.size(), c); }

static const char* errName(Err e) { return e == Err::None ? "OK" : errCode(e); }

// One vector file. `count` receives the number of vectors replayed.
static void replay(const std::string& path, int& count) {
  std::ifstream f(path);
  CHECK(f.good(), "cannot open %s", path.c_str());
  std::string line;
  while (std::getline(f, line)) {
    line = trimRight(line);
    if (line.empty() || line[0] == '#') continue;
    const size_t arrow = line.rfind(" => ");
    CHECK(arrow != std::string::npos, "bad vector line: %s", line.c_str());
    if (arrow == std::string::npos) continue;
    const std::string frame = line.substr(0, arrow);
    const std::vector<std::string> want = split(line.substr(arrow + 4), ' ');
    count++;

    // 1. Direct parse.
    Command c;
    const Err e = parseStr(frame, c);
    if (want[0] == "OK") {
      CHECK(e == Err::None, "%s: expected OK, got %s", frame.c_str(), errName(e));
      if (e != Err::None) continue;
      CHECK(want.size() >= 2 && c.cmd == want[1][0] && want[1].size() == 1, "%s: command %c", frame.c_str(), c.cmd);
      CHECK(static_cast<size_t>(c.argc) + 2 == want.size(), "%s: %d args, vector has %d", frame.c_str(), c.argc,
            static_cast<int>(want.size()) - 2);
      for (size_t i = 0; i < c.argc && i + 2 < want.size(); i++) {
        const std::string a = c.arg(i)[0] ? c.arg(i) : "-";  // an empty argument is written '-'
        CHECK(a == want[i + 2], "%s: arg %d is '%s', vector says '%s'", frame.c_str(), static_cast<int>(i), a.c_str(),
              want[i + 2].c_str());
      }
      // 2. Re-encoding the parsed fields reproduces the frame byte for byte.
      std::string body(1, c.cmd);
      for (size_t i = 0; i < c.argc; i++) body += std::string(",") + c.arg(i);
      char out[kMaxLongFrame + 8];
      const size_t n = encodeFrame(body.c_str(), out, sizeof out);
      CHECK(n == frame.size() + 1 && std::string(out, n) == frame + "\n", "%s: re-encode gave %.*s", frame.c_str(),
            static_cast<int>(n), out);
    } else {
      CHECK(want[0] == "ERR" && want.size() == 2, "bad expectation: %s", line.c_str());
      CHECK(std::strcmp(errName(e), want[1].c_str()) == 0, "%s: expected ERR %s, got %s", frame.c_str(),
            want[1].c_str(), errName(e));
    }

    // 3. The same frame through the byte-wise LineReader (plain and CRLF), the way hostlink feeds it.
    for (int crlf = 0; crlf < 2; crlf++) {
      LineReader r;
      bool got = false;
      const std::string wire = frame + (crlf ? "\r\n" : "\n");
      for (char ch : wire) got = r.feed(ch);
      CHECK(got, "%s: reader did not complete the line", frame.c_str());
      Err er;
      Command c2;
      if (r.overflowed()) er = Err::OV;
      else er = parse(r.data(), r.size(), c2);
      if (r.overflowed()) {
        CHECK(want[0] == "ERR" && want[1] == "OV", "%s: reader overflow but vector says %s", frame.c_str(), line.c_str());
      } else {
        CHECK(er == e, "%s: reader path gives %s, direct %s", frame.c_str(), errName(er), errName(e));
      }
    }
  }
}

// Builders for the MCU-to-host frames must reproduce the vectors (encode/parse symmetry).
static void checkBuilders(const std::string& path) {
  std::ifstream f(path);
  std::string line;
  int built = 0;
  while (std::getline(f, line)) {
    line = trimRight(line);
    const size_t arrow = line.rfind(" => ");
    if (line.empty() || line[0] == '#' || arrow == std::string::npos) continue;
    if (line.compare(arrow + 4, 3, "OK ") != 0) continue;
    const std::string frame = line.substr(0, arrow);
    Command c;
    if (parseStr(frame, c) != Err::None) continue;
    char body[kMaxLongFrame + 8];
    size_t n = 0;
    uint32_t a = 0, b = 0, d = 0, e = 0, g = 0;
    uint8_t mac[6], fw[3];
    switch (c.cmd) {
      case 'I':
        parseUint(c.arg(0), 255, a);
        n = fmtHello(body, sizeof body, a, c.arg(1), c.arg(2));
        break;
      case 'A':
        parseUint(c.arg(0), 0xFFFFFFFFu, a);
        n = fmtAck(body, sizeof body, a);
        break;
      case 'K':
        parseUint(c.arg(0), 99, a);
        n = fmtButton(body, sizeof body, a, c.arg(1)[0] == '1');
        break;
      case 'E': n = fmtError(body, sizeof body, c.arg(0)); break;
      case 'N':
        parseUint(c.arg(0), 3, a);
        parseUint(c.arg(1), 99, b);
        n = fmtEspNowStatus(body, sizeof body, a, b, c.arg(2)[0]);
        break;
      case 'O':
        parseUint(c.arg(2), 99, a);
        parseHexU32(c.arg(4), b);
        parseUint(c.arg(5), 13, d);
        n = fmtMeshStatus(body, sizeof body, c.arg(0)[0], c.arg(1)[0], a, c.arg(3)[0] == '1', b, d);
        break;
      case 'D':
        parseMac(c.arg(0), mac);
        if (c.argc == 2) {
          n = fmtRosterGone(body, sizeof body, mac);
        } else {
          parseUint(c.arg(3), 127, a);
          unsigned x, y, z;
          std::sscanf(c.arg(4), "%u.%u.%u", &x, &y, &z);
          fw[0] = static_cast<uint8_t>(x);
          fw[1] = static_cast<uint8_t>(y);
          fw[2] = static_cast<uint8_t>(z);
          n = fmtRoster(body, sizeof body, mac, c.arg(1)[0], std::strcmp(c.arg(2), "-") ? c.arg(2) : "", a, fw,
                        std::strcmp(c.arg(5), "-") ? c.arg(5) : "");
        }
        break;
      case 'F':
      case 'W':
      case 'Y': {
        uint8_t pay[100];
        size_t pn = 0;
        if (hexDecode(c.arg(0), pay, sizeof pay, pn)) n = fmtFeed(body, sizeof body, c.cmd, pay, pn);
        break;
      }
      case 'C': n = fmtConfig(body, sizeof body, c.arg(0), c.arg(1)); break;
      case 'P': {
        const std::string sub = c.arg(0);
        if (sub == "req") {
          parseMac(c.arg(1), mac);
          n = fmtPairRequest(body, sizeof body, mac, std::strcmp(c.arg(2), "-") ? c.arg(2) : "",
                             std::strcmp(c.arg(3), "-") ? c.arg(3) : "");
        } else if (sub == "cmd") {
          parseMac(c.arg(1), mac);
          parseUint(c.arg(2), 7, a);
          parseUint(c.arg(3), 0xFFFFFFFFu, g);
          n = fmtPairCommand(body, sizeof body, mac, a, g);
        } else if (sub == "paired") {
          parseMac(c.arg(1), mac);
          n = fmtPairDone(body, sizeof body, mac);
        } else if (sub == "state") {
          parseUint(c.arg(2), 120, a);
          n = fmtPairState(body, sizeof body, c.arg(1)[0] == '1', a);
        }
        break;
      }
      default: break;  // host-to-MCU frames have no builder here
    }
    (void)e;
    if (n == 0) continue;
    char out[kMaxLongFrame + 8];
    const size_t m = encodeFrame(body, out, sizeof out);
    CHECK(m > 0 && std::string(out, m) == frame + "\n", "builder for %s gave %.*s", frame.c_str(), static_cast<int>(m),
          out);
    built++;
  }
  CHECK(built >= 15, "only %d builder checks ran for %s", built, path.c_str());
  std::printf("  builder symmetry: %d frames\n", built);
}

static void checkHelpers() {
  CHECK(checksum("L,G", 3) == 0x27, "checksum of L,G");
  CHECK(frameLimit('J') == 160 && frameLimit('F') == 160 && frameLimit('W') == 160 && frameLimit('Y') == 160 &&
            frameLimit('D') == 160 && frameLimit('P') == 160,
        "long commands");
  CHECK(frameLimit('C') == 64 && frameLimit('L') == 64 && frameLimit('U') == 64 && frameLimit('R') == 64 &&
            frameLimit('S') == 64 && frameLimit('O') == 64,
        "short commands");
  // A 64-byte short frame (63 chars + newline) parses; 65 is OV. A 160-byte long frame parses; 161 is OV.
  {
    std::string name(12, 'A');
    char out[200];
    CHECK(encodeFrame("L,G", out, sizeof out) == 8 && std::strcmp(out, "$L,G*27\n") == 0, "encodeFrame");
    std::string body64 = "X," + std::string(64 - 1 - 3 - 2 - 1, '9');  // frame = 1 + body + 3 + 1 = 64
    CHECK(encodeFrame(body64.c_str(), out, sizeof out) == 64, "64-byte short frame encodes");
    std::string body65 = body64 + "9";
    CHECK(encodeFrame(body65.c_str(), out, sizeof out) == 0, "65-byte short frame refused");
    std::string longBody = "Y," + std::string(160 - 1 - 3 - 2 - 1, 'A');
    CHECK(encodeFrame(longBody.c_str(), out, sizeof out) == 160, "160-byte long frame encodes");
    CHECK(encodeFrame((longBody + "A").c_str(), out, sizeof out) == 0, "161-byte long frame refused");
    CHECK(encodeFrame("L,G", out, 8) == 0 && encodeFrame("L,G", out, 9) == 8, "capacity respected");
  }
  // Line reader: a line over 160 bytes is flagged and the next line is clean; empty lines come through.
  {
    LineReader r;
    std::string big(300, 'x');
    bool done = false;
    for (char c : big) done = r.feed(c);
    CHECK(!done, "no line before the newline");
    done = r.feed('\n');
    CHECK(done && r.overflowed(), "overflow flagged");
    for (char c : std::string("$V*56")) r.feed(c);
    done = r.feed('\n');
    CHECK(done && !r.overflowed() && r.size() == 5, "next line is clean");
    done = r.feed('\n');
    CHECK(done && r.size() == 0, "empty line");
  }
  // UART boot noise (classic ESP32 behind a USB-UART bridge): a garbage line is rejected without side effects, the hello
  // after it parses, and a banner with no final newline is dropped by the same '$' restart rule hostlink.cpp applies.
  {
    LineReader r;
    Command c;
    bool done = false;
    for (char ch : std::string("ets Jun  8 2016 00:22:57\n")) done = r.feed(ch);
    CHECK(done && parse(r.data(), r.size(), c) != Err::None, "boot garbage line is rejected");
    for (char ch : std::string("$V*56")) r.feed(ch);
    done = r.feed('\n');
    CHECK(done && parse(r.data(), r.size(), c) == Err::None && c.cmd == 'V', "hello after a garbage line parses");
    for (char ch : std::string("rst:0x1 (POWERON),boot:0x13 $V*56")) {
      if (ch == '$' && r.size() > 0 && r.data()[0] != '$') r.feed('\n');
      r.feed(ch);
    }
    done = r.feed('\n');
    CHECK(done && parse(r.data(), r.size(), c) == Err::None && c.cmd == 'V', "hello after a banner without newline");
  }
  // Number and hex helpers.
  uint32_t v = 0;
  CHECK(parseUint("4294967295", 0xFFFFFFFFu, v) && v == 0xFFFFFFFFu, "u32 max");
  CHECK(!parseUint("4294967296", 0xFFFFFFFFu, v), "u32 overflow");
  CHECK(!parseUint("01", 9, v) && !parseUint("", 9, v) && !parseUint("-1", 9, v) && !parseUint("+1", 9, v), "canonical");
  CHECK(parseHexU32("0000ABCD", v) && v == 0xABCD && !parseHexU32("0000abcd", v) && !parseHexU32("ABCD", v), "id hex");
  uint8_t mac[6];
  CHECK(parseMac("AABBCCDDEEFF", mac) && mac[0] == 0xAA && mac[5] == 0xFF && !parseMac("AABBCCDDEEF", mac), "mac");
  char hx[13];
  macToHex(mac, hx);
  CHECK(std::strcmp(hx, "AABBCCDDEEFF") == 0, "mac to hex");
  uint8_t buf[4];
  size_t n = 0;
  CHECK(hexDecode("0A0B", buf, 4, n) && n == 2 && buf[1] == 0x0B, "hex decode");
  CHECK(!hexDecode("0a0b", buf, 4, n) && !hexDecode("0A0", buf, 4, n) && !hexDecode("0A0B0C0D0E", buf, 4, n), "hex reject");
}

// Spot checks that a host must be able to rely on (things the vectors imply but the replay would not name).
static void checkSemantics() {
  Command c;
  // $S with 1, 2 and 4 arguments is valid, 3 is not.
  CHECK(parseStr("$S,1*4E", c) == Err::None && c.argc == 1, "S one arg");
  CHECK(parseStr("$S,1,7,500,500*55", c) == Err::None && c.argc == 4, "S four args");
  CHECK(parseStr("$S,1,7,500*4C", c) == Err::BA, "S three args");
  // $J sequence id limit: 16 characters pass, 17 do not (WP-H gap).
  auto withBody = [&](const std::string& body, Command& out) {
    char fr[kMaxLongFrame + 8];
    size_t n = encodeFrame(body.c_str(), fr, sizeof fr);
    return n ? parse(fr, n - 1, out) : Err::OV;
  };
  CHECK(withBody("J,1,0,1,0,4294967295,4294967295,4294967295,5000," + std::string(16, 'a') + ",AB", c) == Err::None,
        "16-char sequence id");
  CHECK(withBody("J,1,0,1,0,4294967295,4294967295,4294967295,5000," + std::string(17, 'a') + ",AB", c) == Err::BA,
        "17-char sequence id");
  // Eight groups pass, nine do not.
  CHECK(withBody("J,1,0,1,0,1,1,1,1,x,A:B:C:D:E:F:G:H", c) == Err::None, "8 groups");
  CHECK(withBody("J,1,0,1,0,1,1,1,1,x,A:B:C:D:E:F:G:H:I", c) == Err::BA, "9 groups");
  // A short frame of an unknown command with a bad checksum is CS (checksum before command).
  CHECK(parseStr("$Z*5B", c) == Err::CS && parseStr("$Z*5A", c) == Err::UC, "CS before UC");
  // Carriage return is dropped, an extra one is garbage.
  CHECK(parse("$V*56\r", 6, c) == Err::None, "CRLF");
  // Typed access after parse.
  CHECK(parseStr("$R,M,0000ABCD,7*00", c) == Err::None, "R parses");
  uint32_t id = 0, session = 0;
  CHECK(parseHexU32(c.arg(1), id) && id == 0xABCD && parseUint(c.arg(2), 0xFFFFFFFFu, session) && session == 7, "R fields");
}

int main(int argc, char** argv) {
  if (argc < 2) {
    std::printf("usage: test_hostcore <firmware dir>\n");
    return 2;
  }
  const std::string fw = argv[1];
  int v1 = 0, v2 = 0;
  replay(fw + "/test_vectors.txt", v1);
  replay(fw + "/test_vectors_v2.txt", v2);
  std::printf("  vectors replayed: %d (v1) + %d (v2)\n", v1, v2);
  CHECK(v1 > 100 && v2 > 90, "too few vectors: %d + %d", v1, v2);
  checkBuilders(fw + "/test_vectors.txt");
  checkBuilders(fw + "/test_vectors_v2.txt");
  checkHelpers();
  checkSemantics();
  std::printf("%d checks, %d failed\n", g_checks, g_fails);
  return g_fails ? 1 : 0;
}
