"""
Round donkey feeder - mechanical one-at-a-time interlock - Proof of Concept
==========================================================================

Parametric CAD model (Python + manifold3d).  Run `python3 cad/build.py` to
regenerate every STL, and `python3 cad/verify.py` to re-run the mechanical
checks.

Working principle
-----------------
* A central SELECTOR DISC (rotor) carries exactly ONE notch in its rim.
* Each of the N feeding stations has a LOCKING BOLT (flat slide) that points
  radially at the rim of the selector disc.
* The LID of each station is hinged on a pin.  The lid carries a crank pin that
  runs in a vertical slot of the bolt (Scotch yoke).  Lifting the lid therefore
  *forces* the bolt radially inward by E = 9 mm.
* If the notch is not in front of that bolt, the bolt hits the solid rim after
  0.6 mm and the lid cannot be lifted  -> station locked.
* If the notch is in front of the bolt, the lid opens, the bolt drops into the
  notch and now LOCKS THE SELECTOR DISC.  No other station can ever be selected
  while this lid is open.  -> never more than one bowl open.
* At full opening the crank is at dead-centre, so the selector cannot push the
  bolt back out (self-locking, no springs involved).
* The selector is indexed by a knob; a printed flexure pawl gives a click at
  every station and only allows forward (counter-clockwise) rotation, so the
  feeding position always moves on around the circle -> the donkey has to walk.

Coordinate system
-----------------
Global: origin = centre of the feeder, Z up, table at Z = 0.
Station k (k = 0..N-1, labelled k+1) lies at angle 60*k degrees (CCW from +X).
"Module local" frame: x = radial outward, y = tangential, z = up.
All station parts are modelled in that local frame and rotated into place.
All dimensions in millimetres.
"""
from __future__ import annotations

import math
import numpy as np
from manifold3d import Manifold, CrossSection, FillRule
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
from shapely import affinity

SEG = 96  # circle resolution

# ---------------------------------------------------------------------------
# PARAMETERS
# ---------------------------------------------------------------------------
N = 6                      # number of feeding stations
PITCH = 360.0 / N

# Printing clearances (FDM, 0.4 mm nozzle)
C_SLIDE = 0.30             # per side, sliding fits (bolt in tunnel etc.)
C_DOVE = 0.20              # per side, dovetail / keyed fits
C_POCKET = 0.25            # per side, pawl anchor pocket
EF, EF_H = 0.3, 0.4         # elephant-foot relief on bed-side fits (width, height)

# Pins
PIN_D = 4.0
HOLE_FIXED = 4.3           # pin is retained here (cheeks)
HOLE_ROT = 4.5             # part rotates on the pin (lid ears)
SLOT_W = 4.6               # pin slides in slot (bolt)

# Selector (rotor)
R_ROT = 38.0
ROT_Z0, ROT_Z1 = 25.0, 33.0
NOTCH_HALF = 2.5 + 0.4     # bolt half-thickness + clearance
NOTCH_CHAMF = 1.5

# Locking bolt / Scotch yoke
E = 9.0                    # crank radius  == bolt stroke
TIP_CLR = 0.6              # closed bolt tip to rotor rim
X_TIP = R_ROT + TIP_CLR    # 38.6 (closed)
X_H, Z_H = 63.0, 29.0      # lid hinge axis (local x, z)
DECK = 24.0                # module deck height
PL_T = 5.0                 # bolt plate thickness (y)
PL_Z0 = DECK + 0.3         # modelled bolt bottom (rests on deck in reality)
PL_A_TOP = PL_Z0 + 10.0    # 34.3
NOTCH_R_BOTTOM = X_TIP - E - 0.7   # 28.9

# Hub
R_HUB_DISC = 39.3
HUB_DISC_H = 6.0
R_COLUMN = 27.5
COL_TOP = ROT_Z0           # rotor rests on column top
BORE_D = 10.6               # knob axle (d 10.0) runs in here
BORE_Z0 = 10.0
RPIN_D = 5.0                # retaining pin (selector hold-down)
RPIN_HOLE = 5.4
RPIN_LEDGE_Z = 3.0          # snap ledge under the hub
RPIN_CB_D = 12.0            # counterbore under the hub for the snap tip
KNOB_TOP = ROT_Z1 + 10.0
RPIN_HEAD_D, RPIN_HEAD_H = 11.0, 2.5
RPIN_SEAT_Z = KNOB_TOP - 3.0

# Ratchet / detent
RING_TIP = 19.6
RING_ROOT = 21.0
RING_OUT = 23.0
RING_Z0 = 19.0
CH_IN, CH_OUT = 18.6, 23.6       # channel in column for the ring
CH_FLOOR = 18.0
STUB_TOP = 24.7
BETA_P = 30.0                    # hub angle of the pawl bump (between stations)
PAWL_Z0, PAWL_H = 18.2, 6.2

# Module
MOD_R0 = 39.5                    # inner face
MOD_R1 = 129.0                   # outer end
MOD_HW0, MOD_HW = 21.0, 24.0     # half width at inner face / body
GUIDE_X0, GUIDE_X1 = MOD_R0, 48.5
GUIDE_HW = 7.0
TUNNEL_HW = PL_T / 2 + C_SLIDE   # 2.8
TUNNEL_TOP = PL_A_TOP + 0.6      # 34.9
GUIDE_TOP = TUNNEL_TOP + 2.5
CHEEK_Y0, CHEEK_Y1 = 7.5, 12.5
CHEEK_R = 4.8
EAR_Y0, EAR_Y1 = 3.0, 7.0
TRENCH_Y0, TRENCH_Y1 = 2.8, 7.3
TRENCH_X0, TRENCH_X1, TRENCH_Z = 56.5, 71.0, 21.4
BOWL_X = 103.0
BOWL_R = 21.0
BOWL_POCKET_R = BOWL_R + 0.4
BOWL_FLOOR = 4.0

# Lid
LID_X0 = X_H + 6.0
LID_X1 = 127.0
LID_HW = 23.5
LID_T = 3.0
LID_SLOT_HW = 3.0
LID_SLOT_X1 = X_H + 17.0

# Dovetail (module tongue, local frame)
DT_NECK_HW, DT_HEAD_HW = 4.0, 6.5
DT_X_HEAD = 32.5
DT_H = HUB_DISC_H

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def cs_from_shapely(geom) -> CrossSection:
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    contours = []
    for p in polys:
        if p.is_empty:
            continue
        ext = np.asarray(p.exterior.coords)[:-1]
        if Polygon(ext).exterior.is_ccw is False:
            ext = ext[::-1]
        contours.append(ext)
        for h in p.interiors:
            hc = np.asarray(h.coords)[:-1]
            if Polygon(hc).exterior.is_ccw:
                hc = hc[::-1]
            contours.append(hc)
    return CrossSection(contours, FillRule.Positive)


def extrude_xy(geom, z0, z1) -> Manifold:
    """Extrude a shapely polygon in the XY plane from z0 to z1."""
    return Manifold.extrude(cs_from_shapely(geom), z1 - z0).translate([0, 0, z0])


def extrude_xz(geom, y0, y1) -> Manifold:
    """Profile given in (x, z) coordinates, extruded along Y from y0 to y1."""
    m = Manifold.extrude(cs_from_shapely(geom), y1 - y0)   # (u, v, w)
    # (u, v, w) -> (u, -w, v)  then shift so y in [y0, y1]
    m = m.rotate([90, 0, 0])
    return m.translate([0, y1, 0])


def circle(x, y, r, res=SEG):
    return Point(x, y).buffer(r, resolution=res // 4)


def stadium(p0, p1, r):
    return LineString([p0, p1]).buffer(r, resolution=SEG // 4)


def annulus(r0, r1):
    return circle(0, 0, r1).difference(circle(0, 0, r0))


def sector(r0, r1, a0, a1, n=120):
    """Annular sector between angles a0..a1 (deg, CCW)."""
    angs = np.radians(np.linspace(a0, a1, n))
    outer = [(r1 * math.cos(a), r1 * math.sin(a)) for a in angs]
    inner = [(r0 * math.cos(a), r0 * math.sin(a)) for a in angs[::-1]]
    return Polygon(outer + inner)


def cyl_z(r, z0, z1, x=0.0, y=0.0):
    return Manifold.cylinder(z1 - z0, r, r, SEG).translate([x, y, z0])


def cyl_y(r, y0, y1, x, z):
    """Cylinder along Y axis through (x, z)."""
    m = Manifold.cylinder(y1 - y0, r, r, SEG)        # along +z
    m = m.rotate([-90, 0, 0])                         # +z -> +y
    return m.translate([x, y0, z])


def rot_z(m: Manifold, deg) -> Manifold:
    return m.rotate([0, 0, deg])


def lid_transform(m: Manifold, alpha_deg) -> Manifold:
    """Rotate a lid-attached solid about the hinge axis (opening angle alpha).
    Opening lifts the lid: +x direction turns towards +z."""
    return (m.translate([-X_H, 0, -Z_H])
             .rotate([0, -alpha_deg, 0])
             .translate([X_H, 0, Z_H]))


def bolt_stroke(alpha_deg):
    """Inward bolt displacement (mm, >=0) produced by lid angle alpha."""
    return E * math.sin(math.radians(alpha_deg))


# ---------------------------------------------------------------------------
# PARTS  (each returns a Manifold in its ASSEMBLY position)
# ---------------------------------------------------------------------------

# ---- dovetail -------------------------------------------------------------

def dovetail_profile(offset=0.0):
    p = Polygon([(MOD_R0 + 1.0, -DT_NECK_HW), (MOD_R0 + 1.0, DT_NECK_HW),
                 (MOD_R0 - 0.01, DT_NECK_HW), (DT_X_HEAD, DT_HEAD_HW),
                 (DT_X_HEAD, -DT_HEAD_HW), (MOD_R0 - 0.01, -DT_NECK_HW)])
    if offset:
        p = p.buffer(offset, join_style=2)
    return p


# ---- pawl (detent / one-way ratchet spring) -------------------------------

def pawl_profile():
    """2D outline of the flexure pawl, hub frame."""
    arm = sector(16.2, 18.0, BETA_P - 11.0, BETA_P + 70.0)
    anchor = sector(10.0, 14.5, BETA_P + 62.0, BETA_P + 88.0)
    web = sector(13.8, 16.6, BETA_P + 62.0, BETA_P + 72.0)
    # bump, defined in (s = arc length CCW, r) about BETA_P at r_ref
    r_ref = 19.0
    pts_sr = [(-3.2, 17.6), (-0.6, 20.7), (0.8, 20.7), (1.2, 17.6)]
    pts = []
    for s, r in pts_sr:
        a = math.radians(BETA_P) + s / r_ref
        pts.append((r * math.cos(a), r * math.sin(a)))
    bump = Polygon(pts)
    return unary_union([arm, anchor, web, bump]).buffer(0.15).buffer(-0.15)


def make_pawl():
    return extrude_xy(pawl_profile(), PAWL_Z0, PAWL_Z0 + PAWL_H)


def pawl_pocket_profile():
    p = pawl_profile().buffer(C_POCKET, join_style=2)
    free = sector(14.2, CH_IN + 0.5, BETA_P - 16.0, BETA_P + 61.0)
    return unary_union([p, free])


# ---- hub ------------------------------------------------------------------

def make_hub():
    disc = Polygon(circle(0, 0, R_HUB_DISC))
    sockets = unary_union([affinity.rotate(dovetail_profile(C_DOVE), k * PITCH,
                                           origin=(0, 0)) for k in range(N)])
    disc = disc.difference(sockets)
    hub = extrude_xy(disc, 0, HUB_DISC_H)
    # elephant-foot relief: sockets 0.3 mm wider in the first 0.4 mm
    relief = unary_union([affinity.rotate(dovetail_profile(C_DOVE + EF), k * PITCH, origin=(0, 0))
                          for k in range(N)])
    hub = hub - extrude_xy(relief, -1, EF_H)
    hub = hub + cyl_z(R_COLUMN, HUB_DISC_H - 0.01, COL_TOP)
    # channel for the ratchet ring
    hub = hub - extrude_xy(annulus(CH_IN, CH_OUT), CH_FLOOR, COL_TOP + 1)
    # lower the stub so the rotor bears only on the outer annulus
    hub = hub - cyl_z(CH_IN + 0.01, STUB_TOP, COL_TOP + 1)
    # axle bore
    hub = hub - cyl_z(BORE_D / 2, BORE_Z0, COL_TOP + 1)
    hub = hub - cyl_z(RPIN_HOLE / 2, -1, BORE_Z0 + 0.01)
    hub = hub - cyl_z(RPIN_CB_D / 2, -1, RPIN_LEDGE_Z)
    # pawl pocket
    hub = hub - extrude_xy(pawl_pocket_profile(), CH_FLOOR, COL_TOP + 1)
    # direction-of-rotation arrows on the column top annulus? (no - hidden)
    return hub


# ---- selector rotor ---------------------------------------------------------

def ring_inner_profile():
    """Inner outline of the ratchet ring (rotor frame) as polygon points."""
    r_mid = 20.3
    pockets = [BETA_P + PITCH * m for m in range(N)]
    pts = []
    n = 2160
    for i in range(n):
        psi = 360.0 * i / n
        r = RING_TIP
        for pc in pockets:
            d = (psi - pc + 180.0) % 360.0 - 180.0
            s = math.radians(d) * r_mid
            if -0.9 <= s <= 1.1:
                r = RING_ROOT
            elif -5.4 <= s < -0.9:                    # ramp (forward exit)
                t = (s + 5.4) / 4.5
                r = RING_TIP + t * (RING_ROOT - RING_TIP)
        a = math.radians(psi)
        pts.append((r * math.cos(a), r * math.sin(a)))
    # make the steep wall exactly radial: insert explicit vertices
    poly = Polygon(pts)
    for pc in pockets:
        a = math.radians(pc) + 1.1 / r_mid
        wall = Polygon([(RING_TIP * 0.98 * math.cos(a - 0.004), RING_TIP * 0.98 * math.sin(a - 0.004)),
                        (RING_ROOT * math.cos(a - 0.004), RING_ROOT * math.sin(a - 0.004)),
                        (RING_ROOT * math.cos(a - 0.0001), RING_ROOT * math.sin(a - 0.0001)),
                        (RING_TIP * 0.98 * math.cos(a - 0.0001), RING_TIP * 0.98 * math.sin(a - 0.0001))])
        poly = poly.union(wall)
    return poly


def key_profile(clear=0.0):
    c = circle(0, 0, 5.0 + clear)
    k = box(4.0, -1.5 - clear, 6.5 + clear, 1.5 + clear)
    return unary_union([c, k])


def make_rotor():
    disc = circle(0, 0, R_ROT)
    notch = Polygon([(NOTCH_R_BOTTOM, -NOTCH_HALF), (R_ROT - NOTCH_CHAMF, -NOTCH_HALF),
                     (R_ROT + 0.5, -NOTCH_HALF - NOTCH_CHAMF - 0.5),
                     (R_ROT + 5, -NOTCH_HALF - NOTCH_CHAMF - 0.5),
                     (R_ROT + 5, NOTCH_HALF + NOTCH_CHAMF + 0.5),
                     (R_ROT + 0.5, NOTCH_HALF + NOTCH_CHAMF + 0.5),
                     (R_ROT - NOTCH_CHAMF, NOTCH_HALF), (NOTCH_R_BOTTOM, NOTCH_HALF)])
    disc = disc.difference(notch).difference(key_profile(0.2))
    rotor = extrude_xy(disc, ROT_Z0, ROT_Z1)
    ring = circle(0, 0, RING_OUT).difference(ring_inner_profile())
    rotor = rotor + extrude_xy(ring, RING_Z0, ROT_Z0 + 0.01)
    rotor = rotor - extrude_xy(key_profile(0.2 + EF), ROT_Z1 - EF_H, ROT_Z1 + 1)   # elephant-foot relief
    # engraved arrow on top face pointing at the notch
    arrow = Polygon([(33.5, 0), (27.0, -3.2), (27.0, -1.2), (17.0, -1.2),
                     (17.0, 1.2), (27.0, 1.2), (27.0, 3.2)])
    rotor = rotor - extrude_xy(arrow, ROT_Z1 - 0.6, ROT_Z1 + 1)
    # forward-direction arc arrows (CCW) on top face
    for a0 in (60, 180, 300):
        arc = sector(31.0, 32.6, a0, a0 + 40)
        a = math.radians(a0 + 40)
        head = Polygon([(29.6 * math.cos(a), 29.6 * math.sin(a)),
                        (34.0 * math.cos(a), 34.0 * math.sin(a)),
                        (31.8 * math.cos(a + 0.13), 31.8 * math.sin(a + 0.13))])
        rotor = rotor - extrude_xy(arc.union(head), ROT_Z1 - 0.6, ROT_Z1 + 1)
    return rotor


# ---- knob -------------------------------------------------------------------

def make_knob():
    head = unary_union([circle(0, 0, 15.0),
                        Polygon([(0, 9.0), (23.0, 0), (0, -9.0)])]).buffer(1.0).buffer(-1.0)
    # grip scallops (away from the pointer)
    for i in range(10):
        a = math.radians(36 * i + 18)
        if abs(((36 * i + 18) + 180) % 360 - 180) < 40:
            continue
        head = head.difference(circle(16.3 * math.cos(a), 16.3 * math.sin(a), 2.2))
    z0, z1 = ROT_Z1, KNOB_TOP
    knob = extrude_xy(head, z0, z1)
    knob = knob + extrude_xy(key_profile(0.0), ROT_Z0 + 0.4, z0 + 0.01)
    knob = knob + cyl_z(4.97, BORE_Z0 + 0.6, ROT_Z0 + 0.41)
    knob = knob - cyl_z(RPIN_HOLE / 2, 0, z1 + 1)
    knob = knob - cyl_z(RPIN_HEAD_D / 2 + 0.4, RPIN_SEAT_Z, z1 + 1)
    # engraved pointer arrow on top
    arrow = Polygon([(21.0, 0), (15.0, -3.0), (15.0, -1.0), (7.5, -1.0),
                     (7.5, 1.0), (15.0, 1.0), (15.0, 3.0)])
    knob = knob - extrude_xy(arrow, z1 - 0.6, z1 + 1)
    return knob


# ---- module (one feeding station) --------------------------------------------

def module_footprint():
    p = Polygon([(MOD_R0, -MOD_HW0), (52.0, -MOD_HW), (MOD_R1, -MOD_HW),
                 (MOD_R1, MOD_HW), (52.0, MOD_HW), (MOD_R0, MOD_HW0)])
    return p.buffer(-3, join_style=1).buffer(3, join_style=1)


def make_module(station_no: int | None = None):
    body = extrude_xy(module_footprint(), 0, DECK)
    # bowl pocket + finger notch
    body = body - cyl_z(BOWL_POCKET_R, BOWL_FLOOR, DECK + 1, BOWL_X, 0)
    body = body - cyl_z(6.0, 12.0, DECK + 1, BOWL_X + BOWL_R + 1.0, 0)
    # dovetail tongue (under the inner face)
    body = body + extrude_xy(dovetail_profile(), EF_H, DT_H)
    body = body + extrude_xy(dovetail_profile(-EF), 0, EF_H + 0.01)
    # guide block with tunnel for the bolt
    guide = extrude_xy(box(GUIDE_X0, -GUIDE_HW, GUIDE_X1, GUIDE_HW), DECK - 0.01, GUIDE_TOP)
    tunnel = extrude_xy(box(GUIDE_X0 - 1, -TUNNEL_HW, GUIDE_X1 + 1, TUNNEL_HW), DECK, TUNNEL_TOP)
    body = body + guide - tunnel
    # hinge cheeks
    cheek = unary_union([box(X_H - CHEEK_R, DECK - 0.01, X_H + CHEEK_R, Z_H),
                         circle(X_H, Z_H, CHEEK_R)])
    for s in (1, -1):
        y0, y1 = (CHEEK_Y0, CHEEK_Y1) if s > 0 else (-CHEEK_Y1, -CHEEK_Y0)
        body = body + extrude_xz(cheek, y0, y1)
        # trench for the lid ears' swing
        tr = box(TRENCH_X0, TRENCH_Z, TRENCH_X1, DECK + 1)
        ty0, ty1 = (TRENCH_Y0, TRENCH_Y1) if s > 0 else (-TRENCH_Y1, -TRENCH_Y0)
        body = body - extrude_xz(tr, ty0, ty1)
    body = body - cyl_y(HOLE_FIXED / 2, -CHEEK_Y1 - 1, CHEEK_Y1 + 1, X_H, Z_H)
    # station number pips on top of the guide block
    if station_no:
        pips = pip_layout(station_no)
        cx, cy = (GUIDE_X0 + GUIDE_X1) / 2, 0.0
        for (px, py) in pips:
            body = body - cyl_z(1.1, GUIDE_TOP - 0.6, GUIDE_TOP + 1, cx + px * 2.9, cy + py * 3.6)
    return body


def pip_layout(n):
    L = {1: [(0, 0)], 2: [(-1, -1), (1, 1)], 3: [(-1, -1), (0, 0), (1, 1)],
         4: [(-1, -1), (-1, 1), (1, -1), (1, 1)],
         5: [(-1, -1), (-1, 1), (0, 0), (1, -1), (1, 1)],
         6: [(-1, -1), (-1, 0), (-1, 1), (1, -1), (1, 0), (1, 1)]}
    return L[n]


# ---- locking bolt -------------------------------------------------------------

def bolt_profile_xz():
    A = box(X_TIP, PL_Z0, X_H - 5.0, PL_A_TOP)
    B1 = box(X_H - 5.0, PL_Z0, X_H + 5.0, Z_H + E + SLOT_W / 2 + 0.4 + 2.5)
    B2 = box(X_H + 5.0 - 0.01, PL_Z0, X_H + E + SLOT_W / 2 + 0.3 + 2.4, Z_H + SLOT_W / 2 + 2.5)
    p = unary_union([A, B1, B2]).buffer(-0.8, join_style=1).buffer(0.8, join_style=1)
    # restore the sharp tip region (chamfered in plan instead)
    p = p.union(box(X_TIP, PL_Z0, X_TIP + 3, PL_A_TOP))
    hs = stadium((X_H, Z_H), (X_H + E + 0.3, Z_H), SLOT_W / 2)      # axle slot
    vs = stadium((X_H, Z_H), (X_H, Z_H + E + 0.4), SLOT_W / 2)      # crank slot
    return p.difference(hs).difference(vs)


def make_bolt(stroke=0.0):
    b = extrude_xz(bolt_profile_xz(), -PL_T / 2, PL_T / 2)
    # tip chamfers in plan view (self-centring in the notch)
    # 45 deg x 1.0 mm chamfer on both tip corners (line through (X_TIP, 1.5)-(X_TIP+1, 2.5))
    cut = Polygon([(X_TIP - 1, 0.5), (X_TIP + 2, 3.5), (X_TIP - 1, 3.5)])
    for c in (cut, affinity.scale(cut, 1, -1, origin=(0, 0))):
        b = b - extrude_xy(c, 0, 60)
    return b.translate([-stroke, 0, 0])


# ---- lid ------------------------------------------------------------------------

def ear_profile_xz():
    A = circle(X_H, Z_H, 4.6)
    B = circle(X_H, Z_H + E, 4.5)
    arm = unary_union([A, B]).convex_hull
    web = unary_union([A, box(X_H + 5.0, DECK, X_H + 11.0, DECK + LID_T)]).convex_hull
    foot = box(X_H - 4.6, DECK, X_H, Z_H)
    p = unary_union([arm, web, foot])
    p = p.difference(circle(X_H, Z_H, HOLE_ROT / 2)).difference(circle(X_H, Z_H + E, HOLE_ROT / 2))
    return p


def make_lid(alpha=0.0):
    plate = box(LID_X0, -LID_HW, LID_X1, LID_HW).buffer(-2, join_style=1).buffer(2, join_style=1)
    plate = plate.difference(box(LID_X0 - 1, -LID_SLOT_HW, LID_SLOT_X1, LID_SLOT_HW))
    lid = extrude_xy(plate, DECK, DECK + LID_T)
    # grip tab
    lid = lid + extrude_xy(box(LID_X1 - 6, -10, LID_X1, 10).buffer(-1, join_style=1).buffer(1),
                           DECK + LID_T - 0.01, DECK + LID_T + 5)
    for s in (1, -1):
        y0, y1 = (EAR_Y0, EAR_Y1) if s > 0 else (-EAR_Y1, -EAR_Y0)
        lid = lid + extrude_xz(ear_profile_xz(), y0, y1)
    return lid_transform(lid, alpha)


# ---- bowl -------------------------------------------------------------------------

def make_bowl():
    h = DECK - 0.6 - BOWL_FLOOR
    outer = cyl_z(BOWL_R, 0, h)
    inner = Manifold.cylinder(h, BOWL_R - 2.0 - 1.5, BOWL_R - 2.0, SEG).translate([0, 0, 2.0])
    b = outer - inner
    return b.translate([BOWL_X, 0, BOWL_FLOOR])


# ---- snap pins -----------------------------------------------------------------------

def snap_pin_local(grip, d=PIN_D, head_d=7.0, head_h=2.0, lip_d=4.7, slot=1.3,
                   slot_len=7.0, lip_len=2.2, flat=0.2):
    """Snap pin along +z, head underside at z=0, `grip` = material thickness held.
    Split tip with a lip; flats at +-y are the print faces."""
    head = Manifold.cylinder(head_h, head_d / 2, head_d / 2, SEG).translate([0, 0, -head_h])
    L = grip + 0.3
    shaft = Manifold.cylinder(L, d / 2, d / 2, SEG)
    lip = Manifold.cylinder(lip_len, lip_d / 2, d / 2 - 0.1, SEG).translate([0, 0, L])
    p = head + shaft + lip
    p = p - Manifold.cube([slot, 40, slot_len]).translate([-slot / 2, -20, L + lip_len - slot_len])
    flats = Manifold.cube([40, 40, 200]).translate([-20, d / 2 - flat, -50])
    p = p - flats - flats.mirror([0, 1, 0])
    return p


AXLE_GRIP = 2 * CHEEK_Y1                 # 25
CRANK_GRIP = 2 * EAR_Y1                  # 14


def make_axle_pin():
    p = snap_pin_local(AXLE_GRIP)        # local z -> global -y
    p = p.rotate([90, 0, 0])
    return p.translate([X_H, CHEEK_Y1, Z_H])


def make_crank_pin(alpha=0.0):
    p = snap_pin_local(CRANK_GRIP).rotate([90, 0, 0]).translate([X_H, EAR_Y1, Z_H + E])
    return lid_transform(p, alpha)


RPIN_GRIP = RPIN_SEAT_Z - RPIN_LEDGE_Z


def retaining_pin_local():
    return snap_pin_local(RPIN_GRIP, d=RPIN_D, head_d=RPIN_HEAD_D, head_h=RPIN_HEAD_H,
                          lip_d=5.9, slot=1.4, slot_len=11.0, lip_len=2.0, flat=0.3)


def make_retaining_pin():
    """Vertical pin through knob and hub, snaps under the hub: holds selector + knob down."""
    return retaining_pin_local().rotate([180, 0, 0]).translate([0, 0, RPIN_SEAT_Z])


def make_pin_print(local):
    """Pin laid flat for printing: axis along X, flat face on the bed."""
    p = local.rotate([0, 90, 0]).rotate([90, 0, 0])   # axis -> x, flats (y) -> z
    bb = p.bounding_box()
    return p.translate([-bb[0], -bb[1], -bb[2]])


# ---------------------------------------------------------------------------
# ASSEMBLY
# ---------------------------------------------------------------------------

def station_parts(k, alpha=0.0, stroke=None):
    """All parts of station k (0-based) in global coordinates for lid angle alpha.
    `stroke` overrides the bolt position (used to test blocked states)."""
    if stroke is None:
        stroke = bolt_stroke(alpha)
    ang = k * PITCH
    parts = {
        "module": make_module(k + 1),
        "bowl": make_bowl(),
        "bolt": make_bolt(stroke),
        "lid": make_lid(alpha),
        "axle_pin": make_axle_pin(),
        "crank_pin": make_crank_pin(alpha),
    }
    return {f"s{k + 1}_{n}": rot_z(m, ang) for n, m in parts.items()}


def centre_parts(rotor_deg=0.0):
    return {
        "hub": make_hub(),
        "pawl": make_pawl(),
        "rotor": rot_z(make_rotor(), rotor_deg),
        "knob": rot_z(make_knob(), rotor_deg),
        "retaining_pin": rot_z(make_retaining_pin(), rotor_deg),
    }
