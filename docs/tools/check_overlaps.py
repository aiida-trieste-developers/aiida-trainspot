"""Collision check done on the generated SVG itself, not on my mental model of it.

For every group it works out: where it actually sits (a static translate, or the start/end of its
motion path), how big it really is (from its own child shapes and text), and when it is on screen
(from its opacity keyframes). Then it reports pairs that share space *and* time.

The earlier hand-written check missed the whole class of bug the user kept seeing, because it only
looked at fixed decorations and never at where moving tokens come to rest.
"""

import re
import sys
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
NUM = r"-?\d+(?:\.\d+)?"


def text_box(x, y, s, size, anchor):
    # rough but consistent: mono ~0.60em per char, Inter bold ~0.56em
    w = len(s) * size * 0.60
    if anchor == "middle":
        x0, x1 = x - w / 2, x + w / 2
    elif anchor == "end":
        x0, x1 = x - w, x
    else:
        x0, x1 = x, x + w
    return (x0, y - size * 0.82, x1, y + size * 0.28)


def local_extent(g):
    """Bounding box of a group's own drawing, in its local coordinates."""
    xs, ys = [], []
    for el in g.iter():
        t = el.tag
        if t == NS + "path" and el.get("d"):
            nums = [float(v) for v in re.findall(NUM, el.get("d"))]
            xs += nums[0::2]
            ys += nums[1::2]
        elif t == NS + "circle":
            cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
            r = float(el.get("r", 0))
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
        elif t == NS + "text":
            size = float(el.get("font-size", 10))
            tx, ty = float(el.get("x", 0)), float(el.get("y", 0))
            b = text_box(tx, ty, "".join(el.itertext()).strip(), size, el.get("text-anchor", "start"))
            xs += [b[0], b[2]]
            ys += [b[1], b[3]]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def intervals(kt, vs):
    """Every separate on-screen stretch, not one span from first to last -- elements that repeat
    once per iteration are visible in bursts, and merging them invents overlaps that never happen.
    """
    out, start = [], None
    for i, (t, v) in enumerate(zip(kt, vs, strict=False)):
        if v > 0.05 and start is None:
            start = kt[i - 1] if i else t
        elif v <= 0.05 and start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, kt[-1]))
    return out


def window(g):
    for el in g.iter(NS + "animate"):
        if el.get("attributeName") != "opacity":
            continue
        kt = [float(v) for v in el.get("keyTimes").split(";")]
        vs = [float(v) for v in el.get("values").split(";")]
        iv = intervals(kt, vs)
        if iv:
            return iv
    return [(0.0, 1.0)]


def path_points(d):
    nums = [float(v) for v in re.findall(NUM, d)]
    pts = list(zip(nums[0::2], nums[1::2], strict=False))
    return pts


def main(path, vb_w, vb_h):
    raw = open(path).read()
    root = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb_w} {vb_h}">{raw}</svg>')

    # document order == paint order: something drawn earlier passes *behind* what follows it
    order = {id(el): i for i, el in enumerate(root.iter())}
    items = []  # (name, x0,y0,x1,y1, [intervals], kind, z)

    def add(name, box, win, kind, z=0, has_text=False):
        if box:
            items.append((name, box[0], box[1], box[2], box[3], win, kind, z, has_text))

    moved_own_texts = set()
    idx = 0
    for g in root.iter(NS + "g"):
        idx += 1
        mot = g.find(NS + "animateMotion")
        tr = g.get("transform", "")
        ext = local_extent(g)
        if ext is None:
            continue
        win = window(g)

        # A group can also be moved by animateTransform. Checking only its authored coordinates
        # misses wherever it ends up -- which is exactly where the closing tableau assembles.
        xf = [a for a in g if a.tag == NS + "animateTransform"]
        if xf:
            tx = ty = 0.0
            sc = 1.0
            for a in xf:
                vals = a.get("values").split(";")
                last = vals[len(vals) // 2].strip()  # the held mid-animation state
                nums = [float(v) for v in re.findall(NUM, last)]
                if a.get("type") == "translate" and nums:
                    tx, ty = (nums + [0.0])[:2]
                elif a.get("type") == "scale" and nums:
                    sc = nums[0]
                kt = [float(v) for v in a.get("keyTimes").split(";")]
                moved = [(kt[i], kt[i + 1]) for i in range(len(kt) - 1)]
            box = (ext[0] * sc + tx, ext[1] * sc + ty, ext[2] * sc + tx, ext[3] * sc + ty)
            mid = [(kt[2], kt[3])] if len(kt) > 3 else win
            add(f"moved#{idx}", box, mid, "text", order[id(g)])  # treated as furniture: it must not land on anything
            moved_own_texts.update(id(t) for t in g.iter(NS + "text"))
        if mot is not None and mot.get("path"):
            pts = path_points(mot.get("path"))
            if not pts:
                continue
            # the atoms, electrons and budding variants live inside their badge on purpose;
            # they are the only motions with more than one window, so they are easy to tell apart
            if len(mot.get("keyTimes", "").split(";")) > 4:
                continue
            # a token lingers at the end of its journey; that is where a clash is persistent
            for label, (px, py) in (("start", pts[0]), ("end", pts[-1])):
                box = (ext[0] + px, ext[1] + py, ext[2] + px, ext[3] + py)
                add(
                    f"token#{idx}:{label}",
                    box,
                    win,
                    "token",
                    order[id(g)],
                    has_text=g.find(NS + "text") is not None or any(True for _ in g.iter(NS + "text")),
                )
        elif tr.startswith("translate"):
            px, py = (float(v) for v in re.findall(NUM, tr)[:2])
            box = (ext[0] + px, ext[1] + py, ext[2] + px, ext[3] + py)
            add(f"parked#{idx}", box, win, "token", order[id(g)], has_text=any(True for _ in g.iter(NS + "text")))

    # texts that ride inside a token were already counted with it, in the token's own coordinates
    parent = {c: p for p in root.iter() for c in p}
    token_texts = set()
    for g in root.iter(NS + "g"):
        if g.find(NS + "animateMotion") is not None or g.get("transform", "").startswith("translate"):
            token_texts |= {id(t) for t in g.iter(NS + "text")}

    def inherited_window(el):
        """A caption inside a fade group carries no animation of its own: the window is the group's."""
        node = el
        while node is not None:
            for a in list(node):
                if a.tag == NS + "animate" and a.get("attributeName") == "opacity":
                    kt = [float(v) for v in a.get("keyTimes").split(";")]
                    vs = [float(v) for v in a.get("values").split(";")]
                    iv = intervals(kt, vs)
                    if iv:
                        return iv
            node = parent.get(node)
        return [(0.0, 1.0)]

    # the stage discs are obstacles too: a caption that slides under one is just as unreadable
    for c in root.iter(NS + "circle"):
        if id(c) in {
            id(x)
            for g in root.iter(NS + "g")
            if g.find(NS + "animateMotion") is not None
            for x in g.iter(NS + "circle")
        }:
            continue
        try:
            r = float(c.get("r", 0))
        except ValueError:
            continue
        if r < 30 or c.get("fill", "none") == "none":
            continue
        cx, cy = float(c.get("cx", 0)), float(c.get("cy", 0))
        add(
            f"disc@{cx:.0f},{cy:.0f},r{r:.0f}",
            (cx - r, cy - r, cx + r, cy + r),
            inherited_window(c),
            "text",
            order[id(c)],
        )

    for t in root.iter(NS + "text"):
        if id(t) in token_texts or id(t) in moved_own_texts:
            continue
        size = float(t.get("font-size", 10))
        content = "".join(t.itertext()).strip()
        if not content:
            continue
        box = text_box(float(t.get("x", 0)), float(t.get("y", 0)), content, size, t.get("text-anchor", "start"))
        parent_win = inherited_window(t)
        add(
            f"text:'{content[:26]}'@{float(t.get('x',0)):.0f},{float(t.get('y',0)):.0f}",
            box,
            parent_win,
            "text",
            order[id(t)],
        )

    def overlap(a, b):
        return not (a[3] <= b[1] or b[3] <= a[1] or a[4] <= b[2] or b[4] <= a[2])

    def time_overlap(a, b):
        for s0, s1 in a[5]:
            for u0, u1 in b[5]:
                if not (s1 <= u0 or u1 <= s0):
                    return True
        return False

    print(f"{len(items)} positioned items extracted from the generated SVG")
    hits = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            if a[6] == "token" and b[6] == "token":
                continue  # tokens meeting tokens is the story, not a bug
            if a[6] == "text" and b[6] == "text" and a[0] == b[0]:
                continue  # the same caption redrawn each iteration
            if not (overlap(a, b) and time_overlap(a, b)):
                continue
            # passing behind is only harmless for something with nothing to read on it:
            # a token carrying its own count disappears under the disc, which is just as broken
            tok, txt = (a, b) if a[6] == "token" else (b, a)
            if tok[6] == "token" and txt[6] == "text" and tok[7] < txt[7] and not tok[8]:
                continue
            if a[6] == "text" and b[6] == "text" and a[0].startswith("disc") and b[0].startswith("disc"):
                continue
            hits.append((a[0], b[0]))
    seen = set()
    for a, b in hits:
        k = tuple(sorted((a.split("#")[0] + a[-4:], b)))
        if k in seen:
            continue
        seen.add(k)
        print("  CLASH:", a, "<->", b)
    print("total token/text clashes sharing space and time:", len(hits))
    # anything drawn outside the canvas
    off = [it for it in items if it[1] < -8 or it[2] < -8 or it[3] > vb_w + 8 or it[4] > vb_h + 8]
    print("items outside the canvas:", len(off))
    for it in off[:8]:
        print("   OFF:", it[0], [round(v) for v in it[1:5]])


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]))
