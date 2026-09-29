#!/usr/bin/env python3
"""ChEMBL BloomMap JSON builder -- the chemical-space analogue of
BloomMap/process/build_bloommap_json.py (the shared producer (bloommap_build.py).

Same JSON contract (themes / volumes / tree / meta), same support-smoothed
feature scoring and G7 budget -- reused verbatim by importing build_all() and
the generic helpers from bloommap_build. Only the inputs and the
DICTIONARY semantics change:

  rows    = ChEMBL molecules (100,000)
  columns = folded Morgan-r2 substructure bits in [0, 10,000,000)
  leaves  = chemotype clusters from the divisive hseg tree
  feature = a folded Morgan substructure bit. There is NO canonical human name
            for a folded bit, so the dictionary label is the bit id itself,
            "bit<col>" -- shown by number, never fabricated (project rule:
            unnamed index -> by number).

The chemical MEANING of each leaf is carried separately in meta as a leaf
EXEMPLAR: the ChEMBL id (+ SMILES) of the molecule closest to the leaf centroid,
computed by exact sparse cosine over the corpus. That is the real, citable
chemotype label, and it never invents a name.
"""
import importlib.util
import json
import os
import sys

import numpy as np
import scipy.sparse as sp

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PIPE = os.path.join(REPO, "tmp", "chembl_pipeline")

# Import bloommap_build by path and reuse its generic functions.
_spec = importlib.util.spec_from_file_location(
    "bloommap_build", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bloommap_build.py"))
bm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bm)

# --- ChEMBL inputs (env-overridable; defaults = 100k/10M poster) ------------ #
NODES_PATH = os.environ.get("BM_NODES", os.path.join(PIPE, "chembl100k_hseg.nodes.jsonl"))
ROW_LEAF_PATH = os.environ.get("BM_ROW_LEAF", os.path.join(PIPE, "chembl100k_hseg.row_leaf.csv"))
CORPUS_PATH = os.environ.get("BM_CORPUS", os.path.join(PIPE, "stageB_100k", "features.npz"))
CHEMBL_IDS_PATH = os.environ.get("BM_CHEMBL_IDS", os.path.join(PIPE, "stageB_100k", "chembl_ids.txt"))
CHEMREPS_PATH = os.path.join(REPO, "data", "chembl", "chembl_37_chemreps.txt")
DOMAIN_TAG = os.environ.get("BM_DOMAIN", "chembl_100k_chemotypes")

OUT_DIR = os.environ.get("BM_OUT_DIR", os.path.join(REPO, "BloomMap", "data", "chembl"))
THEMES_PATH = os.path.join(OUT_DIR, "bloommap.themes.json")
VOLUMES_PATH = os.path.join(OUT_DIR, "bloommap.volumes.json")
TREE_PATH = os.path.join(OUT_DIR, "bloommap.tree.json")
META_PATH = os.path.join(OUT_DIR, "bloommap.meta.json")


def load_nodes():
    nodes = {}
    with open(NODES_PATH) as fh:
        for line in fh:
            line = line.strip()
            if line:
                n = json.loads(line)
                nodes[n["address"]] = n
    return nodes


def load_row_leaf():
    import csv
    from collections import defaultdict
    rows_by_leaf = defaultdict(list)
    n_rows = 0
    with open(ROW_LEAF_PATH, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        assert header == ["row_id", "leaf_address"], header
        for row in reader:
            rows_by_leaf[row[1]].append(int(row[0]))
            n_rows += 1
    for leaf in rows_by_leaf:
        rows_by_leaf[leaf].sort()
    return rows_by_leaf, n_rows


def load_corpus():
    return sp.load_npz(CORPUS_PATH)


def leaf_exemplars(C, rows_by_leaf, nodes, chembl_ids):
    """For each leaf, the molecule closest to the (sparse) leaf centroid.

    Centroid = L2-normalised mean of the leaf's already-L2-normalised rows;
    exemplar = argmax cosine(row, centroid) over the leaf. Returns
    {leaf_address: {"row": int, "chembl_id": str, "cosine": float}}.
    """
    out = {}
    for addr, n in nodes.items():
        if not n["is_leaf"]:
            continue
        rows = np.asarray(rows_by_leaf[addr], dtype=np.int64)
        sub = C[rows]                              # m x D sparse
        centroid = np.asarray(sub.mean(axis=0)).ravel()
        nrm = np.linalg.norm(centroid)
        if nrm > 0:
            centroid = centroid / nrm
        # cosine of each row with the centroid (rows already unit-norm)
        cos = sub.dot(centroid)                    # length m
        j = int(np.argmax(cos))
        row = int(rows[j])
        out[addr] = {"row": row, "chembl_id": chembl_ids[row],
                     "cosine": float(cos[j])}
    return out


def load_smiles_for(chembl_id_set):
    """Map the needed ChEMBL ids -> canonical SMILES from the chemreps TSV."""
    want = set(chembl_id_set)
    smiles = {}
    with open(CHEMREPS_PATH) as fh:
        fh.readline()  # header
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] in want:
                smiles[parts[0]] = parts[1]
                if len(smiles) == len(want):
                    break
    return smiles


def main():
    # Override the imported module's ChEMBL-incompatible gate constants.
    nodes = load_nodes()
    rows_by_leaf, n_rows = load_row_leaf()
    C = load_corpus()
    n_dims = C.shape[1]
    chembl_ids = open(CHEMBL_IDS_PATH).read().split()
    assert len(chembl_ids) == C.shape[0], (len(chembl_ids), C.shape[0])

    n_leaves = sum(1 for n in nodes.values() if n["is_leaf"])
    print(f"[chembl] nodes={len(nodes)} leaves={n_leaves} rows={n_rows} "
          f"D_raw={n_dims:,}")

    # Patch module gate constants so build_all()'s internal asserts match ChEMBL.
    bm.EXPECTED_N_LEAVES = n_leaves
    bm.EXPECTED_N_ROWS = n_rows
    bm.EXPECTED_N_DIMS = n_dims

    mean_global, global_support, _ = bm.compute_global_stats(C)

    # The "dictionary": folded Morgan bit id -> "bit<col>" label. labels[d]
    # is the label for column d. We pass a lazy-ish list: build it only for the
    # columns that survive (build_all indexes by column < len(labels), else
    # falls back to "dim<col>"). Simplest correct option: full-length list is
    # 10M entries (~600 MB of str) -- too big. Instead supply a dict-like
    # sequence via a custom object that returns "bit<c>" for any index.
    class BitDict:
        def __len__(self):
            return n_dims
        def __getitem__(self, c):
            return "bit%d" % int(c)
    labels = BitDict()

    built = bm.build_all(nodes, rows_by_leaf, C, labels,
                         mean_global, global_support, n_rows)

    themes = built["themes"]
    volumes = built["volumes"]
    tree = built["tree"]
    meta = built["meta"]

    # Replace the generic meta header with ChEMBL semantics + add
    # the leaf exemplars (the real chemotype identity).
    exemplars = leaf_exemplars(C, rows_by_leaf, nodes, chembl_ids)
    smiles = load_smiles_for({e["chembl_id"] for e in exemplars.values()})
    # leaf label (L01..) -> exemplar, via leaf_number_to_address inverse
    addr_to_label = {}
    # Reconstruct address->label from tree meta
    num_to_addr = meta["leaf_number_to_address"]
    # build label from leaf_order position
    for i, label in enumerate(meta["leaf_order"], start=1):
        addr = num_to_addr[str(i)]
        addr_to_label[addr] = label
    leaf_exemplar_by_label = {}
    for addr, ex in exemplars.items():
        lab = addr_to_label.get(addr)
        if lab is None:
            continue
        leaf_exemplar_by_label[lab] = {
            "chembl_id": ex["chembl_id"],
            "smiles": smiles.get(ex["chembl_id"]),
            "centroid_cosine": round(ex["cosine"], 4),
            "row": ex["row"],
        }

    meta["domain"] = DOMAIN_TAG
    meta["orientation"] = {
        "cluster_axis": "molecules (ChEMBL rows)",
        "feature_axis": "folded Morgan-r2 substructure bits (columns)",
        "dictionary": "bit<col> (folded Morgan bit id; no canonical name)",
    }
    meta["d_raw"] = n_dims
    meta["morgan_radius"] = 2
    meta["leaf_exemplars"] = leaf_exemplar_by_label
    meta.pop("corpus_sha256", None)

    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(themes, open(THEMES_PATH, "w"), indent=1)
    json.dump(volumes, open(VOLUMES_PATH, "w"), indent=1)
    json.dump(tree, open(TREE_PATH, "w"), indent=1)
    json.dump(meta, open(META_PATH, "w"), indent=1)

    print(f"[chembl] drawn features = {meta['drops']['drawn_feature_count']} "
          f"(dropped {meta['drops']['dropped_feature_count']}, "
          f"budget {meta['drops']['budget']})")
    print("[chembl] leaf exemplars:")
    for lab in meta["leaf_order"]:
        ex = leaf_exemplar_by_label.get(lab, {})
        print(f"    {lab}  {ex.get('chembl_id','?'):14} cos={ex.get('centroid_cosine')}"
              f"  {(ex.get('smiles') or '')[:48]}")
    print(f"[chembl] wrote 4 JSON files to {OUT_DIR}")


if __name__ == "__main__":
    main()
