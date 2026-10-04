// Debounced buttons wired between the pin and GND (internal pull-up). Button n reports as id n
// (1..4); the host decides what each press means (config/default_settings.toml).
// main.cpp maps the edges to `$K` (host alive) or to remote CMD frames (`$C btn1..4`).
#pragma once
#include <Arduino.h>

typedef void (*ButtonEdgeFn)(uint8_t id, bool down);  // every debounced edge

void buttonsBegin(ButtonEdgeFn onEdge);
void buttonsPoll();
bool buttonsHeld(uint8_t id);  // id 1..4: the raw pin is pressed right now (used for the boot-time pairing hold)
