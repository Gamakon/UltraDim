"""UltraDim worked example: a sparse family, end to end.

The corpus is 2,000 sparse rows over 20,000 dimensions, in 20 planted topics.
Each row has 32 non-zeros; 30 of them come from a 36-dimension pool shared
by its topic, so rows in the same topic are real neighbours.

The script runs:
    create -> upsert with facets -> identity lookup before the index exists
    -> make searchable (window=1) -> search -> filtered search
    -> insert more rows and search for them with no rebuild
    -> exact oracle -> measure recall -> kNN graph -> UMAP fit -> transform
    -> cluster -> replace a row -> delete a row

Run:
    python3.12 docs/examples/02_sparse_worked_example.py
"""

import json
import math
import tempfile
import time

import numpy as np

import ultradim

D_RAW = 20_000       # width of the sparse space
N_ROWS = 2_000
N_TOPICS = 20
NNZ = 32             # non-zeros per row
POOL, SHARED = 36, 30


def rpc(db, rpc_name, **fields):
    return json.loads(db.call_json(rpc_name, json.dumps(fields)))


def hits(response):
    return [(r["id"]["point_id_options"]["Num"], round(r["score"], 4))
            for r in response["result"]]


def planted_rows(seed=5):
    """Sparse rows as {"indices": [...], "values": [...]}, values unit length."""
    rng = np.random.default_rng(seed)
    topics = [rng.choice(D_RAW, POOL, replace=False) for _ in range(N_TOPICS)]
    rows = []
    for i in range(N_ROWS):
        topic = topics[i % N_TOPICS]
        idx = np.unique(np.concatenate([
            rng.choice(topic, SHARED, replace=False),
            rng.choice(D_RAW, NNZ - SHARED, replace=False),
        ]))
        vals = np.abs(rng.standard_normal(len(idx)).astype(np.float32))
        vals /= np.linalg.norm(vals)
        order = np.argsort(idx)
        rows.append({"indices": [int(x) for x in idx[order]],
                     "values": [float(x) for x in vals[order]]})
    return rows


def main():
    rows = planted_rows()
    max_nnz = math.ceil(1.10 * max(len(r["indices"]) for r in rows))
    print(f"corpus: {N_ROWS} rows x {D_RAW} dims, max_nnz_per_row={max_nnz}")

    path = tempfile.mkdtemp(prefix="ultradim_sparse_")
    db = ultradim.UltraDim(path)
    name = "papers"

    # 1. Create a sparse family.
    rpc(db, "CreateUltradimV23Collection",
        name=name, source_dim=D_RAW, projection_dim=128,
        seeds=[11, 22, 33, 44], sparse_substrate=True, max_nnz_per_row=max_nnz)

    # 2. Insert every row with two facets: a content_key and an integer topic.
    facets = [{"fields": {
        "content_key": {"kind": {"KeywordValue": f"paper-{i:04d}"}},
        "topic": {"kind": {"IntValue": i % N_TOPICS}},
    }} for i in range(N_ROWS)]
    up = rpc(db, "UpsertUltradimV23Points", name=name,
             batch={"row_ids": list(range(N_ROWS)),
                    "sparse_vectors": rows, "facets": facets})
    print("upsert:", up["points_inserted"], "rows")

    # 3. Identity lookup works before the index exists.
    hit = rpc(db, "GetUltradimV23RowByContentKey", name=name, content_key="paper-0007")
    miss = rpc(db, "GetUltradimV23RowByContentKey", name=name, content_key="paper-9999")
    print("lookup paper-0007:", hit["found"], "row", hit["row_id"],
          "| paper-9999:", miss["found"])

    # 4. Make the family searchable, one settle pass per record.
    t0 = time.time()
    built = rpc(db, "BuildUltradimV23TrellisIndex", name=name, window=1)
    print(f"build: {built['graph_nodes']} nodes in {time.time() - t0:.1f} s")

    # 5. Search with row 0, excluding row 0 itself. Every hit is topic 0.
    found = rpc(db, "UltradimV23TrellisTemplateSearch", name=name,
                sparse_query=rows[0], top_k=5, exclude_ids=[0])
    print("top-5 for row 0:", hits(found))
    print("  same topic:", all(i % N_TOPICS == 0 for i, _ in hits(found)),
          "| candidates:", found["stats"]["candidates_pooled"])

    # 6. The same search with a facet filter on topic 0.
    filtered = rpc(db, "UltradimV23TrellisTemplateSearch", name=name,
                   sparse_query=rows[0], top_k=5, exclude_ids=[0],
                   template_filter={"must": [{"field": "topic", "cond": {"MatchInt": 0}}]})
    print("filtered top-5 :", hits(filtered),
          "| candidates:", filtered["stats"]["candidates_pooled"])

    # 7. Insert five more rows. They are searchable at once, with no rebuild.
    more = [{"fields": {"content_key": {"kind": {"KeywordValue": f"paper-{N_ROWS + i:04d}"}}}}
            for i in range(5)]
    rpc(db, "UpsertUltradimV23Points", name=name,
        batch={"row_ids": list(range(N_ROWS, N_ROWS + 5)),
               "sparse_vectors": rows[:5], "facets": more})
    again = rpc(db, "UltradimV23TrellisTemplateSearch", name=name,
                sparse_query=rows[1], top_k=3)
    print("after 5 more rows, top-3 for row 1:", hits(again))

    # 8. Exact ground truth for 50 queries, then recall of the index against it.
    oracle = rpc(db, "CreateSparseOracles", name=name,
                 query_ids=list(range(50)), top_k=10)
    print("oracle:", oracle["n_queries"], "queries over", oracle["n_committed"], "rows")
    for seeds in ([11, 22, 33, 44], [11, 22]):
        rec = rpc(db, "MeasureRecall", name=name, oracle_path=oracle["artifact_path"],
                  k=10, exclude_self=True, use_template=True, active_seeds=seeds)
        print(f"recall@10 with {len(seeds)} seeds: {rec['recall_at_k']:.4f}"
              f"  p50 {rec['p50_ms']:.2f} ms  p95 {rec['p95_ms']:.2f} ms")

    # 9. A kNN graph, a 2-D UMAP map, and placing new points on the map.
    graph = rpc(db, "BuildUltradimV23KnnGraph", name=name, k=15, append=False)
    print("knn graph:", graph["graph_id"], "rows", graph["rows_processed"])
    fit = rpc(db, "FitUltradimV23Umap", name=name, graph_id=graph["graph_id"],
              n_components=2, n_neighbors=15, n_epochs=50, umap_seed=7, deterministic=True)
    print("umap fit:", fit["umap_id"], "epochs", fit["epochs_run"])
    emb = rpc(db, "GetUltradimV23UmapEmbedding", name=name, umap_id=fit["umap_id"],
              limit=3, offset_ordinal=0)
    coords = emb["embeddings"]
    print("first 3 rows on the map:",
          [[round(x, 2) for x in coords[i:i + 2]] for i in range(0, 6, 2)])
    placed = rpc(db, "TransformUltradimV23Umap", name=name, umap_id=fit["umap_id"],
                 sparse_queries=rows[:2])
    print("rows 0 and 1 placed  :",
          [[round(x, 2) for x in placed["embeddings"][i:i + 2]] for i in range(0, 4, 2)])

    # 10. Spherical k-means into 4 clusters.
    cl = rpc(db, "ClusterUltradimV23", name=name, num_clusters=4, max_cycles=25)
    print("cluster sizes:", cl["cluster_sizes"], "cycles", cl["cycles"],
          "mean_log10_p_real", round(cl["mean_log10_p_real"], 1))

    # 11. Replace row 7's vector. The replacement gets a new row id; the key follows it.
    rep = rpc(db, "ReplaceUltradimV23Point", name=name, old_row_id=7, sparse_vector=rows[8])
    now = rpc(db, "GetUltradimV23RowByContentKey", name=name, content_key="paper-0007")
    print("replace row 7 -> new row", rep["new_row_id"],
          "| paper-0007 now resolves to row", now["row_id"])
    print("search with row 8's vector:", hits(rpc(
        db, "UltradimV23TrellisTemplateSearch", name=name, sparse_query=rows[8], top_k=3)))

    # 12. Delete the replacement. The row id is not reused.
    gone = rpc(db, "DeleteUltradimV23Point", name=name, row_id=rep["new_row_id"])
    twice = rpc(db, "DeleteUltradimV23Point", name=name, row_id=rep["new_row_id"])
    after = rpc(db, "GetUltradimV23RowByContentKey", name=name, content_key="paper-0007")
    print("delete:", gone["success"], "| second delete already_deleted:",
          twice["was_already_deleted"], "| paper-0007 found:", after["found"])
    print("search with row 8's vector:", hits(rpc(
        db, "UltradimV23TrellisTemplateSearch", name=name, sparse_query=rows[8], top_k=3)))


if __name__ == "__main__":
    main()
