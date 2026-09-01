// Pixel 10 + Pixelsnap accessory envelope (visualization / keepouts).
// Printable chassis is case.scad. Numbers: params.scad.

include <params.scad>;

$fn = 80;

module phone_body() {
    translate([-magnet_cx_from_left, magnet_cy_from_top - phone_h, -phone_t])
        cube([phone_w, phone_h, phone_t]);
}

module camera_bar() {
    translate([-magnet_cx_from_left,
               magnet_cy_from_top - camera_bar_from_top,
               0])
        cube([camera_bar_w, camera_bar_from_top, camera_bar_extra_t]);
}

module magnet_ring() {
    translate([0, 0, adhesive_t])
        difference() {
            cylinder(h = magnet_t, d = magnet_od);
            translate([0, 0, -0.1])
                cylinder(h = magnet_t + 0.2, d = magnet_id);
        }
}

module shunt() {
    translate([0, 0, adhesive_t + magnet_t])
        cylinder(h = shunt_t, d = magnet_od + 1.0);
}

module accessory_outline(h = acc_t) {
    translate([-acc_w / 2, -acc_h / 2, 0])
        cube([acc_w, acc_h, h]);
}

module usb_overmold() {
    // Cable leaves the bottom short edge, still in the plane of the phone back.
    translate([usb_offset_x - usb_overmold_w / 2, -acc_h / 2 - usb_overmold_len, 0])
        cube([usb_overmold_w, usb_overmold_len, usb_h]);
}

module mic_port() {
    translate([acc_w / 2 - 0.2, mic_y - 1.5, adhesive_t + magnet_t + shunt_t + pcb_t])
        cube([wall + 0.4, 3.0, 1.5]);
}

module pcb() {
    z = adhesive_t + magnet_t + shunt_t;
    translate([-pcb_w / 2, -pcb_h / 2, z])
        cube([pcb_w, pcb_h, pcb_t]);
}

%phone_body();
#camera_bar();
color("SteelBlue") magnet_ring();
color("Silver") shunt();
color("ForestGreen", 0.4) pcb();
color("Orange", 0.3) accessory_outline();
color("Red", 0.5) usb_overmold();
color("Yellow") mic_port();
