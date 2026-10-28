# Controller testing without a controller

`tools/virtual-gamepad.py` creates a **Steam Deck-shaped gamepad** through
`/dev/uinput` — the same bus, the same vendor/product id (28de:1205) and the
same canonical button set the real Deck's controller uses. The kernel creates a
joydev node for it, which is exactly the node Chromium's Linux gamepad backend
polls.

    python3 tools/virtual-gamepad.py create --seconds 30 --press select

`tools/test-gamepad.py` drives the real client against the live game with that
pad and checks the whole chain:

  1. Chromium enumerates the pad
  2. its id matches the game's own `steam` branch, so the game uses its
     `xlinux` layout rather than the generic one
  3. the preload's shortcut bridge turns Button 8 into the game's `m` key

**Limitation:** Chromium exposes gamepads only to the **focused** frame, and
only after the page has observed a **user gesture**. A background test window
on a live desktop often satisfies neither, so the tool reports a SKIP with the
reason. The authoritative check is the real Deck, where the game prompts
"press any button" and the user's thumb is the gesture.

Requirements: membership of the `input` group and write access to
`/dev/uinput` (`ls -l /dev/uinput`). Nothing is installed and no real hardware
is touched.
