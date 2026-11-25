import math

CYCLE = 101.0
EASE = "0.42 0 0.22 1"
EPS = 0.004


# ---------------------------------------------------------------- primitives
def hexagon_path(cx, cy, r, rotate=-90):
    pts = [
        (cx + r * math.cos(math.radians(60 * i + rotate)), cy + r * math.sin(math.radians(60 * i + rotate)))
        for i in range(6)
    ]
    return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def frac(t):
    t = min(max(t, 0.0), CYCLE)
    return f"{t/CYCLE:.5f}"


def anim(attr, kts, vals, indent=4):
    return (
        f'{" "*indent}<animate attributeName="{attr}" values="{";".join(str(v) for v in vals)}" '
        f'keyTimes="{";".join(kts)}" dur="{CYCLE}s" repeatCount="indefinite"/>'
    )


def opacity_tag(t_in0, t_in1, t_out0, t_out1, base=1.0, indent=6):
    return anim(
        "opacity", ["0", frac(t_in0), frac(t_in1), frac(t_out0), frac(t_out1), "1"], [0, 0, base, base, 0, 0], indent
    )


def motion_tag(path_d, t0, t1):
    return (
        f'    <animateMotion path="{path_d}" keyPoints="0;0;1;1" keyTimes="0;{frac(t0)};{frac(t1)};1" '
        f'calcMode="spline" keySplines="0 0 1 1;{EASE};0 0 1 1" dur="{CYCLE}s" repeatCount="indefinite"/>'
    )


def pulse_tag(t0, t1):
    return anim("stroke-opacity", ["0", frac(t0), frac((t0 + t1) / 2), frac(t1), "1"], [0, 0, 1, 0, 0])


def breathe_tag(t0, t1, n=3, lo=0.3, hi=1.0):
    kts = ["0", frac(t0 - EPS), frac(t0)]
    vals = [0, 0, lo]
    for i in range(n * 2):
        kts.append(frac(t0 + (t1 - t0) * (i + 1) / (n * 2)))
        vals.append(hi if i % 2 == 0 else lo)
    kts += [frac(t1), frac(t1 + EPS), "1"]
    vals += [lo, 0, 0]
    return anim("stroke-opacity", kts, vals)


def ripple(cx, cy, t0, r0=26, r1=46, color="var(--diag-accent-green)"):
    kt = ["0", frac(t0 - EPS), frac(t0), frac(t0 + 0.65), frac(t0 + 0.65 + EPS), "1"]
    return (
        f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r0}" fill="none" stroke="{color}" stroke-width="1.6" opacity="0">\n'
        + anim("r", kt, [r0, r0, r0, r1, r1, r1])
        + "\n"
        + anim("opacity", kt, [0, 0, 0.5, 0, 0, 0])
        + "\n  </circle>"
    )


def float_text(x, y, txt, t0, color="var(--diag-accent-green)", size=12):
    kt = ["0", frac(t0), frac(t0 + 0.3), frac(t0 + 1.2), frac(t0 + 1.5), "1"]
    return (
        f'  <text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="{size}" '
        f'font-family="\'JetBrains Mono\',monospace" font-weight="700" fill="{color}" opacity="0">{txt}\n'
        + anim("y", kt, [y, y, y - 8, y - 24, y - 29, y - 29])
        + "\n"
        + anim("opacity", kt, [0, 0, 1, 1, 0, 0])
        + "\n  </text>"
    )


def windowed(attr, rest, kfs, windows, laps=3, phase=0.0, indent=4):
    kts, vals = ["0"], [rest]

    def push(t, v):
        f = frac(t)
        if float(f) < float(kts[-1]):
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


def spotlight(body, windows, dim=0.36, pad=0.7, ramp=0.45, fade_out=None):
    kts, vals = ["0"], [0.0]

    def push(t, v):
        f = frac(t)
        if float(f) < float(kts[-1]):
            f = kts[-1]
        kts.append(f)
        vals.append(v)

    rest = 0.0
    for w0, w1 in sorted(windows):
        a, b = w0 - pad, w1 + pad
        push(a - ramp, rest)
        push(a, 1.0)
        push(b, 1.0)
        push(b + ramp, dim)
        rest = dim
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


def celebrate(cx, cy, t0, scale=1.0, n=30):
    o = []
    for i in range(n):
        f = (i + 0.5) / n
        a = math.radians(-158 + 136 * f + 8 * math.sin(i * 2.9))
        d = (90 + 200 * ((math.sin((i + 1) * 12.9898 + cx * 0.013) * 43758.5453) % 1.0)) * scale
        ex = cx + d * math.cos(a)
        ey = cy + d * math.sin(a) * 1.15
        c1 = (cx + d * 0.16 * math.cos(a), cy + d * 1.05 * math.sin(a))
        c2 = (ex, ey - 26 * scale)
        dt = t0 + 0.05 * (i % 5)
        dur = 1.5 + 0.35 * ((i % 3) / 2)
        col = ["var(--diag-primary)", "var(--diag-accent-green)", "var(--diag-accent-orange)"][i % 3]
        body = (
            f'      <path d="{hexagon_path(0,0,4.6*scale)}" fill="{col}"/>'
            if i % 2
            else f'      <circle r="{3.2*scale:.1f}" fill="{col}"/>'
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


# ---------------------------------------------------------------- glyphs (counts sit beside, not below)
def counted(body, count, color, dx=22, size=11, sub=None, above=False):
    if above:
        return body + (
            f'\n      <text x="0" y="-16" text-anchor="middle" font-size="{size}" '
            f'font-family="\'JetBrains Mono\',monospace" font-weight="700" fill="{color}">{count}</text>'
        )
    o = [
        body,
        f'      <text x="{dx}" y="4" font-size="{size}" font-family="\'JetBrains Mono\',monospace" '
        f'font-weight="700" fill="{color}">{count}</text>',
    ]
    if sub:
        o.append(
            f'      <text x="{dx}" y="14" font-size="7" font-family="\'JetBrains Mono\',monospace" '
            f'fill="var(--diag-text-muted)">{sub}</text>'
        )
    return "\n".join(o)


def _stack(r, fill, op_scale, stroke):
    return "".join(
        f'<path d="{hexagon_path(dx,dy,r)}" fill="{fill}" fill-opacity="{op*op_scale:.2f}" stroke="{stroke}" stroke-width="1"/>'
        for dx, dy, op in [(-7, 3, 0.45), (0, -2, 0.72), (7, 3, 1.0)]
    )


def _tick(cx=13, cy=-8, rr=4.8):
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="var(--diag-accent-green)"/>'
        f'<path d="M {cx-rr*0.45:.1f},{cy:.1f} l {rr*0.3:.1f},{rr*0.32:.1f} l {rr*0.6:.1f},-{rr*0.66:.1f}" fill="none" '
        f'stroke="#fff" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def g_structure(r=9, style="plain"):
    if style == "plain":
        return f'      <path d="{hexagon_path(0,0,r)}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.5"/>'
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
        return "      " + f'<circle r="{r}" fill="var(--diag-primary-dark)" filter="url(#ssm)"/>' + edges + dots


def g_rawset(count):
    stack = "".join(
        f'<path d="{hexagon_path(dx,dy,8)}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.4" stroke-opacity="{op}"/>'
        for dx, dy, op in [(-7, 3, 0.5), (0, -2, 0.75), (7, 3, 1.0)]
    )
    return counted("      " + stack, count, "var(--diag-primary)")


def g_dataset(count, sub=None, above=False):
    return counted(
        "      " + _stack(8, "var(--diag-primary)", 1.0, "var(--diag-primary-dark)") + _tick(),
        count,
        "var(--diag-primary)",
        sub=sub,
        above=above,
    )


def g_explored(count):
    return counted(
        "      " + _stack(8, "var(--diag-accent-green)", 0.9, "var(--diag-accent-green)"),
        count,
        "var(--diag-accent-green)",
        sub="explored",
        above=True,
    )


def g_selected(count):
    return counted(
        "      " + _stack(8, "var(--diag-accent-orange)", 1.0, "var(--diag-accent-orange)"),
        count,
        "var(--diag-accent-orange)",
    )


def g_batch_labelled(count):
    return counted(
        "      " + _stack(7, "var(--diag-primary)", 0.9, "var(--diag-primary-dark)") + _tick(11, -7, 4.2),
        f"+{count}",
        "var(--diag-accent-green)",
        above=True,
    )


def g_seeds(count):
    return counted(
        "      " + _stack(6.5, "var(--diag-primary)", 0.85, "var(--diag-primary-dark)") + _tick(10, -6, 3.8),
        count,
        "var(--diag-primary)",
        size=10,
        above=True,
    )


def g_trajectory(count):
    dots = "".join(
        f'<circle cx="{dx}" cy="{dy}" r="3.2" fill="var(--diag-accent-green)" fill-opacity="{op}"/>'
        for dx, dy, op in [(-10, 2, 0.35), (0, -2, 0.68), (10, 3, 1.0)]
    )
    return counted("      " + dots, count, "var(--diag-accent-green)", size=9.5, above=True)


def g_feed():
    return "      " + _stack(6.5, "var(--diag-primary)", 0.4, "var(--diag-primary)")


# ---------------------------------------------------------------- portrait layout
W, H = 400, 640
COL, R = 96, 24
Y = dict(augment=62, label=170, train=278, explore=386, evaluate=494)  # gaps compressed to 108
top_p = lambda n: (COL, Y[n] - R - 12)
bot_p = lambda n: (COL, Y[n] + R + 12)
lft_p = lambda n: (COL - R - 12, Y[n])

MERGE = (272, 224)  # the dataset shelf, in the gap beside Label -> Train
WAIT = (218, 430)  # committee waiting beside Evaluate
POOL = (COL, 448)
THR_Y = 540
SC_X, SC_HW = 292, 74
AGG = (144, 604)
ARC = "M 144.0,604.0 C 16.0,548.0 12.0,272.0 52.0,170.0"
N_FRAMES, N_TRAJ = 8, 3

out, md_win, dft_win, train_win, aug_win = [], [], [], [], []
merges, podium, eval_win, label_win, iter_marks, fade_all, finale = [], [], [], [], [], [], []
DS_BORN = 10.6

# ---------------------------------------------------------------- setup
out.append(moving(g_structure(10), 0.0, 0.3, 1.0, 1.3, line_path((COL, -24), top_p("augment")), 0.3, 1.0))
aug_win.append((1.0, 3.4))
out.append(
    f'  <circle cx="{COL}" cy="{Y["augment"]}" r="{R+5}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2">\n{pulse_tag(3.4,4.0)}\n  </circle>'
)
out.append(ripple(COL, Y["augment"], 3.45))
out.append(moving(g_rawset(24), 3.9, 4.2, 6.05, 6.3, line_path(bot_p("augment"), top_p("label")), 4.1, 6.0))
dft_win.append((6.2, 8.6))
train_win.append((13.0, 15.6))
label_win.append((5.9, 10.8))
out.append(
    f'  <circle cx="{COL}" cy="{Y["label"]}" r="{R+5}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2">\n{pulse_tag(8.6,9.2)}\n  </circle>'
)
out.append(ripple(COL, Y["label"], 8.65))
out.append(moving(g_dataset(24), 9.25, 9.45, 10.65, 10.8, line_path(bot_p("label"), MERGE), 9.4, 10.6))
out.append(ripple(MERGE[0], MERGE[1], 10.6, r0=14, r1=34, color="var(--diag-primary)"))
out.append(
    moving(g_dataset(24, above=True), 11.0, 11.2, 13.05, 13.3, line_path(MERGE, top_p("train")), 11.15, 13.0, base=0.85)
)
SETUP_END = 16.3
out.append(
    f'  <circle cx="{COL}" cy="{Y["train"]}" r="{R+5}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2">\n{pulse_tag(15.6,SETUP_END)}\n  </circle>'
)
out.append(ripple(COL, Y["train"], 15.65))


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
        x = -SC_HW + 10 + (i / (n - 1) if n > 1 else 0.5) * (2 * SC_HW - 20) + (j - 0.5) * 9
        above = i in chosen
        pts.append((x, (-38 + j * 28) if above else (9 + k * 32), above))
    pts.sort(key=lambda p: p[0])
    return pts


def gen_loop(t0, n_up, ds_before, ds_after, final, sp=1.0):
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

    park_y = bot_p("train")[1]
    ev.append(moving(g_structure(9, "potential"), t0 - 0.1, t0 + 0.4, DEP0, DEP0 + 0.05, at=(COL, park_y)))
    for dx in (-20, 20):
        ev.append(moving(g_structure(9, "potential"), t0 - 0.1, t0 + 0.4, GDEP0, GDEP0 + 0.05, at=(COL + dx, park_y)))

    ex_pot = (COL - 15, top_p("explore")[1])
    ex_seeds = (COL + 17, top_p("explore")[1])
    ev.append(
        moving(
            g_structure(9, "potential"),
            DEP0 - 0.05,
            DEP0,
            DEP1 + 0.15,
            DEP1 + 0.4,
            line_path((COL, park_y), ex_pot),
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
            curve_path(MERGE, ex_seeds, (MERGE[0] - 20, MERGE[1] + 120), (ex_seeds[0] + 96, ex_seeds[1] - 46)),
            DEP0 - 0.25,
            DEP1 + 0.1,
        )
    )
    ev.append(ripple(COL, Y["explore"], DEP1, r0=R - 6, r1=R + 10, color="var(--diag-primary)"))

    group_out = PICK0 + 0.4 if not final else SH0_T
    for k, dx in enumerate((-20, 20)):
        ev.append(
            moving(
                g_structure(9, "potential"),
                GDEP0 - 0.05,
                GDEP0,
                group_out,
                group_out + 0.3,
                curve_path(
                    (COL + dx, park_y),
                    (WAIT[0] + k * 20 - 10, WAIT[1]),
                    (COL + dx + 90, park_y + 40),
                    (WAIT[0] - 30, WAIT[1] - 70),
                ),
                GDEP0,
                GDEP1,
            )
        )
    ev.append(
        moving(
            g_structure(9, "potential"),
            FIRE1 - 0.05,
            FIRE1,
            group_out,
            group_out + 0.3,
            curve_path(
                bot_p("explore"), (WAIT[0] + 30, WAIT[1]), (COL + 70, Y["explore"] + 50), (WAIT[0] - 10, WAIT[1] - 40)
            ),
            FIRE1,
            TRJ_LAST - 0.15,
        )
    )
    ev.append(
        fade_group(
            f'    <text x="{WAIT[0]+10}" y="{WAIT[1]-20}" text-anchor="middle" font-size="7.5" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">committee</text>',
            GDEP1,
            GDEP1 + 0.4,
            group_out - 0.2,
            group_out + 0.1,
        )
    )

    ev.append(
        f'  <circle cx="{COL}" cy="{Y["explore"]}" r="{R+4}" fill="none" stroke="var(--diag-accent-green)" stroke-width="1.6">\n{breathe_tag(MD0, MD1)}\n  </circle>'
    )
    ev.append(
        f'  <circle cx="{COL}" cy="{Y["explore"]}" r="{R+5}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2">\n{pulse_tag(FIRE0, FIRE1)}\n  </circle>'
    )

    for i, dx in enumerate((-26, 0, 26)):
        a, b = TRJ0 + i * 0.2 * sp, TRJ1 + i * 0.2 * sp
        ev.append(
            moving(
                g_trajectory(N_FRAMES),
                a - 0.1,
                a + 0.15,
                b + 0.05,
                b + 0.3,
                line_path(bot_p("explore"), (POOL[0] + dx * 0.6, POOL[1])),
                a,
                b,
            )
        )
    ev.append(ripple(POOL[0], POOL[1], POOL0, r0=10, r1=32, color="var(--diag-accent-green)"))
    ev.append(moving(g_explored(N_TRAJ * N_FRAMES), POOL0, POOL0 + 0.4, ENTER0, ENTER0 + 0.1, at=POOL))
    ev.append(
        moving(
            g_explored(N_TRAJ * N_FRAMES),
            ENTER0 - 0.1,
            ENTER0,
            ENTER1 + 0.2,
            ENTER1 + 0.45,
            line_path(POOL, (COL - 20, top_p("evaluate")[1])),
            ENTER0,
            ENTER1,
        )
    )
    ev.append(
        moving(
            g_dataset(ds_before, above=True),
            TRJ0 - 0.3,
            TRJ0 - 0.05,
            ENTER1 + 0.2,
            ENTER1 + 0.45,
            curve_path(
                MERGE,
                (COL + 20, top_p("evaluate")[1]),
                (MERGE[0] + 90, MERGE[1] + 180),
                (COL + 150, top_p("evaluate")[1] - 40),
            ),
            TRJ0 - 0.2,
            ENTER1,
        )
    )
    ev.append(
        f'  <circle cx="{COL}" cy="{Y["evaluate"]}" r="{R+6}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2.2">\n{pulse_tag(EVF0, EVF1)}\n  </circle>'
    )
    eval_win.append((EVF0 - 0.3, PICK1 + 0.6))
    iter_marks.append(RAIN1 + 0.4)

    total = N_TRAJ * N_FRAMES
    axis = (
        f'    <line x1="{SC_X-SC_HW-6}" y1="{THR_Y-44}" x2="{SC_X-SC_HW-6}" y2="{THR_Y+46}" '
        f'stroke="var(--diag-text-muted)" stroke-width="0.9" stroke-opacity="0.45"/>\n'
        f'    <text x="{SC_X-SC_HW+8}" y="{THR_Y-50}" font-size="6.5" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">committee deviation</text>\n'
        f'    <line x1="{SC_X-SC_HW}" y1="{THR_Y}" x2="{SC_X+SC_HW}" y2="{THR_Y}" '
        f'stroke="var(--diag-accent-orange)" stroke-width="1.2" stroke-dasharray="4 3" stroke-opacity="0.85"/>\n'
        f'    <text x="{SC_X+SC_HW+4}" y="{THR_Y+3}" font-size="6.5" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-accent-orange)">thr</text>'
    )
    axis_out = PICK1 + 0.6
    ev.append(fade_group(axis, RAIN0 - 0.4, RAIN0 - 0.1, axis_out, axis_out + 0.4))

    for i, (dx, dy, above) in enumerate(scatter_points(total, n_up, seed=n_up + 1)):
        a = RAIN0 + i * (RAIN1 - RAIN0 - 0.5 * sp) / max(total - 1, 1)
        px, py = SC_X + dx, THR_Y + dy
        dot = (
            '      <circle r="3.2" fill="none" stroke="var(--diag-accent-orange)" stroke-width="1.4"/>'
            '<circle r="6" fill="none" stroke="var(--diag-accent-orange)" stroke-width="0.8" stroke-opacity="0.55"/>'
            if above
            else '      <circle r="2.6" fill="var(--diag-text-muted)" fill-opacity="0.75"/>'
        )
        ev.append(
            moving(
                dot,
                a - 0.15,
                a + 0.1,
                PICK0 + 0.15,
                PICK0 + 0.4,
                line_path((COL + R + 10, Y["evaluate"]), (px, py)),
                a,
                a + 0.75,
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
                    line_path((px, py), (px + dx * 0.1, py + 22)),
                    PICK0 + 0.2,
                    PICK1,
                )
            )

    verdict = f"{n_up} above thr" if n_up else "none above thr"
    vcol = "var(--diag-accent-orange)" if n_up else "var(--diag-accent-green)"
    ev.append(
        fade_group(
            f'    <text x="{SC_X}" y="{THR_Y+76}" text-anchor="middle" font-size="8.5" font-weight="700" '
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
        ev.append(moving(g_selected(n_up), ARC0 - 0.1, ARC0 + 0.05, ARC1 + 0.1, ARC1 + 0.3, ARC, ARC0, ARC1))

        DFT0, DFT1 = ARC1, ARC1 + 2.4 * sp
        dft_win.append((DFT0, DFT1))
        ev.append(
            f'  <circle cx="{COL}" cy="{Y["label"]}" r="{R+5}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2">\n{pulse_tag(DFT1, DFT1+0.5)}\n  </circle>'
        )
        ev.append(ripple(COL, Y["label"], DFT1))

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
                line_path((COL, Y["label"] + R + 22), MERGE),
                SUM0 + 0.4,
                IMP,
            )
        )
        ev.append(ripple(MERGE[0], MERGE[1], IMP, r0=13, r1=34, color="var(--diag-primary)"))
        ev.append(float_text(MERGE[0] - 44, MERGE[1] - 20, f"+{ds_after-ds_before}", IMP))

        D0, D1 = IMP + 0.8, IMP + 0.8 + 2.0 * sp
        ev.append(
            moving(
                g_dataset(ds_after, above=True),
                D0 - 0.2,
                D0,
                D1 + 0.15,
                D1 + 0.4,
                line_path(MERGE, top_p("train")),
                D0,
                D1,
                base=0.85,
            )
        )
        TR0, TR1 = D1, D1 + 2.6 * sp
        train_win.append((TR0, TR1))
        NX0, NX1 = TR1, TR1 + 0.6
        ev.append(
            f'  <circle cx="{COL}" cy="{Y["train"]}" r="{R+5}" fill="none" stroke="var(--diag-accent-green)" stroke-width="2">\n{pulse_tag(NX0, NX1)}\n  </circle>'
        )
        ev.append(ripple(COL, Y["train"], NX0))
        return ev, NX1

    CONV, MOVE0 = CONV_T, MOVE0_T
    MOVE1 = MOVE0 + 2.0
    fade_all.append(MOVE0)
    ev.append(
        fade_group(
            f'    <text x="{SC_X}" y="{THR_Y+92}" text-anchor="middle" font-size="9" font-weight="700" '
            f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-accent-green)">the loop stops here</text>',
            CONV,
            CONV + 0.5,
            MOVE0 + 0.4,
            MOVE0 + 1.0,
        )
    )

    SH0, SH1 = SH0_T, SH0_T + 1.9
    END_ALL = SH1 + 5.2
    podium.append(SH0)
    POT_C, DS_C = (128, 128), (286, 128)
    for k, dst in enumerate(((POT_C[0] - 16, POT_C[1]), (POT_C[0] + 16, POT_C[1]), (POT_C[0], POT_C[1] + 18))):
        ev.append(
            moving(
                g_structure(9, "potential"),
                SH0 - 0.2,
                SH0,
                END_ALL,
                END_ALL + 0.9,
                line_path((WAIT[0] + k * 20 - 10, WAIT[1]), dst),
                SH0,
                SH1,
            )
        )
    ev.append(moving(g_dataset(ds_after), SH0 - 0.2, SH0, END_ALL, END_ALL + 0.9, line_path(MERGE, DS_C), SH0, SH1))

    GL0, GL1 = SH1, END_ALL
    for cx, cy, rr in ((POT_C[0], POT_C[1] + 7, 32), (DS_C[0], DS_C[1] + 3, 28)):
        ev.append(
            f'  <circle cx="{cx}" cy="{cy}" r="{rr}" fill="none" stroke="var(--diag-accent-orange)" stroke-width="1.6">\n{breathe_tag(GL0,GL1,n=3,lo=0.18,hi=0.9)}\n  </circle>'
        )
    for cx, txt in ((POT_C[0], "POTENTIALS"), (DS_C[0], "DATASET")):
        ev.append(
            fade_group(
                f'    <text x="{cx}" y="{POT_C[1]-38}" text-anchor="middle" font-size="9" letter-spacing="0.07em" '
                f'font-family="Inter,sans-serif" font-weight="700" fill="var(--diag-primary)">FINAL {txt}</text>',
                GL0,
                GL0 + 0.4,
                END_ALL,
                END_ALL + 0.9,
            )
        )
    ev.append(celebrate(122, 620, SH1 - 0.45, scale=0.42, n=34))
    ev.append(celebrate(200, 610, SH1 - 0.20, scale=0.60, n=56))
    ev.append(celebrate(280, 624, SH1 + 0.20, scale=0.44, n=34))
    finale.append((SH1 + 0.3, END_ALL))
    return ev, END_ALL + 1.6


t = SETUP_END
ev, t = gen_loop(t, 6, 24, 30, False, sp=1.00)
out += ev
ev, t = gen_loop(t, 3, 30, 33, False, sp=0.74)
out += ev
ev, t = gen_loop(t, 0, 33, 33, True, sp=0.55)
out += ev
print(f"portrait story ends at t={t:.1f}s / CYCLE={CYCLE}s")

# ---------------------------------------------------------------- the two plots, shown only at the end
ERRS = [0.80, 0.45, 0.24]
ERR_TARGET = 0.34
NPTS = [24, 30, 33]
SPREAD = [46.0, 15.0, 3.4]
BOW = [28.0, 8.0, 0.0]
BACK = [0.16, 0.32, 1.0]


def parity_cloud(i, x0, y0, size, dot_r):
    dots, n, sp_i, bow = [], NPTS[i], SPREAD[i], BOW[i]
    for k in range(n):
        u = 0.05 + 0.90 * k / (n - 1)
        j = (math.sin((k + 1) * 17.13 + i * 41.7) * 43758.5453) % 1.0 - 0.5
        j2 = (math.sin((k + 1) * 9.71 + i * 13.3) * 24634.6345) % 1.0 - 0.5
        f = size / 108.0
        bx = min(max(x0 + size * u + j2 * sp_i * 0.4 * f, x0 + 2), x0 + size - 2)
        by = min(max(y0 + size * (1 - u) + (j * sp_i - bow * math.sin(math.pi * u)) * f, y0 + 2), y0 + size - 2)
        dots.append(f'    <circle cx="{bx:.1f}" cy="{by:.1f}" r="{dot_r}" fill="var(--diag-primary)"/>')
    return "\n".join(dots)


def axes(x0, y0, w, h, xlab, ylab, diag=False):
    o = [
        f'  <line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+h}" stroke="var(--diag-text-muted)" stroke-width="0.9" stroke-opacity="0.5"/>',
        f'  <line x1="{x0}" y1="{y0+h}" x2="{x0+w}" y2="{y0+h}" stroke="var(--diag-text-muted)" stroke-width="0.9" stroke-opacity="0.5"/>',
        f'  <text x="{x0-4}" y="{y0+7}" text-anchor="end" font-size="7" font-family="\'JetBrains Mono\',monospace" '
        f'fill="var(--diag-text-muted)">{ylab}</text>',
        f'  <text x="{x0+w}" y="{y0+h+11}" text-anchor="end" font-size="7" font-family="\'JetBrains Mono\',monospace" '
        f'fill="var(--diag-text-muted)">{xlab}</text>',
    ]
    if diag:
        o.append(
            f'  <line x1="{x0}" y1="{y0+h}" x2="{x0+w}" y2="{y0}" stroke="var(--diag-text-muted)" '
            f'stroke-width="0.9" stroke-dasharray="3 3" stroke-opacity="0.6"/>'
        )
    return "\n".join(o)


LX, LY, LW, LH = 40, 300, 134, 104
RX, RY, RS = 226, 300, 104
plots = [
    f'  <text x="{LX}" y="{LY-10}" font-size="8.5" letter-spacing="0.05em" font-family="Inter,sans-serif" '
    f'font-weight="700" fill="var(--diag-text-muted)">RMSE EVOLUTION</text>',
    axes(LX, LY, LW, LH, "iteration", "RMSE"),
]
ty = LY + LH - ERR_TARGET * LH
plots.append(
    f'  <line x1="{LX}" y1="{ty:.1f}" x2="{LX+LW}" y2="{ty:.1f}" stroke="var(--diag-accent-orange)" '
    f'stroke-width="1.1" stroke-dasharray="4 3" stroke-opacity="0.85"/>'
)
plots.append(
    f'  <text x="{LX+LW}" y="{ty-4:.1f}" text-anchor="end" font-size="7" '
    f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-accent-orange)">target</text>'
)
pts = [(LX + LW * (i + 1) / (len(ERRS) + 0.6), LY + LH - e * LH) for i, e in enumerate(ERRS)]
for i in range(1, len(pts)):
    plots.append(
        f'  <line x1="{pts[i-1][0]:.1f}" y1="{pts[i-1][1]:.1f}" x2="{pts[i][0]:.1f}" y2="{pts[i][1]:.1f}" '
        f'stroke="var(--diag-primary)" stroke-width="1.6"/>'
    )
for px, py in pts:
    plots.append(f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="3.6" fill="var(--diag-primary)"/>')
plots.append(
    f'  <text x="{RX}" y="{RY-10}" font-size="8.5" letter-spacing="0.05em" font-family="Inter,sans-serif" '
    f'font-weight="700" fill="var(--diag-text-muted)">PARITY</text>'
)
plots.append(axes(RX, RY, RS, RS, "DFT", "NNIP", diag=True))
for i in range(3):
    plots.append(f'  <g opacity="{BACK[i]}">\n{parity_cloud(i, RX, RY, RS, 2.4)}\n  </g>')
f0, f1 = finale[0]
out.append(fade_group("\n".join("  " + l for l in "\n".join(plots).split("\n")), f0, f0 + 0.8, f1, f1 + 0.9))


# ---------------------------------------------------------------- stages
def icon_augment(cx, cy):
    o = [f'<path d="{hexagon_path(cx,cy-2,5.5)}" fill="var(--diag-primary)"/>']
    for i in range(3):
        a = math.radians(90 + i * 120)
        sx, sy = cx + 13 * math.cos(a), (cy - 2) + 13 * math.sin(a)
        o.append(
            f'<line x1="{cx}" y1="{cy-2}" x2="{sx:.1f}" y2="{sy:.1f}" stroke="var(--diag-primary)" stroke-opacity="0.5" stroke-width="1.1"/>'
        )
        o.append(f'<path d="{hexagon_path(sx,sy,3.2)}" fill="var(--diag-primary)" fill-opacity="0.55"/>')
    return "\n".join(f"  {x}" for x in o)


def icon_label(cx, cy):
    o = [
        f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="none" stroke="var(--diag-primary)" stroke-width="1.2" stroke-opacity="{op}"/>'
        for rr, op in [(12, 0.35), (8, 0.55), (4.2, 0.8)]
    ]
    o.append(f'<circle cx="{cx}" cy="{cy}" r="1.8" fill="var(--diag-primary)"/>')
    return "\n".join(f"  {x}" for x in o)


TL1 = [(-11, -7), (-11, 7)]
TL2 = [(0, -10), (0, 0), (0, 10)]
TL3 = [(11, -7), (11, 7)]


def icon_train(cx, cy):
    o = [f'<circle cx="{cx}" cy="{cy}" r="15.5" fill="var(--diag-accent-orange)" fill-opacity="0.09"/>']
    for a, b in ((TL1, TL2), (TL2, TL3)):
        for p in a:
            for q in b:
                o.append(
                    f'<line x1="{cx+p[0]:.1f}" y1="{cy+p[1]:.1f}" x2="{cx+q[0]:.1f}" y2="{cy+q[1]:.1f}" stroke="var(--diag-accent-orange)" stroke-width="1.1" stroke-opacity="0.55"/>'
                )
    for p in TL1 + TL2 + TL3:
        o.append(
            f'<circle cx="{cx+p[0]:.1f}" cy="{cy+p[1]:.1f}" r="2.4" fill="var(--diag-accent-orange)" fill-opacity="0.75"/>'
        )
    return "\n".join(f"  {x}" for x in o)


MD_RESTS = [(-10, 2), (0, -2), (10, 3)]


def icon_explore(cx, cy):
    p = [(cx + dx, cy + dy) for dx, dy in MD_RESTS]
    return (
        f'  <path d="M {p[0][0]},{p[0][1]} Q {cx-3},{cy-9} {p[1][0]},{p[1][1]} T {p[2][0]},{p[2][1]}" '
        f'fill="none" stroke="var(--diag-accent-green)" stroke-width="1" stroke-opacity="0.35" stroke-dasharray="1 3"/>'
    )


def icon_evaluate(cx, cy):
    o = [
        f'<line x1="{cx-12}" y1="{cy+1}" x2="{cx+12}" y2="{cy+1}" stroke="var(--diag-text-muted)" stroke-width="1" stroke-dasharray="2 2"/>'
    ]
    for dx, dy in [(-8, 7), (-1, 9), (7, 6)]:
        o.append(f'<circle cx="{cx+dx}" cy="{cy+dy}" r="1.8" fill="var(--diag-text-muted)"/>')
    for dx, dy in [(-6, -7), (6, -5)]:
        o.append(f'<circle cx="{cx+dx}" cy="{cy+dy}" r="2.3" fill="var(--diag-accent-orange)"/>')
        o.append(
            f'<circle cx="{cx+dx}" cy="{cy+dy}" r="4.3" fill="none" stroke="var(--diag-accent-orange)" stroke-width="0.9"/>'
        )
    return "\n".join(f"  {x}" for x in o)


def stage(cy, title, icon_fn):
    return "\n".join(
        [
            f'  <circle cx="{COL}" cy="{cy}" r="{R}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.5" filter="url(#ssm)"/>',
            f'  <circle cx="{COL}" cy="{cy}" r="{R-5}" fill="var(--diag-bg-tinted)"/>',
            icon_fn(COL, cy),
            f'  <text x="{COL+R+18}" y="{cy+5}" font-size="13" font-family="Inter,sans-serif" font-weight="700" '
            f'fill="var(--diag-text)">{title}</text>',
        ]
    )


FADE = (fade_all[0], fade_all[0] + 1.4)
stages = [
    spotlight(stage(Y["augment"], "Augment", icon_augment), aug_win, fade_out=FADE),
    spotlight(stage(Y["label"], "Label", icon_label), label_win, fade_out=FADE),
    spotlight(stage(Y["train"], "Train", icon_train), train_win, fade_out=FADE),
    spotlight(stage(Y["explore"], "Explore", icon_explore), md_win, fade_out=FADE),
    spotlight(stage(Y["evaluate"], "Evaluate", icon_evaluate), eval_win, fade_out=FADE),
]


# ---------------------------------------------------------------- in-stage animations
def wander_path(cx, cy, seed):
    r = lambda i: math.sin(seed * 2.3 + i) * 0.5 + math.cos(seed * 1.7 + i * 1.3) * 0.5
    a, b = 10 + 2 * r(0), 7 + 2 * r(1)
    return (
        f"M {cx:.1f},{cy:.1f} C {cx+a*0.5:.1f},{cy-b*1.5:.1f} {cx+a*1.4:.1f},{cy-b*0.7:.1f} {cx+a:.1f},{cy+b*0.4:.1f} "
        f"C {cx+a*0.7:.1f},{cy+b*1.6:.1f} {cx-a*0.3:.1f},{cy+b*1.2:.1f} {cx-a*0.8:.1f},{cy+b*0.5:.1f} "
        f"C {cx-a*1.5:.1f},{cy-b*0.2:.1f} {cx-a*0.9:.1f},{cy-b*1.1:.1f} {cx:.1f},{cy:.1f} Z"
    )


def md_motion(path_d, windows, laps=3, shift=0.0):
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


def ellipse_path(cx, cy, rx, ry):
    return f"M {cx-rx:.1f},{cy:.1f} A {rx},{ry} 0 1 0 {cx+rx:.1f},{cy:.1f} A {rx},{ry} 0 1 0 {cx-rx:.1f},{cy:.1f} Z"


live = []
md_atoms = []
for i, ((dx, dy), op) in enumerate(zip(MD_RESTS, (0.35, 0.68, 1.0), strict=False)):
    md_atoms.append(
        "  <g>\n"
        + md_motion(wander_path(COL + dx, Y["explore"] + dy, seed=i * 1.7 + 0.4), md_win, laps=3, shift=i * 0.2)
        + f'\n    <circle r="3.3" fill="var(--diag-accent-green)" fill-opacity="{op}"/>\n  </g>'
    )
live.append(spotlight("\n".join(md_atoms), md_win, fade_out=FADE))

AUG_SEG = (aug_win[0][1] - aug_win[0][0]) / 4
for i in range(6):
    ph = i * 0.16
    a = math.radians(90 + i * 60)
    sx, sy = COL + 22 * math.cos(a), (Y["augment"] - 2) + 22 * math.sin(a)
    live.append(
        '  <g opacity="0">\n'
        + md_motion(line_path((COL, Y["augment"] - 2), (sx, sy)), aug_win, laps=4, shift=ph * AUG_SEG)
        + "\n"
        + f'    <path d="{hexagon_path(0,0,4.4)}" fill="var(--diag-bg)" stroke="var(--diag-primary)" stroke-width="1.3"/>\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.18, 1.0), (0.78, 1.0), (1.0, 0.0)], aug_win, laps=4, phase=ph)
        + "\n  </g>"
    )

for oi, (rx, ry, rot, laps) in enumerate([(13, 5.6, -22, 4), (9.6, 4.1, 52, 3)]):
    live.append(
        f'  <g transform="rotate({rot},{COL},{Y["label"]})">\n'
        f'    <ellipse cx="{COL}" cy="{Y["label"]}" rx="{rx}" ry="{ry}" fill="none" stroke="var(--diag-primary)" '
        f'stroke-width="0.8" stroke-dasharray="2 3" opacity="0">\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.15, 0.5), (0.85, 0.5), (1.0, 0.0)], dft_win, laps=1, indent=6)
        + "\n    </ellipse>\n"
        '    <g opacity="0">\n'
        + md_motion(ellipse_path(COL, Y["label"], rx, ry), dft_win, laps=laps, shift=oi * 0.12).replace(
            "    <", "      <"
        )
        + "\n"
        '      <circle r="2.3" fill="var(--diag-primary)"/>\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.12, 1.0), (0.88, 1.0), (1.0, 0.0)], dft_win, laps=1, indent=6)
        + "\n    </g>\n  </g>"
    )

for gi, (a, b) in enumerate(((TL1, TL2), (TL2, TL3))):
    edges = "".join(
        f'<line x1="{COL+p[0]:.1f}" y1="{Y["train"]+p[1]:.1f}" x2="{COL+q[0]:.1f}" y2="{Y["train"]+q[1]:.1f}" '
        f'stroke="var(--diag-accent-orange)" stroke-width="1.3"/>'
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
for li, layer in enumerate((TL1, TL2, TL3)):
    nodes = "".join(
        f'<circle cx="{COL+p[0]:.1f}" cy="{Y["train"]+p[1]:.1f}" r="2.7" fill="var(--diag-accent-orange)"/>'
        for p in layer
    )
    live.append(
        f'  <g opacity="0">\n    {nodes}\n'
        + windowed("opacity", 0, [(0.0, 0.0), (0.12, 1.0), (0.5, 0.0), (1.0, 0.0)], train_win, laps=4, phase=li * 0.16)
        + "\n  </g>"
    )

# the shelf, always on screen once it exists
bounds = [DS_BORN] + [m[0] for m in merges] + [podium[0]]
counts = [24] + [m[1] for m in merges]
for i, c in enumerate(counts):
    a, b = bounds[i], bounds[i + 1]
    out.append(moving(g_dataset(c, sub="labelled"), a, a + 0.25, b, b + 0.12, at=MERGE, base=0.72))
out.append(
    fade_group(
        f'    <text x="{MERGE[0]-30}" y="{MERGE[1]+22}" text-anchor="end" font-size="7" letter-spacing="0.04em" '
        f'font-family="\'JetBrains Mono\',monospace" fill="var(--diag-text-muted)">labelled dataset</text>',
        DS_BORN,
        DS_BORN + 0.3,
        podium[0],
        podium[0] + 0.2,
    )
)

defs = (
    '  <defs>\n    <filter id="ssm" x="-60%" y="-60%" width="220%" height="220%">'
    '<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="var(--diag-primary-dark)" flood-opacity="0.22"/></filter>\n  </defs>'
)
bg, row, y = ["  <g>"], 0, 10
while y < H:
    x = 10 + (13 if row % 2 else 0)
    while x < W:
        bg.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="0.9" fill="var(--diag-primary)" opacity="0.05"/>')
        x += 26
    y += 22.5
    row += 1
bg.append("  </g>")

open("/tmp/mobile_full.txt", "w").write("\n".join([defs] + bg + out + stages + live))
print("viewBox:", W, H)
