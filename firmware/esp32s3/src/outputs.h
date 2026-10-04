// Physical outputs: lights, horn pin, PWM beeper, fault LED, and the MCU-timed whistle pattern.
// This module owns the applied state only; deciding WHO drives it (host or radio) is main.cpp.
// Pin overrides (-DPIN_GREEN=n ...) are documented in outputs.cpp.
#pragma once
#include <Arduino.h>

static const uint16_t DEFAULT_BLAST_MS = 500;
static const uint16_t DEFAULT_GAP_MS = 500;

void outputsBegin();             // pins as outputs, safe state (RED, silent) applied
void outputsPoll();              // call every loop(): steps the whistle pattern and the beeper
void outputsApply();             // writes the pins from the current state

uint8_t outputsLightsMask();     // G=1 Y=2 R=4
void outputsSetLightsMask(uint8_t mask);
bool outputsHornRaw();           // $B / radio buzz level
void outputsSetHornRaw(bool on);
void outputsStartBlasts(int n, uint16_t blastMs, uint16_t gapMs);  // n <= 0 stops
void outputsStopSound();
void outputsSafe();              // RED and silent
void outputsFault(bool on);      // fault LED (polarity handled here)
bool outputsSoundActive();       // a blast pattern is running or the raw horn is on
void outputsSetEnabled(bool lights, bool sound);  // $C lights / sound: a disabled output stays off
// Pairing blink: while on, the three light pins show `mask` whatever the lights setting says.
void outputsSetOverrideLights(bool on, uint8_t mask);
