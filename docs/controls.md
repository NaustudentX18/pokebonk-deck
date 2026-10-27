# Controls

These are the game's own defaults, read from the shipped build of `pokebonk.com`
(`main-D9lomsK5-mvpt1dlr.js`). The client does not remap anything, so the in-game settings
screen remains the single source of truth.

## Keyboard

| Action | Key |
|---|---|
| Move | `W` `A` `S` `D` (or arrow keys) |
| Jump | `Space` |
| Dash — air dive | `Shift` (left) |
| Interact | `E` |
| Ultimate | `R` |
| Lock target | Middle mouse |
| Auto aim | `Q` |
| Auto-run | `T` |
| Big map | `M` |
| Auto ultimate | `Y` |
| Pause | `P` |
| Reroll upgrade | `F` |
| Skip upgrade | `X` |
| Banish upgrade | `Z` |

## Controller

The game polls `navigator.getGamepads()` every frame and detects three layouts.

| Layout | When it is chosen |
|---|---|
| `std` | The pad reports `mapping === "standard"` — the W3C standard mapping. |
| `xlinux` | Not standard, and the id matches `/xbox\|xinput\|045e\|gamesir\|microsoft\|steam/i`, or both triggers rest at the extreme negative axis. This is the **Steam Deck / Steam Input** path: the virtual pad reports as a Microsoft X-Box 360 pad. |
| `generic` | Everything else. Button indices are read as-is, so an unusual pad can feel scrambled. |

Default button map (standard-mapping indices):

| Action | Index | Face button |
|---|---|---|
| Jump | 0 | A / Cross |
| Dash | 1 | B / Circle |
| Interact | 2 | X / Square |
| Ultimate | 3 | Y / Triangle |
| Aim | 4 | Left bumper / L1 |
| Lock target | 5 | Right bumper / R1 |

Menu navigation maps `confirm` to 0 and `back` to 1, so A confirms and B goes back.

The game also supports:

- **Right-stick camera** with a per-controller direction-learning wizard, stored in
  `localStorage` under `pb-rstick:<gamepadId>`.
- **Rumble** through `navigator.vibrationActuator` / `playEffect('dual-rumble')` where the
  platform exposes it.
- **Xbox vs PlayStation glyphs**, chosen from the pad id (`/054c|dualsense|dualshock|playstation|ps5|ps4/i`).

### The one gotcha

Chromium deliberately hides gamepads until the user has interacted with one — a
fingerprinting mitigation in the Gamepad API itself. A pad will read as "not connected" at
launch and appear the moment you press a button. The client polls for this rather than
trusting the `gamepadconnected` event alone.

## Shell shortcuts

| Shortcut | Action |
|---|---|
| `F10` | Open the shell menu |
| `Esc` | Close the shell menu / resume |
| `F11` | Toggle fullscreen |
| `F5` | Reload the game |
| `F8` | Print controller status |
| `Ctrl+Q` | Quit |

The shell deliberately does not intercept `Escape` while the game is running — the game uses
it to release the pointer lock.
