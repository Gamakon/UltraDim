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
# # The RPC list, error messages, and the automatic tuner
#
# UltraDim has one calling convention. Every operation is a named RPC that
# takes its fields as JSON and answers in JSON. This example lists the RPCs
# the wheel exposes, shows what an error looks like, and runs the automatic
# tuner on a sample of sparse data to choose index settings that meet a
# recall requirement.
#
# What you need: the UltraDim wheel. No GPU is needed for this example.
# It runs in about a minute.
#
# This file is a Python script and a notebook. Run it as a script, or open
# it as a notebook with `jupytext --to ipynb 03_call_json_and_capabilities.py`.

# %%
import json
import tempfile
import time

import numpy as np

import ultradim
from ultradim.autotune import SparseRow, autotune


def in_notebook():
    """True inside a Jupyter kernel, False when run as a script."""
    try:
        from IPython import get_ipython
        return type(get_ipython()).__name__ == "ZMQInteractiveShell"
    except ImportError:
        return False


IN_NOTEBOOK = in_notebook()


def rpc(db, rpc_name, **fields):
    return json.loads(db.call_json(rpc_name, json.dumps(fields)))


path = tempfile.mkdtemp(prefix="ultradim_rpcs_")
db = ultradim.UltraDim(path)
print("wheel version:", ultradim.__version__, "| notebook:", IN_NOTEBOOK)

# %% [markdown]
# ## 1. Every RPC the wheel exposes
#
# `capabilities()` returns the names. There are 204. The names are
# descriptive, so a count of the names that contain a word is a rough map
# of what the engine does: search, UMAP maps, density clustering, k-means,
# reservoir networks, and text embedding. The full list, with each RPC's
# fields, is in the user guide.

# %%
names = db.capabilities()
print("RPC count:", len(names))
groups = {"search": "Search", "umap": "Umap", "hdbscan": "Hdbscan",
          "k-means": "Kmeans", "esn": "Esn", "bert": "Bert"}
for label, needle in groups.items():
    print(f"  {label:8s}: {sum(needle in n for n in names)}")
print("first ten names:", sorted(names)[:10])

# %% [markdown]
# ## 2. A call through `call_json`
#
# `HealthCheck` is the smallest RPC. The pattern is the same for all 204:
# the name, a JSON object of fields, a JSON object back.

# %%
print("HealthCheck:", rpc(db, "HealthCheck", service="ultradim"))

# %% [markdown]
# ## 3. What an error looks like
#
# A call that cannot be carried out raises `RuntimeError`, and the message
# says what to fix: an RPC name that does not exist, a field name that is
# misspelt, a family that has not been created. Catch the exception where
# you want to recover; let it propagate where you do not.

# %%
for rpc_name, fields in (("NoSuchRpc", {}),
                         ("HealthCheck", {"servce": "ultradim"}),
                         ("GetUltradimV23CollectionInfo", {"name": "missing"})):
    try:
        rpc(db, rpc_name, **fields)
    except RuntimeError as err:
        print(f"error from {rpc_name}: {str(err).split(' (')[0]}")

# %% [markdown]
# ## 4. The automatic tuner
#
# An index has settings, and the right settings depend on the data. The
# tuner takes a sample of your rows and a recall requirement, tries
# settings in order, measures recall against exact brute force for each,
# and stops at the first that meets the requirement. What comes back is the
# settings to use when you create the family, the recall they measured,
# and a verdict in words.
#
# The sample here is 1,000 planted sparse rows: 20 topics, each owning a
# pool of 36 dimensions in a space of 20,000, and each row drawing 30 of
# its 32 non-zeros from its topic's pool. The requirement is recall at 10
# of 0.99, measured over 200 queries. On your own data, pass a sample of a
# few thousand rows in the same `SparseRow` form.

# %%
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

# %% [markdown]
# ## 5. Using the answer
#
# `result.best` holds the fields to pass to `CreateUltradimV23Collection`.
# The recall beside it was measured on your sample against exact answers,
# so it is a number about your data, not a default. The tuning guide
# covers what each setting does and how to read the verdict when the
# requirement is not met.
