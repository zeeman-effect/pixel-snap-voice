// Two-piece chassis. The lid is always natural translucent PETG. Default
// tray is the PETG fit print. -D variant="metal" is a 6061 tray only: closed
// phone face, 0.85 mm skin, blind wells for the N52 ring and the clocking
// magnet, four M1.6 posts, no 0.45 mm skirt. The pouch is taped to the board
// underside and wrapped in kapton; the posts carry the board. Dev / USB-C
// variant: J2 is a mid-mount USB-C on the phone-bottom (-Y) edge. Its mouth
// is cut through the -Y end wall, split across tray and lid, inside a shallow
// outer relief so a plug overmold can get close enough to latch. The lid top
// is flat. A local well over U1's IPEX swallows the mated W.FL / MHF III
// plug; an FPC tape mark sits on the inner ceiling toward the phone-bottom
// end. No speaker grille, no side LED windows.
//
// World XY origin is the magnet center. +Z is away from the phone glass.
// All cutouts use that map. Do not wrap lid features in an extra +tray_h.
//
// Print the PETG tray phone-face down and the lid outer-face down. Mating-face
// down turns the 1.2 mm back skin into a 57 x 83 mm unsupported bridge.
//
// `part` picks what to emit: "plate" (both, print orientation), "tray", "lid"
// (outer face down), "lid_worn" (lid in worn Z, for metal renders), "pouch"
// (3.3 mm dummy cell), "button" (TPU 95A pill, head on the bed),
// "button_worn" (same pill in the lid wall, for renders), "assembly" (as worn).
//   openscad -D 'part="lid"' -o export/lid.stl case.scad
//   openscad -D 'variant="metal"' -D 'part="tray"' -o export/metal/tray.stl case.scad

include <params.scad>;

// 64 is enough for a PETG print. Product renders pass render_fn=96.
render_fn = 64;
$fn = render_fn;

part = "plate";
variant = "petg";

function is_metal() = (variant == "metal");

// Closed phone face. skin_t is the non-ferrous web between the magnets and
// the glass. floor_t is that skin plus the 1.5 mm ring, so the magnet backs
// sit flush with the inner floor. The steel plate is already on the ring.
// Posts carry the board. check_dfm.py / check_envelope.py read these numbers.
skin_t = 0.85;
floor_t = 2.35;
standoff_d = 5.0;
pcb_z = floor_t + shunt_t + batt_air + batt_tape + batt_t + batt_swell;
parts_z = pcb_z + pcb_t;
tray_h = parts_z;
lid_h = acc_t - tray_h;
cavity_top = acc_t - shell_back;

// Print-fit only. Not locked in params.json.
// clock_rib is the aluminum left between the ring well and the clocking well
// so a 1 mm end mill can finish both. clock_clear is extra well on each side
// of the 12 x 5 mm block, enough for that tool's corner radius.
pocket_extra = 0.3;
clock_clear = 0.4;
clock_rib = 1.2;
pcb_clear = 0.3;
corner_r = 2.5;
eps = 0.05;

// Tray/lid joint. The board fills the case to one wall per side, so the rim
// outside the 0.3 mm PCB rebate is 0.9 mm and a closed groove (skin, lip and
// land) has no room. The lid keeps a thin outer skirt; the tray lip stands
// inside it, and as a closed ring it still locates the lid on every side.
// The lip's inner face is the board outline, so no part on the board hits it.
// Metal tray has no lip; screws locate the plastic lid.
lip_inset = 0.6;
lip_h = 1.2;
lip_clear = 0.15;
skirt = lip_inset - lip_clear;
joint_top = tray_h + lip_h + lip_clear;

// TPU 95A record pill. SW1 is the spring (2.2 N, 0.2 mm). The visible face
// is an iPhone-case side button: a rounded-rect bezel flush with the lid
// wall, and a smaller rounded press pad that stands proud. Install from
// inside. Inner lip is 0.4 mm, less than the 0.6 mm to the actuator tip.
btn_head_y = 10.0;
btn_head_z = 3.2;
btn_r = 1.05;
btn_border = 0.6;
btn_bezel_t = 0.45;
btn_proud = 0.65;
btn_lip = 0.4;
btn_hole_y = 8.4;
btn_hole_z = 2.2;
btn_pocket_clear = 0.10;
btn_waist_clear = 0.15;
nub_w = 2.0;
nub_h = 1.1;
nub_pretravel = 0.1;
btn_zc = tray_h + lid_h / 2;
btn_hole_z0 = btn_zc - btn_hole_z / 2;
nub_len = btn_tip_inset - nub_pretravel;

// Mic port. The rib stops short of the board so a foam frame can be compressed
// onto it. A pocket in that top holds a mesh disk; three drills through the
// wall enter the pocket above the mesh. The pouch outline ends 25.75 mm from
// center, so the land stays on the wall side of the cell instead of growing
// to a 6 mm square. Foam and mesh are cut parts, not solids in this file.
mic_port_w = 4.2;
mic_port_h = 1.8;
mic_dish_d = 0.35;
mic_gasket_gap = 0.40;
mic_mesh_drop = 0.80;
mic_mesh_x = 3.4;
mic_mesh_y = 3.6;
mic_hole_d = 0.60;
mic_hole_n = 3;
mic_hole_pitch = 1.10;
mic_land_y = 6.0;
mic_land_gap = 0.40;

// Side grip: 18 deg flutes on both long walls, tray and lid. They line up
// when the case is closed. Depth is 0.35 mm in the 1.2 mm wall. The lid skirt
// is only 0.45 mm, so the same flutes go 0.12 mm there and leave ~0.33 mm.
ridge_depth = 0.35;
ridge_skirt_depth = 0.12;
ridge_w = 0.6;
ridge_pitch = 1.6;
ridge_tilt = 18.0;

boss_d = 4.0;

// USB-C mouth (J2, HRO TYPE-C-31-M-13C). The shell face is flush with the
// board edge, which is the inner wall face, so the plug crosses the end wall.
// The mouth clears the 8.94 x 3.16 mm shell by 0.28 mm a side (board slop in
// the 0.3 mm rebate). Round ends, like the plug. The relief is the overmold
// seat: USB-IF max overmold is 12.35 x 6.5 mm, and a plug is 6.65 mm from
// overmold to tip against a 6.20 mm receptacle, so the overmold must land
// within about 0.45-0.5 mm of the shell face: wall - usbc_recess_d is what is
// left of the wall in the relief. Both straddle the tray / lid seam at z = tray_h + 0.02.
usbc_mouth_w = 9.5;
usbc_mouth_h = 3.7;
usbc_recess_w = 12.8;
usbc_recess_h = 6.7;
usbc_recess_r = 1.0;
usbc_recess_d = 0.7;
usbc_zc = tray_h + usbc_mouth_z;

// M1.6 from the lid: lid is clearance plus a shallow CSK so the head sits
// in the PETG. Tray posts get a 1.35 mm tap drill 2.5 mm deep that dies
// above the 2.35 mm inner floor. The 0.85 mm skin stays closed. No printed threads.
tap_depth = 2.5;
tap_floor = 2.5;
csk_d = 3.2;
csk_h = 0.9;

// Two-focus rings on the lid outer face. They run off the lid; the only
// interference is where the two families cross. No edge mirrors.
wave_depth = 0.35;
wave_stroke = 0.5;
wave_step = 4.5;
wave_n = 18;
wave_focus_x = 18.0;
wave_inset = 1.8;

module rounded_box(w, h, t, r) {
    r2 = max(0.01, min(r, w / 2 - 0.01, h / 2 - 0.01));
    hull() {
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (w / 2 - r2), sy * (h / 2 - r2), 0])
                cylinder(h = t, r = r2);
    }
}

module rounded_rect_2d(w, h, r) {
    r2 = max(0.01, min(r, w / 2 - 0.01, h / 2 - 0.01));
    hull() {
        for (sx = [-1, 1], sy = [-1, 1])
            translate([sx * (w / 2 - r2), sy * (h / 2 - r2)])
                circle(r = r2);
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

function hole_xy() = [
    for (sx = [-1, 1], sy = [-1, 1])
        [sx * (pcb_w / 2 - hole_inset), sy * (pcb_h / 2 - hole_inset)]
];

// Blind wells. The phone face stays solid. Glue holds the magnets; a clamp
// plate would land in the air gap under the pouch.
module magnet_wells() {
    ring_r = (magnet_od + pocket_extra) / 2;
    translate([0, 0, skin_t])
        difference() {
            cylinder(h = magnet_t + eps, d = magnet_od + pocket_extra);
            translate([0, 0, -eps])
                cylinder(h = magnet_t + 3 * eps, d = magnet_id - pocket_extra);
        }
    // Long side points at 6 o'clock (phone bottom, -Y). clock_w is the
    // 12 mm length, clock_h the 5 mm width.
    well_y = clock_w + 2 * clock_clear;
    well_x = clock_h + 2 * clock_clear;
    cy = -(ring_r + clock_rib + well_y / 2);
    translate([0, cy, skin_t])
        rounded_box(well_x, well_y, magnet_t + eps, 0.5);
}

// 0.3 mm/side. 0.2 mm was too tight for FDM. At this outline the clearance
// comes out of the wall, which is why the rim is 0.9 mm.
module pcb_rebate() {
    translate([-pcb_w / 2 - pcb_clear, -pcb_h / 2 - pcb_clear, pcb_z])
        cube([pcb_w + 2 * pcb_clear, pcb_h + 2 * pcb_clear, pcb_t + 0.05]);
}

module tray_screws() {
    // Blind tap from the board face, in the posts. Phone face stays closed.
    for (p = hole_xy())
        translate([p[0], p[1], tap_floor])
            cylinder(h = pcb_z - tap_floor + eps, d = tap_d);
}

module lid_screws() {
    for (p = hole_xy()) {
        translate([p[0], p[1], tray_h - eps])
            cylinder(h = lid_h + 2 * eps, d = hole_d);
        translate([p[0], p[1], acc_t - csk_h])
            cylinder(h = csk_h + eps, d1 = hole_d, d2 = csk_d);
    }
}

// Standoffs hang from the back skin and stop on the board top, so the screws
// clamp lid, board and posts together. check_placement keeps courtyards
// 2.1 mm off the holes.
module boss_solids() {
    for (p = hole_xy())
        translate([p[0], p[1], tray_h])
            cylinder(h = cavity_top - tray_h + 0.2, d = boss_d);
}

module tray_posts() {
    for (p = hole_xy())
        translate([p[0], p[1], floor_t])
            cylinder(h = pcb_z - floor_t, d = standoff_d);
}

// Rib from the floor to 0.40 mm under the board. The foam frame lives in that
// gap. Inboard face stays mic_land_gap off the pouch so the cell still fits.
module mic_seal_right() {
    x0 = batt_off_x + batt_w / 2 + mic_land_gap;
    x1 = acc_w / 2 - wall + eps;
    y0 = mic_npth_y - mic_land_y / 2;
    translate([x0, y0, floor_t])
        cube([x1 - x0, mic_land_y, pcb_z - mic_gasket_gap - floor_t]);
}

module mic_port_right() {
    x_wall = acc_w / 2 - wall;
    z_top = pcb_z - mic_gasket_gap;
    z_floor = z_top - mic_mesh_drop;
    zc = z_floor + mic_mesh_drop / 2;
    // Shoulder for a 3 mm mesh disk. Open toward the board, out to the inner wall.
    translate([
        x_wall - mic_mesh_x,
        mic_npth_y - mic_mesh_y / 2,
        z_floor
    ])
        cube([mic_mesh_x + eps, mic_mesh_y, pcb_z - z_floor + eps]);
    for (i = [0 : mic_hole_n - 1])
        translate([
            x_wall - 0.35,
            mic_npth_y + (i - (mic_hole_n - 1) / 2) * mic_hole_pitch,
            zc
        ])
            rotate([0, 90, 0])
                cylinder(h = wall + 0.8, d = mic_hole_d);
    // Shallow outer recess. The drills stay separate; this does not join them.
    hull() {
        for (sy = [-1, 1])
            translate([
                acc_w / 2 - mic_dish_d,
                mic_npth_y + sy * (mic_port_w - mic_port_h) / 2,
                zc
            ])
                rotate([0, 90, 0])
                    cylinder(h = mic_dish_d + 0.2, d = mic_port_h);
    }
}

// Authored on the phone-right wall. A negative mic_npth_x mirrors them
// onto the phone-left wall; Y is already the port's board coordinate.
module mic_seal_solid() {
    if (mic_npth_x < 0)
        mirror([1, 0, 0]) mic_seal_right();
    else
        mic_seal_right();
}

module mic_port_cut() {
    if (mic_npth_x < 0)
        mirror([1, 0, 0]) mic_port_right();
    else
        mic_port_right();
}

// Rounded rectangle in the YZ plane, extruded along +X from x0.
module rounded_along_x(x0, len, cy, cz, wy, wz, r) {
    translate([x0, cy, cz])
        rotate([0, 90, 0])
            rounded_box(wz, wy, len, r);
}

module button_hole_geom() {
    hole_r = max(0.35, btn_r - (btn_head_y - btn_hole_y) / 2);
    // Shallow outer pocket. The TPU bezel sits in here, flush with the wall.
    rounded_along_x(
        -acc_w / 2 - 0.3,
        btn_bezel_t + 0.5,
        btn_y,
        btn_zc,
        btn_head_y + 2 * btn_pocket_clear,
        btn_head_z + 2 * btn_pocket_clear,
        btn_r + btn_pocket_clear
    );
    // Through-hole for the waist. Smaller than the bezel so the pill stays in.
    rounded_along_x(
        -acc_w / 2 - 0.5,
        wall + 1.0,
        btn_y,
        btn_zc,
        btn_hole_y,
        btn_hole_z,
        hole_r
    );
}

module button_pill_geom() {
    press_y = btn_head_y - 2 * btn_border;
    press_z = btn_head_z - 2 * btn_border;
    press_r = max(0.35, btn_r - btn_border);
    waist_y = btn_hole_y - 2 * btn_waist_clear;
    waist_z = btn_hole_z - 2 * btn_waist_clear;
    waist_r = max(0.3, press_r - 0.15);
    union() {
        // Flush rounded bezel in the lid pocket.
        rounded_along_x(
            -acc_w / 2,
            btn_bezel_t + 0.2,
            btn_y,
            btn_zc,
            btn_head_y,
            btn_head_z,
            btn_r
        );
        // Proud press pad. Slight taper so the face reads moulded, not cubed.
        hull() {
            rounded_along_x(
                -acc_w / 2 - 0.12,
                0.2,
                btn_y,
                btn_zc,
                press_y,
                press_z,
                press_r
            );
            rounded_along_x(
                -acc_w / 2 - btn_proud,
                0.12,
                btn_y,
                btn_zc,
                press_y - 0.22,
                press_z - 0.22,
                max(0.28, press_r - 0.12)
            );
        }
        // Waist through the lid wall.
        rounded_along_x(
            -acc_w / 2 - 0.05,
            wall + 0.1,
            btn_y,
            btn_zc,
            waist_y,
            waist_z,
            waist_r
        );
        // Inner lip. Thicker in Y/Z than the hole; 0.4 mm in X so it misses SW1.
        rounded_along_x(
            -acc_w / 2 + wall,
            btn_lip,
            btn_y,
            btn_zc,
            btn_head_y,
            btn_head_z - 0.2,
            btn_r
        );
        // Nub across the 0.6 mm gap, 0.1 mm rest on the actuator.
        translate([
            -acc_w / 2 + wall - eps,
            btn_y - nub_w / 2,
            tray_h + btn_act_z - nub_h / 2
        ])
            cube([nub_len + eps, nub_w, nub_h]);
    }
}

// Authored on the phone-left wall. A positive btn_x mirrors them onto
// phone-right; Y is already SW1's board coordinate.
module button_hole() {
    if (btn_x < 0)
        button_hole_geom();
    else
        mirror([1, 0, 0]) button_hole_geom();
}

module button_pill() {
    if (btn_x < 0)
        button_pill_geom();
    else
        mirror([1, 0, 0]) button_pill_geom();
}

module button_print() {
    // Head face on the bed. Same solid as the worn pill, turned around.
    translate([0, 0, btn_proud])
        rotate([0, 90, 0])
            translate([acc_w / 2 + btn_proud, 0, 0])
                button_pill_geom();
}

module tray_lip() {
    translate([0, 0, tray_h - 0.3])
        rounded_ring(
            acc_w - 2 * lip_inset,
            acc_h - 2 * lip_inset,
            pcb_w,
            pcb_h,
            lip_h + 0.3,
            max(0.4, corner_r - lip_inset)
        );
}

// The lid's half of the joint: everything inside the skirt, as deep as the lip.
module lid_groove() {
    translate([0, 0, tray_h - eps])
        rounded_box(
            acc_w - 2 * skirt,
            acc_h - 2 * skirt,
            joint_top - tray_h + eps,
            max(0.4, corner_r - skirt)
        );
}

module lid_inner() {
    translate([0, 0, tray_h - eps])
        rounded_box(
            acc_w - 2 * wall,
            acc_h - 2 * wall,
            cavity_top - tray_h + eps,
            max(0.4, corner_r - wall)
        );
}

// Rounded rectangle in the XZ plane, extruded along -Y from y1 to y1 - len.
module rounded_along_y(y1, len, cx, cz, wx, wz, r) {
    translate([cx, y1, cz])
        rotate([90, 0, 0])
            rounded_box(wx, wz, len, r);
}

// Same cut in tray and lid, so the halves line up when closed. The relief
// takes the 0.45 mm lid skirt with it and leaves the tray lip as thin as the wall web.
module usbc_cut() {
    y_out = -acc_h / 2;
    rounded_along_y(
        y_out + usbc_recess_d,
        usbc_recess_d + 1.0,
        usbc_x,
        usbc_zc,
        usbc_recess_w,
        usbc_recess_h,
        usbc_recess_r
    );
    // Through the wall and the lip, a hair past the board edge.
    rounded_along_y(
        usbc_front_y + 0.3,
        wall + 1.3,
        usbc_x,
        usbc_zc,
        usbc_mouth_w,
        usbc_mouth_h,
        usbc_mouth_h / 2 - 0.01
    );
}

function dist_to_rect(px, py, x0, y0, x1, y1) =
    let (qx = min(max(px, x0), x1), qy = min(max(py, y0), y1))
        norm([px - qx, py - qy]);

function ring_hits_lid(cx, cy, r, s, x0, y0, x1, y1) =
    dist_to_rect(cx, cy, x0, y0, x1, y1) <= r + s
    && max(
        norm([cx - x0, cy - y0]),
        norm([cx - x0, cy - y1]),
        norm([cx - x1, cy - y0]),
        norm([cx - x1, cy - y1])
    ) >= r - s;

function ridge_y_lo(yc) =
    yc - (acc_t / 2) * tan(ridge_tilt) - ridge_w / 2;

function ridge_y_hi(yc) =
    yc + (acc_t / 2) * tan(ridge_tilt) + ridge_w / 2;

function ranges_overlap(a0, a1, b0, b1) = !(a1 < b0 || b1 < a0);

function ridge_skip(side, yc) =
    let (
        lo = ridge_y_lo(yc),
        hi = ridge_y_hi(yc),
        mic_side = mic_npth_x < 0 ? -1 : 1,
        btn_side = btn_x < 0 ? -1 : 1
    )
        (side == btn_side && ranges_overlap(lo, hi, btn_y - btn_head_y / 2 - 0.8, btn_y + btn_head_y / 2 + 0.8))
        || (side == mic_side && ranges_overlap(lo, hi, mic_npth_y - mic_port_w / 2 - 0.5, mic_npth_y + mic_port_w / 2 + 0.5));

module ridge_cutters(depth) {
    // Stay inside the long-wall flats. Tilt adds ~1.3 mm of Y, so this margin
    // has to clear the 2.5 mm corner radii or a flute clips off a corner chip.
    y0 = -acc_h / 2 + corner_r + 2.5;
    y1 = acc_h / 2 - corner_r - 2.5;
    n = floor((y1 - y0) / ridge_pitch);
    len = acc_t / cos(ridge_tilt) + 1.0;
    for (side = [-1, 1])
        for (i = [0 : n]) {
            yc = y0 + i * ridge_pitch;
            if (!ridge_skip(side, yc))
                translate([side * acc_w / 2, yc, acc_t / 2])
                    rotate([ridge_tilt, 0, 0])
                        cube([depth * 2, ridge_w, len], center = true);
        }
}

module side_ridges() {
    render(convexity = 8)
        union() {
            intersection() {
                ridge_cutters(ridge_depth);
                if (is_metal()) {
                    translate([-acc_w, -acc_h, -1])
                        cube([2 * acc_w, 2 * acc_h, acc_t + 2]);
                } else {
                    union() {
                        translate([-acc_w, -acc_h, -1])
                            cube([2 * acc_w, 2 * acc_h, tray_h + 1 - 0.02]);
                        translate([-acc_w, -acc_h, joint_top + 0.02])
                            cube([2 * acc_w, 2 * acc_h, acc_t]);
                    }
                }
            }
            if (!is_metal())
                intersection() {
                    ridge_cutters(ridge_skirt_depth);
                    translate([-acc_w, -acc_h, tray_h])
                        cube([2 * acc_w, 2 * acc_h, joint_top - tray_h]);
                }
        }
}

module tray_shell() {
    union() {
        acc_body(floor_t);
        difference() {
            translate([0, 0, floor_t - eps])
                acc_body(tray_h - floor_t + eps);
            translate([0, 0, floor_t - eps])
                rounded_box(
                    acc_w - 2 * wall,
                    acc_h - 2 * wall,
                    tray_h - floor_t + 2 * eps,
                    max(0.4, corner_r - wall)
                );
        }
        tray_posts();
        mic_seal_solid();
    }
}

module tray() {
    difference() {
        union() {
            tray_shell();
            if (!is_metal())
                tray_lip();
        }
        magnet_wells();
        pcb_rebate();
        usbc_cut();
        mic_port_cut();
        tray_screws();
        side_ridges();
    }
}

module wave_rings_2d() {
    s = wave_stroke / 2;
    x0 = -acc_w / 2 + wave_inset;
    x1 = acc_w / 2 - wave_inset;
    y0 = -acc_h / 2 + wave_inset;
    y1 = acc_h / 2 - wave_inset;
    // Double offset merges overlapping annuli into one 2D polygon so the
    // extrude is a closed solid. A raw union of rings is self-intersecting.
    offset(r = 0.02)
        offset(r = -0.02)
            union() {
                for (fx = [-wave_focus_x, wave_focus_x], k = [1 : wave_n])
                    if (ring_hits_lid(fx, 0, k * wave_step, s, x0, y0, x1, y1))
                        difference() {
                            translate([fx, 0])
                                circle(r = k * wave_step + s);
                            translate([fx, 0])
                                circle(r = max(0.01, k * wave_step - s));
                        }
            }
}

module wave_keepouts_2d() {
    for (p = hole_xy())
        translate(p)
            circle(d = boss_d + 1.0);
    // Wave is 0.35 mm into the outer skin. The IPEX well takes 0.85 mm
    // from the inside. Clip the art or those two cuts meet.
    translate([ipex_x, ipex_y])
        circle(d = ipex_recess_d + 1.0);
}

// Local roof pocket over U1's IPEX so a mated W.FL / MHF III plug fits. Remaining
// PETG is shell_back - ipex_recess_depth (0.35 mm). Print outer-face down.
module ipex_recess() {
    translate([ipex_x, ipex_y, cavity_top - eps])
        cylinder(h = ipex_recess_depth + 2 * eps, d = ipex_recess_d);
}

// Shallow inner mark so the adhesive FPC has a seat toward the phone-bottom
// end, over short parts, off the 2.4 mm module.
module antenna_tape_mark() {
    translate([fpc_x, fpc_y, cavity_top - eps])
        rounded_box(fpc_w, fpc_h, 0.2 + eps, 0.6);
}

// 0.35 mm into the back skin. Leaves ~0.85 mm. First-layer art on the PETG
// print (lid outer-face down); CNC can mill the same grooves.
module wave_art() {
    render(convexity = 12)
        translate([0, 0, acc_t - wave_depth])
            linear_extrude(height = wave_depth + eps, convexity = 10)
                offset(r = 0.05)
                    difference() {
                        intersection() {
                            wave_rings_2d();
                            rounded_rect_2d(
                                acc_w - 2 * wave_inset,
                                acc_h - 2 * wave_inset,
                                max(0.2, corner_r - wave_inset)
                            );
                        }
                        wave_keepouts_2d();
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
                button_hole();
                side_ridges();
            }
            boss_solids();
        }
        lid_screws();
        usbc_cut();
        ipex_recess();
        antenna_tape_mark();
        wave_art();
    }
}

module lid_print() {
    translate([0, 0, acc_t])
        rotate([180, 0, 0])
            lid();
}

// Stand-in cell for the fit print: same footprint and thickness as the pouch.
module dummy_pouch() {
    translate([-batt_w / 2, -batt_h / 2, 0])
        cube([batt_w, batt_h, batt_t]);
}

module dummy_pouch_worn() {
    translate([
        batt_off_x - batt_w / 2,
        batt_off_y - batt_h / 2,
        pcb_z - batt_tape - batt_t
    ])
        cube([batt_w, batt_h, batt_t]);
}

if (part == "tray") {
    tray();
} else if (part == "lid") {
    lid_print();
} else if (part == "lid_worn") {
    lid();
} else if (part == "pouch") {
    dummy_pouch();
} else if (part == "button") {
    button_print();
} else if (part == "button_worn") {
    button_pill();
} else if (part == "assembly") {
    tray();
    dummy_pouch_worn();
    button_pill();
    lid();
} else {
    tray();
    translate([acc_w + 8, 0, 0])
        lid_print();
    translate([-acc_w - 8, 0, 0])
        button_print();
}
