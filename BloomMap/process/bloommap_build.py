#!/usr/bin/env python3
"""
bloommap_build.py
=================

Shared data-producer for the UltraDim BloomMap -- a circular-phylogram poster
of a hierarchical clustering. It clusters ROWS (items) over COLUMN dimensions;
each leaf is an item cluster, and a leaf's distinguishing features are columns.
An optional dictionary maps a column index to a human-readable label.

It reads a hierarchical clustering (the tree nodes and a row->leaf map produced
by UltraDim's HierarchicalClusterUltradimV23) plus the sparse corpus, and emits
four JSON files a BloomMap renderer consumes:
  - bloommap.themes.json   (flat theme map; tokens are stable IDs)
  - bloommap.volumes.json  (per-node volume = node size)
  - bloommap.tree.json     (nested topology for the phylogram)
  - bloommap.meta.json     (legend / tooltip / audit metadata)

The corpus-specific producers (build_bloommap_json_chembl.py,
build_bloommap_json_ml20m.py) import the generic helpers from this module and
supply their own inputs, dictionary and meta header. This module's own main()
is retained only as a reference driver.
"""

import os
import sys
import csv
import json
import math
import hashlib
from collections import defaultdict

import numpy as np
import scipy.sparse as sp


# --------------------------------------------------------------------------- #
# Paths (absolute; the script is meant to be run from the repo root, but using
# absolute paths makes it robust to the caller's cwd).
# --------------------------------------------------------------------------- #
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

NODES_PATH = os.path.join(REPO_ROOT, "BloomMap/data/source/hseg.nodes.jsonl")
ROW_LEAF_PATH = os.path.join(REPO_ROOT, "BloomMap/data/source/hseg.row_leaf.csv")
CORPUS_PATH = os.path.join(REPO_ROOT, "data/the corpus/the corpus_100k_sparse_aligned.npz")
DICT_PATH = os.path.join(REPO_ROOT, "data/the corpus/the dictionary file")

OUT_DIR = os.path.join(REPO_ROOT, "BloomMap/data/the corpus")
PROVENANCE_PATH = os.path.join(REPO_ROOT, "BloomMap/data/source/PROVENANCE.md")

THEMES_PATH = os.path.join(OUT_DIR, "bloommap.themes.json")
VOLUMES_PATH = os.path.join(OUT_DIR, "bloommap.volumes.json")
TREE_PATH = os.path.join(OUT_DIR, "bloommap.tree.json")
META_PATH = os.path.join(OUT_DIR, "bloommap.meta.json")


# --------------------------------------------------------------------------- #
# Parameters
# --------------------------------------------------------------------------- #
EPS = 1e-9
TOP_PER_LEAF = 50
TOP_GLOBAL = 100
MAX_DRAWN = 1200          # G7 budget: total distinct drawn features
MIN_KEEP_PER_LEAF = 10    # never let the budget empty a leaf below this many
EXPECTED_N_ROWS = 49970
EXPECTED_N_DIMS = 100000
EXPECTED_N_LEAVES = 43
EXPECTED_CORPUS_SHA = "2a249a0ad6d3fc1886587c01e6097915dd298a26cf0f189785c7fe766a76fe4c"


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def addr_key(address):
    """Natural sort key for a dotted address: split on '.' and compare as ints."""
    return tuple(int(p) for p in address.split("."))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(msg):
    """Print a clear gate-failure message and exit nonzero."""
    print("GATE FAILURE: " + msg, file=sys.stderr)
    print("PHASE 1 GATE: FAIL", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #
def load_nodes():
    """Read the JSONL tree; return dict address -> node-dict."""
    nodes = {}
    with open(NODES_PATH, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            nodes[n["address"]] = n
    return nodes


def load_row_leaf():
    """Return (rows_by_leaf: dict leaf_address -> sorted list[int], n_rows: int)."""
    rows_by_leaf = defaultdict(list)
    n_rows = 0
    with open(ROW_LEAF_PATH, "r", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if header != ["row_id", "leaf_address"]:
            fail("row_leaf.csv header is %r, expected ['row_id','leaf_address']" % (header,))
        for row in reader:
            rid = int(row[0])
            leaf = row[1]
            rows_by_leaf[leaf].append(rid)
            n_rows += 1
    # Sort each row-id list ascending (stable, deterministic slicing).
    for leaf in rows_by_leaf:
        rows_by_leaf[leaf].sort()
    return rows_by_leaf, n_rows


def load_corpus():
    """Load the CSR corpus exactly as the .npz stores separate arrays."""
    z = np.load(CORPUS_PATH)
    shape = tuple(int(x) for x in z["shape"])
    C = sp.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=shape)
    return C


def load_dictionary():
    """
    Return a list[str] labels where labels[d] is the label for
    column/dimension d. Data-row order in the TSV equals the dimension index:
    the customer on data-line i (0-based, after the header) is dimension i.
    """
    labels = []
    with open(DICT_PATH, "r") as fh:
        header = fh.readline().rstrip("\n")
        # header is "label\tVISITS"; we only need the first column going forward.
        for line in fh:
            line = line.rstrip("\n")
            if line == "":
                continue
            code = line.split("\t", 1)[0]
            labels.append(code)
    return labels


# --------------------------------------------------------------------------- #
# A. Tree reconstruction + leaf order
# --------------------------------------------------------------------------- #
def build_children(nodes):
    """parent address -> list of child addresses (unsorted)."""
    children = defaultdict(list)
    root = None
    for addr, n in nodes.items():
        parent = n["parent"]
        if parent is None:
            if root is not None:
                fail("more than one root node found (%s and %s)" % (root, addr))
            root = addr
        else:
            children[parent].append(addr)
    if root is None:
        fail("no root node (parent==null) found in tree")
    return children, root


def dfs_leaf_order(nodes, children, root):
    """
    Stable depth-first traversal; children visited in dotted-address natural
    order. Returns the list of leaf addresses in DFS order.
    """
    leaf_order = []
    # Iterative DFS using an explicit stack so children are processed in
    # natural-sorted order (push reversed so the smallest is popped first).
    stack = [root]
    while stack:
        addr = stack.pop()
        node = nodes[addr]
        if node["is_leaf"]:
            leaf_order.append(addr)
            continue
        kids = sorted(children.get(addr, []), key=addr_key)
        if not kids:
            # Internal node with no children would be a malformed tree; surface it.
            fail("internal node %s has is_leaf=false but no children" % addr)
        for k in reversed(kids):
            stack.append(k)
    return leaf_order


def derive_dfs_leaf_order_recursive(nodes, children, root):
    """
    Independent recursive re-derivation of the DFS leaf order, used by the GATE
    to cross-check the iterative version (guards against a stack-order bug).
    """
    out = []

    def visit(addr):
        node = nodes[addr]
        if node["is_leaf"]:
            out.append(addr)
            return
        for k in sorted(children.get(addr, []), key=addr_key):
            visit(k)

    visit(root)
    return out


# --------------------------------------------------------------------------- #
# B/C. Per-leaf and global feature scoring
# --------------------------------------------------------------------------- #
def compute_global_stats(C):
    """
    Returns (mean_global, global_support) as 1-D float64 / int arrays of length
    n_dims. Computed once.
    """
    n_rows = C.shape[0]
    mean_global = np.asarray(C.mean(axis=0)).ravel().astype(np.float64)
    # Column nonzero counts: build a boolean CSR once, sum down columns.
    Cbool = C.copy()
    Cbool.data = np.ones_like(Cbool.data)
    global_support = np.asarray(Cbool.sum(axis=0)).ravel().astype(np.int64)
    return mean_global, global_support, n_rows


def leaf_feature_scores(C, rows, mean_global):
    """
    For a single leaf with the given row-id list, compute the full per-column
    score array (vectorised) plus the support array. Returns (score, lift,
    support) each a length-n_dims float64/float64/int64 numpy array.

    score(c) = log((mean_leaf[c]+eps)/(mean_global[c]+eps)) * sqrt(support_leaf[c])
    lift(c)  = log((mean_leaf[c]+eps)/(mean_global[c]+eps))
    """
    idx = np.asarray(rows, dtype=np.int64)
    sub = C[idx]  # CSR row-slicing is fast.
    mean_leaf = np.asarray(sub.mean(axis=0)).ravel().astype(np.float64)
    subbool = sub.copy()
    subbool.data = np.ones_like(subbool.data)
    support_leaf = np.asarray(subbool.sum(axis=0)).ravel().astype(np.int64)

    lift = np.log((mean_leaf + EPS) / (mean_global + EPS))
    score = lift * np.sqrt(support_leaf.astype(np.float64))
    return score, lift, support_leaf


def top_k_by_score(score, valid_mask, k):
    """
    Return the indices of the top-k columns by score among columns where
    valid_mask is True, sorted by (-score, column_index) for determinism.
    """
    valid_cols = np.nonzero(valid_mask)[0]
    if valid_cols.size == 0:
        return np.empty((0,), dtype=np.int64)
    valid_scores = score[valid_cols]
    if valid_cols.size <= k:
        order = valid_cols
    else:
        # argpartition for the top-k, then a full deterministic sort of those.
        part = np.argpartition(-valid_scores, k - 1)[:k]
        order = valid_cols[part]
    # Final deterministic ordering: score descending, then column index ascending.
    final = sorted(order.tolist(), key=lambda c: (-float(score[c]), int(c)))
    return np.asarray(final, dtype=np.int64)


def minmax_weight(values):
    """
    Min-max normalise a list of floats into [0,1] with best (max) -> 1.0.
    If all equal, every weight is 1.0.
    """
    if len(values) == 0:
        return []
    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        return [1.0 for _ in values]
    span = vmax - vmin
    return [(v - vmin) / span for v in values]


# --------------------------------------------------------------------------- #
# The full pipeline (run twice for determinism gate)
# --------------------------------------------------------------------------- #
def build_all(nodes, rows_by_leaf, C, labels,
              mean_global, global_support, n_rows):
    """
    Pure(ish) builder: given already-loaded inputs and precomputed global stats,
    produce the four output objects + audit info. No file IO. Deterministic.

    Returns a dict with keys:
      themes, volumes, tree, meta, preview_rows, drawn_count, dropped_count
    """
    # --- A. tree + leaf order ------------------------------------------------
    children, root = build_children(nodes)
    leaf_order = dfs_leaf_order(nodes, children, root)

    if len(leaf_order) != EXPECTED_N_LEAVES:
        fail("DFS produced %d leaves, expected %d" % (len(leaf_order), EXPECTED_N_LEAVES))

    # leaf_address -> leaf_number (1..43) and label ("L01"..)
    width = len(str(len(leaf_order)))
    leaf_addr_to_number = {}
    leaf_addr_to_label = {}
    leaf_labels_in_order = []
    for i, addr in enumerate(leaf_order, start=1):
        leaf_addr_to_number[addr] = i
        label = "L" + str(i).zfill(max(2, width))
        leaf_addr_to_label[addr] = label
        leaf_labels_in_order.append(label)

    # Validate leaf membership + sizes.
    leaf_addrs_in_tree = {a for a, n in nodes.items() if n["is_leaf"]}
    leaf_addrs_in_csv = set(rows_by_leaf.keys())
    if leaf_addrs_in_tree != leaf_addrs_in_csv:
        only_tree = sorted(leaf_addrs_in_tree - leaf_addrs_in_csv, key=addr_key)
        only_csv = sorted(leaf_addrs_in_csv - leaf_addrs_in_tree, key=addr_key)
        fail("leaf set mismatch tree-vs-csv. only_tree=%r only_csv=%r" % (only_tree, only_csv))

    total_leaf_rows = sum(len(rows_by_leaf[a]) for a in leaf_order)
    if total_leaf_rows != EXPECTED_N_ROWS:
        fail("leaf row-ids sum to %d, expected %d" % (total_leaf_rows, EXPECTED_N_ROWS))

    # Cross-check each leaf's CSV row count equals its node 'size'.
    for addr in leaf_order:
        node_size = int(nodes[addr]["size"])
        csv_size = len(rows_by_leaf[addr])
        if node_size != csv_size:
            fail("leaf %s node size %d != csv row count %d" % (addr, node_size, csv_size))

    # --- B. per-leaf features ------------------------------------------------
    # For each leaf, gather candidate features (col, score, lift, support).
    # We keep TOP_PER_LEAF after the MIN_SUPPORT filter.
    leaf_features = {}        # label -> list of dicts {col, score, lift, support}
    for addr in leaf_order:
        label = leaf_addr_to_label[addr]
        rows = rows_by_leaf[addr]
        leaf_size = len(rows)
        min_support = max(2, math.ceil(0.01 * leaf_size))

        score, lift, support = leaf_feature_scores(C, rows, mean_global)
        valid_mask = support >= min_support
        top_cols = top_k_by_score(score, valid_mask, TOP_PER_LEAF)

        feats = []
        for c in top_cols.tolist():
            feats.append({
                "col": int(c),
                "score": float(score[c]),
                "lift": float(lift[c]),
                "support": int(support[c]),
            })
        leaf_features[label] = feats

    # --- C. global / centre features ----------------------------------------
    global_score = mean_global * np.sqrt(global_support.astype(np.float64))
    # All columns are candidates for the centre; take top TOP_GLOBAL.
    g_all_mask = np.ones(global_score.shape[0], dtype=bool)
    g_top_cols = top_k_by_score(global_score, g_all_mask, TOP_GLOBAL)
    global_features = []
    for c in g_top_cols.tolist():
        global_features.append({
            "col": int(c),
            "score": float(global_score[c]),
            # lift is not meaningful for the centre; store the raw mean instead.
            "mean": float(mean_global[c]),
            "support": int(global_support[c]),
        })

    # --- D. stable IDs + budget ---------------------------------------------
    # Collect the best score (across every set it appears in) for each column.
    best_score = {}                  # col -> best (max) score
    appears_in = defaultdict(set)    # col -> set of set-labels ("global","L05",...)

    for f in global_features:
        c = f["col"]
        s = f["score"]
        if c not in best_score or s > best_score[c]:
            best_score[c] = s
        appears_in[c].add("global")

    for label in leaf_labels_in_order:
        for f in leaf_features[label]:
            c = f["col"]
            s = f["score"]
            if c not in best_score or s > best_score[c]:
                best_score[c] = s
            appears_in[c].add(label)

    # Protected columns: each leaf's top MIN_KEEP_PER_LEAF features (by score,
    # already ordered) must survive the budget.
    protected = set()
    for label in leaf_labels_in_order:
        for f in leaf_features[label][:MIN_KEEP_PER_LEAF]:
            protected.add(f["col"])

    # Apply the G7 budget on the count of DISTINCT drawn columns.
    all_cols_sorted = sorted(
        best_score.keys(),
        key=lambda c: (-best_score[c], c),
    )
    dropped_cols = set()
    if len(all_cols_sorted) > MAX_DRAWN:
        # Walk worst-first; drop until we are within budget, never dropping a
        # protected column.
        n_over = len(all_cols_sorted) - MAX_DRAWN
        # worst-first = reverse of the best-first ordering
        for c in reversed(all_cols_sorted):
            if n_over <= 0:
                break
            if c in protected:
                continue
            dropped_cols.add(c)
            n_over -= 1
        if n_over > 0:
            # Could not get within budget without dropping protected columns.
            fail("cannot meet MAX_DRAWN=%d budget without emptying leaf petals "
                 "(protected=%d, total=%d)" %
                 (MAX_DRAWN, len(protected), len(all_cols_sorted)))

    kept_cols = [c for c in all_cols_sorted if c not in dropped_cols]

    # Assign stable IDs: sort kept columns by (-best_score, col), C0001.. .
    id_width = max(4, len(str(len(kept_cols))))
    col_to_id = {}
    for i, c in enumerate(kept_cols, start=1):
        col_to_id[c] = "C" + str(i).zfill(id_width)

    # id -> label (resolve via dictionary; never fabricate a code).
    n_dims = C.shape[1]
    id_to_text = {}
    for c in kept_cols:
        cid = col_to_id[c]
        if 0 <= c < len(labels):
            id_to_text[cid] = labels[c]
        else:
            id_to_text[cid] = "dim%d" % c

    # --- Build themes (tokens are IDs; weights min-max within each set) -------
    themes = {}

    # Global / centre.
    g_kept = [f for f in global_features if f["col"] not in dropped_cols]
    g_weights = minmax_weight([f["score"] for f in g_kept])
    g_entries = []
    for f, w in zip(g_kept, g_weights):
        g_entries.append((col_to_id[f["col"]], float(w), float(f["score"])))
    # Order by weight desc, tie-break by id asc.
    g_entries.sort(key=lambda e: (-e[1], e[0]))
    themes["global"] = [[e[0], e[1]] for e in g_entries]

    # Per-leaf petals.
    for label in leaf_labels_in_order:
        kept = [f for f in leaf_features[label] if f["col"] not in dropped_cols]
        weights = minmax_weight([f["score"] for f in kept])
        entries = []
        for f, w in zip(kept, weights):
            entries.append((col_to_id[f["col"]], float(w), float(f["score"])))
        entries.sort(key=lambda e: (-e[1], e[0]))
        themes[label] = [[e[0], e[1]] for e in entries]

    # --- Volumes -------------------------------------------------------------
    volumes = {"global": {"volume": int(nodes[root]["size"])}}
    for addr in leaf_order:
        label = leaf_addr_to_label[addr]
        volumes[label] = {"volume": int(nodes[addr]["size"])}

    # --- Tree (nested topology) ---------------------------------------------
    def build_tree_node(addr):
        node = nodes[addr]
        is_leaf = bool(node["is_leaf"])
        leaf_number = leaf_addr_to_number[addr] if is_leaf else None
        label = leaf_addr_to_label[addr] if is_leaf else None
        obj = {
            "address": addr,
            "leaf_number": leaf_number,
            "size": int(node["size"]),
            "log10_lift": float(node["log10_lift"]),
            "depth": int(node["level"]),
            "is_leaf": is_leaf,
            "label": label,
        }
        if not is_leaf:
            kids = sorted(children.get(addr, []), key=addr_key)
            obj["children"] = [build_tree_node(k) for k in kids]
        else:
            obj["children"] = []
        return obj

    tree = build_tree_node(root)

    # --- Meta ---------------------------------------------------------------
    feature_detail = {}
    for c in kept_cols:
        cid = col_to_id[c]
        feature_detail[cid] = {
            "col": int(c),
            "best_score": float(best_score[c]),
            "appears_in": sorted(appears_in[c]),
        }

    leaf_number_to_address = {}
    for addr in leaf_order:
        leaf_number_to_address[str(leaf_addr_to_number[addr])] = addr

    meta = {
        "domain": "the corpus_100k_posterA",
        "orientation": {
            "cluster_axis": "products(SKU rows)",
            "feature_axis": "customers(columns)",
            "dictionary": "label",
        },
        "n_rows": int(n_rows),
        "n_dims": int(n_dims),
        "n_leaves": len(leaf_order),
        "leaf_order": leaf_labels_in_order,
        "leaf_number_to_address": leaf_number_to_address,
        "id_to_text": id_to_text,
        "params": {
            "eps": EPS,
            "top_per_leaf": TOP_PER_LEAF,
            "top_global": TOP_GLOBAL,
            "max_drawn": MAX_DRAWN,
            "min_support_rule": "max(2,ceil(0.01*leaf_size))",
        },
        "drops": {
            "dropped_feature_count": len(dropped_cols),
            "drawn_feature_count": len(kept_cols),
            "budget": MAX_DRAWN,
        },
        "corpus_sha256": EXPECTED_CORPUS_SHA,
        "feature_detail": feature_detail,
    }

    # --- Preview rows (first 8 leaves) --------------------------------------
    preview_rows = []
    for addr in leaf_order[:8]:
        label = leaf_addr_to_label[addr]
        num = leaf_addr_to_number[addr]
        size = int(nodes[addr]["size"])
        feats = leaf_features[label][:5]
        feat_view = []
        for f in feats:
            c = f["col"]
            cid = col_to_id.get(c, "(dropped)")
            code = id_to_text.get(cid, "(dropped)") if cid != "(dropped)" else "(dropped)"
            feat_view.append({
                "id": cid,
                "cust": code,
                "lift": f["lift"],
                "support": f["support"],
            })
        preview_rows.append({
            "leaf_number": num,
            "label": label,
            "size": size,
            "feats": feat_view,
        })

    return {
        "themes": themes,
        "volumes": volumes,
        "tree": tree,
        "meta": meta,
        "leaf_order_addresses": leaf_order,
        "leaf_labels_in_order": leaf_labels_in_order,
        "preview_rows": preview_rows,
        "drawn_count": len(kept_cols),
        "dropped_count": len(dropped_cols),
        "id_to_text": id_to_text,
        "children": children,
        "root": root,
    }


# --------------------------------------------------------------------------- #
# Serialisation helpers
# --------------------------------------------------------------------------- #
def dumps_compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True, sort_keys=False)


def dumps_meta(obj):
    # Meta is allowed to be indented for readability; keep keys in insertion
    # order (deterministic because we build them deterministically).
    return json.dumps(obj, indent=2, ensure_ascii=True, sort_keys=False)


# --------------------------------------------------------------------------- #
# Preview printing
# --------------------------------------------------------------------------- #
def print_preview(preview_rows):
    print("")
    print("=" * 78)
    print("BLOOMMAP PREVIEW -- first 8 leaves (Poster A: products clustered over customers)")
    print("=" * 78)
    for pr in preview_rows:
        print("")
        print("Leaf %2d  [%s]  size=%d" % (pr["leaf_number"], pr["label"], pr["size"]))
        print("  %-8s %-18s %12s %8s" % ("id", "label", "lift", "support"))
        print("  " + "-" * 50)
        for f in pr["feats"]:
            print("  %-8s %-18s %12.4f %8d" %
                  (f["id"], f["cust"], f["lift"], f["support"]))


# --------------------------------------------------------------------------- #
# GATE checks
# --------------------------------------------------------------------------- #
def run_gates(result_a, result_b, nodes, rows_by_leaf):
    """
    (a) leaf sizes sum to 49970 over exactly 43 leaves
    (b) every drawn ID resolves to a real label
    (c) two in-process builds are byte-identical (themes + meta)
    (d) leaf_order is a valid DFS (every leaf once; matches recursive re-derive)
    (e) drawn_count <= budget and dropped recorded
    """
    # (a)
    leaf_order = result_a["leaf_order_addresses"]
    if len(leaf_order) != EXPECTED_N_LEAVES:
        fail("(a) leaf count %d != %d" % (len(leaf_order), EXPECTED_N_LEAVES))
    total = sum(len(rows_by_leaf[a]) for a in leaf_order)
    if total != EXPECTED_N_ROWS:
        fail("(a) leaf sizes sum to %d != %d" % (total, EXPECTED_N_ROWS))

    # (b) every drawn ID in themes resolves to a label in id_to_text, and
    #     every id_to_text value is a real label-shaped string (or dim<index>).
    id_to_text = result_a["id_to_text"]
    drawn_ids = set()
    for key, entries in result_a["themes"].items():
        for tok, _w in entries:
            drawn_ids.add(tok)
    missing = sorted(i for i in drawn_ids if i not in id_to_text)
    if missing:
        fail("(b) %d drawn IDs have no id_to_text entry, e.g. %r" % (len(missing), missing[:5]))
    empty_vals = sorted(i for i in drawn_ids if not id_to_text.get(i))
    if empty_vals:
        fail("(b) %d drawn IDs resolve to empty text, e.g. %r" % (len(empty_vals), empty_vals[:5]))

    # (c) determinism: byte-identical themes + meta across the two builds.
    ta = dumps_compact(result_a["themes"]).encode("utf-8")
    tb = dumps_compact(result_b["themes"]).encode("utf-8")
    if ta != tb:
        fail("(c) themes JSON not byte-identical across two in-process builds")
    ma = dumps_meta(result_a["meta"]).encode("utf-8")
    mb = dumps_meta(result_b["meta"]).encode("utf-8")
    if ma != mb:
        fail("(c) meta JSON not byte-identical across two in-process builds")

    # (d) DFS validity: re-derive recursively and compare; check each leaf once.
    children = result_a["children"]
    root = result_a["root"]
    recursive = derive_dfs_leaf_order_recursive(nodes, children, root)
    if recursive != leaf_order:
        fail("(d) iterative DFS leaf order != recursive re-derivation")
    if len(set(leaf_order)) != len(leaf_order):
        fail("(d) leaf_order contains a duplicate leaf")
    tree_leaf_addrs = {a for a, n in nodes.items() if n["is_leaf"]}
    if set(leaf_order) != tree_leaf_addrs:
        fail("(d) leaf_order set != set of is_leaf nodes in tree")

    # (e) budget.
    drawn = result_a["drawn_count"]
    dropped = result_a["dropped_count"]
    if drawn > MAX_DRAWN:
        fail("(e) drawn_feature_count %d > budget %d" % (drawn, MAX_DRAWN))
    meta_drawn = result_a["meta"]["drops"]["drawn_feature_count"]
    meta_dropped = result_a["meta"]["drops"]["dropped_feature_count"]
    if meta_drawn != drawn or meta_dropped != dropped:
        fail("(e) meta drop counts (%d/%d) disagree with build (%d/%d)" %
             (meta_drawn, meta_dropped, drawn, dropped))

    print("PHASE 1 GATE: PASS")
    print("  (a) 43 leaves sum to 49970 rows")
    print("  (b) all %d drawn IDs resolve to label" % len(drawn_ids))
    print("  (c) themes + meta byte-identical across two builds")
    print("  (d) leaf_order is a valid DFS (iterative == recursive)")
    print("  (e) drawn=%d <= budget=%d ; dropped=%d" % (drawn, MAX_DRAWN, dropped))


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def write_provenance(corpus_sha, drawn, dropped):
    lines = []
    lines.append("# BloomMap Phase 1 Provenance (Poster A)")
    lines.append("")
    lines.append("Data-producer: `BloomMap/process/build_bloommap_json.py`")
    lines.append("")
    lines.append("## Orientation")
    lines.append("")
    lines.append("Poster A clusters **products (SKU rows)** over **customer dimensions "
                 "(columns)**. Each leaf is a product cluster; its distinguishing "
                 "features are CUSTOMERS (columns), resolved to label via the "
                 "dictionary. There is no PROD_CODE in this poster.")
    lines.append("")
    lines.append("## Inputs read (full paths)")
    lines.append("")
    lines.append("- Tree nodes      : `%s`" % NODES_PATH)
    lines.append("- Row->leaf map   : `%s`" % ROW_LEAF_PATH)
    lines.append("- Corpus CSR npz  : `%s`" % CORPUS_PATH)
    lines.append("- Dictionary TSV  : `%s`" % DICT_PATH)
    lines.append("")
    lines.append("## Corpus integrity")
    lines.append("")
    lines.append("- sha256(corpus npz) = `%s`" % corpus_sha)
    lines.append("")
    lines.append("## Parameters")
    lines.append("")
    lines.append("- eps               = %s" % repr(EPS))
    lines.append("- top_per_leaf      = %d" % TOP_PER_LEAF)
    lines.append("- top_global        = %d" % TOP_GLOBAL)
    lines.append("- max_drawn (budget)= %d" % MAX_DRAWN)
    lines.append("- min_keep_per_leaf = %d" % MIN_KEEP_PER_LEAF)
    lines.append("- min_support_rule  = max(2, ceil(0.01 * leaf_size))")
    lines.append("- score(c, leaf)    = log((mean_leaf+eps)/(mean_global+eps)) * sqrt(support_leaf)")
    lines.append("- global_score(c)   = mean_global * sqrt(global_support)")
    lines.append("")
    lines.append("## Outputs written")
    lines.append("")
    lines.append("- `%s`" % THEMES_PATH)
    lines.append("- `%s`" % VOLUMES_PATH)
    lines.append("- `%s`" % TREE_PATH)
    lines.append("- `%s`" % META_PATH)
    lines.append("")
    lines.append("## Drawn-feature budget result")
    lines.append("")
    lines.append("- drawn_feature_count   = %d" % drawn)
    lines.append("- dropped_feature_count = %d" % dropped)
    lines.append("- budget                = %d" % MAX_DRAWN)
    lines.append("")
    with open(PROVENANCE_PATH, "w") as fh:
        fh.write("\n".join(lines))


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main():
    # --- Load inputs ---------------------------------------------------------
    print("Loading inputs ...")
    nodes = load_nodes()
    if len(nodes) != 85:
        fail("expected 85 tree nodes, got %d" % len(nodes))

    rows_by_leaf, n_rows = load_row_leaf()
    if n_rows != EXPECTED_N_ROWS:
        fail("row_leaf.csv has %d data rows, expected %d" % (n_rows, EXPECTED_N_ROWS))

    C = load_corpus()
    if C.shape != (EXPECTED_N_ROWS, EXPECTED_N_DIMS):
        fail("corpus shape %r != expected %r" % (C.shape, (EXPECTED_N_ROWS, EXPECTED_N_DIMS)))

    labels = load_dictionary()
    if len(labels) != EXPECTED_N_DIMS:
        fail("dictionary has %d customers, expected %d" % (len(labels), EXPECTED_N_DIMS))

    # --- Corpus integrity (sha256) ------------------------------------------
    print("Hashing corpus (sha256) ...")
    corpus_sha = sha256_file(CORPUS_PATH)
    if corpus_sha != EXPECTED_CORPUS_SHA:
        fail("corpus sha256 %s != expected %s" % (corpus_sha, EXPECTED_CORPUS_SHA))

    # --- Global stats (once) -------------------------------------------------
    print("Computing global column stats (mean + support) ...")
    mean_global, global_support, n_rows2 = compute_global_stats(C)
    if n_rows2 != EXPECTED_N_ROWS:
        fail("global stats saw %d rows, expected %d" % (n_rows2, EXPECTED_N_ROWS))

    # --- Build TWICE (determinism gate) -------------------------------------
    print("Building BloomMap artefacts (pass 1/2) ...")
    result_a = build_all(nodes, rows_by_leaf, C, labels,
                         mean_global, global_support, n_rows)
    print("Building BloomMap artefacts (pass 2/2, determinism check) ...")
    result_b = build_all(nodes, rows_by_leaf, C, labels,
                         mean_global, global_support, n_rows)

    # --- Write outputs (from pass-1 results) --------------------------------
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(THEMES_PATH, "w") as fh:
        fh.write(dumps_compact(result_a["themes"]))
    with open(VOLUMES_PATH, "w") as fh:
        fh.write(dumps_compact(result_a["volumes"]))
    with open(TREE_PATH, "w") as fh:
        fh.write(dumps_compact(result_a["tree"]))
    with open(META_PATH, "w") as fh:
        fh.write(dumps_meta(result_a["meta"]))

    write_provenance(corpus_sha, result_a["drawn_count"], result_a["dropped_count"])

    # --- Preview -------------------------------------------------------------
    print_preview(result_a["preview_rows"])

    # --- Gates ---------------------------------------------------------------
    print("")
    run_gates(result_a, result_b, nodes, rows_by_leaf)

    # --- Final report --------------------------------------------------------
    sizes = {
        "themes": os.path.getsize(THEMES_PATH),
        "volumes": os.path.getsize(VOLUMES_PATH),
        "tree": os.path.getsize(TREE_PATH),
        "meta": os.path.getsize(META_PATH),
    }
    print("")
    print("Drawn features : %d" % result_a["drawn_count"])
    print("Dropped features: %d" % result_a["dropped_count"])
    print("Output file sizes (bytes):")
    print("  bloommap.themes.json  : %d" % sizes["themes"])
    print("  bloommap.volumes.json : %d" % sizes["volumes"])
    print("  bloommap.tree.json    : %d" % sizes["tree"])
    print("  bloommap.meta.json    : %d" % sizes["meta"])


if __name__ == "__main__":
    main()
