#!/usr/bin/env python3
"""Render the FULL 500k chemotype tree as a standalone SVG sunburst — same
geometry as sunburst.html (d3.partition: concentric rings = depth, arc span =
leaf mass) but emitted as a pure .svg (no browser, no D3 runtime).

Colour ramp runs BLUE -> GREEN by log10 cohesion lift (looser -> tighter).
Red is deliberately avoided so the figure never reads as "problems".

Run: python3 BloomMap/galaxy/build_sunburst_svg.py
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
NODES = os.path.join(HERE, "..", "..", "tmp", "chembl_pipeline",
                     "chembl500k_30m_hseg.nodes.jsonl")
OUT = os.path.join(HERE, "..", "posters", "chembl_500k_sunburst.svg")

W = 1000          # full canvas (px)
R = W / 2 - 20    # outer radius of the sunburst
PAD = 0.0008      # angular pad between siblings (radians), matches D3 padAngle


def lerp(a, b, t):
    return a + (b - a) * t


def blue_green(t):
    """t in [0,1] -> hex colour. Deep blue (loose) -> bright green (tight),
    passing through teal. No red channel of note, so nothing reads as alarm."""
    t = max(0.0, min(1.0, t))
    # control stops: deep navy-blue, mid teal, bright green
    stops = [
        (0.00, (12, 32, 96)),     # deep blue  (#0c2060)
        (0.45, (20, 120, 150)),   # teal       (#147896)
        (0.75, (30, 170, 120)),   # sea-green  (#1eaa78)
        (1.00, (120, 220, 80)),   # bright green(#78dc50)
    ]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            r = round(lerp(c0[0], c1[0], f))
            g = round(lerp(c0[1], c1[1], f))
            b = round(lerp(c0[2], c1[2], f))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#78dc50"


def arc_path(cx, cy, x0, x1, r0, r1):
    """SVG path for an annular sector spanning angles [x0,x1] (rad, 0 = up,
    clockwise, matching D3 partition) and radii [r0,r1]."""
    # D3 uses angle measured clockwise from the positive y-axis (12 o'clock).
    def pt(angle, r):
        return (cx + r * math.sin(angle), cy - r * math.cos(angle))
    large = 1 if (x1 - x0) > math.pi else 0
    p0o = pt(x0, r1)
    p1o = pt(x1, r1)
    p1i = pt(x1, r0)
    p0i = pt(x0, r0)
    if r0 <= 0.0:
        # wedge from centre
        return (f"M{p0o[0]:.2f},{p0o[1]:.2f}"
                f"A{r1:.2f},{r1:.2f} 0 {large} 1 {p1o[0]:.2f},{p1o[1]:.2f}"
                f"L{cx:.2f},{cy:.2f}Z")
    return (f"M{p0o[0]:.2f},{p0o[1]:.2f}"
            f"A{r1:.2f},{r1:.2f} 0 {large} 1 {p1o[0]:.2f},{p1o[1]:.2f}"
            f"L{p1i[0]:.2f},{p1i[1]:.2f}"
            f"A{r0:.2f},{r0:.2f} 0 {large} 0 {p0i[0]:.2f},{p0i[1]:.2f}Z")


def main():
    nodes = [json.loads(l) for l in open(NODES) if l.strip()]
    by_addr = {n["address"]: {
        "address": n["address"],
        "level": n["level"],
        "size": n["size"],
        "is_leaf": n["is_leaf"],
        "lift": n.get("log10_lift") or 0.0,
        "children": [],
        "value": 0.0,
    } for n in nodes}
    root = None
    for n in nodes:
        node = by_addr[n["address"]]
        p = n.get("parent")
        if p is None:
            root = node
        elif p in by_addr:
            by_addr[p]["children"].append(node)

    max_level = max(n["level"] for n in nodes)
    lifts = [n.get("log10_lift") or 0.0 for n in nodes]
    lmin = max(1.0, min(lifts))
    lmax = max(lifts)
    log_lmin, log_lmax = math.log10(lmin), math.log10(lmax)

    # d3.hierarchy.sum: leaves carry size, internal value = sum of children.
    def compute_value(node):
        if not node["children"]:
            node["value"] = float(node["size"]) if node["is_leaf"] else 0.0
        else:
            node["value"] = sum(compute_value(c) for c in node["children"])
        return node["value"]
    compute_value(root)

    # sort children by descending value (matches .sort((a,b)=>b.value-a.value))
    def sort_children(node):
        node["children"].sort(key=lambda c: -c["value"])
        for c in node["children"]:
            sort_children(c)
    sort_children(root)

    # d3.partition geometry: angular extent proportional to value; radial band
    # proportional to depth. Total depth bands = max_level + 1 (root ring included).
    band = R / (max_level + 1)
    arcs = []

    def layout(node, x0, x1, depth):
        r0 = depth * band
        r1 = (depth + 1) * band
        if depth > 0:  # root (depth 0) drawn as a centre dot, not an arc
            arcs.append((node, x0, x1, r0, r1))
        total = node["value"]
        if total <= 0 or not node["children"]:
            return
        cur = x0
        for c in node["children"]:
            frac = c["value"] / total
            cx1 = cur + frac * (x1 - x0)
            layout(c, cur, cx1, depth + 1)
            cur = cx1

    layout(root, 0.0, 2 * math.pi, 0)

    cx = cy = W / 2
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{W}" '
        f'viewBox="0 0 {W} {W}">')
    parts.append(f'<rect width="{W}" height="{W}" fill="#0d0f14"/>')
    for node, x0, x1, r0, r1 in arcs:
        # apply a small angular pad like D3 padAngle
        a0 = x0 + PAD / 2
        a1 = max(a0, x1 - PAD / 2)
        t = (math.log10(max(node["lift"], lmin)) - log_lmin) / (log_lmax - log_lmin) \
            if log_lmax > log_lmin else 0.5
        fill = blue_green(t)
        d = arc_path(cx, cy, a0, a1, r0, r1)
        parts.append(f'<path d="{d}" fill="{fill}" stroke="#0d0f14" '
                     f'stroke-width="0.4"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="#cfd6e4"/>')
    parts.append('</svg>')

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(parts))
    print(f"wrote {OUT} ({os.path.getsize(OUT)//1024} KB)")
    print(f"  {len(nodes)} nodes, {sum(1 for n in nodes if n['is_leaf'])} leaves, "
          f"{max_level+1} levels, {len(arcs)} arcs drawn")
    print(f"  lift {lmin:.0f} .. {lmax:.0f}  ->  blue..green")


if __name__ == "__main__":
    main()
