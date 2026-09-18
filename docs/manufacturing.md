# Manufacturing

One-off / quick-turn. Prefer JLCPCB + LCSC Basic parts. Do not send Gerbers until ERC, DRC, envelope check, and `recorder_test` pass.

## PCB (Phase 1)

| Item | Default |
| --- | --- |
| Fab | JLCPCB (PCBWay is the backup) |
| Layers | 4 (F.Cu, In1.Cu, In2.Cu, B.Cu) |
| Thickness | 0.8 mm (`params.json`). 1.6 mm only if a later envelope check still passes |
| Finish | ENIG (USB-C and fine pitch) |
| Impedance | None. Do not order the controlled-impedance option. USB is full speed only, so D+/D− are a plain 0.2 mm pair on a 0.4 mm pitch over In1 GND (~75 Ω). Reasoning in `hardware/kicad/README.md` |
| Min trace / space | 0.15 mm. Inside standard capability, so no fine-line surcharge |
| Via | 0.6 mm pad on a 0.3 mm drill, one size everywhere. 0.3 mm is JLC's preferred hole, so no small-via surcharge — do not let a re-route drop below it |
| Silkscreen | Standard font, 1.0 mm characters on a 0.15 mm stroke. Not the high-precision option |
| Assembly | JLCPCB SMT for every surface-mount part, wave solder for BT1, extra-parts bag for J1 (do not assemble the UART header) |
| Panel | Single board is fine for a one-off |

Mic: keep the acoustic port on the board edge, away from U4/U5 and the USB connector. SD: low-profile push-push or friction socket; if height blows the envelope, redesign for eMMC (still a solved pattern).

See [`hardware/kicad/README.md`](../hardware/kicad/README.md) for stackup and keepouts.

## Magnet array

Buy a **commodity MagSafe / Qi2 accessory magnet ring** plus matching thin steel shunt. Do not CNC magnets. Pocket the ring in CAD to the datasheet of the part in the BOM (OD/ID/thickness vary by 1–2 mm across vendors). Adhesive: 3M VHB or the ring’s stock tape, phone-facing side as the vendor intends.

## Plastic prototype (Phase 1 chassis)

- FDM (PETG) for fit checks, or SLS/MJF nylon if the USB-C pocket needs better accuracy
- JLCPCB 3D print or any local service
- Print the magnet pocket slightly loose, shim with tape, then tighten after the real ring arrives

## Metal chassis (Phase 2)

- **6061 aluminum CNC** (JLCPCB / PCBWay)
- **Not steel, not 400-series stainless** as the main shell — it steals flux from the ring
- 3D-print remains the fit gauge; metal is a copy of a passing plastic shell
- Isolate the shunt from the aluminum with a thin plastic or adhesive layer if the CAD shows a shorted loop around the ring

## Battery

Pouch LiPo sized after CAD. Use a protected cell if it still fits; otherwise a PCM board in the leftover volume. Capacity is leftover mm³, not a marketing number — update [`docs/bom.md`](bom.md) when the pouch is picked.

## Order checklist

1. If you changed schematic sources, run `python hardware/kicad/recorder/generate_recorder.py` then `python hardware/kicad/recorder/verify_schematic.py`. That overwrites sheets only. It does not write `recorder.kicad_pcb`.
2. `python scripts/check_gates.py` (envelope, `recorder_test`, schematic ERC, outline/holes, MCU SKU, pins). Official copper DRC is `kicad-cli pcb drc`. A clean run writes the whole upload package in one pass: `hardware/kicad/fab/` from `kicad-cli`, and `hardware/kicad/jlcpcb_bom.csv` + `jlcpcb_cpl.csv` + `jlcpcb_extra.csv` from `generate_jlc.py`. Send them only if that run just happened. If gates or DRC fail, edit the board. Do not stop at the report.
3. Optional: ngspice `sim/spice/power_path.cir`
4. Human glance in KiCad 10: USB length/impedance, courtyard collisions, 3D vs case. Footprint XY: `hardware/kicad/recorder/placement.json`.
5. Upload `hardware/kicad/fab/` Gerbers + `hardware/kicad/jlcpcb_bom.csv` + `jlcpcb_cpl.csv` to JLCPCB. Step 2 writes those from `recorder.kicad_pcb`, so upload the files that run just produced. Do not hand-edit the CSVs: LCSC order codes come from the tables in [`docs/bom.md`](bom.md), and which parts the machine places comes from the board's own `exclude_from_pos_files` / `exclude_from_bom` flags. A missing LCSC on an assembly-BOM part fails the generator. BT1 is through-hole: it is in the BOM for wave solder, not in the pick-and-place file. J1 is through-hole and **off** the assembly BOM — add `jlcpcb_extra.csv` under Extra Parts in the JLC cart so they ship the header loose; do not wave-solder it. **SP1:** JLC places C18186315 from their EasyEDA library 0° (`BUZ-SMD_4P-L13.0-W13.0-P11.4-BL`, pin 1 bottom-left), not this KiCad land's 0° (pad 1 bottom-right). CPL rotation is 0. In the assembly preview, the coil must sit on the numbered pads toward the analog island, not on the dummy pair toward the top edge. A left-right swap only inverts polarity. 180° leaves the speaker open.
6. Order magnet ring and LiPo **before** locking CNC metal
7. SMT board: follow [`docs/bringup-custom.md`](bringup-custom.md)
