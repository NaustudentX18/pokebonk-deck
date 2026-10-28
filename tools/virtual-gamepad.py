#!/usr/bin/env python3
"""Create a virtual Steam Deck-style gamepad through uinput.

The Steam Deck's controller enumerates on Linux as an Xbox-360 style pad, and
the game picks it up through Chromium's Gamepad API. This creates an
equivalent device so the whole chain can be tested on a machine that has no
real controller:

    Chromium enumerates it  ->  navigator.getGamepads() sees it
    the game applies its own 'xlinux' layout  ->  the in-game prompts change

Usage:
    python3 tools/virtual-gamepad.py create        # make it and hold it open
    python3 tools/virtual-gamepad.py create --name "Steam Deck"
"""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import os
import struct
import sys
import time

# Linux input event codes.
EV_ABS = 0x03
EV_KEY = 0x01
EV_SYN = 0x00
ABS_X = 0x00
ABS_Y = 0x01
ABS_RX = 0x03
ABS_RY = 0x04
ABS_Z = 0x02
ABS_RZ = 0x05
ABS_HAT0X = 0x10
ABS_HAT0Y = 0x11

BTN_A = 0x130
BTN_B = 0x131
BTN_C = 0x132
BTN_X = 0x133
BTN_Y = 0x134
BTN_Z = 0x135
BTN_TL = 0x136
BTN_TR = 0x137
BTN_TL2 = 0x138
BTN_TR2 = 0x139
BTN_SELECT = 0x13a
BTN_START = 0x13b
BTN_MODE = 0x13c
BTN_THUMBL = 0x13d
BTN_THUMBR = 0x13e

# uinput ioctls (linux/uinput.h).
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_DEV_SETUP = 0x405c5503        # _IOW('U', 3, struct uinput_setup)
UI_ABS_SETUP = 0x40045504        # _IOW('U', 4, struct uinput_abs_setup)
UI_SET_EVBIT = 0x40045564        # _IOW('U', 100, int)
UI_SET_KEYBIT = 0x40045565       # _IOW('U', 101, int)
UI_SET_ABSBIT = 0x40045567       # _IOW('U', 103, int)

# The Steam Deck's controller reports this VID/PID (28de:1205).
STEAM_DECK_VID = 0x28de
STEAM_DECK_PID = 0x1205

# An Xbox 360 pad for comparison.
XBOX_VID = 0x045e
XBOX_PID = 0x028e

UINPUT_MAX_NAME_SIZE = 80


def _ioctl(fd, request, arg=0):
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    return libc.ioctl(fd, request, arg)


def create(name: str = "Steam Deck", deck: bool = True):
    """Create the virtual pad. Returns (fd, uinput_user_dev)."""
    fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
    try:
        _ioctl(fd, UI_SET_EVBIT, EV_KEY)
        _ioctl(fd, UI_SET_EVBIT, EV_ABS)
        _ioctl(fd, UI_SET_EVBIT, EV_SYN)

        # The canonical Linux gamepad button set, in code order. Chromium
        # translates the kernel's button POSITIONS, so a device that declares
        # only a subset of the codes lands on the wrong gamepad buttons —
        # which is exactly how a virtual pad stops being a faithful stand-in
        # for the real Deck's controller.
        for code in (BTN_A, BTN_B, BTN_C, BTN_X, BTN_Y, BTN_Z, BTN_TL, BTN_TR,
                     BTN_TL2, BTN_TR2, BTN_SELECT, BTN_START, BTN_MODE,
                     BTN_THUMBL, BTN_THUMBR):
            _ioctl(fd, UI_SET_KEYBIT, code)

        for axis in (ABS_X, ABS_Y, ABS_RX, ABS_RY, ABS_Z, ABS_RZ, ABS_HAT0X, ABS_HAT0Y):
            _ioctl(fd, UI_SET_ABSBIT, axis)

        vid, pid = (STEAM_DECK_VID, STEAM_DECK_PID) if deck else (XBOX_VID, XBOX_PID)

        # struct uinput_setup { struct input_id id; char name[80];
        #                       __u32 ff_effects_max; };
        # input_id is four __u16 (bustype, vendor, product, version), so the
        # name starts at offset 8 — not 12 as in the older uinput_user_dev.
        buf = bytearray(92)
        struct.pack_into("H", buf, 0, 0x03)          # bustype: BUS_USB
        struct.pack_into("H", buf, 2, vid)           # vendor
        struct.pack_into("H", buf, 4, pid)           # product
        struct.pack_into("H", buf, 6, 0x0111)        # version
        name_bytes = name.encode("utf-8")[:UINPUT_MAX_NAME_SIZE - 1]
        buf[8:8 + len(name_bytes)] = name_bytes
        struct.pack_into("I", buf, 88, 1)            # ff_effects_max

        if _ioctl(fd, UI_DEV_SETUP, bytes(buf)) != 0:
            raise OSError("UI_DEV_SETUP failed")

        # Each axis gets its own UI_ABS_SETUP: code, then the absinfo
        # (value, minimum, maximum, fuzz, flat).
        ranges = {
            ABS_X: (-32768, 32767), ABS_Y: (-32768, 32767),
            ABS_RX: (-32768, 32767), ABS_RY: (-32768, 32767),
            ABS_Z: (-32768, 32767), ABS_RZ: (-32768, 32767),
            ABS_HAT0X: (-1, 1), ABS_HAT0Y: (-1, 1),
        }
        for axis, (lo, hi) in ranges.items():
            # struct uinput_abs_setup { __u16 code; __u16 filler;
            #   struct input_absinfo { value, minimum, maximum, fuzz, flat }; }
            # The filler is part of the layout — without it the ioctl fails
            # with EINVAL, the axes are never created, and the kernel makes
            # no joydev node for the device.
            absinfo = (struct.pack("i", 0) + struct.pack("i", lo) + struct.pack("i", hi)
                       + struct.pack("i", 0) + struct.pack("i", 0))
            if _ioctl(fd, UI_ABS_SETUP, struct.pack("HH", axis, 0) + absinfo) != 0:
                raise OSError(f"UI_ABS_SETUP failed for axis {axis}")

        if _ioctl(fd, UI_DEV_CREATE) != 0:
            raise OSError("UI_DEV_CREATE failed")

        # The axes the game reads.
        for axis, value in ((ABS_X, 0), (ABS_Y, 0), (ABS_Z, 0),
                            (ABS_RX, 0), (ABS_RY, 0), (ABS_RZ, 0),
                            (ABS_HAT0X, 0), (ABS_HAT0Y, 0)):
            os.write(fd, struct.pack("llHHi", 0, 0, EV_ABS, axis, value))
        os.write(fd, struct.pack("llHHi", 0, 0, EV_SYN, 0, 0))

        return fd
    except Exception:
        os.close(fd)
        raise


def emit(fd, events):
    for kind, code, value in events:
        os.write(fd, struct.pack("llHHi", 0, 0, kind, code, value))
    os.write(fd, struct.pack("llHHi", 0, 0, EV_SYN, 0, 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create"])
    parser.add_argument("--name", default="Steam Deck")
    parser.add_argument("--xbox", action="store_true",
                        help="pretend to be an Xbox 360 pad instead of a Steam Deck")
    parser.add_argument("--seconds", type=float, default=0,
                        help="create, then exit after this many seconds")
    parser.add_argument("--press", default="",
                        help="buttons to press while it is alive, comma separated "
                             "(a,b,x,y,select,l3,r3,back,start)")
    args = parser.parse_args()

    fd = create(args.name, deck=not args.xbox)
    print(f"[virtual-gamepad] created {args.name!r} (fd {fd})")

    buttons = {
        "a": BTN_A, "b": BTN_B, "x": BTN_X, "y": BTN_Y,
        "select": BTN_SELECT, "back": BTN_SELECT, "start": BTN_START,
        "l3": BTN_THUMBL, "r3": BTN_THUMBR,
        "l1": BTN_TL, "r1": BTN_TR, "lb": BTN_TL, "rb": BTN_TR,
        "mode": BTN_MODE,
    }

    deadline = time.time() + args.seconds if args.seconds else None
    while deadline is None or time.time() < deadline:
        if args.press:
            for name in args.press.split(","):
                name = name.strip().lower()
                if name in buttons:
                    emit(fd, [(EV_KEY, buttons[name], 1)])
                    time.sleep(0.06)
                    emit(fd, [(EV_KEY, buttons[name], 0)])
                    time.sleep(0.24)
        else:
            time.sleep(0.2)

    print("[virtual-gamepad] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
