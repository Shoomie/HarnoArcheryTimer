// Plain data passed from the serial link (hostlink) to the mesh node (radio): the typed contents of $U and $J.
#pragma once
#include <Arduino.h>

struct HostTimer {          // $U
  uint8_t mode;             // 0 idle, 1 running, 2 waiting, 3 finished
  uint8_t phase;
  uint32_t remainingMs;     // valid at the moment the frame was received
  uint8_t endNo, totalEnds, group, round, totalRounds;
  uint8_t flags;            // bit0 paused, bit1 emergency latch, bit2 buzzer
  uint8_t rev;
};

struct HostSession {        // $J
  uint8_t rev, flags, totalEnds, practiceEnds;  // flags: bit0 alternate order, bit1 auto-advance
  uint32_t prepMs, shootMs, warnMs, delayMs;    // 0xFFFFFFFF keeps the sequence's value
  char seqId[17];                               // 1-16 chars
  uint8_t groupsN;                              // 1-8
  char groups[8][9];                            // 1-8 chars each
};
