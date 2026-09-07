# Changelog

Every release is cut for all three platforms: macOS on Apple silicon, Linux
x86_64, Linux aarch64. Python 3.12. The RPC count is what `capabilities()`
returns on that wheel.

## 0.4.0 — 2026-09-07

- The wheel carries its licence: the PolyForm Noncommercial 1.0.0 text at
  `ultradim/LICENSE` and the notice at `ultradim/LICENSES/LICENSE.md`.
  Earlier wheels carried no terms.
- Metadata: Python 3.12 declared (earlier wheels said 3.9 and were refused
  on 3.9 to 3.11 with no reason given); numpy declared as a dependency.
- No bill of materials inside the Linux wheels. Every Linux wheel from 0.2.0
  to 0.3.12 carried one.
- Engine unchanged from 0.3.12. 204 RPCs, 46 MCP tools.

## 0.3.12 — 2026-08-27

- Housekeeping. Three messages inside the wheel that named the engine's
  earlier host database are reworded. No behaviour change. 204 RPCs.

## 0.3.11 — 2026-08-27

- Replace and delete: if the last step of a write that succeeded cannot
  complete, the family is taken out of service and the error says the write
  succeeded and not to retry. On 0.3.10 that case left the family refusing
  lifecycle operations until a restart.
- A delete failure no longer has its error replaced by a later one.

## 0.3.10 — 2026-08-27

- Replace and delete: an ordinary write failure after the durable step is
  repaired in the running process. The replacement is completed and made
  searchable before the error is returned. On 0.3.9 the family refused
  writes until a restart.
- The engine's single-slot lifecycle record can no longer be overwritten by
  a later operation.

## 0.3.9 — 2026-08-27

- `ReplaceUltradimV23Point` and `DeleteUltradimV23Point`: replace the vector
  held for a row, or retire a row. A replace writes the replacement at a new
  row id; your `content_key` stays stable. 202 to 204 RPCs, 44 to 46 tools.
- `GetUltradimV23RowByContentKey` returns the newest live row for a key. It
  returned the oldest before. This applies to dense families too.
- Writers serialise per family.

## 0.3.8 — 2026-08-25

- UMAP on the GPU: every blocking poll is bounded
  (`ULTRADIM_GPU_POLL_TIMEOUT_SECS`); one GPU device is shared across fits
  instead of one per fit; the buffer ceiling is clamped to what the device
  reports.
- Linux wheels are `manylinux_2_28` (glibc 2.28 or later). 202 RPCs.

## 0.3.7 — 2026-08-13

- The auto-tuner ships inside the wheel as `ultradim.autotune`.
- The MCP server documents which request fields the engine does not read.

## 0.3.6 — 2026-08-13

- Seventeen MCP tools for UMAP and HDBSCAN over RPCs that already shipped:
  kNN graph, fit, transform, incremental fit, lineages over time, cluster
  migration between two times.

## 0.3.5 — 2026-08-12

- `GetUltradimV23RowByContentKey`: exact identity lookup by a key you stored
  on the row. Answers before the family is indexed. 201 to 202 RPCs.

## 0.3.4 — 2026-08-09

- `make_searchable(name, window=1)`: the `window` field reaches the settle.
  On 0.3.3 it was accepted and ignored.

## 0.3.3 — 2026-08-09

- The settle window floor is 1, so a record is searchable after one settle
  pass. It was 100.

## 0.3.2 — 2026-08-08

- `UltradimV23MultiFamilySearch`: one query across several families in one
  call, joined on row id, with a per-family present flag. 200 to 201 RPCs.
- Facet maps on upsert: arbitrary integer and keyword facets per row,
  filterable during candidate collection.

## 0.3.1 — 2026-08-06

- `make_searchable(name)` is the one call that creates, builds and waits.
- `list_rpcs` and `describe_rpc` carry a status per RPC.
- The health banner reports the loaded wheel's real version.

## 0.3.0 — 2026-08-06

- All 200 RPCs implemented. First release cut for
  all three platforms.

## 0.2.0 — 2026-08-03

- The API re-hosted on the current engine. Seven RPCs live.

## 0.1.x — July 2026

- 200 RPCs on the earlier engine. Superseded.
