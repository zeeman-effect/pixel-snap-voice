---
name: make-board-manufacturable
description: Close PCB, CAD, and schematic gaps until the recorder board can go to a fab. Use when the user mentions manufacturing, fab, Gerbers, JLCPCB, DRC, ERC, routing, traces, ratsnest, placement, check_gates, "board not ready", or when a hardware check fails.
---

# Make the board manufacturable

Checks diagnose. They do not finish the job. If docs or a script say the board is not fab-ready, that is the work list.

## Loop

1. Name the actual gap. Unrouted nets, DRC, footprint, envelope, pin mismatch, missing jack, wrong XY.
2. Edit the file that owns that gap. See the table in `AGENTS.md`.
3. Regenerate only what that edit requires. Close KiCad first.
4. Re-run the one check that covers the gap, not a full speech about every script.
5. Repeat until the gap is closed or you are blocked on a human action you cannot do.

Do not end a turn with only "the board is not fab-ready." Either you edited something, or you say exactly what only the user can do (KiCad open, a caliper measurement, a part pick).

Current gap list lives in `hardware/kicad/recorder/placement.json` under `open_items`. Work those. Update the list when an item is done or the plan changes.

## Who owns what

| Gap | Edit | Prove with |
| --- | --- | --- |
| Schematic nets, parts, pins | `generate_recorder.py`, `PSV.kicad_sym` | `generate_recorder.py` then `verify_schematic.py` |
| Footprint XY | `placement.json` and `recorder.kicad_pcb` together | `check_placement.py`; update CAD if a wall or pocket moves |
| Clean placement reset | `generate_pcb.py` via KiCad 10 `python.exe` | Wipes copper. Re-pour and re-route after. |
| Planes | `route_pcb.py --planes-only` | Same KiCad interpreter |
| Signal traces | `recorder.kicad_pcb` in KiCad and/or `route_pcb.py` | `kicad-cli pcb drc` |
| Case / stack / keepouts | `params.json`, `params.scad`, `case.scad` | `check_envelope.py` |
| GPIO | `hardware/kicad/pins.py`, `firmware/boards/custom.h`, `pinmap.md` | `check_pins.py` |
| MCU SKU | `params.json` `mcu` plus schematic sources | `check_mcu.py` |

`scripts/check_gates.py` reads files already on disk. It does not route, place, or pick parts. The Python file named `check_drc.py` is outline and holes, not copper DRC. Official copper DRC is `kicad-cli pcb drc` on `recorder.kicad_pcb`.

Ship only after gates are clean, `kicad-cli pcb drc` is clean, and `kicad-cli` has just written `hardware/kicad/fab/` from `recorder.kicad_pcb`. Until then, keep editing.

## Routing

The autorouter in `route_pcb.py` (no flag) is experimental. Use it if it saves time. Then fix shorts, missed nets, USB, and analog. Prefer a board that passes DRC over a rule that says "hand-route only" and then doing nothing.

Do not refuse to move a part because `placement.json` or `INTERFACE.md` lists an old XY. Move the part, update those files, and update the case if the wall cut moves.

## Wipe hazards (not bans)

- `generate_recorder.py` overwrites sheets. It does not write the PCB.
- `generate_pcb.py` creates an empty board and places parts. It deletes existing traces, vias, and zones.
- Do not run either generator while `~recorder.kicad_pro.lck` exists.

## Human-only stops

Stop and ask only for:

- A real caliper number (Pixel body, Pixelsnap center, stuffed-board height)
- KiCad has the project open
- A part number the user has to buy or reject

Everything else is an edit.
