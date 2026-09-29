# ---
# jupyter:
#   jupytext:
#     formats: py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # UltraDim → BloomMap: cluster, then draw the clustering
#
# A BloomMap is a circular phylogram of a hierarchical clustering: a centre, a
# ring of population-sized leaves, and petals carrying each leaf's distinguishing
# features. UltraDim produces the clustering; BloomMap draws it. This example
# runs the clustering here and shows the tree BloomMap consumes. The renderer and
# the finished posters are in the `BloomMap/` folder at the repo root.
#
# Everything below runs against the embedded engine in the wheel — no server.

# %%
import json
import os
import tempfile

import numpy as np
import ultradim

db = ultradim.UltraDim(tempfile.mkdtemp(prefix="ultradim_bloommap_"))


def rpc(rpc_name, **fields):
    return json.loads(db.call_json(rpc_name, json.dumps(fields)))


# %% [markdown]
# ## 1. A corpus with planted structure
#
# 1,200 sparse rows in 60 planted topics of 20, each row 16 non-zeros in a
# 5,000-wide space, values drawn from U(0.5, 1.5) so cosines are distinct. A real
# corpus — molecules, films, baskets — has this shape: many rows, a wide sparse
# feature space, and group structure to recover.

# %%
D, N, NNZ, N_GROUPS = 5_000, 1_200, 16, 60
GROUP_SIZE = N // N_GROUPS
rng = np.random.default_rng(0)
templates = [np.sort(rng.choice(D, NNZ, replace=False)) for _ in range(N_GROUPS)]
labels = np.repeat(np.arange(N_GROUPS), GROUP_SIZE)


def make_row(group, r):
    idx = templates[group].copy()
    vals = r.uniform(0.5, 1.5, len(idx)).astype(np.float32)
    vals /= np.linalg.norm(vals)
    return {"indices": [int(i) for i in idx], "values": [float(v) for v in vals]}


rows = [make_row(labels[i], rng) for i in range(N)]
print(f"{N} rows, {N_GROUPS} planted groups, {D}-dim sparse space")

# %% [markdown]
# ## 2. Ingest and cluster hierarchically
#
# `HierarchicalClusterUltradimV23` splits the corpus into a tree. `max_depth`
# bounds the depth; `min_pop` is the smallest node it will split. Each node
# carries its population, its level, and a lift score — how much tighter the node
# is than chance.

# %%
FAMILY = "bloommap_demo"
rpc("CreateUltradimV23Collection", name=FAMILY, source_dim=D, projection_dim=128,
    seeds=[11, 22], sparse_substrate=True, max_nnz_per_row=NNZ)
rpc("UpsertUltradimV23Points", name=FAMILY,
    batch={"row_ids": list(range(N)), "sparse_vectors": rows})

tree = rpc("HierarchicalClusterUltradimV23", name=FAMILY, max_depth=5, min_pop=10)
print(f"nodes      : {tree['num_nodes']}")
print(f"leaves     : {tree['num_leaves']}")
print(f"max level  : {tree['max_level']}")
print(f"coverage   : {tree['leaf_coverage']} of {N} rows")

# %% [markdown]
# ## 3. The tree BloomMap draws
#
# Each node has an `address` (its path from the root), a `parent`, a `level`, a
# `size` (population), and `log10_lift`. BloomMap maps size to a
# leaf's area and lift to its colour. This is the `nodes` list the
# `BloomMap/process/build_bloommap_json_*.py` producers read.

# %%
nodes = tree["nodes"]
root = nodes[0]
print(f"root : addr={root['address']!r} size={root['size']} level={root['level']}")
leaves = [n for n in nodes if n.get("is_leaf")]
print(f"\n{len(leaves)} leaves; the five largest:")
for n in sorted(leaves, key=lambda x: -x["size"])[:5]:
    print(f"  addr={n['address']:>6}  size={n['size']:>4}  level={n['level']}  "
          f"log10_lift={n['log10_lift']:.2f}")

# %% [markdown]
# ## 4. From here to a poster
#
# For ChEMBL and MovieLens the steps were:
#
# 1. Cluster it as above (the `BloomMap/process/hseg_*.py` scripts do this against
#    the full ChEMBL and MovieLens corpora over the client-server gRPC API).
# 2. Run a `BloomMap/process/build_bloommap_json_*.py` producer to turn the tree
#    and the sparse corpus into the four `bloommap.*.json` files.
# 3. Render them with the D3 code in `BloomMap/renderer/` — an SVG/PNG poster, or
#    an interactive page you open in a browser.
#
# The finished ChEMBL (50,000 and 500,000 molecules at 30,000,000 dimensions) and
# MovieLens posters, and the interactive Chemotype Galaxy, are in `BloomMap/`.
# See `BloomMap/README.md`.

# %%
# Write this demo tree to disk, in the shape a producer reads.
out = os.path.join(tempfile.mkdtemp(prefix="bloommap_tree_"), "demo_tree.json")
with open(out, "w") as f:
    json.dump({"num_nodes": tree["num_nodes"], "num_leaves": tree["num_leaves"],
               "nodes": nodes}, f, indent=1)
print(f"tree written to {out}")
