# A Guide to Tuning UltraDim

This guide says which settings change the quality of an UltraDim index, which
do not, and what to do when the recall gate refuses your data.

The running example is a family of sparse keys that would not clear the
index's recall gate. The conclusion drawn at the time was that the limit was
a property of the keys. It was not. The projection width was too small, and the
one set of controls that governs projection width had never been changed.

---

## 1. The one idea to hold onto

An UltraDim family compresses each input vector through a set of random
projections before it indexes anything. A raw input of width `source_dim`
is projected down to a key of width `projection_dim`, once per **seed**.
More seeds means more independent views of the same row, combined by a
vote. A wider `projection_dim` means each view keeps more of the original
directions.

If a search cannot find a row's true neighbours, the usual cause is that
the projection has thrown away the distinction between them. The neighbours
were there. The cure is almost always more projection capacity, more seeds
or a wider projection, not more search effort.

---

## 2. The settings that change recall

There are two kinds of setting. Projection settings are fixed when the
family is created and can only be changed by building a fresh family.
Retrieval settings are set per request and cost nothing to sweep.

### 2a. Projection settings, set once at `create_collection`

These are read from your request and frozen into the family.

| Setting | Field | What it governs | To raise recall |
|---|---|---|---|
| `source_dim` | required | The width of your raw input, what the projection projects from. | Fixed by your data. Not a choice. |
| `projection_dim` | required | The width of the projected key the index uses. Standard is 2048. | Increase it, 2048 to 4096. Each view keeps more directions. |
| `seeds` | required | The number of independent random projections. Each seed is one Rademacher projection matrix, one key per row per seed, combined by a vote. | Add seeds, 4 to 8 to 16. More views recover a separation a small set collapses. |
| `max_nnz_per_row` | required for sparse | The most non-zeros a row may carry. A row over the cap is **rejected**, not truncated. | Derive it from your data (§5). A cap set too low rejects real rows. |
| `sparse_substrate` | required | Sparse (CSR) or dense storage. | A choice of storage, not a recall setting. |

Everything else on the create request is ignored on the current build:
`default_top_m`, `default_hnsw_ef`, `hnsw_m`, `hnsw_ef_construct`,
`quantisation`, `projection_mode`, `matrix_type`. The engine fixes them
(top_m 400, hnsw_ef 128, formula projection, Rademacher matrix, no
quantisation). Setting them does nothing. Do not spend a rebuild on a field
the engine does not read.

The request documents a maximum of 8 seeds. The engine checks only that you
supply at least one. More than 8 will run, but the standard configuration
was validated at 8 or fewer, so measure with care beyond that.

### 2b. Retrieval settings, set per request, free to sweep

These go on each `MeasureRecall` call and change nothing in the stored
family.

| Setting | What it governs | To raise recall |
|---|---|---|
| `active_seeds` | Which of the family's seeds vote on each query. Build a family at 16 seeds, then vote over 4, 8 or 16 per request, with no rebuild. | Vote over more of them. |
| `k` | recall@k, how many neighbours you grade against. | A reporting choice, not a fix. |
| `exclude_self` | Whether the query row is excluded from its own results. Set it `true` for a self-query test. | A correctness setting, not a recall one. See the warning below. |

**`top_m` and `hnsw_ef` do nothing on `MeasureRecall` in this build.** The
request accepts them, and the response and the log echo them back, but the
search never reads them. Sweeping them sweeps fields nothing consumes.
Recall will look flat and you will wrongly conclude the projection is at
fault. The serving-time breadth settings (`walk_ef`, `beam_ef`,
`walk_expansions`, `take_per_seed`) do reach the search, but on
`TrellisTemplateSearch`, not through `MeasureRecall`.

**Always set `exclude_self=true` when your query rows are in the index.**
The query row matches itself at rank 1. Without excluding it, recall@10 is
exactly 0.9 for every configuration, because the query fills one of the ten
slots while the exact answer excludes it. A flat 0.9000 across every
configuration is this, not a property of your data.

Because `active_seeds` is per request, one oracle build lets you sweep the
seed count for free (§4). Exhaust it first. It is the strongest recall
setting short of a rebuild.

---

## 3. When the recall gate refuses

UltraDim's UMAP fit refuses to embed a graph whose measured recall is below
0.99. A low-recall graph has the wrong neighbours, so a map drawn on it
draws the wrong structure. The gate is the engine refusing to certify a bad
map. You may override it with `force=true`, which proceeds and logs a
warning, but forcing past a real recall failure publishes a map you have
been told is wrong. Reserve it for the case in §3c.

A refused gate is an instruction. Follow it in this order.

### 3a. First, vote over more seeds. Free.

Build the family at the largest seed count you intend to try, say 16, then
sweep `active_seeds` 4, 8, 16 against a fixed oracle. This needs no rebuild.
The seeds are all present; you are choosing how many vote. If recall climbs
over 0.99, you are done. The neighbours were reachable; you were not voting
over enough views. Because `top_m` and `hnsw_ef` are dead on `MeasureRecall`,
this is the only free setting that moves recall here.

### 3b. If more seeds do not move recall, widen the projection

If voting over 16 seeds instead of 4 leaves recall flat, you have shown the
limit is the projection width, not the number of views. The candidates are
not separable in a 2048-wide key at all. Now, and only now, rebuild with
more projection capacity:

1. Widen `projection_dim`, 2048 to 4096.
2. Re-derive `max_nnz_per_row` from the data if you defaulted it (§5).

Rebuild the family at the wider projection and measure again, sweeping
`active_seeds` against the new oracle. "Recall does not change with the
seed count, so the limit is in the keys" is a statement about the number of
views, and it is exactly the evidence that you must now change the
projection width. The two are different halves of the pipeline. Do not stop
between them.

If your earlier evidence came from sweeping `top_m` or `hnsw_ef` on
`MeasureRecall` and seeing no change, that is not evidence of anything. Those
settings are dead on this build. Re-establish the result by sweeping
`active_seeds`, which the search does read.

### 3c. Only after both sweeps is a limit in the keys

If recall still will not clear 0.99 after sweeping seeds and
`projection_dim`, then the limit is a property of the keys. Report it with
the sweep as evidence, or proceed with `force=true` and record the measured
recall. A limit reported without the projection sweep is an unfinished
experiment.

---

## 4. Measuring recall natively

The engine measures its own recall exactly. You need no NumPy and no outside
tool.

1. **`CreateSparseOracles`**: pick a held-out set of query rows, a few
   hundred, and compute their exact top-k neighbours by brute force. This
   writes an oracle file and returns its path. Despite the name it serves
   dense families too. Build it once.
2. **`MeasureRecall`**: for each seed count, call it with that
   `active_seeds` subset, `k`, and `exclude_self=true` against the same
   oracle. It returns `recall_at_k`, the mean over queries, and latency
   percentiles. The whole `active_seeds` sweep reuses the one oracle.
3. **For projection changes** you must build a fresh family and a fresh
   oracle, then measure. This is the slow axis. Sweep it last and coarsely.

`BuildUltradimV23KnnGraph` also returns `measured_recall_at_k` directly. It
is -1 if you passed `oracle_sample=0`. That is a quick in-line check without
a separate oracle.

---

## 5. `max_nnz_per_row`: derive it, never default it

`max_nnz_per_row` is the cap on non-zeros per sparse row. The engine rejects
any row over the cap. A cap set too low throws real rows away, which is
worse than a quiet loss of quality.

There is no correct fixed value. Pre-scan the dataset, take the observed
maximum non-zero count, and set the cap to `ceil(1.10 × observed_max)`. The
ten per cent headroom absorbs a denser row arriving later. The cap cannot be
changed after upsert without a rebuild, so scan before you create.

---

## 6. A worked recovery

The families in the running example were built at `projection_dim=2048`,
four seeds, `max_nnz_per_row=2048`, the default posture, the same for all
three. Two measured recall near 0.92 and 0.98 and were set aside as limited
by the keys. The evidence given was that recall did not move when `top_m`
was varied, 1600 against 4000. On this build that evidence is void: `top_m`
is not read by `MeasureRecall`. No setting the search reads was ever varied.
The recovery:

1. Rebuild the two failing families at 16 seeds, then sweep `active_seeds`
   4, 8, 16 against one oracle. No further rebuild. This shows whether
   recall moves with the number of voting views.
2. If more seeds do not clear 0.99, rebuild at `projection_dim=4096` and
   sweep `active_seeds` again against the new oracle.
3. Re-derive `max_nnz_per_row` from the true non-zero distribution.
4. Only if 0.99 is still out of reach after all of the above is "limited by
   the keys" a defensible statement, and now it carries the sweep as
   evidence.

Steps 1 to 3 are what the auto-tuner does for you. It ships in the wheel as
`ultradim.autotune`. Point it at a sample of your data; it derives the cap,
sweeps `active_seeds` against one oracle, and widens the projection only if
the free sweep fails.

---

## 7. Quick reference

- **Recall too low, gate refused?** Build at 16 seeds and sweep
  `active_seeds` 4, 8, 16 first, free. If flat, widen `projection_dim`
  2048 to 4096, a rebuild. Only then is it the keys.
- **Free to sweep, per request:** `active_seeds`, `k`. Always
  `exclude_self=true` for a self-query test.
- **Needs a rebuild:** `projection_dim`, `max_nnz_per_row`, and the seed set
  the family is built with.
- **Dead on `MeasureRecall`, accepted and echoed but never read:** `top_m`,
  `hnsw_ef`. Do not sweep them here.
- **Does nothing on create:** `default_top_m`, `default_hnsw_ef`, `hnsw_m`,
  `hnsw_ef_construct`, `quantisation`, `projection_mode`, `matrix_type`.
- **Measure with:** `CreateSparseOracles` once, then `MeasureRecall` per
  configuration with `exclude_self=true`.
- **`max_nnz_per_row`:** `ceil(1.10 × observed_max_nnz)` from a pre-scan.
- **Let the tuner do it:** `ultradim.autotune`.
