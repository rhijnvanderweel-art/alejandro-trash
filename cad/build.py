"""
Export all printable parts (in their print orientation) and reference assemblies.

    python3 cad/build.py            -> stl/*.stl, assembly/*.stl, assembly/*.3mf
"""
import os
import sys

import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(__file__))
import feeder as F

ROOT = os.path.join(os.path.dirname(__file__), "..")


def on_bed(m, flip=False, lay_y=False):
    if flip:
        m = m.rotate([180, 0, 0])
    if lay_y:
        m = m.rotate([-90, 0, 0])        # model Y (thickness) becomes print Z
    bb = m.bounding_box()
    return m.translate([-(bb[0] + bb[3]) / 2, -(bb[1] + bb[4]) / 2, -bb[2]])


def print_parts():
    """name -> (Manifold in print orientation, quantity, support note)"""
    parts = {
        "01_hub": (on_bed(F.make_hub()), 1, "none"),
        "02_selector_disc": (on_bed(F.make_rotor(), flip=True), 1, "none (print top face down)"),
        "03_knob": (on_bed(F.make_knob(), flip=True), 1, "none (print head down)"),
        "04_pawl_spring": (on_bed(F.make_pawl()), 1, "none - PETG preferred"),
    }
    for k in range(1, F.N + 1):
        parts[f"05_station_module_{k}"] = (on_bed(F.make_module(k)), 1, "none (tunnel = 5.6 mm bridge)")
    parts.update({
        "06_locking_bolt": (on_bed(F.make_bolt(), lay_y=True), F.N, "none (print flat)"),
        "07_lid": (on_bed(F.make_lid()), F.N, "none"),
        "08_bowl": (on_bed(F.make_bowl()), F.N, "none"),
        "09_hinge_pin": (F.make_pin_print(F.snap_pin_local(F.AXLE_GRIP)), F.N + 2, "none (print lying, 2 spares)"),
        "10_crank_pin": (F.make_pin_print(F.snap_pin_local(F.CRANK_GRIP)), F.N + 2, "none (print lying, 2 spares)"),
        "11_retaining_pin": (F.make_pin_print(F.retaining_pin_local()), 2, "none (print lying, 1 spare)"),
    })
    return parts


def to_trimesh(m):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    t = np.asarray(mesh.tri_verts)
    return trimesh.Trimesh(vertices=v, faces=t, process=True)


COLORS = {"module": (217, 199, 163), "bowl": (106, 159, 212), "bolt": (224, 83, 60),
          "lid": (127, 176, 105), "axle_pin": (60, 60, 60), "crank_pin": (60, 60, 60),
          "hub": (154, 165, 177), "retaining_pin": (60, 60, 60), "pawl": (242, 193, 78), "rotor": (61, 90, 128), "knob": (238, 150, 75)}


def assembly(rotor_deg=0.0, alphas=None):
    alphas = alphas or {}
    parts = dict(F.centre_parts(rotor_deg))
    for k in range(F.N):
        parts.update(F.station_parts(k, alphas.get(k, 0.0)))
    return parts


def export_assembly(parts, path_stem):
    scene = trimesh.Scene()
    merged = []
    for n, m in parts.items():
        tm = to_trimesh(m)
        key = n.split("_", 1)[1] if n.startswith("s") and n[1].isdigit() else n
        tm.visual.face_colors = COLORS.get(key, (200, 200, 200)) + (255,)
        scene.add_geometry(tm, node_name=n, geom_name=n)
        merged.append(tm)
    scene.export(path_stem + ".3mf")
    trimesh.util.concatenate(merged).export(path_stem + ".stl")


def main():
    stl_dir = os.path.join(ROOT, "stl")
    asm_dir = os.path.join(ROOT, "assembly")
    os.makedirs(stl_dir, exist_ok=True)
    os.makedirs(asm_dir, exist_ok=True)
    for name, (m, qty, note) in print_parts().items():
        tm = to_trimesh(m)
        assert tm.is_watertight and tm.is_volume, name
        fn = os.path.join(stl_dir, f"{name}.stl")
        tm.export(fn)
        bb = m.bounding_box()
        print(f"{name:28s} x{qty}  {bb[3]-bb[0]:6.1f} x {bb[4]-bb[1]:6.1f} x {bb[5]-bb[2]:5.1f} mm  {m.volume()/1000:6.1f} cm3")
    export_assembly(assembly(0.0), os.path.join(asm_dir, "assembly_all_closed"))
    export_assembly(assembly(0.0, {0: 90.0}), os.path.join(asm_dir, "assembly_station1_open"))
    print("assemblies written")


if __name__ == "__main__":
    main()
