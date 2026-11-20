"""Builds the static profile graphics into assets/.

    python scripts/build.py

Writes a dark and a light version of: hero, bench (section 1 header),
setup (stack), footer. The season chart is built by season.py in CI.
"""

import math
import os
import random

from kit import MONO, THEMES, esc, f, sector_header, svg, text

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

# ---------------------------------------------------------------------------
# Circuit + lap simulation. The telemetry trace in the hero is computed from
# the circuit drawn next to it, so the car, the cursor and the numbers agree.
# ---------------------------------------------------------------------------

TRACK_PTS = [
    (60, 170), (150, 172), (236, 170), (272, 162), (282, 144), (266, 130),
    (226, 124), (196, 112), (188, 90), (206, 66), (248, 50), (292, 44),
    (314, 30), (306, 12), (278, 8), (200, 16), (120, 22), (92, 30),
    (76, 22), (56, 24), (30, 40), (16, 72), (14, 112), (22, 148), (36, 166),
]
TRACK_BOX = (836, 196)  # where the circuit sits in the hero
LAP_SECONDS = 10.0      # one replayed lap on screen
LIGHTS_OUT = 2.5        # seconds into the page load


def catmull_closed(pts):
    """Closed Catmull-Rom spline as cubic Bezier segments."""
    n = len(pts)
    segs = []
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        segs.append((p1, c1, c2, p2))
    return segs


def bez(seg, u):
    p0, c1, c2, p1 = seg
    a, b, c, d = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
    return (a * p0[0] + b * c1[0] + c * c2[0] + d * p1[0],
            a * p0[1] + b * c1[1] + c * c2[1] + d * p1[1])


def track_path(segs, ox, oy):
    p = segs[0][0]
    out = [f"M{f(p[0] + ox)} {f(p[1] + oy)}"]
    for _, c1, c2, p1 in segs:
        out.append(f"C{f(c1[0] + ox)} {f(c1[1] + oy)} {f(c2[0] + ox)} {f(c2[1] + oy)} {f(p1[0] + ox)} {f(p1[1] + oy)}")
    return "".join(out) + "Z"


def simulate():
    segs = catmull_closed(TRACK_PTS)
    raw = [bez(s, k / 80) for s in segs for k in range(80)]
    # resample at equal distances
    cum = [0.0]
    for i in range(1, len(raw) + 1):
        a, b = raw[i - 1], raw[i % len(raw)]
        cum.append(cum[-1] + math.dist(a, b))
    length_px = cum[-1]
    n = 720
    pts, j = [], 0
    for i in range(n):
        s = length_px * i / n
        while cum[j + 1] < s:
            j += 1
        a, b = raw[j], raw[(j + 1) % len(raw)]
        u = (s - cum[j]) / max(cum[j + 1] - cum[j], 1e-9)
        pts.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))

    m_per_px = 5200 / length_px          # a 5.2 km lap
    ds = m_per_px * length_px / n

    # curvature from three points, then smoothed
    k = []
    for i in range(n):
        a, b, c = pts[i - 4], pts[i], pts[(i + 4) % n]
        ab, bc, ca = math.dist(a, b), math.dist(b, c), math.dist(c, a)
        area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        k.append((2 * area2 / max(ab * bc * ca, 1e-9)) / m_per_px)
    k = [sum(k[(i + d) % n] for d in range(-3, 4)) / 7 for i in range(n)]

    v_top, a_lat, a_brk = 92.0, 20.0, 45.0
    vmax = [min(v_top, math.sqrt(a_lat / max(c, 1e-6))) for c in k]
    v = vmax[:]
    for _ in range(3):  # forward (traction) and backward (braking) passes, wrapped
        for i in range(1, 2 * n):
            p, c = (i - 1) % n, i % n
            acc = 14.0 * (1 - v[p] / v_top) + 0.6
            v[c] = min(v[c], math.sqrt(v[p] ** 2 + 2 * acc * ds))
        for i in range(2 * n, 0, -1):
            c, p = i % n, (i - 1) % n
            v[p] = min(v[p], math.sqrt(v[c] ** 2 + 2 * a_brk * ds))

    dv = [v[(i + 1) % n] - v[i] for i in range(n)]
    throttle = [d > 0.02 or v[i] > v_top - 0.5 for i, d in enumerate(dv)]
    brake = [d < -0.25 for d in dv]

    t = [0.0]
    for i in range(n):
        t.append(t[-1] + ds / ((v[i] + v[(i + 1) % n]) / 2))
    lap = t[-1]
    return dict(segs=segs, n=n, v=v, t=t, lap=lap, throttle=throttle, brake=brake,
                start=pts[0], heading=(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]))


def fmt_lap(sec):
    m = int(sec // 60)
    return f"{m}:{sec - 60 * m:06.3f}"


# ---------------------------------------------------------------------------
# Lettering. Monoline, chamfered, race-number proportions. Drawn as strokes so
# each one can be "driven" in. No font files involved.
# ---------------------------------------------------------------------------

GLYPHS = {
    "S": ["M96 16H40L16 40V76L40 100H72L96 124V160L72 184H16"],
    "O": ["M16 104V40L40 16H72L96 40V160L72 184H40L16 160V100"],
    "H": ["M16 16V184", "M96 16V184", "M16 100H96"],
    "A": ["M16 184V48L48 16H64L96 48V184", "M16 112H96"],
    "M": ["M16 184V16L56 76L96 16V184"],
}


def hero(t, sim):
    W, H = 1200, 600
    css = []
    b = []
    seg = sim["segs"]
    ox, oy = TRACK_BOX
    tp = track_path(seg, ox, oy)

    css.append("""
.fade{animation:fade .7s ease both}
@keyframes fade{from{opacity:0}}
.hx{transform-box:fill-box;transform-origin:0 50%;animation:hx 1.2s cubic-bezier(.6,0,.2,1) .1s both}
@keyframes hx{from{transform:scaleX(0)}}
.lamp{opacity:0;animation-name:lamp;animation-timing-function:steps(1,end)}
@keyframes lamp{0%,100%{opacity:1}}
.ln{fill:none;stroke-width:32;stroke-linejoin:miter;stroke-miterlimit:3;stroke-dasharray:1 1;
animation:ln .62s cubic-bezier(.7,0,.25,1) both}
@keyframes ln{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
.gl{fill:none;stroke-width:2;stroke-dasharray:1 1;animation:gl 1.1s cubic-bezier(.5,0,.2,1) both}
@keyframes gl{0%{stroke-dashoffset:1;opacity:1}60%{stroke-dashoffset:0;opacity:1}100%{stroke-dashoffset:0;opacity:0}}
.fl{opacity:0;animation:fl .07s steps(1,end)}
@keyframes fl{0%,100%{opacity:1}}
.fx{animation:fx .05s linear both}
@keyframes fx{from{opacity:0}to{opacity:1}}
.tr{fill:none;stroke-dasharray:1 1;animation:tr 2.6s cubic-bezier(.45,0,.2,1) .5s both}
@keyframes tr{from{stroke-dashoffset:1}}
.up{transform-box:fill-box;transform-origin:50% 100%;animation:up .9s cubic-bezier(.2,.8,.2,1) both}
@keyframes up{from{transform:scaleY(0)}}
""")

    # header row -----------------------------------------------------------
    b.append(text(40, 36, "SACKEDBALL", 14, t["ink"], weight=700, spacing=3, extra=' class="fade"'))
    b.append(text(178, 36, "/  GITHUB PROFILE  /  2026", 14, t["dim"], spacing=2, extra=' class="fade" style="animation-delay:.15s"'))
    b.append(text(1160, 36, "MUMBAI  19.08°N  72.88°E", 14, t["dim"], "end", spacing=2, extra=' class="fade" style="animation-delay:.3s"'))
    b.append(f'<rect class="hx" x="40" y="54" width="1120" height="1" fill="{t["hair"]}"/>')

    # start lights ---------------------------------------------------------
    gx, gy, pw, ph, gap = 828, 84, 52, 96, 18
    b.append(f'<g class="fade" style="animation-delay:.2s">')
    b.append(f'<rect x="{gx - 10}" y="{gy + 6}" width="{5 * pw + 4 * gap + 20}" height="8" rx="2" fill="{t["pod"]}" stroke="{t["pod_edge"]}"/>')
    for i in range(5):
        x = gx + i * (pw + gap)
        b.append(f'<rect x="{x}.5" y="{gy}.5" width="{pw}" height="{ph}" rx="10" fill="{t["pod"]}" stroke="{t["pod_edge"]}"/>')
        for ly in (gy + 28, gy + 68):
            b.append(f'<circle cx="{x + pw / 2}" cy="{ly}" r="14" fill="{t["lamp_off"]}"/>')
    b.append("</g>")
    b.append(f'<defs><radialGradient id="halo"><stop offset="0" stop-color="{t["lamp_on"]}" stop-opacity=".55"/>'
             f'<stop offset="1" stop-color="{t["lamp_on"]}" stop-opacity="0"/></radialGradient></defs>')
    for i in range(5):
        on = 0.3 + i * 0.4
        x = gx + i * (pw + gap) + pw / 2
        b.append(f'<g class="lamp" style="animation-delay:{on:.2f}s;animation-duration:{LIGHTS_OUT - on:.2f}s">')
        for ly in (gy + 28, gy + 68):
            b.append(f'<circle cx="{x}" cy="{ly}" r="30" fill="url(#halo)"/>')
            b.append(f'<circle cx="{x}" cy="{ly}" r="14" fill="{t["lamp_on"]}"/>')
            b.append(f'<circle cx="{x - 4}" cy="{ly - 4}" r="4" fill="#FFD2C8" opacity=".8"/>')
        b.append("</g>")
    b.append(text(gx, gy + ph + 26, "LIGHTS", 12, t["mute"], spacing=3, extra=' class="fade" style="animation-delay:.4s"'))

    # name -----------------------------------------------------------------
    nx, ny, adv = 40, 92, 142
    d0 = LIGHTS_OUT + 0.05
    for li, ch in enumerate("SOHAM"):
        x = nx + li * adv
        for si, d in enumerate(GLYPHS[ch]):
            delay = d0 + li * 0.085 + si * 0.11
            b.append(f'<path class="gl" pathLength="1" d="{d}" transform="translate({x - 6} {ny + 6})" '
                     f'stroke="{t["accent"]}" style="animation-delay:{delay - 0.12:.2f}s"/>')
            b.append(f'<path class="ln" pathLength="1" d="{d}" transform="translate({x} {ny})" '
                     f'stroke="{t["ink"]}" style="animation-delay:{delay:.2f}s"/>')

    # sector bars under the name, filled live by the car ---------------------
    sim_t, n, lap = sim["t"], sim["n"], sim["lap"]
    sec_idx = [0, n // 3, 2 * n // 3, n]
    sec_frac = [sim_t[i] / lap for i in sec_idx]
    sec_time = [sim_t[sec_idx[k + 1]] - sim_t[sec_idx[k]] for k in range(3)]
    bx, by, bw, bg = 40, 318, 218, 13
    colors = [t["purple"], t["green"], t["yellow"]]
    for k in range(3):
        x = bx + k * (bw + bg)
        a, z = sec_frac[k], min(sec_frac[k + 1], 0.98)  # keyTimes must not go backwards
        b.append(f'<rect x="{x}" y="{by}" width="{bw}" height="6" fill="{t["faint"]}"/>')
        b.append(f'<rect x="{x}" y="{by}" width="0" height="6" fill="{colors[k]}">'
                 f'<animate attributeName="width" begin="{LIGHTS_OUT}s" dur="{LAP_SECONDS}s" repeatCount="indefinite" '
                 f'values="0;0;{bw};{bw};0" keyTimes="0;{a:.4f};{z:.4f};0.985;1"/></rect>')
        b.append(text(x, by + 28, f"S{k + 1}", 12, colors[k], weight=700, spacing=2))
        b.append(text(x + bw, by + 28, f"{sec_time[k]:.3f}", 12, t["dim"], "end", spacing=1))

    # split-flap subtitle -------------------------------------------------------
    rnd = random.Random(7)
    pool = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789/#"
    sub = "STUDENT  /  DATA  /  FORMULA 1 TELEMETRY"
    cx0, cy, cw = 46, 396, 16.6
    t0 = LIGHTS_OUT + 0.7
    for i, ch in enumerate(sub):
        if ch == " ":
            continue
        x = cx0 + i * cw
        start = t0 + i * 0.035
        flips = 4
        for k in range(flips):
            g = rnd.choice(pool)
            b.append(f'<text class="fl" x="{f(x)}" y="{cy}" font-size="24" text-anchor="middle" fill="{t["mute"]}" '
                     f'style="animation-delay:{start + k * 0.07:.3f}s">{esc(g)}</text>')
        fill = t["accent"] if ch == "/" else t["ink"]
        b.append(f'<text class="fx" x="{f(x)}" y="{cy}" font-size="24" text-anchor="middle" font-weight="600" fill="{fill}" '
                 f'style="animation-delay:{start + flips * 0.07:.3f}s">{esc(ch)}</text>')

    # circuit -------------------------------------------------------------------
    b.append(f'<g class="fade" style="animation-delay:.5s">')
    b.append(f'<path d="{tp}" fill="none" stroke="{t["faint"]}" stroke-width="12" stroke-linejoin="round"/>')
    b.append(f'<path d="{tp}" fill="none" stroke="{t["hair"]}" stroke-width="2" stroke-linejoin="round"/>')
    sx, sy = sim["start"][0] + ox, sim["start"][1] + oy
    hx, hy = sim["heading"]
    ang = math.degrees(math.atan2(hy, hx))
    b.append(f'<g transform="translate({f(sx)} {f(sy)}) rotate({f(ang)})">')
    for r in range(4):
        for c in range(2):
            col = t["ink"] if (r + c) % 2 == 0 else t["faint"]
            b.append(f'<rect x="{-3 + c * 3}" y="{-8 + r * 4}" width="3" height="4" fill="{col}"/>')
    b.append("</g></g>")
    b.append(text(ox + 10, oy + 196, "CIRCUIT  /  5.2 KM", 12, t["mute"], spacing=3, extra=' class="fade" style="animation-delay:.6s"'))

    # time-warp: equal steps in time -> fraction of distance covered
    frames = 60
    key_t, key_s = [], []
    for j in range(frames + 1):
        target = lap * j / frames
        i = 0
        while i < n and sim_t[i + 1] < target:
            i += 1
        i = min(i, n - 1)
        u = (target - sim_t[i]) / max(sim_t[i + 1] - sim_t[i], 1e-9)
        key_t.append(j / frames)
        key_s.append(min((i + u) / n, 1.0))
    kt = ";".join(f"{x:.4f}" for x in key_t)
    ks = ";".join(f"{x:.4f}" for x in key_s)
    smil = f'begin="{LIGHTS_OUT}s" dur="{LAP_SECONDS}s" repeatCount="indefinite" calcMode="linear" keyTimes="{kt}"'

    trail = 70
    offs = ";".join(f"{trail - 1000 * s:.1f}" for s in key_s)
    b.append(f'<path d="{tp}" pathLength="1000" fill="none" stroke="{t["accent"]}" stroke-width="3.5" stroke-linecap="round" '
             f'stroke-dasharray="{trail} {1000 - trail}" stroke-dashoffset="{trail}" opacity="0">'
             f'<set attributeName="opacity" to="1" begin="{LIGHTS_OUT}s"/>'
             f'<animate attributeName="stroke-dashoffset" values="{offs}" {smil}/></path>')
    # car on the grid, then the moving car
    b.append(f'<circle cx="{f(sx)}" cy="{f(sy)}" r="6" fill="{t["accent"]}">'
             f'<set attributeName="opacity" to="0" begin="{LIGHTS_OUT}s"/></circle>')
    b.append(f'<g opacity="0"><set attributeName="opacity" to="1" begin="{LIGHTS_OUT}s"/>'
             f'<circle r="11" fill="{t["accent"]}" opacity=".18"/><circle r="6" fill="{t["accent"]}"/>'
             f'<animateMotion path="{tp}" keyPoints="{ks}" {smil}/></g>')

    # telemetry ---------------------------------------------------------------
    px0, px1, py0, py1 = 150, 1160, 452, 530
    vmin, vmax = 50 / 3.6, 345 / 3.6
    v = sim["v"]

    def X(i):
        return px0 + (px1 - px0) * i / n

    def Y(val):
        return py1 - (py1 - py0) * (val - vmin) / (vmax - vmin)

    b.append(f'<g class="fade" style="animation-delay:.3s">')
    b.append(f'<rect x="40" y="436" width="1120" height="1" fill="{t["hair"]}"/>')
    for km in range(6):
        x = px0 + (px1 - px0) * km / 5.2
        if x <= px1:
            b.append(f'<rect x="{f(x)}" y="436" width="1" height="6" fill="{t["hair"]}"/>')
            b.append(text(x + 5, 450, f"{km} KM", 10, t["mute"], spacing=1))
    for kmh in (100, 200, 300):
        y = Y(kmh / 3.6)
        b.append(f'<rect x="{px0}" y="{f(y)}" width="{px1 - px0}" height="1" fill="{t["faint"]}"/>')
        b.append(text(px0 - 8, y + 4, str(kmh), 10, t["mute"], "end"))
    b.append(text(40, 496, "SPEED", 12, t["dim"], weight=700, spacing=3))
    b.append(text(40, 549, "THR", 12, t["dim"], weight=700, spacing=3))
    b.append(text(40, 567, "BRK", 12, t["dim"], weight=700, spacing=3))
    b.append("</g>")

    step = 2
    line = "M" + " L".join(f"{f(X(i))} {f(Y(v[i]))}" for i in range(0, n, step)) + f" L{f(X(n))} {f(Y(v[0]))}"
    area = line + f" L{px1} {py1} L{px0} {py1}Z"
    b.append(f'<path d="{area}" fill="{t["ink"]}" opacity=".05" class="fade" style="animation-delay:1.6s"/>')
    b.append(f'<path class="tr" pathLength="1" d="{line}" stroke="{t["ink"]}" stroke-width="1.6" stroke-linejoin="round"/>')

    def runs(flags):
        out, i = [], 0
        while i < n:
            if flags[i]:
                j = i
                while j < n and flags[j]:
                    j += 1
                out.append((i, j))
                i = j
            else:
                i += 1
        return out

    for (a, z) in runs(sim["throttle"]):
        b.append(f'<rect class="up" x="{f(X(a))}" y="542" width="{f(X(z) - X(a))}" height="8" fill="{t["green"]}" '
                 f'style="animation-delay:{0.6 + 2.4 * a / n:.2f}s"/>')
    for (a, z) in runs(sim["brake"]):
        b.append(f'<rect class="up" x="{f(X(a))}" y="560" width="{f(max(X(z) - X(a), 2))}" height="8" fill="{t["accent"]}" '
                 f'style="animation-delay:{0.6 + 2.4 * a / n:.2f}s"/>')

    # live cursor + readout
    xs = ";".join(f"{f(X(s * n))} 0" for s in key_s)
    b.append(f'<g opacity="0"><set attributeName="opacity" to="1" begin="{LIGHTS_OUT}s"/>'
             f'<animateTransform attributeName="transform" type="translate" values="{xs}" {smil}/>')
    b.append(f'<rect x="-0.5" y="440" width="1" height="132" fill="{t["accent"]}"/>')
    for j in range(frames):
        i = min(int(key_s[j] * n), n - 1)
        kmh = v[i] * 3.6
        gear = max(1, min(8, int(kmh / 40) + 1))
        x_here = X(key_s[j] * n)
        right = x_here > 1020
        anchor, dx, rx = ("end", -10, -116) if right else ("start", 10, 2)
        a = key_t[j]
        z = key_t[j + 1]
        b.append(f'<g opacity="0"><animate attributeName="opacity" begin="{LIGHTS_OUT}s" dur="{LAP_SECONDS}s" '
                 f'repeatCount="indefinite" calcMode="discrete" values="0;1;0" keyTimes="0;{a:.4f};{z:.4f}"/>'
                 f'<rect x="{rx}" y="451" width="114" height="22" rx="2" fill="{t["bg"]}" stroke="{t["hair"]}"/>'
                 f'<text x="{dx}" y="466" font-size="13" font-weight="700" fill="{t["ink"]}" text-anchor="{anchor}">'
                 f'{int(round(kmh)):>3} KM/H  G{gear}</text></g>')
    b.append("</g>")

    b.append(text(40, 594, "TRACE COMPUTED FROM THE CIRCUIT ABOVE  /  ONE LAP REPLAYED EVERY 10 S", 11, t["mute"], spacing=2,
                  extra=' class="fade" style="animation-delay:1s"'))
    b.append(text(1160, 594, f"SIM LAP  {fmt_lap(lap)}", 11, t["dim"], "end", 700, 2,
                  extra=' class="fade" style="animation-delay:1s"'))

    return svg(W, H, "Soham, Sackedball",
               "Five start lights come on and go out, the name SOHAM is drawn in, and a car laps a small circuit "
               "while a speed, throttle and brake trace follows it. Student, data, Formula 1 telemetry.",
               "".join(css), b)


# ---------------------------------------------------------------------------
# Section 1 header: what I'm building
# ---------------------------------------------------------------------------

def bench(t):
    css, body = sector_header(t, 1, "ON THE BENCH", "CURRENTLY BUILDING", "purple")
    return svg(1200, 96, "Section 1: on the bench", "Section header for what Soham is currently building.", css, body)


# ---------------------------------------------------------------------------
# Section 2: setup sheet (the stack)
# ---------------------------------------------------------------------------

STACK = [
    ("DATA", ["Python", "pandas", "NumPy", "scikit-learn", "FastF1", "FastAPI", "Jupyter", "Matplotlib"]),
    ("WEB", ["TypeScript", "React", "Vite", "Tailwind", "Node.js", "PixiJS"]),
    ("ANDROID", ["Kotlin", "Jetpack Compose", "Android Studio"]),
]


def setup(t):
    css, body = sector_header(t, 2, "SETUP SHEET", "WHAT THE CAR RUNS ON", "green")
    own_css = """
.row{animation:row .8s cubic-bezier(.2,.7,.2,1) both}
@keyframes row{from{opacity:0;transform:translateY(10px)}}
.chk{animation:chk 9s linear infinite both}
@keyframes chk{0%%{fill-opacity:0}3%%{fill-opacity:1}90%%{fill-opacity:1}100%%{fill-opacity:0}}
.scan{animation:scan 9s linear infinite}
@keyframes scan{0%%{transform:translateY(0);opacity:0}4%%{opacity:1}85%%{opacity:1}100%%{transform:translateY(%(h)spx);opacity:0}}
"""
    size, cw = 21, 21 * 0.62
    x0, x1 = 230, 1160
    rows = []
    for label, items in STACK:
        lines, cur, w = [], [], 0
        for it in items:
            iw = len(it) * cw + 62
            if cur and w + iw - 40 > x1 - x0:
                lines.append(cur)
                cur, w = [], 0
            cur.append(it)
            w += iw
        lines.append(cur)
        rows.append((label, lines))

    y = 128
    k = 0
    total_items = sum(len(i) for _, i in STACK)
    row_y = []
    for ri, (label, lines) in enumerate(rows):
        row_y.append(y)
        body.append(f'<g class="row" style="animation-delay:{0.2 + ri * 0.15:.2f}s">')
        body.append(text(40, y + 7, label, 13, t["dim"], weight=700, spacing=3))
        body.append(text(160, y + 7, f"0{ri + 1}", 13, t["mute"], spacing=2))
        for li, line in enumerate(lines):
            x = x0
            ly = y + li * 40
            for it in line:
                body.append(f'<rect class="chk" x="{f(x)}" y="{ly - 3}" width="10" height="10" fill="{t["green"]}" '
                            f'stroke="{t["hair"]}" style="animation-delay:{k * 9 / total_items * 0.8:.2f}s"/>')
                body.append(text(x + 22, ly + 7, it, size, t["ink"]))
                x += len(it) * cw + 40 + 22
                k += 1
        y += len(lines) * 40 + 24
        body.append(f'<rect x="40" y="{y - 22}" width="1120" height="1" fill="{t["faint"]}"/>')
        body.append("</g>")
        y += 16
    h = y + 10
    span = row_y[-1] - row_y[0] + 40
    body.append(f'<rect class="scan" x="26" y="{row_y[0] - 18}" width="3" height="32" fill="{t["green"]}"/>')
    css += own_css % {"h": span}
    return svg(1200, h, "Setup sheet: Soham's stack",
               "Data: " + ", ".join(STACK[0][1]) + ". Web: " + ", ".join(STACK[1][1]) +
               ". Android: " + ", ".join(STACK[2][1]) + ".", css, body)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

def footer(t):
    css = """
.run{animation:run 8s cubic-bezier(.45,0,.25,1) infinite}
@keyframes run{0%{transform:translateX(0)}70%{transform:translateX(1080px)}100%{transform:translateX(1080px)}}
.tail{transform-box:fill-box;transform-origin:100% 50%;animation:tail 8s cubic-bezier(.45,0,.25,1) infinite}
@keyframes tail{0%{transform:scaleX(.2);opacity:0}10%{opacity:1}60%{transform:scaleX(1);opacity:1}72%{transform:scaleX(.05);opacity:0}100%{opacity:0}}
.flag rect{animation:flag 8s steps(1,end) infinite}
@keyframes flag{0%,69%{opacity:.35}70%,100%{opacity:1}}
"""
    b = [f'<rect x="40" y="40" width="1120" height="1" fill="{t["hair"]}"/>', '<g class="flag">']
    for r in range(4):
        for c in range(3):
            if (r + c) % 2 == 0:
                b.append(f'<rect x="{1124 + c * 6}" y="{28 + r * 6}" width="6" height="6" fill="{t["ink"]}"/>')
    b.append("</g>")
    b.append('<g class="run">')
    b.append(f'<rect class="tail" x="-16" y="39" width="56" height="3" fill="{t["accent"]}"/>')
    b.append(f'<circle cx="40" cy="40.5" r="5" fill="{t["accent"]}"/></g>')
    b.append(text(40, 78, "END OF SESSION", 12, t["dim"], weight=700, spacing=3))
    b.append(text(1160, 78, "SACKEDBALL  /  MUMBAI, IN", 12, t["mute"], "end", spacing=3))
    return svg(1200, 100, "End of session", "A car crosses the finish line.", css, b)


def main():
    os.makedirs(OUT, exist_ok=True)
    sim = simulate()
    for name, t in THEMES.items():
        for part, fn in (("hero", lambda t: hero(t, sim)), ("bench", bench), ("setup", setup), ("footer", footer)):
            path = os.path.join(OUT, f"{part}-{name}.svg")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(fn(t))
            print(f"wrote {os.path.relpath(path)}  {os.path.getsize(path) // 1024} KB")
    print("sim lap", fmt_lap(sim["lap"]))


if __name__ == "__main__":
    main()
