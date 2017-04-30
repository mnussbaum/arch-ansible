#!/usr/bin/python3
# Copied from https://gist.github.com/meeuw/0271963355ce6667d87fc0b3fbafa45a
# not sure if this works yet

import evdev
import sys

upper = { '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0' }

with evdev.UInput() as ui:
    escape = False
    for letter in sys.argv[1]:
        if letter == ' ':
            key = evdev.ecodes.KEY_SPACE
        elif letter in upper:
            key = evdev.ecodes.ecodes['KEY_'+upper[letter]]
        elif letter == '\\':
            escape = True
            continue
        elif escape and letter == 'r':
            escape = False
            key = evdev.ecodes.KEY_ENTER
        else:
            key = evdev.ecodes.ecodes['KEY_'+letter.upper()]
        if letter.isupper() or letter in upper:
            ui.write(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_LEFTSHIFT, 1)

        print(key)
        ui.write(evdev.ecodes.EV_KEY, key, 1)
        ui.write(evdev.ecodes.EV_KEY, key, 0)

        if letter.isupper() or letter in upper:
            ui.write(evdev.ecodes.EV_KEY, evdev.ecodes.KEY_LEFTSHIFT, 0)
    ui.syn()
