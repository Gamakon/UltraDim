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
# # Quickstart: a dense family
#
# Four calls: create a family, insert 200 vectors, build the index, search.
# Everything runs inside this Python process, in a directory on disk. There
# is no server to start and no port to open.
#
# What you need: the UltraDim wheel. No GPU is needed for this example. It
# runs in a few seconds.
#
# This file is a Python script and a notebook. Run it as a script, or open
# it as a notebook with `jupytext --to ipynb 01_dense_quickstart.py`.

# %%
import json
import tempfile

import numpy as np

import ultradim


def in_notebook():
    """True inside a Jupyter kernel, False when run as a script."""
    try:
        from IPython import get_ipython
        return type(get_ipython()).__name__ == "ZMQInteractiveShell"
    except ImportError:
        return False


IN_NOTEBOOK = in_notebook()


def rpc(db, rpc_name, **fields):
    """Call one RPC by name. Fields go in as JSON, the answer comes back as a dict."""
    return json.loads(db.call_json(rpc_name, json.dumps(fields)))


def hits(response):
    """A search answer as (row id, score) pairs."""
    return [(r["id"]["point_id_options"]["Num"], round(r["score"], 4))
            for r in response["result"]]


path = tempfile.mkdtemp(prefix="ultradim_quickstart_")
db = ultradim.UltraDim(path)
print("wheel version:", ultradim.__version__, "| notebook:", IN_NOTEBOOK)
print("RPC count    :", len(db.capabilities()))

# %% [markdown]
# ## 1. The vectors
#
# 200 unit vectors of 256 dimensions in 20 planted groups. Each vector is
# 0.8 of its group's centre plus 0.2 of noise, so vectors of one group are
# neighbours by construction and the search below has a known right
# answer.

# %%
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


vectors = planted_vectors()
print(len(vectors), "vectors of", len(vectors[0]), "dimensions")

# %% [markdown]
# ## 2. Create the family
#
# A family holds vectors of one width. `name`, `source_dim`,
# `projection_dim` and `seeds` are required. `source_dim` is the width of
# your vectors. `projection_dim` and `seeds` are the index's settings. For
# data of real width the setting to test first is 2048 with four seeds; it
# has served almost every corpus indexed to date. This toy corpus is 256
# wide, so 128 is used here. The tuning guide covers the procedure, and the
# automatic tuner in example 03 runs it for you from a sample of your data.

# %%
created = rpc(db, "CreateUltradimV23Collection",
              name="quickstart", source_dim=256, projection_dim=128,
              seeds=[11, 22, 33, 44], sparse_substrate=False)
print("create       :", created["success"], created["full_collection"])

# %% [markdown]
# ## 3. Insert the vectors
#
# Row ids start at 0 and continue without gaps. A batch is a list of row
# ids and a list of vectors of the same length.

# %%
inserted = rpc(db, "UpsertUltradimV23Points", name="quickstart",
               batch={"row_ids": list(range(len(vectors))),
                      "vectors": [{"data": v} for v in vectors]})
print("upsert       :", inserted["points_inserted"], "rows")

# %% [markdown]
# ## 4. Build the index
#
# One call makes the family searchable. The answer reports the size of
# the index and the time it took.

# %%
built = rpc(db, "BuildUltradimV23TrellisIndex", name="quickstart")
print("build        :", built["graph_nodes"], "nodes,",
      round(built["build_ms"], 1), "ms")

# %% [markdown]
# ## 5. Search
#
# The query is the first stored vector. It finds itself at a score of 1.0,
# and the other four hits are rows of its own group: rows 20, 40, 60 and
# so on, since row `i` belongs to group `i mod 20`. Scores are true cosines
# against the stored vectors. The answer also carries the time the search
# took.

# %%
found = rpc(db, "UltradimV23Search", name="quickstart",
            query={"data": vectors[0]}, top_k=5)
print("top-5        :", hits(found))
print("same group   :", all(i % 20 == 0 for i, _ in hits(found)))
print("timing (ms)  :", round(found["stats"]["total_ms"], 3))

# %% [markdown]
# ## Next
#
# Example 02 takes a sparse corpus through the rest of the database:
# facets and filters, recall against exact answers, maps, clustering,
# replacing and deleting rows. Example 03 lists every RPC and runs the
# automatic tuner. Example 04 animates a map that grows with a stream.
