#!/usr/bin/env python3
"""ML-20M movie-cluster BloomMap JSON builder -- the movie-space analogue of
tmp/chembl_pipeline/build_bloommap_json_chembl.py (which itself wraps the
the shared pipeline Poster-A producer BloomMap/process/build_bloommap_json.py).

Same JSON contract (themes / volumes / tree / meta), same support-smoothed
feature scoring and budget -- reused verbatim by importing build_all() and the
generic helpers from bloommap_build. Only the inputs and the DICTIONARY
semantics change:

  rows    = MovieLens movies (26,744)
  columns = user ordinals in [0, 138,493)
  leaves  = movie clusters from the divisive hseg tree over `ml20m_movies`
  feature = a user ordinal. A user ordinal has no human name, so the dictionary
            label is the ordinal itself, "user<col>" -- shown by number, never
            fabricated (project rule: unnamed index -> by number).

The MEANING of each leaf is carried separately in meta as the leaf EXEMPLARS:
the top-3 movies (by title) nearest the leaf centroid, computed by exact sparse
cosine over the corpus. Those movie titles ARE the cluster labels for the
BloomMap -- the purpose is genre/topic discovery (a "Toy Story" petal = family
animation) without any genre metadata.

CORPUS SEMANTICS: the clustering ran on the RESIDENT L2-row-normalised rating
DIRECTION vectors (what the family stores). The raw-ratings sidecar has the same
support but raw magnitudes, so we L2-row-normalise it here to reproduce exactly
what the clustering and the centroids saw.

Run (after tmp/ml20m_bloommap/hseg_ml20m_movies.py has produced the tree):
  python3 tmp/ml20m_bloommap/build_bloommap_json_ml20m.py
"""
import csv
import importlib.util
import json
import os
import sys

import numpy as np
import scipy.sparse as sp

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PIPE = os.path.join(REPO, "tmp", "ml20m_bloommap")

# Import bloommap_build by path and reuse its generic functions.
_spec = importlib.util.spec_from_file_location(
    "bloommap_build", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bloommap_build.py"))
bm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bm)

# --- ML-20M inputs (env-overridable) ---------------------------------------- #
NODES_PATH = os.environ.get("BM_NODES", os.path.join(PIPE, "ml20m_movies_hseg.nodes.jsonl"))
ROW_LEAF_PATH = os.environ.get("BM_ROW_LEAF", os.path.join(PIPE, "ml20m_movies_hseg.row_leaf.csv"))
# Raw-ratings movies CSR sidecar (row-normalised below to the resident direction).
CORPUS_PATH = os.environ.get(
    "BM_CORPUS", os.path.join(REPO, "data", "movielens", "ml20m_ratings_movies.npz"))
TITLES_PATH = os.environ.get(
    "BM_TITLES", os.path.join(REPO, "data", "movielens", "ml20m_movie_titles.tsv"))
# MovieLens links.csv: movieId -> imdbId (already zero-padded to 7) / tmdbId. Used
# to stamp each cell member with the PUBLIC movieId (the number printed in the
# cell) and the IMDb id (the per-cell hover link). The internal row ordinal never
# reaches the artwork.
LINKS_PATH = os.environ.get(
    "BM_LINKS", os.path.join(REPO, "data", "movielens", "ml-20m", "links.csv"))
DOMAIN_TAG = os.environ.get("BM_DOMAIN", "ml20m_movie_clusters")

OUT_DIR = os.environ.get("BM_OUT_DIR", os.path.join(REPO, "BloomMap", "data", "ml20m_movies"))
LEAVES_TSV = os.environ.get("BM_LEAVES_TSV", os.path.join(PIPE, "leaves.tsv"))
THEMES_PATH = os.path.join(OUT_DIR, "bloommap.themes.json")
VOLUMES_PATH = os.path.join(OUT_DIR, "bloommap.volumes.json")
TREE_PATH = os.path.join(OUT_DIR, "bloommap.tree.json")
META_PATH = os.path.join(OUT_DIR, "bloommap.meta.json")

N_EXEMPLARS = 3
# Per-cell member lists for the Voronoi tessellation. Each leaf petal (and the
# centre disc) numbers its cells with the ordinals of the movies NEAREST that
# cluster's centroid — one movie per cell. The renderer fills only as many cells
# as the tessellation has (<= the word-count budget), so we store a comfortable
# head of the nearest-centroid order: enough to fill the largest tessellation
# with margin, no more (every leaf has >=246 members, the centre draws from all
# 26,744 rows). N_LEAF_MEMBERS >= cluster word budget (30); N_ROOT_MEMBERS >=
# global word budget (60).
N_LEAF_MEMBERS = 60
N_ROOT_MEMBERS = 80


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


def load_corpus_resident():
    """Raw movies CSR -> L2-row-normalised direction (the resident substrate)."""
    C = sp.load_npz(CORPUS_PATH).tocsr().astype(np.float64)
    # Row L2-normalise in place (support unchanged; matches CSR sidecar semantics).
    norms = np.sqrt(np.asarray(C.multiply(C).sum(axis=1)).ravel())
    norms[norms == 0] = 1.0
    inv = sp.diags(1.0 / norms)
    return (inv @ C).tocsr()


def load_titles():
    """movie/row ordinal -> title. For ml20m_movies the row ordinal IS the movie
    ordinal (col_ordinal in the TSV), so col_ordinal -> title is the row map."""
    titles = {}
    with open(TITLES_PATH, newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader)
        assert header[:3] == ["col_ordinal", "movie_id", "title"], header
        for row in reader:
            titles[int(row[0])] = row[2]
    return titles


def load_row_movie_id():
    """row ordinal (col_ordinal) -> PUBLIC MovieLens movieId (the number printed
    in each cell; <=6 digits). The internal ordinal is NEVER printed."""
    row_to_movie_id = {}
    with open(TITLES_PATH, newline="") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader)
        assert header[:3] == ["col_ordinal", "movie_id", "title"], header
        for row in reader:
            row_to_movie_id[int(row[0])] = int(row[1])
    return row_to_movie_id


def load_movie_id_to_imdb():
    """MovieLens movieId -> imdbId (zero-padded to 7) from links.csv. The IMDb URN
    for the hover link is https://www.imdb.com/title/tt{imdbId}/ ."""
    m2i = {}
    with open(LINKS_PATH, newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        assert header[:3] == ["movieId", "imdbId", "tmdbId"], header
        for row in reader:
            if len(row) >= 2 and row[1]:
                # links.csv already stores imdbId zero-padded to 7; pad defensively.
                m2i[int(row[0])] = str(row[1]).zfill(7)
    return m2i


def leaf_exemplars(C, rows_by_leaf, nodes, titles, k=N_EXEMPLARS):
    """For each leaf, the k movies closest to the (sparse) leaf centroid, plus a
    coherence diagnostic.

    Centroid = L2-normalised mean of the leaf's already-L2-normalised rows;
    exemplars = top-k rows by cosine(row, centroid) over the leaf (rows already
    unit-norm). Returns
    {leaf_address: {"exemplars": [{"row","movie_ordinal","title","cosine"}, ...],
                    "mean_member_cosine": float,   # leaf compactness
                    "centroid_nnz": int,           # #users defining the centroid
                    "top3_identical_cosine": bool}} # degenerate tiny-support flag
    """
    out = {}
    for addr, n in nodes.items():
        if not n["is_leaf"]:
            continue
        rows = np.asarray(rows_by_leaf[addr], dtype=np.int64)
        sub = C[rows]                              # m x D sparse (unit rows)
        centroid = np.asarray(sub.mean(axis=0)).ravel()
        nrm = np.linalg.norm(centroid)
        if nrm > 0:
            centroid = centroid / nrm
        cos = sub.dot(centroid)                    # length m
        kk = min(k, len(rows))
        order = np.argsort(-cos)[:kk]
        exs = []
        for j in order:
            row = int(rows[j])
            exs.append({"row": row, "movie_ordinal": row,
                        "title": titles.get(row, "movie%d" % row),
                        "cosine": float(cos[j])})
        top = np.sort(cos)[::-1][:kk]
        ident = bool(len(top) >= 2 and np.allclose(top, top[0], atol=1e-4))
        out[addr] = {
            "exemplars": exs,
            "mean_member_cosine": float(cos.mean()),
            "centroid_nnz": int((centroid != 0).sum()),
            "top3_identical_cosine": ident,
        }
    return out


def _member_record(row, cosine, titles, row_to_movie_id, movie_id_to_imdb):
    """One cell member record. The PUBLIC movieId is the number printed in the
    cell; imdb_id (7-digit, or "" if unlinked) drives the hover link; title is the
    hover text. movie_ordinal is kept for data-file joins/provenance only — it is
    NEVER rendered into the artwork.
    """
    row = int(row)
    movie_id = row_to_movie_id.get(row)
    imdb = movie_id_to_imdb.get(movie_id, "") if movie_id is not None else ""
    return {"movie_id": movie_id,
            "imdb_id": imdb,
            "title": titles.get(row, "movie%d" % row),
            "centroid_cosine": round(float(cosine), 4),
            "movie_ordinal": row}


def leaf_members(C, rows_by_leaf, nodes, titles, row_to_movie_id,
                 movie_id_to_imdb, k=N_LEAF_MEMBERS):
    """Per leaf, the top-k movies nearest the leaf centroid (nearest-first) — the
    cells of that petal's Voronoi tessellation. Same centroid + cosine as
    leaf_exemplars (which is just the top-3 slice), so cell 0 == exemplar 0. Each
    member carries its PUBLIC movieId (printed), imdbId (hover link), title (hover
    text), and the internal ordinal (data-file join only, never rendered). Returns
    {leaf_address: [record, ...]}.
    """
    out = {}
    for addr, n in nodes.items():
        if not n["is_leaf"]:
            continue
        rows = np.asarray(rows_by_leaf[addr], dtype=np.int64)
        sub = C[rows]                              # m x D sparse (unit rows)
        centroid = np.asarray(sub.mean(axis=0)).ravel()
        nrm = np.linalg.norm(centroid)
        if nrm > 0:
            centroid = centroid / nrm
        cos = sub.dot(centroid)                    # length m
        kk = min(k, len(rows))
        # Deterministic nearest-first order: cosine descending, ties by ordinal.
        order = sorted(range(len(rows)), key=lambda j: (-float(cos[j]), int(rows[j])))[:kk]
        out[addr] = [
            _member_record(rows[j], cos[j], titles, row_to_movie_id, movie_id_to_imdb)
            for j in order
        ]
    return out


def root_members(C, titles, row_to_movie_id, movie_id_to_imdb, k=N_ROOT_MEMBERS):
    """The globally most-central movies — nearest the ROOT centroid (the L2-norm
    of the mean of every unit row) — which fill the centre disc's cells. Same
    record contract as the leaves (public movieId printed, imdbId hover link).
    """
    centroid = np.asarray(C.mean(axis=0)).ravel()
    nrm = np.linalg.norm(centroid)
    if nrm > 0:
        centroid = centroid / nrm
    cos = C.dot(centroid)                          # length n_rows
    kk = min(k, C.shape[0])
    order = sorted(range(C.shape[0]), key=lambda r: (-float(cos[r]), int(r)))[:kk]
    return [
        _member_record(r, cos[r], titles, row_to_movie_id, movie_id_to_imdb)
        for r in order
    ]


def main():
    nodes = load_nodes()
    rows_by_leaf, n_rows = load_row_leaf()
    C = load_corpus_resident()
    n_dims = C.shape[1]
    titles = load_titles()
    row_to_movie_id = load_row_movie_id()
    movie_id_to_imdb = load_movie_id_to_imdb()

    n_leaves = sum(1 for n in nodes.values() if n["is_leaf"])
    print(f"[ml20m] nodes={len(nodes)} leaves={n_leaves} rows={n_rows} "
          f"D_raw={n_dims:,}")

    # Patch module gate constants so build_all()'s internal asserts match ML-20M.
    bm.EXPECTED_N_LEAVES = n_leaves
    bm.EXPECTED_N_ROWS = n_rows
    bm.EXPECTED_N_DIMS = n_dims

    mean_global, global_support, _ = bm.compute_global_stats(C)

    # The "dictionary": user ordinal -> "user<col>" label, never fabricated.
    class UserDict:
        def __len__(self):
            return n_dims

        def __getitem__(self, c):
            return "user%d" % int(c)
    labels = UserDict()

    built = bm.build_all(nodes, rows_by_leaf, C, labels,
                         mean_global, global_support, n_rows)

    themes = built["themes"]
    volumes = built["volumes"]
    tree = built["tree"]
    meta = built["meta"]

    # Leaf exemplars = the real cluster identity (top-3 movie titles) + coherence.
    exemplars = leaf_exemplars(C, rows_by_leaf, nodes, titles)
    num_to_addr = meta["leaf_number_to_address"]
    addr_to_label = {}
    for i, label in enumerate(meta["leaf_order"], start=1):
        addr = num_to_addr[str(i)]
        addr_to_label[addr] = label
    leaf_exemplar_by_label = {}
    coherence_by_label = {}
    for addr, rec in exemplars.items():
        lab = addr_to_label.get(addr)
        if lab is None:
            continue
        leaf_exemplar_by_label[lab] = [
            {"title": e["title"], "movie_ordinal": e["movie_ordinal"],
             "centroid_cosine": round(e["cosine"], 4), "row": e["row"]}
            for e in rec["exemplars"]
        ]
        coherence_by_label[lab] = {
            "mean_member_cosine": round(rec["mean_member_cosine"], 4),
            "centroid_nnz": rec["centroid_nnz"],
            "top3_identical_cosine": rec["top3_identical_cosine"],
        }

    # Per-cell member lists (nearest-centroid movies) for the Voronoi cells. The
    # leaf lists are keyed by the same "L01".. labels as themes/volumes; the root
    # list fills the centre disc. Cell number = movie_ordinal; hover = title.
    members_by_addr = leaf_members(C, rows_by_leaf, nodes, titles,
                                   row_to_movie_id, movie_id_to_imdb)
    leaf_members_by_label = {}
    for addr, mem in members_by_addr.items():
        lab = addr_to_label.get(addr)
        if lab is not None:
            leaf_members_by_label[lab] = mem
    root_member_list = root_members(C, titles, row_to_movie_id, movie_id_to_imdb)

    meta["leaf_members"] = leaf_members_by_label
    meta["root_members"] = root_member_list

    meta["domain"] = DOMAIN_TAG
    meta["orientation"] = {
        "cluster_axis": "movies (MovieLens rows)",
        "feature_axis": "user ordinals (columns)",
        "dictionary": "user<col> (user ordinal; no canonical name)",
    }
    meta["d_raw"] = n_dims
    meta["resident_semantics"] = "L2-row-normalised rating direction"
    meta["leaf_exemplars"] = leaf_exemplar_by_label
    meta["leaf_coherence"] = coherence_by_label
    meta.pop("corpus_sha256", None)

    os.makedirs(OUT_DIR, exist_ok=True)
    json.dump(themes, open(THEMES_PATH, "w"), indent=1)
    json.dump(volumes, open(VOLUMES_PATH, "w"), indent=1)
    json.dump(tree, open(TREE_PATH, "w"), indent=1)
    json.dump(meta, open(META_PATH, "w"), indent=1)

    # leaves.tsv for the report / renderer: leaf_id, population, lift, coherence,
    # top1..3. mean_member_cosine = leaf compactness; centroid_nnz = #users
    # defining the centroid; top3_identical = degenerate tiny-support flag.
    node_by_addr = {a: n for a, n in nodes.items()}
    with open(LEAVES_TSV, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["leaf_id", "address", "population", "log10_lift",
                    "mean_member_cosine", "centroid_nnz", "top3_identical",
                    "top1", "top2", "top3"])
        for i, label in enumerate(meta["leaf_order"], start=1):
            addr = num_to_addr[str(i)]
            nd = node_by_addr[addr]
            exs = leaf_exemplar_by_label.get(label, [])
            coh = coherence_by_label.get(label, {})
            tops = [e["title"] for e in exs] + ["", "", ""]
            w.writerow([label, addr, nd["size"],
                        round(nd["log10_lift"], 3) if nd["log10_lift"] is not None else "",
                        coh.get("mean_member_cosine", ""),
                        coh.get("centroid_nnz", ""),
                        int(coh.get("top3_identical_cosine", False)),
                        tops[0], tops[1], tops[2]])

    print(f"[ml20m] drawn features = {meta['drops']['drawn_feature_count']} "
          f"(dropped {meta['drops']['dropped_feature_count']}, "
          f"budget {meta['drops']['budget']})")
    print("[ml20m] leaf exemplars (top-3 nearest-centroid movies):")
    for lab in meta["leaf_order"]:
        exs = leaf_exemplar_by_label.get(lab, [])
        titles_str = " | ".join(f"{e['title']} ({e['centroid_cosine']})" for e in exs)
        print(f"    {lab}  {titles_str}")
    print(f"[ml20m] wrote 4 JSON files to {OUT_DIR}")
    print(f"[ml20m] wrote {LEAVES_TSV}")


if __name__ == "__main__":
    main()
