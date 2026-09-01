// Printable two-piece PETG chassis (tray toward phone, lid toward pocket).
// Magnet pocket is 0.3 mm loose for the first print. Shim, then tighten after the real ring arrives.
// Later CNC copy: 6061, not steel. Isolate the shunt from aluminium with tape.
//
// World XY origin is the magnet center. +Z is away from the phone glass.
// All cutouts use that map. Do not wrap lid features in an extra +tray_h.

include <params.scad>;

$fn = 64;

// Derived split: tray is phone face through the PCB. Lid is everything above.
pcb_z = adhesive_t + magnet_t + shunt_t;
parts_z = pcb_z + pcb_t;
tray_h = parts_z;
lid_h = acc_t - tray_h;

// Print-fit only. Not locked in params.json.
pocket_extra = 0.3;
magnet_floor = 0.4;
pcb_clear = 0.3;
batt_xy_clear = 0.6;
batt_off_x = 0.0;
batt_off_y = 16.0;
corner_r = 2.5;
// Lip outer sits on the rim outside the PCB rebate (0.45 mm/side at these numbers).
lip_inset = 0.75;
lip_w = 1.0;
lip_h = 1.2;
lip_clear = 0.2;
usb_slot_w = usb_overmold_w + 1.0;
usb_slot_h = usb_h + 1.0;
eps = 0.05;
// MK1 NPTH from recorder.kicad_pcb: footprint (30, 10) rot 90°, pad
// local (0.68, 0). KiCad PCB rotation is clockwise → board (30.00, 9.32).
// Duct to that hole, not the footprint centre. MK1 stays on F.Cu.
mic_npth_x = 30.00;
mic_npth_y = 9.32;
duct_well = 3.0;
duct_w = 3.0;
duct_floor = 0.5;

module rounded_box(w, h, t, r) {
    r2 = max(0.01, min(r, w / 2 - 0.01, h / 2 - 0.01));
    hull() {
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (w / 2 - r2), sy * (h / 2 - r2), 0])
                cylinder(h = t, r = r2);
    }
}

module acc_body(h) {
    rounded_box(acc_w, acc_h, h, corner_r);
}

module rounded_ring(ow, oh, iw, ih, t, r) {
    difference() {
        rounded_box(ow, oh, t, r);
        translate([0, 0, -eps])
            rounded_box(iw, ih, t + 2 * eps, max(0.2, r - (ow - iw) / 2));
    }
}

// Annular well from a printable floor up to the PCB. Center stays open.
// The ring sits on the floor and cannot fall through the phone face.
module magnet_pocket() {
    translate([0, 0, magnet_floor])
        cylinder(h = pcb_z - magnet_floor + 0.05, d = magnet_od + pocket_extra);
}

module shunt_pocket() {
    translate([0, 0, adhesive_t + magnet_t])
        cylinder(h = shunt_t + 0.15, d = magnet_od + 1.4);
}

module magnet_id_bore() {
    translate([0, 0, -eps])
        cylinder(h = tray_h + 2 * eps, d = magnet_id - 0.8);
}

// 0.3 mm/side. Uses the 0.6 mm leftover outside 2×1.2 mm walls. 0.2 mm was too tight for FDM.
module pcb_rebate() {
    translate([-pcb_w / 2 - pcb_clear, -pcb_h / 2 - pcb_clear, pcb_z])
        cube([pcb_w + 2 * pcb_clear, pcb_h + 2 * pcb_clear, pcb_t + 0.05]);
}

module boss_solid(x, y) {
    translate([x, y, 0])
        cylinder(h = tray_h, d = 4.0);
}

module boss_solids() {
    ix = pcb_w / 2 - hole_inset;
    iy = pcb_h / 2 - hole_inset;
    boss_solid(ix, iy);
    boss_solid(-ix, iy);
    boss_solid(ix, -iy);
    boss_solid(-ix, -iy);
}

module tray_screws() {
    // hole_d 1.7 is M1.6 clearance, not a tap.
    ix = pcb_w / 2 - hole_inset;
    iy = pcb_h / 2 - hole_inset;
    for (p = [[ix, iy], [-ix, iy], [ix, -iy], [-ix, -iy]])
        translate([p[0], p[1], -eps])
            cylinder(h = tray_h + 2 * eps, d = hole_d);
}

module lid_screws() {
    ix = pcb_w / 2 - hole_inset;
    iy = pcb_h / 2 - hole_inset;
    for (p = [[ix, iy], [-ix, iy], [ix, -iy], [-ix, -iy]])
        translate([p[0], p[1], tray_h - eps])
            cylinder(h = lid_h + 2 * eps, d = hole_d + 0.2);
}

// Rectangular first-pass mouth. Connector-accurate J2 pocket waits for real placement.
// Starts at PCB copper so the tray gets a real bite, not a 0.6 mm sliver.
module usb_slot() {
    translate([
        usb_offset_x - usb_slot_w / 2,
        -acc_h / 2 - 1.0,
        pcb_z
    ])
        cube([usb_slot_w, wall + 6.0, usb_slot_h]);
}

// Side features live at PCB top. Nudge 0.3 mm into the tray so the split still cuts.
module mic_port() {
    translate([acc_w / 2 - wall - 1.0, mic_y - 1.5, parts_z - 0.3])
        cube([wall + 2.5, 3.0, 2.0]);
}

// Under-PCB air path: B.Cu NPTH → well → +X channel → right wall → mic_port().
// Phone-face floor stays (z = 0 .. duct_floor). Does not enter the magnet well.
module mic_duct() {
    air_h = pcb_z - duct_floor + eps;
    union() {
        translate([mic_npth_x - duct_well / 2, mic_npth_y - duct_well / 2, duct_floor])
            cube([duct_well, duct_well, air_h]);
        translate([mic_npth_x, mic_npth_y - duct_w / 2, duct_floor])
            cube([acc_w / 2 - mic_npth_x + 1.0, duct_w, air_h]);
        translate([acc_w / 2 - wall - 1.0, mic_y - 1.5, duct_floor])
            cube([wall + 2.5, 3.0, tray_h - duct_floor + eps]);
    }
}

module button_hole() {
    translate([-acc_w / 2 - 1.0, btn_y - 3.5, parts_z - 0.3])
        cube([wall + 2.5, 7.0, 3.5]);
}

module led_window() {
    translate([-acc_w / 2 - 0.5, led_y - 0.8, parts_z + 0.4])
        cube([wall + 1.5, 1.6, 1.6]);
}

module tray_lip() {
    translate([0, 0, tray_h - 0.3])
        rounded_ring(
            acc_w - 2 * lip_inset,
            acc_h - 2 * lip_inset,
            acc_w - 2 * lip_inset - 2 * lip_w,
            acc_h - 2 * lip_inset - 2 * lip_w,
            lip_h + 0.3,
            max(0.4, corner_r - lip_inset)
        );
}

module lid_groove() {
    translate([0, 0, tray_h])
        rounded_ring(
            acc_w - 2 * lip_inset + 2 * lip_clear,
            acc_h - 2 * lip_inset + 2 * lip_clear,
            acc_w - 2 * lip_inset - 2 * lip_w - 2 * lip_clear,
            acc_h - 2 * lip_inset - 2 * lip_w - 2 * lip_clear,
            lip_h + 0.2,
            max(0.3, corner_r - lip_inset + lip_clear)
        );
}

module lid_inner() {
    land = lip_inset + lip_w + lip_clear + 0.6;
    translate([0, 0, tray_h - eps])
        rounded_box(
            acc_w - 2 * land,
            acc_h - 2 * land,
            lip_h + 2 * eps,
            max(0.4, corner_r - land)
        );
    translate([0, 0, tray_h + lip_h - eps])
        rounded_box(
            acc_w - 2 * wall,
            acc_h - 2 * wall,
            lid_h - lip_h - shell_back - 0.2,
            max(0.4, corner_r - wall)
        );
}

// 40×30×5 leftover pocket, shifted +Y so it misses U1 (+14, −18) and J2 on the bottom edge.
// Closed 1.2 mm back: the fence hangs from the inner face of shell_back.
module battery_fence() {
    outer_w = batt_w + 2 * batt_xy_clear + 2.4;
    outer_h = batt_h + 2 * batt_xy_clear + 2.4;
    inner_w = batt_w + 2 * batt_xy_clear;
    inner_h = batt_h + 2 * batt_xy_clear;
    fence_h = 3.5;
    embed = 0.8;
    translate([batt_off_x, batt_off_y, 0]) {
        translate([-outer_w / 2, -outer_h / 2, acc_t - shell_back])
            cube([outer_w, outer_h, embed]);
        translate([-outer_w / 2, -outer_h / 2, acc_t - shell_back - fence_h])
            difference() {
                cube([outer_w, outer_h, fence_h + 0.2]);
                translate([(outer_w - inner_w) / 2, (outer_h - inner_h) / 2, -eps])
                    cube([inner_w, inner_h, fence_h + 0.3]);
            }
    }
}

module tray() {
    difference() {
        union() {
            difference() {
                union() {
                    acc_body(tray_h);
                    tray_lip();
                }
                magnet_pocket();
                shunt_pocket();
                magnet_id_bore();
                pcb_rebate();
                usb_slot();
                mic_port();
                mic_duct();
                button_hole();
            }
            boss_solids();
        }
        tray_screws();
    }
}

module lid() {
    difference() {
        union() {
            difference() {
                translate([0, 0, tray_h])
                    acc_body(lid_h);
                lid_groove();
                lid_inner();
                usb_slot();
                mic_port();
                button_hole();
                led_window();
            }
            battery_fence();
        }
        lid_screws();
    }
}

// Two-up on one FDM plate: tray phone-face down, lid mating-face down.
tray();
translate([acc_w + 8, 0, -tray_h])
    lid();
