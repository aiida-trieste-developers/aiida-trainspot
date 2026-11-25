import math

CYCLE = 101.0
EASE = "0.42 0 0.22 1"
EPS = 0.004  # tiny hold offset: keeps values pinned instead of interpolating across the whole cycle


# ---------------------------------------------------------------- primitives
def hexagon_path(cx, cy, r, rotate=-90):
    pts = [
        (cx + r * math.cos(math.radians(60 * i + rotate)), cy + r * math.sin(math.radians(60 * i + rotate)))
        for i in range(6)
    ]
    return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def frac(t):
    t = min(max(t, 0.0), CYCLE)  # never wrap: a negative or overshooting time would land at the far end
    return f"{t/CYCLE:.5f}"


def anim(attr, kts, vals, indent=4):
    return (
        f'{" "*indent}<animate attributeName="{attr}" values="{";".join(str(v) for v in vals)}" '
        f'keyTimes="{";".join(kts)}" dur="{CYCLE}s" repeatCount="indefinite"/>'
    )


def opacity_tag(t_in0, t_in1, t_out0, t_out1, base=1.0, indent=6):
    kt = ["0", frac(t_in0), frac(t_in1), frac(t_out0), frac(t_out1), "1"]
    return anim("opacity", kt, [0, 0, base, base, 0, 0], indent)


def motion_tag(path_d, t0, t1):
    return (
        f'    <animateMotion path="{path_d}" keyPoints="0;0;1;1" keyTimes="0;{frac(t0)};{frac(t1)};1" '
        f'calcMode="spline" keySplines="0 0 1 1;{EASE};0 0 1 1" dur="{CYCLE}s" repeatCount="indefinite"/>'
    )


def pulse_tag(t0, t1):
    kt = ["0", frac(t0), frac((t0 + t1) / 2), frac(t1), "1"]
    return anim("stroke-opacity", kt, [0, 0, 1, 0, 0])


def breathe_tag(t0, t1, n=3, lo=0.3, hi=1.0):
    """Slow 'working' oscillation. Pinned to 0 outside [t0,t1] -- otherwise it bleeds across the whole cycle."""
    kts = ["0", frac(t0 - EPS), frac(t0)]
    vals = [0, 0, lo]
    for i in range(n * 2):
        kts.append(frac(t0 + (t1 - t0) * (i + 1) / (n * 2)))
        vals.append(hi if i % 2 == 0 else lo)
    kts += [frac(t1), frac(t1 + EPS), "1"]
    vals += [lo, 0, 0]
    return anim("stroke-opacity", kts, vals)


def ripple(cx, cy, t0, r0=46, r1=76, color="var(--diag-accent-green)"):
    """Expanding arrival ring. Held invisible outside its own window."""
    kt = ["0", frac(t0 - EPS), frac(t0), frac(t0 + 0.65), frac(t0 + 0.65 + EPS), "1"]
    return (
        f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r0}" fill="none" stroke="{color}" stroke-width="2" opacity="0">\n'
        + anim("r", kt, [r0, r0, r0, r1, r1, r1])
        + "\n"
        + anim("opacity", kt, [0, 0, 0.5, 0, 0, 0])
        + "\n  </circle>"
    )


def float_text(x, y, txt, t0, color="var(--diag-accent-green)", size=14):
    kt = ["0", frac(t0), frac(t0 + 0.3), frac(t0 + 1.2), frac(t0 + 1.5), "1"]
    return (
        f'  <text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="{size}" font-family="\'JetBrains Mono\',monospace" '
        f'font-weight="700" fill="{color}" opacity="0">{txt}\n'
        + anim("y", kt, [y, y, y - 10, y - 30, y - 36, y - 36])
        + "\n"
        + anim("opacity", kt, [0, 0, 1, 1, 0, 0])
        + "\n  </text>"
    )


def windowed(attr, rest, kfs, windows, laps=3, phase=0.0, indent=4):
    """Animate `attr` through `kfs` (fraction-of-lap, value) inside each window, resting elsewhere."""
    kts, vals = ["0"], [rest]

    def push(t, v):
        f = frac(t)
        if float(f) < float(kts[-1]):  # rounding at a lap boundary must never step backwards
            f = kts[-1]
        kts.append(f)
        vals.append(v)

    for w0, w1 in windows:
        seg = (w1 - w0) / laps
        s0 = w0 + phase * seg
        push(s0 - EPS, rest)
        for l in range(laps):
            for p, v in kfs:
                push(s0 + seg * l + p * seg, v)
        push(s0 + seg * laps + EPS, rest)
    kts.append("1")
    vals.append(rest)
    return anim(attr, kts, vals, indent)


def spotlight(body, windows, dim=0.38, pad=0.7, ramp=0.45, fade_out=None):
    """Hold a stage dimmed except while it is actually working."""
    kts, vals = ["0"], [0.0]

    def push(t, v):
        f = frac(t)
        if float(f) < float(kts[-1]):
            f = kts[-1]
        kts.append(f)
        vals.append(v)

    rest = 0.0  # a stage is not on screen at all until the first time it is needed
    for w0, w1 in sorted(windows):
        a, b = w0 - pad, w1 + pad
        push(a - ramp, rest)
        push(a, 1.0)
        push(b, 1.0)
        push(b + ramp, dim)
        rest = dim  # from then on it stays, half lit, waiting its turn
    if fade_out:
        push(fade_out[0], rest)
        push(fade_out[1], 0.0)
        rest = 0.0
    kts.append("1")
    vals.append(rest)
    return f'  <g opacity="0">\n{body}\n' + anim("opacity", kts, vals) + "\n  </g>"


def anim_transform(ttype, kts, vals, additive=None, ease_at=1):
    add = f' additive="{additive}"' if additive else ""
    ks = ";".join(EASE if i == ease_at else "0 0 1 1" for i in range(len(kts) - 1))
    return (
        f'    <animateTransform attributeName="transform" type="{ttype}" values="{";".join(vals)}" '
        f'keyTimes="{";".join(kts)}" calcMode="spline" keySplines="{ks}" dur="{CYCLE}s" '
        f'repeatCount="indefinite"{add}/>'
    )


def celebrate(cx, cy, t0, scale=1.0, n=30):
    """A firework: launched from below, opening upward, drooping at the top. No concentric rings."""
    o = []
    for i in range(n):
        f = (i + 0.5) / n
        a = math.radians(-158 + 136 * f + 8 * math.sin(i * 2.9))
        d = (110 + 215 * ((math.sin((i + 1) * 12.9898 + cx * 0.013) * 43758.5453) % 1.0)) * scale
        ex = cx + d * math.cos(a)
        ey = cy + d * math.sin(a) * 1.15
        c1 = (cx + d * 0.16 * math.cos(a), cy + d * 1.05 * math.sin(a))
        c2 = (ex, ey - 34 * scale)
        dt = t0 + 0.05 * (i % 5)
        dur = 1.5 + 0.35 * ((i % 3) / 2)
        col = ["var(--diag-primary)", "var(--diag-accent-green)", "var(--diag-accent-orange)"][i % 3]
        body = (
            f'      <path d="{hexagon_path(0,0,6.4*scale)}" fill="{col}"/>'
            if i % 2
            else f'      <circle r="{4.4*scale:.1f}" fill="{col}"/>'
        )
        o.append(
            moving(
                body,
                dt,
                dt + 0.1,
                dt + dur * 0.55,
                dt + dur * 0.95,
                curve_path((cx, cy), (ex, ey), c1, c2),
                dt,
                dt + dur,
            )
        )
    return "\n".join(o)


def fade_group(body, t_in0, t_in1, t_out0, t_out1):
    return f'  <g opacity="0">\n{body}\n{opacity_tag(t_in0,t_in1,t_out0,t_out1,indent=4)}\n  </g>'


def moving(body, t_in0, t_in1, t_out0, t_out1, path_d=None, tm0=None, tm1=None, base=1.0, at=None):
    head = (
        ["  <g>", motion_tag(path_d, tm0, tm1)] if path_d else [f'  <g transform="translate({at[0]:.1f},{at[1]:.1f})">']
    )
    return "\n".join(head + ["    <g>", body, opacity_tag(t_in0, t_in1, t_out0, t_out1, base), "    </g>", "  </g>"])


def line_path(p0, p1):
    return f"M {p0[0]:.1f},{p0[1]:.1f} L {p1[0]:.1f},{p1[1]:.1f}"


def curve_path(p0, p1, c1, c2):
    return f"M {p0[0]:.1f},{p0[1]:.1f} C {c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p1[0]:.1f},{p1[1]:.1f}"


def arc_path(p0, p1, mid_y):
    (x0, y0), (x1, y1) = p0, p1
    return f"M {x0:.1f},{y0:.1f} C {x0-150:.1f},{mid_y:.1f} {x1+200:.1f},{mid_y:.1f} {x1:.1f},{y1:.1f}"


# ---------------------------------------------------------------- glyphs
def g_structure(r=11, style="plain"):
    if style == "plain":
        return f'      <path d="{hexagon_path(0,0,r)}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.6"/>'
    if style == "labelled":
        bx, by = r * 0.68, -r * 0.68
        return (
            "      "
            + f'<path d="{hexagon_path(0,0,r)}" fill="var(--diag-primary)" fill-opacity="0.2" stroke="var(--diag-primary)" stroke-width="1.6"/>'
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{r*0.42:.1f}" fill="var(--diag-accent-green)"/>'
            f'<path d="M {bx-r*0.2:.1f},{by:.1f} l {r*0.14:.1f},{r*0.14:.1f} l {r*0.26:.1f},-{r*0.28:.1f}" fill="none" stroke="#fff" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if style == "potential":
        # a potential is a trained network, not a structure: a tiny 2-2 net instead of a hexagon
        nd = [(-r * 0.44, -r * 0.36), (-r * 0.44, r * 0.36), (r * 0.44, -r * 0.36), (r * 0.44, r * 0.36)]
        edges = "".join(
            f'<line x1="{nd[i][0]:.1f}" y1="{nd[i][1]:.1f}" x2="{nd[j][0]:.1f}" y2="{nd[j][1]:.1f}" '
            f'stroke="#fff" stroke-width="{r*0.08:.2f}" stroke-opacity="0.8"/>'
            for i in (0, 1)
            for j in (2, 3)
        )
        dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r*0.16:.2f}" fill="#fff"/>' for x, y in nd)
        return "      " + f'<circle r="{r}" fill="var(--diag-primary-dark)" filter="url(#ss)"/>' + edges + dots


def counted(body, count, color, dy=24, size=11.5, sub=None):
    o = [
        body,
        f'      <text x="0" y="{dy}" text-anchor="middle" font-size="{size}" font-family="\'JetBrains Mono\',monospace" '
        f'font-weight="700" fill="{color}">{count}</text>',
    ]
    if sub:
        o.append(
            f'      <text x="0" y="{dy+11}" text-anchor="middle" font-size="8" font-family="\'JetBrains Mono\',monospace" '
            f'fill="var(--diag-text-muted)">{sub}</text>'
        )
    return "\n".join(o)


def _stack(r, fill, op_scale, stroke):
    return "".join(
        f'<path d="{hexagon_path(dx,dy,r)}" fill="{fill}" fill-opacity="{op*op_scale:.2f}" stroke="{stroke}" stroke-width="1.1"/>'
        for dx, dy, op in [(-9, 4, 0.45), (0, -3, 0.72), (9, 4, 1.0)]
    )


def _tick(cx=17, cy=-10, rr=6.0):
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="var(--diag-accent-green)"/>'
        f'<path d="M {cx-rr*0.45:.1f},{cy:.1f} l {rr*0.3:.1f},{rr*0.32:.1f} l {rr*0.6:.1f},-{rr*0.66:.1f}" fill="none" '
        f'stroke="#fff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def g_dataset(count, r=10, sub="labelled"):
    return counted(
        "      " + _stack(r, "var(--diag-primary)", 1.0, "var(--diag-primary-dark)") + _tick(),
        count,
        "var(--diag-primary)",
        dy=25,
        size=13,
        sub=sub,
    )


def g_rawset(count):
    stack = "".join(
        f'<path d="{hexagon_path(dx,dy,10)}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.5" stroke-opacity="{op}"/>'
        for dx, dy, op in [(-9, 4, 0.5), (0, -3, 0.75), (9, 4, 1.0)]
    )
    return counted("      " + stack, count, "var(--diag-primary)", dy=25, size=13, sub="augmented")


def g_explored(count):
    return counted(
        "      " + _stack(10, "var(--diag-accent-green)", 0.9, "var(--diag-accent-green)"),
        count,
        "var(--diag-accent-green)",
        dy=25,
        size=13,
        sub="explored",
    )


def g_seeds(count):
    stack = "".join(
        f'<path d="{hexagon_path(dx,dy,8)}" fill="var(--diag-primary)" fill-opacity="{op*0.85:.2f}" stroke="var(--diag-primary-dark)" stroke-width="1"/>'
        for dx, dy, op in [(-7, 3, 0.45), (0, -2, 0.72), (7, 3, 1.0)]
    )
    return counted(
        "      " + stack + _tick(13, -8, 4.8), count, "var(--diag-primary)", dy=21, size=11, sub="input structures"
    )


def g_trajectory(count):
    dots = "".join(
        f'<circle cx="{dx}" cy="{dy}" r="4" fill="var(--diag-accent-green)" fill-opacity="{op}"/>'
        for dx, dy, op in [(-13, 3, 0.35), (0, -3, 0.68), (13, 4, 1.0)]
    )
    tail = (
        '<path d="M -13,3 Q -4,-9 0,-3 T 13,4" fill="none" stroke="var(--diag-accent-green)" '
        'stroke-width="1.1" stroke-opacity="0.4" stroke-dasharray="1 3"/>'
    )
    return counted("      " + tail + dots, count, "var(--diag-accent-green)", dy=-22, size=10.5, sub="frames")


def g_selected(count, sub="selected"):
    return counted(
        "      " + _stack(10, "var(--diag-accent-orange)", 1.0, "var(--diag-accent-orange)"),
        count,
        "var(--diag-accent-orange)",
        dy=25,
        size=13,
        sub=sub,
    )


def g_feed():
    return "      " + "".join(
        f'<path d="{hexagon_path(dx,dy,8)}" fill="var(--diag-primary)" fill-opacity="0.35" stroke="var(--diag-primary)" stroke-width="0.9"/>'
        for dx, dy in [(-7, 3), (0, -2), (7, 3)]
    )


def g_selected_ghost():
    return "      " + "".join(
        f'<path d="{hexagon_path(dx,0,9)}" fill="none" stroke="var(--diag-accent-orange)" stroke-width="1.6"/>'
        for dx in (-8, 8)
    )


def g_batch_labelled(count):
    return counted(
        "      " + _stack(9, "var(--diag-primary)", 0.9, "var(--diag-primary-dark)") + _tick(15, -9, 5.2),
        f"+{count}",
        "var(--diag-accent-green)",
        dy=23,
        size=12,
        sub="just labelled",
    )


# ---------------------------------------------------------------- MD atoms
def wander_path(cx, cy, seed):
    r = lambda i: math.sin(seed * 2.3 + i) * 0.5 + math.cos(seed * 1.7 + i * 1.3) * 0.5
    a, b = 13 + 3 * r(0), 9 + 3 * r(1)
    return (
        f"M {cx:.1f},{cy:.1f} C {cx+a*0.5:.1f},{cy-b*1.5:.1f} {cx+a*1.4:.1f},{cy-b*0.7:.1f} {cx+a:.1f},{cy+b*0.4:.1f} "
        f"C {cx+a*0.7:.1f},{cy+b*1.6:.1f} {cx-a*0.3:.1f},{cy+b*1.2:.1f} {cx-a*0.8:.1f},{cy+b*0.5:.1f} "
        f"C {cx-a*1.5:.1f},{cy-b*0.2:.1f} {cx-a*0.9:.1f},{cy-b*1.1:.1f} {cx:.1f},{cy:.1f} Z"
    )


def ellipse_path(cx, cy, rx, ry):
    return f"M {cx-rx:.1f},{cy:.1f} A {rx},{ry} 0 1 0 {cx+rx:.1f},{cy:.1f} A {rx},{ry} 0 1 0 {cx-rx:.1f},{cy:.1f} Z"


def md_motion(path_d, windows, laps=2, shift=0.0):
    kts, kps = ["0"], ["0"]
    for w0, w1 in windows:
        w0 += shift
        w1 += shift
        seg = (w1 - w0) / laps
        kts.append(frac(w0))
        kps.append("0")
        for l in range(laps):
            kts.append(frac(w0 + seg * (l + 1)))
            kps.append("1")
            if l < laps - 1:
                kts.append(frac(w0 + seg * (l + 1) + 0.002))
                kps.append("0")
        kts.append(frac(w1 + 0.004))
        kps.append("0")
    kts.append("1")
    kps.append("0")
    return (
        f'    <animateMotion path="{path_d}" keyPoints="{";".join(kps)}" keyTimes="{";".join(kts)}" '
        f'calcMode="linear" dur="{CYCLE}s" repeatCount="indefinite"/>'
    )


# ---------------------------------------------------------------- layout
ROW = 260
X = dict(augment=130, label=470, train=810, explore=1150, evaluate=1490)
R = 46
IN_GAP, OUT_GAP = 36, 24  # an arriving set is as wide as the gap, so it needs the extra room
out_p = lambda n: (X[n] + R + OUT_GAP, ROW)
in_p = lambda n: (X[n] - R - IN_GAP, ROW)
bot_p = lambda n: (X[n], ROW + R + 80)  # clear of the title and caption under each badge

FAN, TRAJ_LANE = 58, 56
LANE_GROUP = ROW - 132
WAIT = (X["evaluate"] - 176, LANE_GROUP)
THR_Y = ROW + 152
SCAT_HW = 96
AGG = (X["evaluate"] - 232, THR_Y + 66)  # below the plot: its route out must not cross the axis caption
MERGE = (X["label"] + 130, ROW + R + 80)  # the dataset shelf: always on screen, between Label and Train
RES_POT = (1362, 126)  # the two results sit side by side, not at opposite ends
RES_DS = (1546, 130)
ARC_MIDY = 508
POOL = ((X["explore"] + X["evaluate"]) / 2, ROW)
CX = 823
DS_CX = 973
N_FRAMES, N_TRAJ = 8, 3

out, md_win, dft_win, train_win, aug_win = [], [], [], [], []
merges, podium, eval_win, label_win, iter_marks, fade_all, finale = [], [], [], [], [], [], []
DS_BORN = 10.6

# ---------------------------------------------------------------- setup
out.append(moving(g_structure(12), 0.0, 0.3, 1.0, 1.3, line_path((-30, ROW), in_p("augment")), 0.3, 1.0))
aug_win.append((1.0, 3.4))
out.append(
    f'  <circle cx="{X["augment"]}" cy="{ROW}" r="{R+7}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2.5">\n{pulse_tag(3.4,4.0)}\n  </circle>'
)
out.append(ripple(X["augment"], ROW, 3.45))
out.append(moving(g_rawset(24), 3.9, 4.2, 6.05, 6.3, line_path(out_p("augment"), in_p("label")), 4.1, 6.0))
dft_win.append((6.2, 8.6))
train_win.append((11.6, 14.2))
label_win.append((5.9, 10.8))
out.append(
    f'  <circle cx="{X["label"]}" cy="{ROW}" r="{R+7}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2.5">\n{pulse_tag(8.6,9.2)}\n  </circle>'
)
out.append(ripple(X["label"], ROW, 8.65))
out.append(moving(g_dataset(24), 9.25, 9.45, 10.65, 10.8, line_path(bot_p("label"), MERGE), 9.4, 10.6))
out.append(ripple(MERGE[0], MERGE[1], 10.6, r0=16, r1=44, color="var(--diag-primary)"))
out.append(moving(g_dataset(24), 11.0, 11.2, 13.05, 13.3, line_path(MERGE, in_p("train")), 11.15, 13.0, base=0.85))
train_win[0] = (13.0, 15.6)
SETUP_END = 16.3
out.append(
    f'  <circle cx="{X["train"]}" cy="{ROW}" r="{R+7}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2.5">\n{pulse_tag(15.6,SETUP_END)}\n  </circle>'
)
out.append(ripple(X["train"], ROW, 15.65))


# ---------------------------------------------------------------- one iteration
def scatter_points(n, n_up, seed):
    # which frames land above the line must not be decided by the same index that sets their x,
    # or the selected ones are always the leftmost and always rain in first
    order = sorted(range(n), key=lambda i: (math.sin((i + 1) * 7.77 + seed * 3.31) * 10937.13) % 1.0)
    chosen = set(order[:n_up])
    pts = []
    for i in range(n):
        j = (math.sin((i + 1) * 12.9898 + seed * 78.233) * 43758.5453) % 1.0
        k = (math.sin((i + 1) * 4.1414 + seed * 21.7) * 24634.6345) % 1.0
        x = -SCAT_HW + 14 + (i / (n - 1) if n > 1 else 0.5) * (2 * SCAT_HW - 28) + (j - 0.5) * 13
        above = i in chosen
        pts.append((x, (-52 + j * 40) if above else (12 + k * 44), above))
    pts.sort(key=lambda p: p[0])
    return pts


def gen_loop(t0, n_up, ds_before, ds_after, final, sp=1.0):
    """Sp < 1 compresses a repeat iteration: the first pass is shown in full, later ones move quicker."""
    ev = []
    T = lambda r: t0 + r * sp
    HOLD_END = T(2.0)
    DEP0, DEP1 = T(2.0), T(3.4)
    GDEP0, GDEP1 = T(2.2), T(4.3)
    MD0, MD1 = T(3.4), T(6.6)
    FIRE0, FIRE1 = T(6.6), T(7.2)
    TRJ0, TRJ1 = T(7.2), T(9.1)
    TRJ_LAST = TRJ1 + 0.4 * sp
    POOL0 = TRJ_LAST + 0.3
    ENTER0 = POOL0 + 1.2
    ENTER1 = ENTER0 + 1.7 * sp
    EVF0, EVF1 = ENTER1 + 0.25, ENTER1 + 0.9
    RAIN0, RAIN1 = ENTER1 + 0.5, ENTER1 + 3.0 * sp
    PICK0 = RAIN1 + 2.8 * sp
    PICK1 = PICK0 + 1.6 * sp
    CONV_T = PICK1 + 0.8
    MOVE0_T = CONV_T + 1.5
    SH0_T = MOVE0_T + 0.4
    md_win.append((MD0, MD1))

    park_x = out_p("train")[0]
    ev.append(moving(g_structure(11, "potential"), t0 - 0.1, t0 + 0.4, DEP0, DEP0 + 0.05, at=(park_x, ROW)))
    for dy in (-15, 15):
        ev.append(moving(g_structure(11, "potential"), t0 - 0.1, t0 + 0.4, GDEP0, GDEP0 + 0.05, at=(park_x, ROW + dy)))
    ex_pot = (in_p("explore")[0] - 4, ROW - 24)
    ex_seeds = (in_p("explore")[0] - 4, ROW + 26)
    ev.append(
        moving(
            g_structure(11, "potential"),
            DEP0 - 0.05,
            DEP0,
            DEP1 + 0.15,
            DEP1 + 0.4,
            line_path((park_x, ROW), ex_pot),
            DEP0,
            DEP1,
        )
    )
    ev.append(
        moving(
            g_seeds(N_TRAJ),
            DEP0 - 0.35,
            DEP0 - 0.1,
            DEP1 + 0.25,
            DEP1 + 0.5,
            curve_path(MERGE, ex_seeds, (MERGE[0] + 230, MERGE[1] + 40), (ex_seeds[0] - 84, ROW + 62)),
            DEP0 - 0.25,
            DEP1 + 0.1,
        )
    )
    ev.append(ripple(X["explore"], ROW, DEP1, r0=R - 8, r1=R + 14, color="var(--diag-primary)"))
    group_out = PICK0 + 0.4 if not final else SH0_T
    for dy, dx in ((-15, -18), (15, 0)):
        ev.append(
            moving(
                g_structure(11, "potential"),
                GDEP0 - 0.05,
                GDEP0,
                group_out,
                group_out + 0.3,
                line_path((park_x, ROW + dy), (WAIT[0] + dx, WAIT[1])),
                GDEP0,
                GDEP1,
            )
        )
    # the potential that drove MD joins the other two, so the whole committee is present at scoring
    ev.append(
        moving(
            g_structure(11, "potential"),
            FIRE1 - 0.05,
            FIRE1,
            group_out,
            group_out + 0.3,
            curve_path(
                out_p("explore"),
                (WAIT[0] + 18, WAIT[1]),
                (out_p("explore")[0] + 70, ROW - 40),
                (WAIT[0] - 30, WAIT[1] - 20),
            ),
            FIRE1,
            TRJ_LAST - 0.15,
        )
    )
    ev.append(
        fade_group(
            f'    <text x="{WAIT[0]}" y="{WAIT[1]-36}" text-anchor="middle" font-size="8.5" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">committee of</text>\n'
            f'    <text x="{WAIT[0]}" y="{WAIT[1]-26}" text-anchor="middle" font-size="8.5" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">potentials</text>',
            GDEP1,
            GDEP1 + 0.4,
            group_out - 0.2,
            group_out + 0.1,
        )
    )
    ev.append(
        f'  <circle cx="{X["explore"]}" cy="{ROW}" r="{R+5}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2">\n{breathe_tag(MD0, MD1)}\n  </circle>'
    )
    ev.append(
        f'  <circle cx="{X["explore"]}" cy="{ROW}" r="{R+7}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2.5">\n{pulse_tag(FIRE0, FIRE1)}\n  </circle>'
    )

    for i, y in enumerate((ROW - TRAJ_LANE, ROW, ROW + TRAJ_LANE)):
        a, b = TRJ0 + i * 0.2 * sp, TRJ1 + i * 0.2 * sp
        ev.append(
            moving(
                g_trajectory(N_FRAMES),
                a - 0.1,
                a + 0.15,
                b + 0.05,
                b + 0.3,
                line_path((out_p("explore")[0], y), (POOL[0], POOL[1] + (y - ROW) * 0.2)),
                a,
                b,
            )
        )
    ev.append(
        fade_group(
            f'    <text x="{POOL[0]:.0f}" y="{ROW-TRAJ_LANE-34}" text-anchor="middle" font-size="9" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-accent-green)">{N_TRAJ} trajectories</text>',
            TRJ0,
            TRJ0 + 0.4,
            TRJ_LAST,
            TRJ_LAST + 0.3,
        )
    )
    # the three trajectories pool into a single explored set carrying the total frame count
    ev.append(ripple(POOL[0], POOL[1], POOL0, r0=12, r1=44, color="var(--diag-accent-green)"))
    ev.append(moving(g_explored(N_TRAJ * N_FRAMES), POOL0, POOL0 + 0.4, ENTER0, ENTER0 + 0.1, at=POOL))
    ev.append(
        moving(
            g_explored(N_TRAJ * N_FRAMES),
            ENTER0 - 0.1,
            ENTER0,
            ENTER1 + 0.2,
            ENTER1 + 0.45,
            line_path(POOL, (in_p("evaluate")[0] - 6, ROW - 30)),
            ENTER0,
            ENTER1,
        )
    )
    # the labelled dataset comes up along the bottom and enters alongside it
    ev.append(
        moving(
            g_dataset(ds_before),
            TRJ0 - 0.3,
            TRJ0 - 0.05,
            ENTER1 + 0.2,
            ENTER1 + 0.45,
            curve_path(
                MERGE, (in_p("evaluate")[0] - 6, ROW + 4), (MERGE[0] + 380, 470), (in_p("evaluate")[0] - 230, 380)
            ),
            TRJ0 - 0.2,
            ENTER1,
        )
    )
    ev.append(
        f'  <circle cx="{X["evaluate"]}" cy="{ROW}" r="{R+9}" fill="none" stroke="var(--diag-accent-green)" stroke-width="3">\n{pulse_tag(EVF0, EVF1)}\n  </circle>'
    )
    eval_win.append((EVF0 - 0.3, PICK1 + 0.6))
    iter_marks.append(RAIN1 + 0.4)

    total = N_TRAJ * N_FRAMES
    axis = (
        f'    <line x1="{X["evaluate"]-SCAT_HW-8}" y1="{THR_Y-60}" x2="{X["evaluate"]-SCAT_HW-8}" y2="{THR_Y+62}" '
        f'stroke="var(--diag-text-muted)" stroke-width="1" stroke-opacity="0.45"/>\n'
        f'    <text x="{X["evaluate"]-SCAT_HW-14}" y="{THR_Y-56}" text-anchor="end" font-size="8" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">committee</text>\n'
        f'    <text x="{X["evaluate"]-SCAT_HW-14}" y="{THR_Y-46}" text-anchor="end" font-size="8" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">deviation</text>\n'
        f'    <line x1="{X["evaluate"]-SCAT_HW}" y1="{THR_Y}" x2="{X["evaluate"]+SCAT_HW}" y2="{THR_Y}" '
        f'stroke="var(--diag-accent-orange)" stroke-width="1.4" stroke-dasharray="5 4" stroke-opacity="0.85"/>\n'
        f'    <text x="{X["evaluate"]+SCAT_HW+6}" y="{THR_Y+3.5}" font-size="8.5" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-accent-orange)">threshold</text>'
    )
    axis_out = PICK1 + 0.6
    ev.append(fade_group(axis, RAIN0 - 0.4, RAIN0 - 0.1, axis_out, axis_out + 0.4))
    ev.append(
        fade_group(
            f'    <text x="{X["evaluate"]}" y="{THR_Y+102}" text-anchor="middle" font-size="9" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">{total} frames scored</text>',
            RAIN0,
            RAIN0 + 0.4,
            axis_out,
            axis_out + 0.4,
        )
    )

    for i, (dx, dy, above) in enumerate(scatter_points(total, n_up, seed=n_up + 1)):
        a = RAIN0 + i * (RAIN1 - RAIN0 - 0.5 * sp) / max(total - 1, 1)
        px, py = X["evaluate"] + dx, THR_Y + dy
        dot = (
            '      <circle r="4.2" fill="none" stroke="var(--diag-accent-orange)" stroke-width="1.7"/>'
            '<circle r="8" fill="none" stroke="var(--diag-accent-orange)" stroke-width="1" stroke-opacity="0.55"/>'
            if above
            else '      <circle r="3.4" fill="var(--diag-text-muted)" fill-opacity="0.75"/>'
        )
        ev.append(
            moving(
                dot, a - 0.15, a + 0.1, PICK0 + 0.15, PICK0 + 0.4, line_path(bot_p("evaluate"), (px, py)), a, a + 0.75
            )
        )
        if above:
            ev.append(
                moving(
                    dot,
                    PICK0 + 0.1,
                    PICK0 + 0.25,
                    PICK0 + 0.85,
                    PICK0 + 1.0,
                    line_path((px, py), AGG),
                    PICK0 + 0.15,
                    PICK0 + 0.9,
                )
            )
        else:
            ev.append(
                moving(
                    dot,
                    PICK0 + 0.1,
                    PICK0 + 0.25,
                    PICK0 + 0.5,
                    PICK1,
                    line_path((px, py), (px + dx * 0.12, py + 26)),
                    PICK0 + 0.2,
                    PICK1,
                )
            )

    verdict = f"{n_up} frames above threshold" if n_up else "no frame above threshold"
    vcol = "var(--diag-accent-orange)" if n_up else "var(--diag-accent-green)"
    ev.append(
        fade_group(
            f'    <text x="{X["evaluate"]}" y="{THR_Y+121}" text-anchor="middle" font-size="10.5" font-weight="700" '
            f'font-family="\'JetBrains Mono\',monospace" fill="{vcol}">{verdict}</text>',
            RAIN1 + 0.2,
            RAIN1 + 0.6,
            axis_out,
            axis_out + 0.4,
        )
    )

    if not final:
        ARC0 = PICK0 + 1.35
        ARC1 = ARC0 + 3.2 * sp
        ev.append(moving(g_selected(n_up), PICK0 + 0.85, PICK0 + 1.05, ARC0 + 0.05, ARC0 + 0.15, at=AGG))
        arc_d = arc_path(AGG, bot_p("label"), ARC_MIDY)
        ev.append(moving(g_selected(n_up), ARC0 - 0.1, ARC0 + 0.05, ARC1 + 0.1, ARC1 + 0.3, arc_d, ARC0, ARC1))

        DFT0, DFT1 = ARC1, ARC1 + 2.4 * sp  # DFT actually takes time, and shows it
        dft_win.append((DFT0, DFT1))
        ev.append(
            f'  <circle cx="{X["label"]}" cy="{ROW}" r="{R+7}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2.5">\n{pulse_tag(DFT1, DFT1+0.5)}\n  </circle>'
        )
        ev.append(ripple(X["label"], ROW, DFT1))

        # ---- the new batch is absorbed into the standing dataset, whose count ticks up on impact ----
        SUM0 = DFT1 + 0.45
        IMP = SUM0 + 1.4
        merges.append((IMP, ds_after))
        label_win.append((DFT0 - 0.2, IMP + 0.5))
        ev.append(
            moving(
                g_batch_labelled(n_up),
                SUM0 + 0.3,
                SUM0 + 0.5,
                IMP - 0.05,
                IMP + 0.05,
                line_path(bot_p("label"), MERGE),
                SUM0 + 0.4,
                IMP,
            )
        )
        ev.append(ripple(MERGE[0], MERGE[1], IMP, r0=16, r1=42, color="var(--diag-primary)"))
        ev.append(float_text(MERGE[0] + 62, MERGE[1] - 16, f"+{ds_after-ds_before}", IMP))

        D0, D1 = IMP + 0.8, IMP + 0.8 + 2.0 * sp
        ev.append(
            moving(
                g_dataset(ds_after),
                D0 - 0.2,
                D0,
                D1 + 0.15,
                D1 + 0.4,
                line_path(MERGE, in_p("train")),
                D0,
                D1,
                base=0.85,
            )
        )
        TR0, TR1 = D1, D1 + 2.6 * sp
        train_win.append((TR0, TR1))
        NX0, NX1 = TR1, TR1 + 0.6
        ev.append(
            f'  <circle cx="{X["train"]}" cy="{ROW}" r="{R+7}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2.5">\n{pulse_tag(NX0, NX1)}\n  </circle>'
        )
        ev.append(ripple(X["train"], ROW, NX0))
        return ev, NX1

    # ---- converged: the pipeline steps out and the result takes the centre ----
    CONV, MOVE0 = CONV_T, MOVE0_T
    MOVE1 = MOVE0 + 2.0
    fade_all.append(MOVE0)
    # the verdict is said once, where it is decided; the closing frame needs no caption
    ev.append(
        fade_group(
            f'    <text x="{X["evaluate"]}" y="{THR_Y+140}" text-anchor="middle" font-size="11" font-weight="700" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-accent-green)">the loop stops here</text>',
            CONV,
            CONV + 0.5,
            MOVE0 + 0.4,
            MOVE0 + 1.0,
        )
    )

    SH0, SH1 = SH0_T, SH0_T + 1.9
    ev.append(celebrate(CX - 338, 470, SH1 - 0.45, scale=0.66, n=40))
    ev.append(celebrate(CX, 452, SH1 - 0.20, scale=1.0, n=70))
    ev.append(celebrate(CX + 330, 476, SH1 + 0.20, scale=0.70, n=40))
    END_ALL = SH1 + 5.2  # plots, results and captions all leave together
    podium.append(SH0)
    DS_C, POT_C = (700, 330), (958, 330)
    for src_dx, dst in (
        (-18, (POT_C[0] - 20, POT_C[1])),
        (0, (POT_C[0] + 20, POT_C[1])),
        (18, (POT_C[0], POT_C[1] + 22)),
    ):
        ev.append(
            moving(
                g_structure(11, "potential"),
                SH0 - 0.2,
                SH0,
                END_ALL,
                END_ALL + 0.9,
                line_path((WAIT[0] + src_dx, WAIT[1]), dst),
                SH0,
                SH1,
            )
        )
    ev.append(
        moving(g_dataset(ds_after, sub=None), SH0 - 0.2, SH0, END_ALL, END_ALL + 0.9, line_path(MERGE, DS_C), SH0, SH1)
    )

    GL0, GL1 = SH1, END_ALL
    for cx, cy, rr in ((POT_C[0], POT_C[1] + 9, 43), (DS_C[0], DS_C[1] + 7, 38)):
        ev.append(
            f'  <circle cx="{cx}" cy="{cy}" r="{rr}" fill="none" stroke="var(--diag-accent-orange)" stroke-width="2">\n{breathe_tag(GL0,GL1,n=3,lo=0.18,hi=0.9)}\n  </circle>'
        )
    for cx, txt in ((POT_C[0], "FINAL POTENTIALS"), (DS_C[0], "FINAL DATASET")):
        ev.append(
            fade_group(
                f'    <text x="{cx}" y="{POT_C[1]-52}" text-anchor="middle" font-size="11" letter-spacing="0.07em" '
                f'font-family="Inter,sans-serif" font-weight="700" fill="var(--diag-primary)">{txt}</text>',
                GL0,
                GL0 + 0.4,
                END_ALL,
                END_ALL + 0.9,
            )
        )
    finale.append((SH1 + 0.3, END_ALL))
    return ev, END_ALL + 1.6


t = SETUP_END
ev, t = gen_loop(t, 6, 24, 30, False, sp=1.00)
out += ev
ev, t = gen_loop(t, 3, 30, 33, False, sp=0.74)
out += ev
ev, t = gen_loop(t, 0, 33, 33, True, sp=0.55)
out += ev
print(f"story ends at t={t:.1f}s / CYCLE={CYCLE}s")

bounds = [DS_BORN] + [m[0] for m in merges] + [podium[0]]
counts = [24] + [m[1] for m in merges]
for i, c in enumerate(counts):
    a, b = bounds[i], bounds[i + 1]
    out.append(moving(g_dataset(c), a, a + 0.25, b, b + 0.12, at=MERGE, base=0.72))
out.append(
    fade_group(
        f'    <text x="{MERGE[0]}" y="{MERGE[1]-30}" text-anchor="middle" font-size="8.5" letter-spacing="0.05em" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">labelled dataset</text>',
        DS_BORN,
        DS_BORN + 0.3,
        podium[0],
        podium[0] + 0.2,
    )
)


# ---------------------------------------------------------------- progress panels
# Two monitors that fill in as the run proceeds. The parity cloud both tightens and grows,
# since every iteration adds structures, and earlier passes stay behind at lower opacity.
PANEL_Y, PANEL_H = 44, 108
CURVE = (168, PANEL_Y, 196, PANEL_H)
PAR = (452, PANEL_Y, PANEL_H, PANEL_H)
ERRS = [0.80, 0.45, 0.24]
ERR_TARGET = 0.34  # the curve only drops under it on the last pass
NPTS = [24, 30, 33]
SPREAD = [46.0, 15.0, 3.4]
BOW = [28.0, 8.0, 0.0]  # the first model is not just noisy, it is bent off the diagonal
BACK = [[1.0, 0.30, 0.16], [0.0, 1.0, 0.32], [0.0, 0.0, 1.0]]


def parity_cloud(i, x0, y0, size, dot_r):
    dots = []
    n, sp_i, bow = NPTS[i], SPREAD[i], BOW[i]
    for k in range(n):
        u = 0.05 + 0.90 * k / (n - 1)
        j = (math.sin((k + 1) * 17.13 + i * 41.7) * 43758.5453) % 1.0 - 0.5
        j2 = (math.sin((k + 1) * 9.71 + i * 13.3) * 24634.6345) % 1.0 - 0.5
        f = size / PANEL_H
        bx = x0 + size * u + j2 * sp_i * 0.4 * f
        by = y0 + size * (1 - u) + (j * sp_i - bow * math.sin(math.pi * u)) * f
        bx = min(max(bx, x0 + 2), x0 + size - 2)  # a wide first pass must still stay inside the box
        by = min(max(by, y0 + 2), y0 + size - 2)
        dots.append(f'    <circle cx="{bx:.1f}" cy="{by:.1f}" r="{dot_r}" fill="var(--diag-primary)"/>')
    return "\n".join(dots)


def parity_axes(x0, y0, size, label_size=7.5):
    return "\n".join(
        [
            f'  <line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+size}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-opacity="0.5"/>',
            f'  <line x1="{x0}" y1="{y0+size}" x2="{x0+size}" y2="{y0+size}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-opacity="0.5"/>',
            f'  <line x1="{x0}" y1="{y0+size}" x2="{x0+size}" y2="{y0}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-dasharray="3 3" stroke-opacity="0.6"/>',
            f'  <text x="{x0+size}" y="{y0+size+13}" text-anchor="end" font-size="{label_size}" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">DFT</text>',
            f'  <text x="{x0-6}" y="{y0+9}" text-anchor="end" font-size="{label_size}" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">NNIP</text>',
        ]
    )


def curve_block(x0, y0, w, h, dot_r=4, label_size=7.5):
    o = [
        f'  <line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+h}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-opacity="0.5"/>',
        f'  <line x1="{x0}" y1="{y0+h}" x2="{x0+w}" y2="{y0+h}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-opacity="0.5"/>',
        f'  <text x="{x0-6}" y="{y0+9}" text-anchor="end" font-size="{label_size}" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">RMSE</text>',
        f'  <text x="{x0+w}" y="{y0+h+13}" text-anchor="end" font-size="{label_size}" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">iteration</text>',
    ]
    p = [(x0 + w * (i + 1) / (len(ERRS) + 0.6), y0 + h - e * h) for i, e in enumerate(ERRS)]
    for i in range(1, len(p)):
        o.append(
            f'  <line x1="{p[i-1][0]:.1f}" y1="{p[i-1][1]:.1f}" x2="{p[i][0]:.1f}" y2="{p[i][1]:.1f}" '
            f'stroke="var(--diag-primary)" stroke-width="1.8"/>'
        )
    for px, py in p:
        o.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="{dot_r}" fill="var(--diag-primary)"/>')
    return "\n".join(o)


panel = []
cx0, cy0, cw, ch = CURVE
panel.append(
    f'  <text x="{cx0}" y="{cy0-11}" font-size="9" letter-spacing="0.06em" font-family="Inter,sans-serif" '
    f'font-weight="700" fill="var(--diag-text-muted)">RMSE EVOLUTION</text>'
)
panel.append(
    f'  <line x1="{cx0}" y1="{cy0}" x2="{cx0}" y2="{cy0+ch}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-opacity="0.5"/>'
)
panel.append(
    f'  <line x1="{cx0}" y1="{cy0+ch}" x2="{cx0+cw}" y2="{cy0+ch}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-opacity="0.5"/>'
)
panel.append(
    f'  <text x="{cx0-6}" y="{cy0+9}" text-anchor="end" font-size="7.5" font-family="\'JetBrains Mono\',monospace" '
    f'fill="var(--diag-text-muted)">RMSE</text>'
)
ty = cy0 + ch - ERR_TARGET * ch
panel.append(
    f'  <line x1="{cx0}" y1="{ty:.1f}" x2="{cx0+cw}" y2="{ty:.1f}" stroke="var(--diag-accent-orange)" '
    f'stroke-width="1.3" stroke-dasharray="5 4" stroke-opacity="0.85"/>'
)
panel.append(
    f'  <text x="{cx0+cw}" y="{ty-5:.1f}" text-anchor="end" font-size="7.5" '
    f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-accent-orange)">target</text>'
)
panel.append(
    f'  <text x="{cx0+cw}" y="{cy0+ch+13}" text-anchor="end" font-size="7.5" '
    f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">iteration</text>'
)
pts = [(cx0 + cw * (i + 1) / (len(ERRS) + 0.6), cy0 + ch - e * ch) for i, e in enumerate(ERRS)]
for i, (px, py) in enumerate(pts):
    m = iter_marks[i]
    if i:
        qx, qy = pts[i - 1]
        panel.append(
            fade_group(
                f'    <line x1="{qx:.1f}" y1="{qy:.1f}" x2="{px:.1f}" y2="{py:.1f}" '
                f'stroke="var(--diag-primary)" stroke-width="1.6"/>',
                m,
                m + 0.6,
                CYCLE - 1.2,
                CYCLE - 0.6,
            )
        )
    panel.append(
        fade_group(
            f'    <circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="var(--diag-primary)"/>',
            m,
            m + 0.45,
            CYCLE - 1.2,
            CYCLE - 0.6,
        )
    )
    panel.append(ripple(px, py, m, r0=4, r1=17, color="var(--diag-primary)"))

px0, py0, pw, ph = PAR
panel.append(
    f'  <text x="{px0}" y="{py0-11}" font-size="9" letter-spacing="0.06em" font-family="Inter,sans-serif" '
    f'font-weight="700" fill="var(--diag-text-muted)">PARITY</text>'
)
panel.append(parity_axes(px0, py0, ph))
for i in range(3):
    kts, vals = ["0"], [0]

    def push(t, v, _k=kts, _v=vals):
        f = frac(t)
        if float(f) < float(_k[-1]):
            f = _k[-1]
        _k.append(f)
        _v.append(v)

    for j in range(i, 3):
        m = iter_marks[j]
        push(m - 0.02, vals[-1])
        push(m + 0.5, BACK[i][j])
    push(CYCLE - 1.2, vals[-1])
    push(CYCLE - 0.6, 0)
    kts.append("1")
    vals.append(0)
    panel.append(f'  <g opacity="0">\n{parity_cloud(i, px0, py0, ph, 2.6)}\n' + anim("opacity", kts, vals) + "\n  </g>")

PANEL_C, FIN_C, PSCALE = (364, 98), (CX, 152), 1.34
TX = FIN_C[0] - PSCALE * PANEL_C[0]
TY = FIN_C[1] - PSCALE * PANEL_C[1]
mv0, mv1 = fade_all[0], fade_all[0] + 2.2
fin_end = finale[0][1]
kt = ["0", frac(mv0), frac(mv1), frac(fin_end + 1.0), frac(fin_end + 1.25), "1"]
out.append(
    "  <g>\n"
    + anim_transform("translate", kt, ["0 0", "0 0", f"{TX:.1f} {TY:.1f}", f"{TX:.1f} {TY:.1f}", "0 0", "0 0"])
    + "\n"
    + anim_transform("scale", kt, ["1", "1", f"{PSCALE}", f"{PSCALE}", "1", "1"], additive="sum")
    + "\n"
    + spotlight(
        "\n".join(panel),
        [(t - 0.3, t + 1.6) for t in iter_marks] + [(mv0, fin_end - 0.7)],
        dim=0.5,
        pad=0.2,
        fade_out=(fin_end, fin_end + 0.9),
    )
    + "\n  </g>"
)


# ---------------------------------------------------------------- badges
def engine_badge(cx, cy, r, title, caption, icon_fn):
    return "\n".join(
        [
            f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.8" filter="url(#ss)"/>',
            f'  <circle cx="{cx}" cy="{cy}" r="{r-7}" fill="var(--diag-bg-tinted)"/>',
            icon_fn(cx, cy),
            f'  <text x="{cx}" y="{cy+r+24}" text-anchor="middle" font-size="15" font-family="Inter,sans-serif" font-weight="700" fill="var(--diag-text)">{title}</text>',
            f'  <text x="{cx}" y="{cy+r+40}" text-anchor="middle" font-size="8.5" font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">{caption}</text>',
        ]
    )


def icon_augment(cx, cy):
    o = [f'<path d="{hexagon_path(cx,cy-3,7)}" fill="var(--diag-primary)"/>']
    for i in range(3):
        a = math.radians(90 + i * 120)
        sx, sy = cx + 17 * math.cos(a), (cy - 3) + 17 * math.sin(a)
        o.append(
            f'<line x1="{cx}" y1="{cy-3}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="var(--diag-primary)" stroke-opacity="0.5" stroke-width="1.3"/>'
        )
        o.append(f'<path d="{hexagon_path(sx,sy,4)}" fill="var(--diag-primary)" fill-opacity="0.55"/>')
    return "\n".join(f"  {x}" for x in o)


def icon_label(cx, cy):
    o = [
        f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="none" stroke="var(--diag-primary)" stroke-width="1.5" stroke-opacity="{op}"/>'
        for rr, op in [(15, 0.35), (10, 0.55), (5.2, 0.8)]
    ]
    o.append(f'<circle cx="{cx}" cy="{cy}" r="2.1" fill="var(--diag-primary)"/>')
    return "\n".join(f"  {x}" for x in o)


TRAIN_L1 = [(-15, -9.5), (-15, 9.5)]
TRAIN_L2 = [(0, -13.5), (0, 0), (0, 13.5)]
TRAIN_L3 = [(15, -9.5), (15, 9.5)]


def icon_train(cx, cy):
    o = [f'<circle cx="{cx}" cy="{cy}" r="20.5" fill="var(--diag-accent-orange)" fill-opacity="0.09"/>']
    for a, b in ((TRAIN_L1, TRAIN_L2), (TRAIN_L2, TRAIN_L3)):
        for p in a:
            for q in b:
                o.append(
                    f'<line x1="{cx+p[0]:.1f}" y1="{cy+p[1]:.1f}" x2="{cx+q[0]:.1f}" y2="{cy+q[1]:.1f}" stroke="var(--diag-accent-orange)" stroke-width="1.4" stroke-opacity="0.55"/>'
                )
    for p in TRAIN_L1 + TRAIN_L2 + TRAIN_L3:
        o.append(
            f'<circle cx="{cx+p[0]:.1f}" cy="{cy+p[1]:.1f}" r="3.1" fill="var(--diag-accent-orange)" fill-opacity="0.75"/>'
        )
    return "\n".join(f"  {x}" for x in o)


MD_RESTS = [(-13, 3), (0, -3), (13, 4)]


def icon_explore(cx, cy):
    p = [(cx + dx, cy + dy) for dx, dy in MD_RESTS]
    return (
        f'  <path d="M {p[0][0]},{p[0][1]} Q {cx-4},{cy-11} {p[1][0]},{p[1][1]} T {p[2][0]},{p[2][1]}" '
        f'fill="none" stroke="var(--diag-accent-green)" stroke-width="1.1" stroke-opacity="0.35" stroke-dasharray="1 3"/>'
    )


def icon_evaluate(cx, cy):
    o = [
        f'<line x1="{cx-16}" y1="{cy+1}" x2="{cx+16}" y2="{cy+1}" stroke="var(--diag-text-muted)" stroke-width="1.2" stroke-dasharray="2 2"/>'
    ]
    for dx, dy in [(-11, 9), (-2, 11), (9, 8)]:
        o.append(f'<circle cx="{cx+dx}" cy="{cy+dy}" r="2.3" fill="var(--diag-text-muted)"/>')
    for dx, dy in [(-8, -9), (7, -7)]:
        o.append(f'<circle cx="{cx+dx}" cy="{cy+dy}" r="3" fill="var(--diag-accent-orange)"/>')
        o.append(
            f'<circle cx="{cx+dx}" cy="{cy+dy}" r="5.5" fill="none" stroke="var(--diag-accent-orange)" stroke-width="1.1"/>'
        )
    return "\n".join(f"  {x}" for x in o)


FADE = (fade_all[0], fade_all[0] + 1.4)
badges = [
    spotlight(
        engine_badge(X["augment"], ROW, R, "Augment", "1 structure -&gt; N variants", icon_augment),
        aug_win,
        fade_out=FADE,
    ),
    spotlight(engine_badge(X["label"], ROW, R, "Label", "DFT: E, F, &#963;", icon_label), label_win, fade_out=FADE),
    spotlight(
        engine_badge(X["train"], ROW, R, "Train", "committee of potentials", icon_train), train_win, fade_out=FADE
    ),
    spotlight(
        engine_badge(X["explore"], ROW, R, "Explore", "potential + seeds -&gt; MD", icon_explore), md_win, fade_out=FADE
    ),
    spotlight(
        engine_badge(X["evaluate"], ROW, R + 2, "Evaluate &amp; Select", "committee disagreement", icon_evaluate),
        eval_win,
        fade_out=FADE,
    ),
]

# ---------------------------------------------------------------- in-badge animations (drawn above the badges)
live = []

# MD: the atoms wander while the dynamics runs. They sit at rest the rest of the time, so they
# have to follow the Explore spotlight -- otherwise they stay bright while their own box dims.
md_atoms = []
for i, ((dx, dy), op) in enumerate(zip(MD_RESTS, (0.35, 0.68, 1.0), strict=False)):
    md_atoms.append(
        "  <g>\n"
        + md_motion(wander_path(X["explore"] + dx, ROW + dy, seed=i * 1.7 + 0.4), md_win, laps=3, shift=i * 0.2)
        + f'\n    <circle r="4.3" fill="var(--diag-accent-green)" fill-opacity="{op}"/>\n  </g>'
    )
live.append(spotlight("\n".join(md_atoms), md_win, fade_out=FADE))

# Augment: variants bud off the seed structure, one spoke after another
AUG_SEG = (aug_win[0][1] - aug_win[0][0]) / 4
for i in range(6):
    ph = i * 0.16
    a = math.radians(90 + i * 60)
    sx, sy = X["augment"] + 30 * math.cos(a), (ROW - 2) + 30 * math.sin(a)
    live.append(
        '  <g opacity="0">\n'
        + md_motion(line_path((X["augment"], ROW - 2), (sx, sy)), aug_win, laps=4, shift=ph * AUG_SEG)
        + "\n"
        + f'    <path d="{hexagon_path(0,0,6)}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.6"/>\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.18, 1.0), (0.78, 1.0), (1.0, 0.0)], aug_win, laps=4, phase=ph)
        + "\n  </g>"
    )
live.append(
    f'  <path d="{hexagon_path(X["augment"],ROW-2,7.5)}" fill="var(--diag-primary)" opacity="0">\n'
    + windowed("opacity", 0, [(0.0, 0.0), (0.1, 1.0), (0.9, 1.0), (1.0, 0.0)], aug_win, laps=1)
    + "\n  </path>"
)

# DFT: electrons run their orbits around the nucleus while the calculation is on
ORBITS = [(17.5, 7.5, -22, 4), (13, 5.5, 52, 3)]
for oi, (rx, ry, rot, laps) in enumerate(ORBITS):
    path = ellipse_path(X["label"], ROW, rx, ry)
    live.append(
        f'  <g transform="rotate({rot},{X["label"]},{ROW})">\n'
        f'    <ellipse cx="{X["label"]}" cy="{ROW}" rx="{rx}" ry="{ry}" fill="none" stroke="var(--diag-primary)" '
        f'stroke-width="0.9" stroke-dasharray="2 3" opacity="0">\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.15, 0.5), (0.85, 0.5), (1.0, 0.0)], dft_win, laps=1, indent=6)
        + "\n    </ellipse>\n"
        '    <g opacity="0">\n'
        + md_motion(path, dft_win, laps=laps, shift=oi * 0.12).replace("    <", "      <")
        + "\n"
        '      <circle r="2.9" fill="var(--diag-primary)"/>\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.12, 1.0), (0.88, 1.0), (1.0, 0.0)], dft_win, laps=1, indent=6)
        + "\n    </g>\n  </g>"
    )
live.append(
    f'  <circle cx="{X["label"]}" cy="{ROW}" r="2.1" fill="var(--diag-primary)" opacity="0">\n'
    + windowed("opacity", 0, [(0.0, 0.0), (0.12, 1.0), (0.55, 0.4), (1.0, 0.0)], dft_win, laps=4)
    + "\n  </circle>"
)

# Train: activation sweeps forward through the network, layer by layer
for gi, (a, b) in enumerate(((TRAIN_L1, TRAIN_L2), (TRAIN_L2, TRAIN_L3))):
    edges = "".join(
        f'<line x1="{X["train"]+p[0]:.1f}" y1="{ROW+p[1]:.1f}" x2="{X["train"]+q[0]:.1f}" y2="{ROW+q[1]:.1f}" '
        f'stroke="var(--diag-accent-orange)" stroke-width="1.6"/>'
        for p in a
        for q in b
    )
    live.append(
        f'  <g opacity="0">\n    {edges}\n'
        + windowed(
            "opacity", 0, [(0.0, 0.0), (0.18, 0.95), (0.55, 0.0), (1.0, 0.0)], train_win, laps=4, phase=gi * 0.16
        )
        + "\n  </g>"
    )
for li, layer in enumerate((TRAIN_L1, TRAIN_L2, TRAIN_L3)):
    nodes = "".join(
        f'<circle cx="{X["train"]+p[0]:.1f}" cy="{ROW+p[1]:.1f}" r="3.4" fill="var(--diag-accent-orange)"/>'
        for p in layer
    )
    live.append(
        f'  <g opacity="0">\n    {nodes}\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.12, 1.0), (0.5, 0.0), (1.0, 0.0)], train_win, laps=4, phase=li * 0.16)
        + "\n  </g>"
    )

defs = (
    '  <defs>\n    <filter id="ss" x="-60%" y="-60%" width="220%" height="220%">'
    '<feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="var(--diag-primary-dark)" flood-opacity="0.22"/></filter>\n  </defs>'
)

W, H = X["evaluate"] + R + 110, 585
bg, row, y = ["  <g>"], 0, 13.6
while y < H:
    x = 13.6 + (17 if row % 2 else 0)
    while x < W:
        bg.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="1.1" fill="var(--diag-primary)" opacity="0.05"/>')
        x += 34
    y += 29.6
    row += 1
bg.append("  </g>")

open("/tmp/v12_full.txt", "w").write("\n".join([defs] + bg + out + badges + live))
print("viewBox:", W, H, "| md:", len(md_win), "dft:", len(dft_win), "train:", len(train_win))
