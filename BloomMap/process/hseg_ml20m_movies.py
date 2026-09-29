#!/usr/bin/env python3
"""Hierarchical (divisive) segmentation over the SPARSE ml20m_movies family.

Direct adaptation of tmp/chembl_pipeline/hseg_chembl.py (the proven C=2 split /
per-child C=1 cohesion / strict null-lift acceptance tree) to the MovieLens-20M
item-side family `ml20m_movies` (26,744 movies x 138,493 users, resident values =
L2-row-normalised rating DIRECTION, D_proj=2048, formula projection). The null is
sparse + nnz-matched to the corpus, same as the other corpus runs.

Substrate facts (carried over unchanged from ChEMBL):
* sparse row_ids are 0-based contiguous (movie ordinal == row ordinal here);
* C=1 -> max_cycles=1 (one centroid, assignments cannot change);
* C=2 split -> max_cycles=32;
* the null family is its OWN formula collection (rademacher_hash_v1 / formula,
  D_proj=2048 matching the SUT) so its projection matches the system under test.

Knob difference vs ChEMBL: 26,744 rows (vs 100k) -> MIN_POP scaled to keep the
same ~0.9% relative granularity so leaf count lands in the 40-80 target band.
nnz-per-row is highly skewed for movies (users-per-movie p50=18, max=67,310) so
the null pool is drawn from the ACTUAL corpus nnz distribution, never a constant.

Run (server up, ml20m_movies ingested):
  python3 tmp/ml20m_bloommap/hseg_ml20m_movies.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ultradim-bindings"))
from ultradimdb import UltraDimClient  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# All knobs env-overridable. Unset == the ml20m_movies defaults below.
# Corpus = the RAW-ratings movies CSR sidecar; nnz support is identical to the
# resident L2-normalised direction rows (normalisation does not change support),
# so its nnz-per-row distribution is the correct null match.
CORPUS = Path(os.environ.get(
    "HSEG_CORPUS", str(REPO / "data" / "movielens" / "ml20m_ratings_movies.npz")))

FAMILY = os.environ.get("HSEG_FAMILY", "ml20m_movies")
D_RAW = int(os.environ.get("HSEG_D_RAW", 138_493))
D_PROJ = int(os.environ.get("HSEG_D_PROJ", 2048))
SEED = int(os.environ.get("HSEG_SEED", 12345))
MAX_DEPTH = int(os.environ.get("HSEG_MAX_DEPTH", 7))
# ~0.9% of 26,744 -> broad film families, targets 40-80 leaves.
MIN_POP = int(os.environ.get("HSEG_MIN_POP", 240))
MIN_FRAC = float(os.environ.get("HSEG_MIN_FRAC", 0.10))
TAU_K = float(os.environ.get("HSEG_TAU_K", 2.0))
MARGIN_K = float(os.environ.get("HSEG_MARGIN_K", 1.0))
C1_CYCLES = int(os.environ.get("HSEG_C1_CYCLES", 1))
C2_CYCLES = int(os.environ.get("HSEG_C2_CYCLES", 32))
OUT_BASE = os.environ.get(
    "HSEG_OUT_BASE", str(REPO / "tmp" / "ml20m_bloommap" / "ml20m_movies_hseg"))

# The null build reuses only 2 seeds for speed (system-under-test uses 4); the
# null is a projection-space cohesion baseline, not a retrieval index, so a
# 2-seed rademacher formula collection at the same D_proj is sufficient (same as
# the ChEMBL run's build_seeds=(42, 137)).
NULL_D_PROJ = int(os.environ.get("HSEG_NULL_D_PROJ", D_PROJ))


class SparseFittedNull:
    """nnz-matched sparse random-direction null, power-of-two size buckets."""

    def __init__(self, client, nnz_pool, max_n, n_draws=5, build_seeds=(42, 137)):
        self.client = client
        self.n_draws = n_draws
        self._cache = {}
        largest_bucket = 1 << (max_n - 1).bit_length()
        self.cap = min(largest_bucket * 2, largest_bucket + 8192)
        self.name = f"ml20m_movies_hseg_null_{int(time.time())}"
        rng = np.random.default_rng(20260712)
        nnz_draw = rng.choice(nnz_pool, size=self.cap, replace=True)
        cap_nnz = int(math.ceil(int(nnz_draw.max()) * 1.10))
        print(f"[null] building SPARSE nnz-matched null '{self.name}' "
              f"N={self.cap} D={D_RAW} D_proj={NULL_D_PROJ} "
              f"nnz p50={int(np.percentile(nnz_draw, 50))} "
              f"max={int(nnz_draw.max())} cap_nnz={cap_nnz} ...", flush=True)
        r = client.create_ultradim_v23_collection(
            name=self.name, source_dim=D_RAW, projection_dim=NULL_D_PROJ,
            seeds=list(build_seeds), sparse_substrate=True,
            max_nnz_per_row=cap_nnz, matrix_type="rademacher_hash_v1",
            projection_mode="formula")
        if not r.get("success"):
            raise RuntimeError(f"null create failed: {r.get('error_message')}")
        t0 = time.time()
        BATCH = 500
        for s in range(0, self.cap, BATCH):
            e = min(s + BATCH, self.cap)
            svs = []
            for i in range(s, e):
                k = int(nnz_draw[i])
                idx = np.sort(rng.choice(D_RAW, size=k, replace=False))
                val = rng.standard_normal(k)
                val /= np.linalg.norm(val)
                svs.append((idx.astype(int).tolist(), val.astype(float).tolist()))
            ur = client.upsert_ultradim_v23_points(
                name=self.name, row_ids=list(range(s, e)), sparse_vectors=svs)
            if not ur.get("success"):
                raise RuntimeError(f"null upsert failed: {ur.get('error_message')}")
        print(f"[null] ingested in {time.time()-t0:.1f}s", flush=True)
        self._null_ids = list(range(self.cap))

    @staticmethod
    def bucket(size):
        return 1 << max(1, (max(2, size) - 1).bit_length())

    def get(self, size):
        b = min(self.bucket(size), self.cap)
        if b in self._cache:
            return self._cache[b]
        vals = []
        rng = np.random.default_rng(0xC0FFEE + b)
        for _ in range(self.n_draws):
            if b >= self.cap:
                window = self._null_ids
            else:
                start = int(rng.integers(0, self.cap - b + 1))
                window = self._null_ids[start:start + b]
            nr = self.client.cluster_ultradim_v23(
                self.name, num_clusters=1, init_seed=1, row_ids=window,
                max_cycles=C1_CYCLES, use_kmeans_plus_plus=True)
            if not nr.get("success"):
                raise RuntimeError(f"null cluster failed: {nr.get('error_message')}")
            vals.append(nr["mean_log10_p_real"])
        vals = np.array(vals, dtype=np.float64)
        rec = {"bucket": b, "mean": float(vals.mean()),
               "spread": float(vals.std()), "samples": vals.tolist(), "n_null": b}
        self._cache[b] = rec
        return rec


class Node:
    __slots__ = ("ids", "address", "level", "log10_lift", "c1_mean",
                 "null_rec", "raw_inertia", "cluster_ms", "is_leaf",
                 "stop_reason", "weighted_child_lift", "arm")

    def __init__(self, ids, address, level):
        self.ids = ids
        self.address = address
        self.level = level
        self.log10_lift = None
        self.c1_mean = None
        self.null_rec = None
        self.raw_inertia = None
        self.cluster_ms = None
        self.is_leaf = False
        self.stop_reason = None
        self.weighted_child_lift = None
        self.arm = None


def score_c1(client, node, null):
    r = client.cluster_ultradim_v23(
        FAMILY, num_clusters=1, init_seed=SEED, row_ids=node.ids,
        max_cycles=C1_CYCLES, use_kmeans_plus_plus=True)
    if not r.get("success"):
        raise RuntimeError(f"C=1 failed at {node.address}: {r.get('error_message')}")
    nb = null.get(len(node.ids))
    node.c1_mean = r["mean_log10_p_real"]
    node.raw_inertia = r["final_inertia"]
    node.cluster_ms = r["cluster_ms"]
    node.arm = r["mean_update_arm"]
    node.null_rec = nb
    node.log10_lift = nb["mean"] - r["mean_log10_p_real"]


def main():
    z = np.load(CORPUS)
    C = sp.csr_matrix((z["data"], z["indices"], z["indptr"]),
                      shape=tuple(int(x) for x in z["shape"]))
    nnz_pool = np.diff(C.indptr)
    print(f"[corpus] {CORPUS.name} shape={C.shape} nnz={C.nnz:,} "
          f"nnz/row min={int(nnz_pool.min())} p50={int(np.percentile(nnz_pool,50))} "
          f"max={int(nnz_pool.max())}", flush=True)

    client = UltraDimClient(host="localhost", port=6334)
    info = client.get_ultradim_v23_info(FAMILY)
    if info["substrate"] != "sparse":
        raise RuntimeError(f"{FAMILY} substrate {info['substrate']!r} != sparse")
    print(f"[family] {FAMILY} substrate=sparse seeds={info['seeds']} "
          f"mode={info['projection_mode']} D_proj={info['projection_dim']}", flush=True)

    t_run = time.time()
    boot = client.cluster_ultradim_v23(
        FAMILY, num_clusters=1, init_seed=SEED, max_cycles=C1_CYCLES,
        use_kmeans_plus_plus=True)
    if not boot.get("success"):
        raise RuntimeError(f"root C=1 failed: {boot.get('error_message')}")
    all_ids = list(boot["row_id_order"])
    n_total = len(all_ids)
    print(f"[root] N={n_total} D_raw={boot['source_dim']} "
          f"arm={boot['mean_update_arm']}", flush=True)

    null = SparseFittedNull(client, nnz_pool, max_n=n_total)

    root = Node(all_ids, "1", 0)
    root.c1_mean = boot["mean_log10_p_real"]
    root.raw_inertia = boot["final_inertia"]
    root.cluster_ms = boot["cluster_ms"]
    root.arm = boot["mean_update_arm"]
    root.null_rec = null.get(n_total)
    root.log10_lift = root.null_rec["mean"] - boot["mean_log10_p_real"]
    print(f"[root] log10_lift={root.log10_lift:+.3f} "
          f"(null mean={root.null_rec['mean']:.3f} "
          f"spread={root.null_rec['spread']:.3f})", flush=True)

    all_nodes = [root]
    queue = [root]
    ms_samples = [root.cluster_ms]

    while queue:
        node = queue.pop()
        size = len(node.ids)
        if size < MIN_POP:
            node.is_leaf = True
            node.stop_reason = f"min_pop:{size}<{MIN_POP}"
            continue
        if node.level >= MAX_DEPTH:
            node.is_leaf = True
            node.stop_reason = f"max_depth:{node.level}>={MAX_DEPTH}"
            continue

        r = client.cluster_ultradim_v23(
            FAMILY, num_clusters=2, init_seed=SEED, row_ids=node.ids,
            max_cycles=C2_CYCLES, use_kmeans_plus_plus=True)
        if not r.get("success"):
            node.is_leaf = True
            node.stop_reason = f"c2_failed:{r.get('error_message')}"
            continue
        ms_samples.append(r["cluster_ms"])
        order, assign = r["row_id_order"], r["assignments"]
        side0 = [order[i] for i in range(len(order)) if assign[i] == 0]
        side1 = [order[i] for i in range(len(order)) if assign[i] == 1]
        if not side0 or not side1:
            node.is_leaf = True
            node.stop_reason = "degenerate_split"
            continue
        big_ids, small_ids = (side0, side1) if len(side0) >= len(side1) else (side1, side0)
        big = Node(big_ids, node.address + ".1", node.level + 1)
        small = Node(small_ids, node.address + ".2", node.level + 1)
        for ch in (big, small):
            score_c1(client, ch, null)
            ms_samples.append(ch.cluster_ms)

        spread = node.null_rec["spread"] if node.null_rec else 0.0
        tau = TAU_K * max(spread, 1e-9)
        margin = MARGIN_K * max(spread, 1e-9)
        wcl = (len(big_ids) * big.log10_lift +
               len(small_ids) * small.log10_lift) / size
        node.weighted_child_lift = wcl
        fails = []
        if not (big.log10_lift > tau):
            fails.append("big_lift<=tau")
        if not (small.log10_lift > tau):
            fails.append("small_lift<=tau")
        if not (wcl > node.log10_lift + margin):
            fails.append("wcl<=parent+margin")
        if not (len(small_ids) >= max(MIN_POP, MIN_FRAC * size)):
            fails.append("small_below_min_frac")

        if not fails:
            all_nodes.extend([big, small])
            for ch in (big, small):
                if len(ch.ids) >= MIN_POP and ch.level < MAX_DEPTH:
                    queue.append(ch)
                else:
                    ch.is_leaf = True
                    ch.stop_reason = (f"min_pop:{len(ch.ids)}<{MIN_POP}"
                                      if len(ch.ids) < MIN_POP
                                      else f"max_depth:{ch.level}>={MAX_DEPTH}")
            print(f"[split] {node.address} (n={size}, lift={node.log10_lift:+.2f}) -> "
                  f".1 n={len(big_ids)} lift={big.log10_lift:+.2f} | "
                  f".2 n={len(small_ids)} lift={small.log10_lift:+.2f}", flush=True)
        else:
            node.is_leaf = True
            node.stop_reason = "split_rejected:" + ",".join(fails)
            print(f"[stop ] {node.address} (n={size}): {node.stop_reason}", flush=True)

    leaves = [n for n in all_nodes if n.is_leaf]
    out_jsonl = Path(OUT_BASE + ".nodes.jsonl")
    out_csv = Path(OUT_BASE + ".row_leaf.csv")
    with open(out_jsonl, "w") as jf:
        for n in all_nodes:
            parent = n.address.rsplit(".", 1)[0] if "." in n.address else None
            nb = n.null_rec or {}
            jf.write(json.dumps({
                "address": n.address, "level": n.level, "parent": parent,
                "size": len(n.ids), "raw_inertia": n.raw_inertia,
                "mean_log10_p_real": n.c1_mean, "log10_lift": n.log10_lift,
                "weighted_child_lift": n.weighted_child_lift,
                "is_leaf": n.is_leaf, "stop_reason": n.stop_reason,
                "null_bucket": nb.get("bucket"), "null_mean": nb.get("mean"),
                "null_spread": nb.get("spread"),
                "mean_update_arm": n.arm, "cluster_ms": n.cluster_ms,
            }) + "\n")
    with open(out_csv, "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow(["row_id", "leaf_address"])
        covered = 0
        for lf in leaves:
            for rid in lf.ids:
                w.writerow([rid, lf.address])
                covered += 1

    ms = np.array(ms_samples, dtype=np.float64)
    print("\n=== SEGMENTATION SUMMARY (ml20m_movies sparse 138,493-D) ===")
    print(f"  family={FAMILY}  N={n_total}  D_raw={D_RAW}  substrate=sparse")
    print(f"  nodes={len(all_nodes)}  leaves={len(leaves)}  "
          f"max_level={max(n.level for n in all_nodes)}")
    print(f"  leaf coverage: {covered}/{n_total}")
    print(f"  per-call cluster_ms p50={np.percentile(ms, 50):.0f} "
          f"p95={np.percentile(ms, 95):.0f} (n={len(ms)})")
    print(f"  total wall: {time.time()-t_run:.1f}s (incl. null build)")
    print(f"  wrote {out_jsonl} + {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
