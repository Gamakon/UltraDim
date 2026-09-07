# Running with and without a GPU

UltraDim uses the GPU for three operations: UMAP fits, k-means clustering,
and k-means lineages. Everything else runs on the CPU. Without a GPU those
three return an error at once; the rest of the database works. This page
gives the measurements behind that sentence and the two settings that
govern the GPU.

## What was measured

One script, run twice on the same data, calling the 0.4.0 wheel through
`UltraDim(path).call_json(rpc, json)`. Without a GPU: a Linux arm64
container (`python:3.12-slim`), 16 CPUs, 35 GB of memory, no GPU device, no
Vulkan driver, the `manylinux_2_28_aarch64` wheel. With a GPU: an Apple M3
Max under macOS, Metal, the `macosx_11_0_arm64` wheel.

Data: 500 sparse rows of 20,000 dimensions with 32 non-zeros each, drawn
from 20 planted topics; and 500 dense rows of 256 dimensions around 20
centres. Projection width 128, four seeds. Seconds are wall-clock for one
call.

| Step | RPC | No GPU | GPU |
|---|---|---|---|
| Create sparse family | CreateUltradimV23Collection | 0.003 s | 0.016 s |
| Upsert 500 sparse rows | UpsertUltradimV23Points | 0.021 s | 0.100 s |
| Make searchable, window 500 | BuildUltradimV23TrellisIndex | 0.044 s | 0.026 s |
| Search, row 0 as query, top 5 | UltradimV23TrellisTemplateSearch | 0.003 s | 0.002 s |
| Exact ground truth, 30 queries, k = 10 | CreateSparseOracles | 0.004 s | 0.010 s |
| Recall against it | MeasureRecall | 0.071 s | 0.054 s |
| Neighbour graph, k = 15 | BuildUltradimV23KnnGraph | 1.246 s | 1.602 s |
| UMAP fit, 2 components, 50 epochs | FitUltradimV23Umap | error, 0.006 s | 0.262 s |
| Clustering, k = 4 | ClusterUltradimV23 | error, 0.002 s | 0.050 s |
| Create dense family | CreateUltradimV23Collection | 0.002 s | 0.006 s |
| Upsert 500 dense rows | UpsertUltradimV23Points | 0.095 s | 0.134 s |
| Make searchable, window 500 | BuildUltradimV23TrellisIndex | 0.050 s | 0.024 s |
| Dense search, row 0 as query, top 3 | UltradimV23Search | 0.003 s | 0.001 s |
| Density lineage, create and apply | CreateUltradimV23HdbscanLineage, ApplyUltradimV23Hdbscan | 0.022 s | 0.042 s |
| k-means lineage, k = 4 | CreateUltradimV23KmeansLineage | error, 0.004 s | 0.072 s |

Both searches returned the query row at rank 1 with score 1.0 on both
machines, and the next four neighbours were the same rows in the same order.
Recall at 10 over the 30 queries was 1.000 on both, at a median of 2.3 ms
per query without a GPU and 1.7 ms with one.

The UMAP fit was first refused on both machines because the graph's measured
recall, 0.978, was below the 0.99 tolerance the fit applies. That refusal is
about the graph, not the GPU. Rerun with `"force": true`, the fit ran on the
GPU machine and failed on the other.

## The error without a GPU

The three failing calls return in under 10 ms with a `RuntimeError` carrying
this text:

```
Internal error: wgpu kmeans init: GpuDeviceUnavailable("No GPU adapter available for 'Rotating-key spherical Lloyd': NotFound { active_backends: Backends(0x0), requested_backends: Backends(NOOP | VULKAN | GL | METAL | DX12 | BROWSER_WEBGPU), supported_backends: Backends(VULKAN | GL), no_fallback_backends: Backends(0x0), no_adapter_backends: Backends(0x0), incompatible_surface_backends: Backends(0x0) }. Check drivers and Metal/Vulkan/DX12 support.")
```

There is no CPU fallback for these three. The family stays usable: a search
on it after the failed call returned its neighbours. On Linux the wheel finds
a GPU through Vulkan, so a GPU machine needs the vendor's Vulkan driver
installed. On macOS it uses Metal. The UMAP fit has one initialisation, the
annealed hierarchical one, on the GPU; the spectral and random ones return
"not implemented" on both machines.

## Two settings

Both are read from the environment once, at the first GPU call in a process.
On a machine with no GPU neither has any effect.

**`ULTRADIM_GPU_POLL_TIMEOUT_SECS`**, whole seconds, default 90. How long a
UMAP fit waits for the GPU to finish one submitted batch of work before it
treats the device as lost and returns an error instead of blocking for ever.
The default is twice the 45 s that one epoch is expected to take at most on
an Apple M-series GPU. Set it higher only on a GPU much slower than that. A
value of 0 removes the limit, and a hung GPU then hangs the calling thread.
The setting applies to the UMAP fit path only; clustering does not read it.

**`ULTRADIM_GPU_BUFFER_LIMIT_GB`**, gigabytes as a decimal, 1 GB being 2^30
bytes, default two-thirds of the machine's memory. The largest single buffer
the engine will allocate on the GPU. Clustering and k-means lineages use the
value as given. UMAP fits reduce it further to what the GPU adapter permits,
because on a machine with unified memory two-thirds of RAM is not a GPU
bound. A value below 0.25 is raised to 0.25. Raise it when a UMAP fit or a
clustering call refuses with a message naming this variable; lower it to
leave GPU memory for other programs.

A value that does not parse, or is not above zero, falls back to the default.
Measured with `ULTRADIM_GPU_BUFFER_LIMIT_GB=abc` and
`ULTRADIM_GPU_POLL_TIMEOUT_SECS=xyz`: every call behaved as with the
defaults, and nothing was printed.

## How to tell whether a GPU was found

The wheel prints nothing. `RUST_LOG` has no effect: with `RUST_LOG=trace` on
both machines, not one line came from the engine. The only sign is the
response of a GPU call. The smallest such call is clustering on a family
with a few rows; it does not need to be searchable first.

```python
import json, ultradim
db = ultradim.UltraDim("./db")
db.call_json("CreateUltradimV23Collection", json.dumps({
    "name": "gpu_check", "source_dim": 64, "projection_dim": 16, "seeds": [1],
    "sparse_substrate": True, "max_nnz_per_row": 8}))
db.call_json("UpsertUltradimV23Points", json.dumps({
    "name": "gpu_check", "batch": {"row_ids": [0, 1, 2, 3],
    "sparse_vectors": [{"indices": [i], "values": [1.0]} for i in range(4)]}}))
try:
    db.call_json("ClusterUltradimV23", json.dumps(
        {"name": "gpu_check", "num_clusters": 2, "max_cycles": 1}))
    print("GPU found")
except RuntimeError as e:
    print("no GPU" if "GpuDeviceUnavailable" in str(e) else e)
```

Measured: "no GPU" in the container after 0.002 s, "GPU found" on the M3 Max
after 0.022 s.
