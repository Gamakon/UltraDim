# UltraDim User Guide

UltraDim is a vector database that runs inside your Python process. You
import it, open a directory, and call it. There is no server to start.

It is built for wide vectors: dense vectors of a few hundred to many
thousand dimensions, and sparse vectors over a space of millions of
dimensions with a few dozen non-zeros each. Search is by cosine
similarity, and every score you get back is the exact cosine between your
query and the stored vector.

This guide is for a scientist who has the wheel and nothing else. Every
code block was run against wheel 0.4.0, and the output shown is what it
printed. The four scripts in `examples/` hold the same code. Each script is also a notebook: the executed notebook, with its outputs, is beside it as `.ipynb`, and `jupytext --to ipynb` regenerates it from the script.

## Contents

1. [Install](#1-install)
2. [A first family](#2-a-first-family)
3. [Core concepts](#3-core-concepts)
4. [Worked example: a sparse family, end to end](#4-worked-example-a-sparse-family-end-to-end)
5. [Measuring recall](#5-measuring-recall)
6. [Maps: kNN graph and UMAP](#6-maps-knn-graph-and-umap)
7. [Clustering](#7-clustering)
8. [The full RPC list](#8-the-full-rpc-list)
9. [The auto-tuner](#9-the-auto-tuner)
10. [Further reading](#10-further-reading)

## 1. Install

The wheel needs Python 3.12. There is one wheel per platform:

| Platform | Wheel |
|---|---|
| macOS, Apple silicon | `UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl` |
| Linux, arm64 | `UltraDim-0.4.0-cp312-cp312-manylinux_2_28_aarch64.whl` |
| Linux, x86_64 | `UltraDim-0.4.0-cp312-cp312-manylinux_2_28_x86_64.whl` |

Install by path. numpy is a declared dependency and comes with it.

```bash
python3.12 -m pip install ./UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl
```

Check the install:

```python
import ultradim
db = ultradim.UltraDim("./my_first_db")
print(ultradim.__version__)       # 0.4.0
print(len(db.capabilities()))     # 204
```

The engine, its storage and its GPU code are compiled into the wheel. On
macOS it uses the GPU through Metal.

The licence text is inside the package at `ultradim/LICENSE`.

## 2. A first family

Full script: [`examples/01_dense_quickstart.py`](examples/01_dense_quickstart.py).

The object `ultradim.UltraDim(path)` has two methods. `capabilities()`
returns the list of RPC names. `call_json(rpc_name, request_json)` calls
one RPC and returns its response as a JSON string. Everything in this
guide is one of those two calls, so two small helpers cover all of it:

```python
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
```

The corpus is 200 unit vectors of 256 dimensions in 20 groups. Each vector
is 0.8 of its group centre plus 0.2 of noise (the function
`planted_vectors` in the script). Then: create, insert, build, search.

```python
path = tempfile.mkdtemp(prefix="ultradim_quickstart_")
db = ultradim.UltraDim(path)
vectors = planted_vectors()

# 1. Create a dense family. name, source_dim, projection_dim and seeds are required.
created = rpc(db, "CreateUltradimV23Collection",
              name="quickstart", source_dim=256, projection_dim=128,
              seeds=[11, 22, 33, 44], sparse_substrate=False)

# 2. Insert the vectors. Row ids start at 0 and continue without gaps.
inserted = rpc(db, "UpsertUltradimV23Points", name="quickstart",
               batch={"row_ids": list(range(len(vectors))),
                      "vectors": [{"data": v} for v in vectors]})

# 3. Make the family searchable (build the index).
built = rpc(db, "BuildUltradimV23TrellisIndex", name="quickstart")

# 4. Search with the first stored vector. It finds itself at score 1.0.
found = rpc(db, "UltradimV23Search", name="quickstart",
            query={"data": vectors[0]}, top_k=5)
print("top-5        :", hits(found))
print("timing (ms)  :", round(found["stats"]["total_ms"], 3))
```

Output:

```
wheel version: 0.4.0
RPC count    : 204
create       : True udv23_dense/quickstart
upsert       : 200 rows
build        : 200 nodes, 5.9 ms
top-5        : [(0, 1.0), (40, 0.9466), (160, 0.9458), (60, 0.9441), (180, 0.9425)]
timing (ms)  : 0.529
```

Row 0 is the query itself, at score 1.0. The next four rows are 40, 160,
60 and 180. All four are in group 0, because the group is `row % 20`.

The database is the directory. Open the same path later, in a new
process, and the family is there with its index. This was run as a second
process on the directory of the quickstart above:

```python
db = ultradim.UltraDim(path)            # same path, new process
info = rpc(db, "GetUltradimV23CollectionInfo", name="quickstart")
found = rpc(db, "UltradimV23Search", name="quickstart", query={"data": vectors[0]}, top_k=3)
```

```
info {'registered': True, 'substrate': 'dense', 'source_dim': 256, 'projection_dim': 128, 'seeds': [11, 22, 33, 44]}
search after reopen [(0, 1.0), (40, 0.9466), (160, 0.9458)]
```

One process at a time may hold a directory open.

## 3. Core concepts

**Family.** A named collection of vectors, with one width and one kind
(dense or sparse). You create it once and address it by name in every
later call. `DropUltradimV23Collection` deletes it outright.

**Dense and sparse.** A dense family stores full float vectors, sent as
`{"data": [floats]}`. A sparse family stores rows as two lists,
`{"indices": [ints], "values": [floats]}`, with indices ascending and
values of unit length. The engine rejects a sparse row whose squared norm
is off by more than 1e-4. A sparse family is created with
`sparse_substrate=True` and needs `max_nnz_per_row`, the largest number of
non-zeros any row may have. Derive that from your data: the observed
maximum times 1.1, rounded up. A row above the cap is rejected, not
truncated. A sparse family rejects a dense query and a dense family
rejects a sparse one.

**Reduction and seeds.** Each row is reduced to `projection_dim` numbers
before it is indexed, using one or more seeds. More seeds raise
recall. A wider `projection_dim` raises recall. Both are fixed when the
family is created.

**Exact scores.** Every score you get back is the exact cosine between your
query and the stored vector. A score of 1.0 is an exact match. Scores are
comparable across families of any width.

**Settle and window.** A row is searchable once its family has been
settled, which is this guide's word for building the index.
`BuildUltradimV23TrellisIndex` does it in one call. The first settle makes
the family live. After that, every row you insert is searchable as soon
as it is inserted, and the index keeps improving behind the arrivals.
`window` is the number of rows settled per pass. The default is 10,000,
for bulk loading. Pass `window=1` when you insert rows one at a time and
must search for each at once. Pass the size of your batch when you insert
in small batches.

**Row ids.** Row ids start at 0 and must continue without gaps. The
engine refuses a batch whose first id is not the next free one, and the
refusal names the id it expected. Ids are never reused. Replacing a row
writes the new vector at a new id; deleting a row keeps its id retired.

**content_key.** A facet you may store on a row, holding any exact string
you choose. `GetUltradimV23RowByContentKey` returns the row id for a key
with no cosine search, before or after the index exists. It returns the
newest live row that carries the key, so the key stays stable across
replacements. Facets are stored on insert, one map per row, and each value
is an integer or a string.

**Errors.** Every call that fails raises `RuntimeError` with the engine's
message. A misspelt field is refused by name, so a call that returns
success applied every field you sent.

## 4. Worked example: a sparse family, end to end

Full script: [`examples/02_sparse_worked_example.py`](examples/02_sparse_worked_example.py).

The corpus is 2,000 sparse rows over 20,000 dimensions in 20 topics. Each
row has 32 non-zeros. Thirty of them come from a pool of 36 dimensions
shared by the row's topic, so rows in one topic are real neighbours with a
cosine near 0.6, while rows from different topics share almost nothing.
The function `planted_rows` in the script builds it.

### Create and insert with facets

```python
max_nnz = math.ceil(1.10 * max(len(r["indices"]) for r in rows))   # 36

rpc(db, "CreateUltradimV23Collection",
    name="papers", source_dim=20_000, projection_dim=128,
    seeds=[11, 22, 33, 44], sparse_substrate=True, max_nnz_per_row=max_nnz)

facets = [{"fields": {
    "content_key": {"kind": {"KeywordValue": f"paper-{i:04d}"}},
    "topic": {"kind": {"IntValue": i % 20}},
}} for i in range(2_000)]
up = rpc(db, "UpsertUltradimV23Points", name="papers",
         batch={"row_ids": list(range(2_000)), "sparse_vectors": rows, "facets": facets})
```

A string facet is written as `{"kind": {"KeywordValue": "..."}}` and an
integer facet as `{"kind": {"IntValue": n}}`. The facets list must have one
entry per row.

### Identity lookup before the index exists

```python
hit = rpc(db, "GetUltradimV23RowByContentKey", name="papers", content_key="paper-0007")
miss = rpc(db, "GetUltradimV23RowByContentKey", name="papers", content_key="paper-9999")
```

```
lookup paper-0007: True row 7 | paper-9999: False
```

A cosine search at this point is refused. The message reads
`no resident template engine for 'papers' and no persisted manifest`,
which means the family has not been settled yet.

### Make it searchable with window=1

```python
built = rpc(db, "BuildUltradimV23TrellisIndex", name="papers", window=1)
```

```
build: 2000 nodes in 3.1 s
```

### Search, and search with a filter

`exclude_ids` keeps the query row out of its own results.

```python
found = rpc(db, "UltradimV23TrellisTemplateSearch", name="papers",
            sparse_query=rows[0], top_k=5, exclude_ids=[0])

filtered = rpc(db, "UltradimV23TrellisTemplateSearch", name="papers",
               sparse_query=rows[0], top_k=5, exclude_ids=[0],
               template_filter={"must": [{"field": "topic", "cond": {"MatchInt": 0}}]})
```

```
top-5 for row 0: [(520, 0.6218), (60, 0.6011), (460, 0.5988), (1920, 0.5831), (280, 0.5667)]
  same topic: True | candidates: 108
filtered top-5 : [(520, 0.6218), (60, 0.6011), (460, 0.5988), (1920, 0.5831), (280, 0.5667)] | candidates: 100
```

Every hit is a multiple of 20, so every hit is in topic 0, the query's
topic. The filter is applied while candidates are collected, not after. A
condition is `MatchInt`, `MatchKeyword`, or `RangeInt` with `gte` and
`lte`. Several conditions under `must` are all required. A row that lacks
the field fails the condition. A filter that excludes the whole
neighbourhood of the query returns nothing, because the search does not
scan every row.

### Insert more rows: searchable at once

Five more rows go in with ids 2000 to 2004. Their vectors are copies of
rows 0 to 4. No second build is needed.

```python
rpc(db, "UpsertUltradimV23Points", name="papers",
    batch={"row_ids": list(range(2_000, 2_005)), "sparse_vectors": rows[:5], "facets": more})
again = rpc(db, "UltradimV23TrellisTemplateSearch", name="papers", sparse_query=rows[1], top_k=3)
```

```
after 5 more rows, top-3 for row 1: [(1, 1.0), (2001, 1.0), (1421, 0.65)]
```

Row 2001 is the copy of row 1. Both come back at 1.0.

### Replace a row

`ReplaceUltradimV23Point` retires the old row and writes the new vector at
a new id. The content_key moves with it. Omit `facets` to keep the old
row's facets; pass `facets` to replace them outright. Changing the
content_key in a replace is refused. Here row 7 takes row 8's vector.

```python
rep = rpc(db, "ReplaceUltradimV23Point", name="papers", old_row_id=7, sparse_vector=rows[8])
now = rpc(db, "GetUltradimV23RowByContentKey", name="papers", content_key="paper-0007")
```

```
replace row 7 -> new row 2005 | paper-0007 now resolves to row 2005
search with row 8's vector: [(8, 1.0), (2005, 1.0), (248, 0.7246)]
```

The replacement is durable and resolvable by key the moment the call
returns. A cosine search sees it once the settle window flushes, which is
why this family was built with `window=1`.

### Delete a row

```python
gone = rpc(db, "DeleteUltradimV23Point", name="papers", row_id=rep["new_row_id"])
twice = rpc(db, "DeleteUltradimV23Point", name="papers", row_id=rep["new_row_id"])
after = rpc(db, "GetUltradimV23RowByContentKey", name="papers", content_key="paper-0007")
```

```
delete: True | second delete already_deleted: True | paper-0007 found: False
search with row 8's vector: [(8, 1.0), (248, 0.7246), (208, 0.6885)]
```

Deleting twice is safe. The row count does not drop and the id is not
freed. There is no undelete.

Replace and delete are for sparse families. The identity lookup works on
both kinds.

## 5. Measuring recall

Recall@k is the fraction of the true k nearest neighbours that the index
returned. The engine computes the true neighbours itself by a full scan.
`CreateSparseOracles` writes them to a file and returns its path;
`MeasureRecall` reads that file and grades the index. Despite the name, both
accept a dense family too.

```python
oracle = rpc(db, "CreateSparseOracles", name="papers", query_ids=list(range(50)), top_k=10)
for seeds in ([11, 22, 33, 44], [11, 22]):
    rec = rpc(db, "MeasureRecall", name="papers", oracle_path=oracle["artifact_path"],
              k=10, exclude_self=True, use_template=True, active_seeds=seeds)
```

```
oracle: 50 queries over 2005 rows
recall@10 with 4 seeds: 1.0000  p50 1.36 ms  p95 1.57 ms
recall@10 with 2 seeds: 1.0000  p50 1.31 ms  p95 1.43 ms
```

Three things to keep:

- `exclude_self=True`. The query row is in the index, so without it the
  row fills one of its own ten slots and recall@10 reads 0.9 at best.
- `active_seeds` is the list of seeds used for each query. It is the
  one retrieval setting `MeasureRecall` passes to the search, and it needs
  no rebuild. Build the family with the most seeds you might want, then
  measure with subsets.
- Report the latency beside the recall. The response carries `p50_ms`,
  `p95_ms` and `mean_ms`.

The oracle's cost is the number of queries times the number of rows, so
hold out a few hundred queries rather than grading every row. A query id
that has been replaced or deleted is refused, so build the oracle before
you retire rows, or choose ids that are still live.

## 6. Maps: kNN graph and UMAP

A map needs a settled family and a stored k-nearest-neighbour graph.
Build the graph first and pass its id to the fit.

```python
graph = rpc(db, "BuildUltradimV23KnnGraph", name="papers", k=15, append=False)
fit = rpc(db, "FitUltradimV23Umap", name="papers", graph_id=graph["graph_id"],
          n_components=2, n_neighbors=15, n_epochs=50, umap_seed=7, deterministic=True)
emb = rpc(db, "GetUltradimV23UmapEmbedding", name="papers", umap_id=fit["umap_id"],
          limit=3, offset_ordinal=0)
placed = rpc(db, "TransformUltradimV23Umap", name="papers", umap_id=fit["umap_id"],
             sparse_queries=rows[:2])
```

```
knn graph: umapknn-aeb1969013af643f rows 2005
umap fit: umap-01d4c31c2b0f91d2 epochs 50
first 3 rows on the map: [[1.1, -2.62], [-7.47, 8.0], [-1.41, 0.41]]
rows 0 and 1 placed  : [[1.09, -2.66], [-7.44, 7.9]]
```

`embeddings` comes back as one flat list, row after row, with
`n_components` numbers per row. The script reshapes it. The embedding call
is paged: pass the response's `next_offset_ordinal` back as
`offset_ordinal` for the next page.

`TransformUltradimV23Umap` places new points on an existing map without
refitting. It takes `sparse_queries` for a sparse family or
`dense_queries` (a list of `{"data": [...]}`) for a dense one. Rows 0 and
1, placed as new points, are within 0.1 of their fitted positions.

The fit's enum fields are integers on the wire: `init` is 0 for annealed,
1 for spectral, 2 for random; `output_metric` is 0 for euclidean, 1 for
spherical. The defaults are annealed and euclidean.

When the fit is asked to build its own graph, it measures that graph's
recall against a sample and refuses below 0.99, naming the recall it
measured. Build the graph yourself and pass `graph_id`, as above, or raise
`k`.

Other map RPCs: `GetUltradimV23UmapInfo`, `ListUltradimV23UmapModels`,
`DropUltradimV23Umap`, and `IncrementalFitUltradimV23Umap` for folding a
new batch into a fitted map. The density-clustering RPCs whose names
contain `Hdbscan` work over the same graph.

### A living map, animated

Full script: [`examples/04_living_map_animation.py`](examples/04_living_map_animation.py).

The script is the method behind the foreign-exchange animation in the
README, on a synthetic stream of 1,500 rows so that it runs in about a
minute. It fits a base map on the first 500 rows, folds the rest in 25 at a
time with `IncrementalFitUltradimV23Umap`, refits over everything so far
whenever the rows folded in since the last fit exceed one fifth of it, and
renders one frame per retained map, each aligned to the frame before it by
a rigid transform on the rows the two share. It writes `living_map.gif`, and an MP4 beside it
if ffmpeg is installed. Nothing is shown on screen.

## 7. Clustering

`ClusterUltradimV23` runs spherical k-means over the reduced rows. It
is sparse-only and refuses a dense family by name.

```python
cl = rpc(db, "ClusterUltradimV23", name="papers", num_clusters=4, max_cycles=25)
```

```
cluster sizes: [515, 410, 588, 492] cycles 25 mean_log10_p_real -473.4
```

The response holds `assignments` (one cluster per row, in `row_id_order`),
`cluster_sizes`, `cycles`, `converged`, and `mean_log10_p_real`. The last
is the cluster quality: the log10 of the probability that clusters this
tight arise by chance on a sphere of this dimension, corrected for the
dimension. More negative is tighter. Do not judge clusters by agreement
with your own labels at this width; k-means at this width has a noise
floor that does not affect search.

The RPCs whose names contain `Kmeans` keep a model and apply it later:
`CreateUltradimV23KmeansLineage` fits a first time window and saves the
model, `AdvanceUltradimV23KmeansLineage` fits the next window warm-started
from the last, `ApplyUltradimV23Kmeans` scores rows against a saved model,
and `GetUltradimV23KmeansMigrationGraph` reports how mass moved between two
windows. Rows enter a window by the `event_ts` you pass at insert, in
milliseconds since the epoch.

## 8. The full RPC list

Full script: [`examples/03_call_json_and_capabilities.py`](examples/03_call_json_and_capabilities.py).

`db.capabilities()` returns every RPC name the wheel exposes. Anything not
shown in this guide is reached the same way, by name through `call_json`.

```python
names = db.capabilities()
print("RPC count:", len(names))
for label, needle in {"search": "Search", "umap": "Umap", "hdbscan": "Hdbscan",
                      "k-means": "Kmeans", "esn": "Esn", "bert": "Bert"}.items():
    print(f"  {label:8s}: {sum(needle in n for n in names)}")
print("HealthCheck:", rpc(db, "HealthCheck", service="ultradim"))
```

```
RPC count: 204
  search  : 16
  umap    : 7
  hdbscan : 9
  k-means : 5
  esn     : 4
  bert    : 2
HealthCheck: {'status': 1}
```

### Errors

Every failure is a `RuntimeError`. The message is the engine's own.

```python
for rpc_name, fields in (("NoSuchRpc", {}),
                         ("HealthCheck", {"servce": "ultradim"}),
                         ("GetUltradimV23CollectionInfo", {"name": "missing"})):
    try:
        rpc(db, rpc_name, **fields)
    except RuntimeError as err:
        print(f"error from {rpc_name}: {str(err).split(' (')[0]}")
```

```
error from NoSuchRpc: unknown RPC 'NoSuchRpc'
error from HealthCheck: unknown request field(s) [servce] for this RPC — not recognised and NOT applied
error from GetUltradimV23CollectionInfo: Some requested entity was not found: UltraDimV23 collection 'missing' not found
```

The unknown-field message goes on to list the fields the RPC does know,
so a misspelling is found in one call. Sending an RPC one wrong field on
purpose is a quick way to read its field list.

The messages you will meet most:

- `no resident template engine for '<name>'`: the family has not been
  settled. Call `BuildUltradimV23TrellisIndex`.
- `expected row_ids[0]=N`: your batch does not continue from the next free
  id. Use the id the message names.
- A norm message on insert: a sparse row is not unit length. Normalise it.
- `settle produced an EMPTY graph`: no pair of rows is similar enough.
  Give the family real structure before lowering the floor;
  `UltradimV23TrellisTemplateSettle` takes an explicit `floor` for the rare
  corpus that needs one.

### Related RPC names

`UltradimV23Search` and `UltradimV23TrellisTemplateSearch` route to the
same core. The first takes a dense `query`, the second takes
`sparse_query` or `dense_query` plus the filter and breadth settings. The
list also carries RPCs for reservoir networks (`Esn`), text encoders
(`Bert`) and multi-family search; the same `call_json` reaches them.

## 9. The auto-tuner

`ultradim.autotune` finds a family configuration whose measured recall
meets a minimum you set. Give it a sample of your sparse rows. It derives
`max_nnz_per_row` from the sample, builds one family per target width at
eight seeds, writes an oracle, and measures recall over four and eight
active seeds. It stops at the first configuration that meets the minimum. If none
meets it at width 2048 it rebuilds at 4096. It builds real families and
oracles as it goes, so give it a sample of a few thousand rows, not the
whole corpus.

```python
from ultradim.autotune import SparseRow, autotune

sample = [SparseRow(indices=[...], values=[...]), ...]   # 1,000 planted rows in the script
result = autotune(db, sample, min_recall=0.99, k=10, n_queries=200)
print("best config :", result.best)
print("best recall :", result.best_recall)
print("verdict     :", result.verdict)
```

```
[autotune] 1000 rows, source_dim(D_raw)=19997, derived max_nnz=36, min_recall=0.99, k=10
[autotune] building family autotune_0: proj=2048 seeds=8 (active_seeds swept per-query against this one build)
[autotune]   proj=2048 active_seeds=4 nnz=36 k=10 -> recall 1.0000
[autotune] RECALL REQUIREMENT MET at proj=2048 active_seeds=4 nnz=36 k=10 (recall 1.0000)
autotune took 1.2 s
best config : Config(projection_dim=2048, active_seeds=[101, 202, 303, 404], max_nnz_per_row=36, k=10)
best recall : 1.0
verdict     : met min_recall 0.99 at proj=2048 active_seeds=4 nnz=36 k=10
```

`result.sweep` lists every configuration tried with its recall. The first
`n_queries` rows of the sample are the held-out queries, so the sample
must have more than `n_queries + 10` rows. The families it builds are
named `autotune_0`, `autotune_1`, and stay in the database until you drop
them. When no configuration meets the minimum, `result.best` is the best it
found and `result.verdict` says so, with the whole sweep as evidence.

## 10. Further reading

- [The tuning guide](UltraDim_Tuning_Guide.md): what moves recall, what
  does not, and what to do when recall falls below tolerance.
- [Replacing and deleting a sparse row](SPARSE_UPSERT_SEMANTICS.md): the
  full rules for row ids, facets, retries and durability.
- [The MCP server](../mcp/README.md): the same engine as tools for an
  assistant, with no Python written by you.
