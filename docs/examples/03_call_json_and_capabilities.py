"""UltraDim: the full RPC list, error messages, and the auto-tuner.

Run:
    python3.12 docs/examples/03_call_json_and_capabilities.py
"""

import json
import tempfile
import time

import numpy as np

import ultradim
from ultradim.autotune import SparseRow, autotune


def rpc(db, rpc_name, **fields):
    return json.loads(db.call_json(rpc_name, json.dumps(fields)))


def main():
    path = tempfile.mkdtemp(prefix="ultradim_rpcs_")
    db = ultradim.UltraDim(path)

    # 1. Every RPC name the wheel exposes.
    names = db.capabilities()
    print("RPC count:", len(names))
    groups = {"search": "Search", "umap": "Umap", "hdbscan": "Hdbscan",
              "k-means": "Kmeans", "esn": "Esn", "bert": "Bert"}
    for label, needle in groups.items():
        print(f"  {label:8s}: {sum(needle in n for n in names)}")

    # 2. A health check through call_json.
    print("HealthCheck:", rpc(db, "HealthCheck", service="ultradim"))

    # 3. Three errors. Each is a RuntimeError whose message says what to fix.
    for rpc_name, fields in (("NoSuchRpc", {}),
                             ("HealthCheck", {"servce": "ultradim"}),
                             ("GetUltradimV23CollectionInfo", {"name": "missing"})):
        try:
            rpc(db, rpc_name, **fields)
        except RuntimeError as err:
            print(f"error from {rpc_name}: {str(err).split(' (')[0]}")

    # 4. The auto-tuner on a 1,000-row sample of planted sparse data.
    rng = np.random.default_rng(5)
    topics = [rng.choice(20_000, 36, replace=False) for _ in range(20)]
    sample = []
    for i in range(1_000):
        idx = np.unique(np.concatenate([rng.choice(topics[i % 20], 30, replace=False),
                                        rng.choice(20_000, 2, replace=False)]))
        vals = np.abs(rng.standard_normal(len(idx)).astype(np.float32))
        vals /= np.linalg.norm(vals)
        order = np.argsort(idx)
        sample.append(SparseRow(indices=[int(x) for x in idx[order]],
                                values=[float(x) for x in vals[order]]))
    t0 = time.time()
    result = autotune(db, sample, min_recall=0.99, k=10, n_queries=200)
    print(f"autotune took {time.time() - t0:.1f} s")
    print("best config :", result.best)
    print("best recall :", result.best_recall)
    print("verdict     :", result.verdict)


if __name__ == "__main__":
    main()
