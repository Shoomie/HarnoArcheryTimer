// PWM beeper (LEDC): a square wave at a given frequency on one pin, for a piezo or a small
// speaker behind a transistor. Optional: PIN_BEEP = -1 compiles it to no-ops.
//
// Two ways to use it:
//   beepTone(hz) / beepOff()      direct control, used to mirror the horn state
//   beepPlay(notes, n)            a short melody; beepPoll() steps it without blocking
// To make nicer tones later, add Note tables (see CHIME_* in main.cpp) or extend beepTone
// with a volume (duty) or an envelope; nothing else needs to change.
#pragma once
#include <Arduino.h>

struct Note {
  uint16_t hz;  // 0 = rest
  uint16_t ms;
};

void beepBegin(int pin);
void beepTone(uint16_t hz, uint8_t dutyPercent = 50);  // 50 % is loudest for a piezo
void beepOff();
void beepPlay(const Note *notes, size_t count);  // replaces anything playing
void beepPoll();                                  // call from loop()
bool beepSequenceActive();
