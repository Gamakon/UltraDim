"""UltraDim quickstart: a dense family in one short script.

Create a family, insert 200 vectors, make the family searchable, and search
with the first stored vector. Everything runs inside this Python process.

Run:
    python3.12 docs/examples/01_dense_quickstart.py
"""

import json
import tempfile

import numpy as np

import ultradim


def rpc(db, rpc_name, **fields):
    """Call one RPC by name. Fields go in as JSON, the answer comes back as a dict."""
    return json.loads(db.call_json(rpc_name, json.dumps(fields)))


def hits(response):
    """Flatten a search response to (row id, score) pairs."""
    return [(r["id"]["point_id_options"]["Num"], round(r["score"], 4))
            for r in response["result"]]


def planted_vectors(n_rows=200, dim=256, n_groups=20, seed=11):
    """Unit vectors in 20 groups: 0.8 of a group centre plus 0.2 of noise."""
    rng = np.random.default_rng(seed)
    centres = rng.standard_normal((n_groups, dim)).astype(np.float32)
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    rows = []
    for i in range(n_rows):
        noise = rng.standard_normal(dim).astype(np.float32)
        noise /= np.linalg.norm(noise)
        v = 0.8 * centres[i % n_groups] + 0.2 * noise
        v /= np.linalg.norm(v)
        rows.append([float(x) for x in v])
    return rows


def main():
    path = tempfile.mkdtemp(prefix="ultradim_quickstart_")
    db = ultradim.UltraDim(path)
    print("wheel version:", ultradim.__version__)
    print("RPC count    :", len(db.capabilities()))

    vectors = planted_vectors()

    # 1. Create a dense family. name, source_dim, projection_dim and seeds are required.
    created = rpc(db, "CreateUltradimV23Collection",
                  name="quickstart", source_dim=256, projection_dim=128,
                  seeds=[11, 22, 33, 44], sparse_substrate=False)
    print("create       :", created["success"], created["full_collection"])

    # 2. Insert the vectors. Row ids start at 0 and continue without gaps.
    inserted = rpc(db, "UpsertUltradimV23Points", name="quickstart",
                   batch={"row_ids": list(range(len(vectors))),
                          "vectors": [{"data": v} for v in vectors]})
    print("upsert       :", inserted["points_inserted"], "rows")

    # 3. Make the family searchable (build the index).
    built = rpc(db, "BuildUltradimV23TrellisIndex", name="quickstart")
    print("build        :", built["graph_nodes"], "nodes,",
          round(built["build_ms"], 1), "ms")

    # 4. Search with the first stored vector. It finds itself at score 1.0.
    found = rpc(db, "UltradimV23Search", name="quickstart",
                query={"data": vectors[0]}, top_k=5)
    print("top-5        :", hits(found))
    print("timing (ms)  :", round(found["stats"]["total_ms"], 3))


if __name__ == "__main__":
    main()
