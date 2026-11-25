"""Render documentation images to docs/img (needs node + playwright + three.js, see render.py)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import feeder as F
from render import render

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "img")
os.makedirs(OUT, exist_ok=True)

COL = {"module": 0xd9c7a3, "bowl": 0x6a9fd4, "bolt": 0xe0533c, "lid": 0x7fb069,
       "axle_pin": 0x3a3a3a, "crank_pin": 0x3a3a3a, "hub": 0x9aa5b1, "pawl": 0xf2c14e,
       "rotor": 0x3d5a80, "knob": 0xee964b, "retaining_pin": 0x3a3a3a}


def key(n):
    return n.split("_", 1)[1] if n[0] == "s" and n[1].isdigit() else n


def asm(rotor_deg=0.0, alphas=None, stations=None):
    alphas = alphas or {}
    parts = dict(F.centre_parts(rotor_deg))
    for k in (stations if stations is not None else range(F.N)):
        parts.update(F.station_parts(k, alphas.get(k, 0.0)))
    return {n: (m, COL[key(n)]) for n, m in parts.items()}


def cut(parts, normal, offset):
    out = {}
    for n, (m, c, *r) in parts.items():
        t = m.trim_by_plane(normal, offset)
        if not t.is_empty():
            out[n] = (t, c, *r)
    return out


def p(name):
    return os.path.join(OUT, name)


# 1 hero
render(asm(0.0, {0: 90.0}), p("hero_station1_open.png"), eye=(300, -330, 290), target=(10, 0, 10), fov=28)
render(asm(0.0), p("all_closed.png"), eye=(300, -330, 290), target=(10, 0, 10), fov=28)

# 2 station close-ups (closed / open)
for a, nm in ((0.0, "station_closed.png"), (90.0, "station_open.png")):
    s = asm(0.0, {0: a}, stations=[0, 1, 5])
    render(s, p(nm), eye=(155, -150, 115), target=(55, 0, 22), fov=30)

# 3 vertical section through station 1 (plane y = 0), closed / half / open
for a, nm in ((0.0, "section_closed.png"), (35.0, "section_35deg.png"), (90.0, "section_open.png")):
    s = cut(asm(0.0, {0: a}, stations=[0]), (0, -1, 0), 0.0)   # keep y <= 0
    render(s, p(nm), eye=(55, 400, 38), target=(55, 0, 38), w=1400, h=800, ortho=40)

# 4 locked station: station 1 is selected, someone lifts the lid of station 2 -> bolt hits the rim
a_max = math.degrees(math.asin(F.TIP_CLR / F.E))
s = cut(asm(0.0, {1: a_max}, stations=[1]), (0.8660254, -0.5, 0), 0.0)
c = (55 * 0.5, 55 * 0.8660254)
render(s, p("section_station2_locked.png"), eye=(c[0] - 400 * 0.8660254, c[1] + 400 * 0.5, 38),
       target=(c[0], c[1], 38), w=1400, h=800, ortho=40)

# 5 plan section at bolt height (z = 29): one bolt in the notch, all others against the rim
for a, rd, nm in ((90.0, 0.0, "plan_section_station1_open.png"),
                  (0.0, 60.0, "plan_section_station2_selected.png")):
    al = {0: a} if a else {}
    s = cut(asm(rd, al), (0, 0, -1), -29.0)                     # keep z <= 29
    render(s, p(nm), eye=(0, 0, 500), target=(0, 0, 0), w=1200, h=1200, ortho=140, up=(0, 1, 0))
s = cut(asm(0.0, {0: 90.0}), (0, 0, -1), -29.0)
render(s, p("plan_section_notch_zoom.png"), eye=(45, 0, 500), target=(45, 0, 0), w=1200, h=900, ortho=26, up=(0, 1, 0))

# 6 ratchet / pawl section (z = 22)
s = {n: v for n, v in asm(0.0, stations=[]).items() if n in ("hub", "pawl", "rotor", "knob", "retaining_pin")}
render(cut(s, (0, 0, -1), -22.0), p("ratchet_section.png"), eye=(4, 10, 400), target=(4, 10, 0),
       w=1200, h=1000, ortho=17, up=(0, 1, 0))

# 7 exploded view (one station + centre)
import numpy as np  # noqa: E402
ex = {}
cp = F.centre_parts(0.0)
lift = {"hub": 0, "pawl": 25, "rotor": 50, "knob": 80, "retaining_pin": 105}
for n, m in cp.items():
    ex[n] = (m.translate([0, 0, lift[n]]), COL[n])
sp = F.station_parts(0, 0.0)
off = {"module": (40, 0, 0), "bowl": (40, 0, 45), "bolt": (40, 0, 30), "lid": (40, 0, 70),
       "axle_pin": (40, -40, 70), "crank_pin": (40, 40, 85)}
for n, m in sp.items():
    ex[n] = (m.translate(list(off[key(n)])), COL[key(n)])
render(ex, p("exploded.png"), eye=(300, -420, 330), target=(55, 0, 65), fov=30)
print("images written to", OUT)
