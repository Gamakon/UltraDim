# A Guide to Tuning UltraDim

For wheel 0.4.0, September 2026.

This guide says which settings change the quality of an UltraDim index,
which do not, and what to do when the recall gate refuses your data.

---

## 1. The short way: let the tuner do it

The wheel ships an auto-tuner. Give it a sample of your sparse rows, a few
thousand, and a recall gate. It derives the non-zero cap from the sample,
builds one family, measures recall against exact ground truth over a rising
number of seeds, and widens the target width only if the seeds are not
enough. It stops at the first configuration that clears the gate.

```python
from ultradim.autotune import SparseRow, autotune

sample = [SparseRow(indices=[...], values=[...]), ...]
result = autotune(db, sample, gate=0.99, k=10, n_queries=200)
print(result.best, result.best_recall, result.verdict)
```

`result.sweep` lists every configuration tried with its recall. If none
clears the gate, `result.verdict` says so and the sweep is the evidence.

The rest of this guide is the same procedure by hand, for anyone who wants
to understand what the tuner is doing or to run one step of it.

---

## 2. The one idea to hold onto

UltraDim reduces each row to a target width, `projection_dim`, before it is
indexed. The reduction is tuned by two settings: one or more seeds, and the
target width. More seeds and a wider target both raise recall.

If a search cannot find a row's true neighbours, the usual cause is that the
reduction has thrown away the distinction between them. The neighbours were
there. The cure is almost always more seeds or a wider `projection_dim`, not
more search effort.

---

## 3. The settings that change recall

There are two kinds of setting. Creation settings are fixed when the family
is created and can only be changed by building a fresh family. Query
settings are set per request and cost nothing to sweep.

### 3a. Creation settings, set once at `create_collection`

| Setting | What it governs | Standard | To raise recall |
|---|---|---|---|
| `source_dim` | The width of your raw input. | Fixed by your data. | Not a choice. |
| `projection_dim` | The target width of the reduction. | 2048 | Widen it, 2048 to 4096. A rebuild. |
| `seeds` | The seeds the reduction uses. | Four. Datasets of thirty million dimensions were indexed at four. | Eight, for the rare corpus four cannot separate. A rebuild. |
| `max_nnz_per_row` | The most non-zeros a sparse row may carry. A row over the cap is **rejected**, not truncated. | Derived from your data, §6. | A cap set too low rejects real rows. |
| `sparse_substrate` | Sparse or dense storage. | By your data. | A choice of storage, not a recall setting. |

The create request accepts other fields. They are reserved and have no
effect on 0.4.0.

### 3b. Query settings, set per request, free to sweep

| Setting | What it governs | To raise recall |
|---|---|---|
| `active_seeds` | Which of the family's seeds are used for each query. Build a family at eight seeds, then use four or eight per request, with no rebuild. | Use more of them. |
| `k` | recall@k, how many neighbours you grade against. | A reporting choice, not a fix. |
| `exclude_self` | Whether the query row is excluded from its own results. | A correctness setting. See below. |

**Always set `exclude_self=true` when your query rows are in the index.**
The query row matches itself at rank 1. Without excluding it, recall@10 is
exactly 0.9 for every configuration, because the query fills one of the ten
slots while the exact answer excludes it. A flat 0.9000 across every
configuration is this, not a property of your data.

`MeasureRecall` accepts other fields. They are reserved and have no effect
on 0.4.0; sweeping them changes nothing.

---

## 4. When the recall gate refuses

UltraDim's UMAP fit refuses to embed a graph whose measured recall is below
0.99. A low-recall graph has the wrong neighbours, so a map drawn on it
draws the wrong structure. You may override it with `force=true`, which
proceeds and logs a warning, but forcing past a real recall failure
publishes a map you have been told is wrong. Reserve it for the case in §4c.

A refused gate is an instruction. Follow it in this order.

### 4a. First, use more seeds. Free.

If the family was built at eight seeds, sweep `active_seeds` over four and
eight against a fixed oracle. No rebuild. If it was built at four, rebuild
at eight and sweep. If recall climbs over 0.99, you are done.

### 4b. If more seeds do not move recall, widen the target

If eight seeds instead of four leaves recall flat, the limit is the target
width, not the number of seeds. Rebuild with `projection_dim` 4096 and
re-derive `max_nnz_per_row` from the data if you defaulted it (§6). Then
sweep `active_seeds` again against a new oracle.

"Recall does not change with the seed count" is a statement about the
number of seeds, and it is the evidence that you must now change the target
width. Do not stop between the two steps.

### 4c. Only after both sweeps is the limit in the data

If recall still will not clear 0.99 after sweeping seeds and
`projection_dim`, the limit is a property of the rows. Report it with the
sweep as evidence, or proceed with `force=true` and record the measured
recall. A limit reported without both sweeps is an unfinished experiment.

---

## 5. Measuring recall

The engine measures its own recall exactly. You need no NumPy and no outside
tool.

1. **`CreateSparseOracles`**: pick a held-out set of query rows, a few
   hundred, and compute their exact top-k neighbours by brute force. It
   writes a file and returns its path. Despite the name it serves dense
   families too. Build it once per family.
2. **`MeasureRecall`**: for each seed count, call it with that
   `active_seeds` subset, `k`, and `exclude_self=true` against the same
   oracle. It returns `recall_at_k`, the mean over the queries, and latency
   percentiles. Report the latency beside the recall.
3. **For a change to `seeds` or `projection_dim`** you must build a fresh
   family and a fresh oracle. This is the slow axis. Sweep it last.

---

## 6. `max_nnz_per_row`: derive it, never default it

`max_nnz_per_row` is the cap on non-zeros per sparse row. The engine rejects
any row over the cap. A cap set too low throws real rows away, which is
worse than a quiet loss of quality.

There is no correct fixed value. Pre-scan the dataset, take the observed
maximum non-zero count, and set the cap to `ceil(1.10 × observed_max)`. The
ten per cent headroom absorbs a denser row arriving later. The cap cannot be
changed after upsert without a rebuild, so scan before you create.

---

## 7. A worked example

A family of sparse rows built at `projection_dim=2048`, four seeds,
`max_nnz_per_row=2048`, measured recall@10 of 0.92 against its oracle, and
was refused by the map gate.

1. Rebuild at eight seeds. Sweep `active_seeds` over four and eight against
   one oracle. Recall moves from 0.92 to 0.95. Not enough, but it moved, so
   seeds are not exhausted.
2. Rebuild at eight seeds and `projection_dim=4096`, with the cap re-derived
   from the data. Sweep `active_seeds` again against a new oracle. Recall
   at eight seeds clears 0.99.
3. Fit the map on that family.

The tuner runs those steps in that order.

---

## 8. Quick reference

- **Recall too low, gate refused?** Seeds first, free if the family has
  them: four, then eight. If flat, widen `projection_dim` to 4096, a
  rebuild. Only then is it the data.
- **Free to sweep, per request:** `active_seeds`, `k`. Always
  `exclude_self=true` for a self-query test.
- **Needs a rebuild:** `seeds`, `projection_dim`, `max_nnz_per_row`.
- **Measure with:** `CreateSparseOracles` once per family, then
  `MeasureRecall` per configuration with `exclude_self=true`.
- **`max_nnz_per_row`:** `ceil(1.10 × observed_max_nnz)` from a pre-scan.
- **Let the tuner do it:** `ultradim.autotune`.
