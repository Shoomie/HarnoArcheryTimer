// USB serial link to the host: protocol v1 and serial v2 framing and command handling (docs/protocol.md).
// The frame logic (checksum, line framing, 64/160 byte rule, parsing, argument validation) lives in lib/hostcore and is
// tested natively; this file only moves bytes and turns validated commands into handler calls.
// This module knows nothing about arbitration or the radio; main.cpp wires the handlers.
#pragma once
#include <Arduino.h>

#include "hostmsg.h"

struct HostHandlers {
  void (*onLights)(uint8_t mask);                                  // $L and $H (G=1 Y=2 R=4)
  // $S, host retransmissions already dropped. blastMs/gapMs are 0 when the host sent no timing.
  void (*onSound)(int count, uint16_t blastMs, uint16_t gapMs);
  void (*onBuzz)(bool on);                                         // $B
  bool (*onMode)(uint8_t mode);                                    // $M (legacy); false = reject
  bool (*onRole)(char role, uint32_t masterId, uint32_t session);  // $R; false = reject
  bool (*onConfig)(const char *key, const char *value);            // $C; true = stored (hostlink echoes it)
  void (*onConfigQuery)();                                         // $Q: answer with hostlinkSendConfig per key
  void (*onTimerState)(const HostTimer &t);                        // $U
  void (*onSession)(const HostSession &s);                         // $J
  bool (*onPairOpen)(uint8_t seconds);                             // $P,open
  void (*onPairClose)();                                           // $P,close
  bool (*onPairAccept)(const uint8_t mac[6], uint8_t mask);        // $P,accept
  bool (*onPairReject)(const uint8_t mac[6]);                      // $P,reject
  bool (*onPairDelete)(const uint8_t mac[6]);                      // $P,del
  bool (*onPairAck)(const uint8_t mac[6], uint32_t counter, uint8_t result);  // $P,ack
  bool (*onPairTx)(uint8_t action);                                // $P,tx
};

void hostlinkBegin(const HostHandlers &handlers, const char *fwVersion, const char *caps);
void hostlinkPoll();                      // call every loop(): reads and handles complete lines
bool hostlinkAlive(uint32_t timeoutMs);   // a valid host command arrived within timeoutMs
void hostlinkSendFrame(const char *body); // adds '$', checksum and newline (drops a frame that is over its limit)
void hostlinkSendStatus(uint8_t mode, uint8_t peers, char source);  // $N,<mode>,<peers>,<H|E|N> (v1 hosts)
void hostlinkSendConfig(const char *key, const char *value);        // $C,<key>,<value>
