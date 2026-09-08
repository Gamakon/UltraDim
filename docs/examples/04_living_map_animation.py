#!/usr/bin/env python3
"""A living map, animated: rows arrive in time order, the map grows with them.

This is the method behind the foreign-exchange animation in the README, on a
synthetic stream so that it runs anywhere in about a minute. One family, one
base map fitted on the first rows, then every later batch folded into the
existing map with IncrementalFitUltradimV23Umap. When the rows folded in
since the last full fit exceed one fifth of that fit, the map is refitted
over everything so far and the new layout is aligned to the previous frame,
so the animation does not jump.

Frames are rendered from the retained maps after the folds, chained into one
frame of reference by a rigid transform on the rows two consecutive maps
share (rotation and translation; the alignment is for the animation only, the
engine's stored positions are untouched). The output is a GIF written to
disk, plus an MP4 if ffmpeg is installed. Nothing is shown on screen.

Run:  python3.12 04_living_map_animation.py
Needs: the ultradim wheel (numpy comes with it), matplotlib, pillow.
"""
import json
import math
import os
import shutil
import subprocess
import tempfile

import numpy as np
import ultradim

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

# ---- the stream ------------------------------------------------------------
N_DAYS = 1_500        # one row per "day"
BASE = 600            # rows in the first map
FOLD = 30             # rows folded in per step
SOURCE_DIM = 20_000   # width of the sparse space
NNZ = 32              # non-zeros per row
TOPICS = 20           # planted structure: each row draws most of its
                      # non-zeros from its topic's pool of 36 dimensions
FPS = 6
OUT = "living_map.gif"


def planted_stream(seed=7):
    """Rows whose topic mixture drifts over time: early days favour the low
    topics, late days the high ones, so the map's populations shift."""
    rng = np.random.default_rng(seed)
    pools = [rng.choice(SOURCE_DIM, 36, replace=False) for _ in range(TOPICS)]
    rows, topics = [], []
    for day in range(N_DAYS):
        # every topic is always present; on top of that a drifting preference
        # moves through the topics over time, so the populations shift
        if rng.random() < 0.6:
            t = int(rng.integers(TOPICS))
        else:
            centre = TOPICS * day / N_DAYS
            t = int(np.clip(round(rng.normal(centre, 3.0)), 0, TOPICS - 1))
        own = rng.choice(pools[t], 30, replace=False)
        noise = rng.choice(SOURCE_DIM, NNZ - 30, replace=False)
        idx = np.unique(np.concatenate([own, noise]))
        val = rng.random(len(idx)).astype(np.float32) + 0.2
        val /= np.linalg.norm(val)
        rows.append({"indices": [int(i) for i in idx], "values": [float(v) for v in val]})
        topics.append(t)
    return rows, np.array(topics)


# ---- the engine calls ------------------------------------------------------
def rpc(db, rpc_name, **fields):
    out = json.loads(db.call_json(rpc_name, json.dumps(fields)))
    if isinstance(out, dict) and out.get("error_message"):
        raise RuntimeError(f"{rpc_name}: {out['error_message']}")
    return out


def fetch_layout(db, fam, umap_id):
    """Every row's 2-D position on one map, as {row_id: (x, y)}."""
    pos, off = {}, 0
    while True:
        page = rpc(db, "GetUltradimV23UmapEmbedding", name=fam, umap_id=umap_id,
                   limit=8192, offset_ordinal=off)
        emb, nc = page["embeddings"], page["n_components"]
        if not emb:
            break
        for i in range(0, len(emb), nc):
            pos[off + i // nc] = (emb[i], emb[i + 1])
        nxt = page.get("next_offset_ordinal")
        if nxt is None or nxt <= off:
            break
        off = nxt
    return pos


# ---- the picture -----------------------------------------------------------
def align(prev, cur):
    """Rigid transform (rotation and translation, no scaling, no reflection)
    that best maps the rows `cur` shares with `prev` onto their `prev`
    positions. For the animation only, so consecutive frames share one frame of
    reference; the engine's stored positions are untouched."""
    keys = [k for k in cur if k in prev]
    if len(keys) < 8:
        return cur
    a = np.array([prev[k] for k in keys]); b = np.array([cur[k] for k in keys])
    am, bm = a.mean(0), b.mean(0)
    u, _, vt = np.linalg.svd((b - bm).T @ (a - am))
    d = np.sign(np.linalg.det(u @ vt)) or 1.0
    r = u @ np.diag([1.0, d]) @ vt
    return {k: tuple((np.array(v) - bm) @ r + am) for k, v in cur.items()}


def render(layout, upto, topics, title, new_ids, path, lims):
    ids = sorted(i for i in layout if i < upto)
    xs = [layout[i][0] for i in ids]; ys = [layout[i][1] for i in ids]
    pad = 0.08
    box = (min(xs), max(xs), min(ys), max(ys))
    if not lims:
        lims.extend(box)
    else:
        lims[0] = min(lims[0], box[0]); lims[1] = max(lims[1], box[1])
        lims[2] = min(lims[2], box[2]); lims[3] = max(lims[3], box[3])
    sx = (lims[1] - lims[0]) or 1.0; sy = (lims[3] - lims[2]) or 1.0
    cmap = plt.get_cmap("viridis")
    fig, ax = plt.subplots(figsize=(6, 6), dpi=90)
    ax.scatter(xs, ys, s=5, c=[cmap(topics[i] / (TOPICS - 1)) for i in ids], linewidths=0, alpha=0.8)
    nw = [i for i in new_ids if i in layout]
    if nw:
        ax.scatter([layout[i][0] for i in nw], [layout[i][1] for i in nw], s=30,
                   c=[cmap(topics[i] / (TOPICS - 1)) for i in nw], edgecolors="black", linewidths=0.6)
    ax.set_xlim(lims[0] - pad * sx, lims[1] + pad * sx)
    ax.set_ylim(lims[2] - pad * sy, lims[3] + pad * sy)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=9)
    fig.text(0.02, 0.02, f"day {upto:4d}", fontsize=14, family="monospace", fontweight="bold")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path); plt.close(fig)


def main():
    rows, topics = planted_stream()
    work = tempfile.mkdtemp(prefix="ultradim_living_map_")
    frames_dir = os.path.join(work, "frames"); os.makedirs(frames_dir)
    db = ultradim.UltraDim(os.path.join(work, "db"))
    fam = "stream"

    # 1. One family, every row inserted, indexed once.
    max_nnz = math.ceil(1.10 * max(len(r["indices"]) for r in rows))
    rpc(db, "CreateUltradimV23Collection", name=fam, source_dim=SOURCE_DIM,
        projection_dim=128, seeds=[11, 22, 33, 44], sparse_substrate=True,
        max_nnz_per_row=max_nnz)
    for start in range(0, N_DAYS, 1000):
        batch = rows[start:start + 1000]
        rpc(db, "UpsertUltradimV23Points", name=fam,
            batch={"row_ids": list(range(start, start + len(batch))), "sparse_vectors": batch})
    rpc(db, "BuildUltradimV23TrellisIndex", name=fam)
    print(f"family: {N_DAYS} rows, indexed")

    # 2. The base map on the first BASE rows.
    graph = rpc(db, "BuildUltradimV23KnnGraph", name=fam, k=12, oracle_sample=200, top_m=1600,
                row_ids=list(range(BASE)))
    fit = rpc(db, "FitUltradimV23Umap", name=fam, graph_id=graph["graph_id"],
              n_components=2, n_neighbors=12, deterministic=True, umap_seed=174)
    uid = fit["umap_id"]
    print(f"base map on {BASE} rows: graph recall {graph.get('measured_recall_at_k'):.4f}")
    lineage = [(BASE, uid, "base")]

    # 3. Fold the rest in, batch by batch. The tolerance: when the rows folded
    #    in since the last full fit exceed one fifth of that fit, refit over
    #    everything so far. (The fold's response reports each batch's own share
    #    of the corpus; the running total is kept here.)
    fitted, folded_since = BASE, 0
    for f0 in range(BASE, N_DAYS, FOLD):
        f1 = min(f0 + FOLD, N_DAYS); ids = list(range(f0, f1))
        inc = rpc(db, "IncrementalFitUltradimV23Umap", name=fam, parent_umap_id=uid,
                  sparse_queries=[rows[i] for i in ids], batch_row_ids=ids, persist=True,
                  top_m=1600)
        uid = inc["child_umap_id"]
        lineage.append((f1, uid, "fold"))
        folded_since += len(ids)
        if folded_since > 0.2 * fitted:
            g2 = rpc(db, "BuildUltradimV23KnnGraph", name=fam, k=12, oracle_sample=200,
                     top_m=1600, row_ids=list(range(f1)))
            u2 = rpc(db, "FitUltradimV23Umap", name=fam, graph_id=g2["graph_id"],
                     n_components=2, n_neighbors=12, deterministic=True, umap_seed=174)
            uid = u2["umap_id"]
            lineage.append((f1, uid, "refit"))
            print(f"day {f1}: {folded_since} rows folded since a fit of {fitted}, refitted over {f1} rows")
            fitted, folded_since = f1, 0
    folds = sum(1 for _, _, k in lineage if k == "fold")
    refits = sum(1 for _, _, k in lineage if k == "refit")
    print(f"lineage: {folds} folds, {refits} refits, {len(lineage)} maps retained")

    # 4. Render every retained map, each aligned to the frame before it.
    lims, frame_paths = [], []
    reference = prev = fetch_layout(db, fam, lineage[0][1])
    render(reference, BASE, topics, "base map", [], os.path.join(frames_dir, "f0000.png"), lims)
    frame_paths.append(os.path.join(frames_dir, "f0000.png"))
    for n, (upto, mid, kind) in enumerate(lineage[1:], start=1):
        raw = fetch_layout(db, fam, mid)
        if kind == "refit":
            reference = align(prev, raw); layout = reference
            title = f"refit over {upto} rows, aligned to the previous frame"
            new = []
        else:
            layout = align(reference, raw)
            title = "fold: the new rows placed, the rest held"
            new = range(upto - FOLD, upto)
        path = os.path.join(frames_dir, f"f{n:04d}.png")
        render(layout, upto, topics, title, new, path, lims)
        frame_paths.append(path); prev = layout

    # 5. Write the animation.
    frames = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in frame_paths]
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
    print(f"wrote {OUT}: {len(frames)} frames, {os.path.getsize(OUT) // 1024} KB")
    if shutil.which("ffmpeg"):
        mp4 = OUT.replace(".gif", ".mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                        "-i", os.path.join(frames_dir, "f%04d.png"), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", mp4],
                       check=True)
        print(f"wrote {mp4}")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
