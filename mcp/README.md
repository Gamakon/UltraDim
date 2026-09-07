# UltraDim MCP server

Exposes an embedded UltraDim database as MCP tools, so an assistant can create
families, ingest vectors, build the WideTrellis index, search it, grade it
against exact ground truth, cluster it, and follow clusters across rolling time
windows — without the user writing any Python.

The database runs **in-process** inside this server. There is no separate engine
and no port: the server is a thin wrapper over the same `ultradim` wheel a human
would `import`.

## ONE engine, ONE API — embedded and gRPC are the same thing

**There is exactly one database, and it lives in the wheel.** Everything below is
the same engine reached three ways, and **all three expose the identical 204
RPCs — nothing is available in one and missing from another:**

1. **Embedded (in-process), the default and simplest:** `import ultradim`,
   `db = ultradim.UltraDim(path)`, then `db.call_json("RpcName", '{…}')`. No
   server, no port. This is the whole database.
2. **This MCP server:** a thin wrapper that calls the *same* embedded wheel and
   exposes the RPCs as MCP tools. It adds no capability — it is the embedded
   path with friendly tool names.
3. **gRPC server** (the client-server edition, available on request): the
   *same* engine behind a socket, for callers in other processes or on other
   machines.

So when a guide shows a UMAP or clustering example over `UltraDimClient` on gRPC,
that is **not** a different or fuller API — the identical call is
`db.call_json("FitUltradimV23Umap", '{…}')` embedded. **If you are already
driving the wheel in-process, do everything in-process — search, UMAP, HDBSCAN,
k-means, recommendation, all 204 RPCs are right there via `call_json`.** You never
need to stand up the gRPC server to reach a feature; pick the transport that suits
your process, not the feature. `capabilities()` returns the same list on all
three.

## START HERE — the version, once

**The server file and the wheel carry the same version.** The wheel (the engine) is `0.4.0`, so
the server is `mcp/ultradim_mcp_server_v0_4_0.py`. Every release bumps the server filename to
match — a `v0_4_0` file runs the `0.4.0` wheel, full stop. Confirm you are in step: `health`
reports `wheel: "0.4.0"` and `version_aligned: true`; if it does not, the wheel and the server file
are out of step and you should reinstall the `0.4.0` wheel (or run the server file that matches the
wheel you have).

**Do not guess what the database can do — ask it.** Call the `whats_available` tool. It prints, live
from the wheel, the version, the happy path, the analytics RPCs, the retired RPCs to avoid, and
every RPC the wheel exposes grouped by area. That listing comes from the wheel's own
`capabilities()`, so it cannot go stale the way prose does. If you think a feature is missing, call
`whats_available` first — it is very likely there under a name you did not expect.

Happy path (WideTrellis): `create_collection` → `upsert_sparse` → `make_searchable` →
`trellis_template_search` (+ `cluster` for analytics). Do not use the retired `UltradimV23Search` /
`get_keys` RPCs.

**Exact identity lookup (new in 0.3.5):** `get_row_by_content_key` fetches a row's numeric id by an
exact key you stored on it — a point lookup, not a search, so it answers even **before** the family
is indexed (settled). Store the key by putting it in the row's facet metadata under `content_key`
when you `upsert_sparse` (`facets=[{"content_key": "..."}]`). Use this for "have I seen this exact
thing before?" — it is exact-string only (a one-character difference misses), and it does not run
the cosine walk.

**It returns the NEWEST LIVE match (changed in 0.3.9).** If you tag several
versions of one entity with the same key, you get the version you wrote LAST,
skipping any that have been replaced or deleted. That is what makes it the
right lookup for "what is the current state of this?" as well as "have I seen
this before?".

Before 0.3.9 it returned the OLDEST match, which after one replace is a row you
can no longer use. **This changed for dense families too**, not only sparse
ones — the lookup is substrate-agnostic. If you relied on the old behaviour,
put the version in the key (`instrument-42@v7`) so each version has its own.
See `docs/SPARSE_UPSERT_SEMANTICS.md`.

**Replace and delete (new in 0.3.9):** `replace_sparse_point` changes the
vector held for a row whose current state has moved on, and
`delete_sparse_point` retires one for good. The thing to know up front: a
replace writes the replacement at a **new row id** — ids are never reused — and
your `content_key` is what stays stable, so the lookup above keeps finding the
current row.

Two things worth knowing before you build on it. A replacement is durable and
resolvable by `content_key` the moment the call returns, but the cosine
**search** sees it only once the settle window flushes — settle with `window=1`
if you replace live state and search for it straight away. And **from 0.3.10** a
failed replace needs no restart: an ordinary write error is rolled forward in
process, the replacement completed and streamed into the running engine, before
the error is returned to you. If a repair cannot complete — or, **from 0.3.11**,
if the lifecycle record cannot be cleared after a write that did succeed — the
family is taken out of service and says so, rather than answering from a state
it cannot vouch for. On 0.3.9 such a failure left the family refusing writes
until a restart. See `docs/SPARSE_UPSERT_SEMANTICS.md`.

**Density maps — UMAP and HDBSCAN (dedicated tools):** the engine's GPU UMAP and HDBSCAN-lineage
RPCs are first-class tools (previously reachable only via `call_rpc`). Both start from a **settled**
family, because the kNN graph they use needs a resident engine and must see every row:

- **UMAP** (reduce a family to a 2..256-D map): `make_searchable` → `build_knn_graph` → `fit_umap`
  → `umap_embedding` (+ `transform_umap` to place new points, `incremental_fit_umap` to fold a
  batch in). Enum knobs take friendly strings (`init`: annealed/spectral/random; `output_metric`:
  euclidean/spherical). Embeddings come back as per-row coordinate lists.
- **HDBSCAN over time**: `make_searchable` → `build_knn_graph` → `create_hdbscan_lineage` →
  `advance_hdbscan_lineage` (as new rows arrive) → `apply_hdbscan` / `cowalk_hdbscan` /
  `hdbscan_migration_graph` to read clusters and how they move between two times.

Call `whats_available` and look at the **"umap / density maps"** group for the full set.

### What the WideTrellis is

The index is a **navigable graph in the HNSW family, with one structural
difference: the frame is built before the data arrives.** The name is the
explanation — a garden trellis is a frame you put up first, and the plant is
trained over it. Classic HNSW grows its graph one insertion at a time, so the
structure depends on arrival order and every insert mutates shared state. The
WideTrellis instead starts from a **pre-built field of well-spaced fixed
points** (deterministic, generated from a seed), and indexing — what this
project calls *settling* — **seats your rows onto that prepared frame** and
refines the edges between them. Searching walks the graph the same way you
would walk an HNSW, then **re-ranks the candidates by exact cosine against the
full original vectors**, so every result you get back has been verified at
full precision — the graph decides where to look, never what the score is.

**Why the frame is pre-built: availability.** Because the structure a record
needs already exists before the record arrives, seating is quick — so once a
family is live, a newly ingested record is **queryable at first touch**, not
after a rebuild. The index then keeps *settling* behind the stream: a rolling
correction revisits each recent ingest window and tightens its edges, so the
earliest queries against a fresh record may pay slightly unoptimised latency,
but there is never a window in which ingested data is unavailable.

What the pre-built frame buys you in practice: builds are **deterministic and
reproducible** (same rows, same seed, same index); ingestion after the first
settle is **streaming** — each new record is seated as it lands rather than
triggering a rebuild; and the frame tolerates **notional points** — fixed points
with no data row seated on them are simply part of the scaffold, which is why
replaced and deleted rows never require the index to be rebuilt. Several
independently-seeded graphs are searched together and pooled, which is where
the recall comes from.

**"Settle" means "finish indexing the records."** It is this project's word for building the
searchable index over the rows you have upserted — a row is not searchable until its family has been
settled. `make_searchable` is the one-call way to do it. Every mention of "settle" below means
exactly this. The **first** settle is the big one — it makes the family live. After that, settling
is continuous: each new record is searchable at first touch, and the settle stream keeps refining
edges behind the arrivals (see "What the WideTrellis is" above).

**Choosing `window` — this decides your latency:**

- **Sending records one at a time (singletons)?** Set **`window=1`**. Each record is added to the
  index the moment it arrives — immediately searchable, no wait. **This is slower**: it runs one
  full indexing pass per record, so a stream of singletons pays that cost every time.
- **Streaming many records? Micro-batch — the recommended way to run.** Collect records for a short
  interval (**about one minute is a good default**), then upsert them together as one small batch
  with `window` set to that batch's size. You get near-realtime freshness without the per-record
  cost. **This is a preference, not a rule** — pick whatever interval suits you (every minute, every
  10 seconds, every 500 records; your call). `window=1` on singletons and a periodic micro-batch are
  the two ends, and anything between is fine.
- **Bulk-loading a whole corpus at once?** Leave `window` at its **10,000** default.

Once a family has been settled once and its engine is resident, every later upsert advances the live
index at first touch — so after the initial build you keep streaming and each new record becomes
searchable as it lands, with no second settle call.

> ### ⚠️ 0.3.4 — record-by-record settle (`window=1`), one call
> `window=1` makes each upserted record searchable after a **single settle
> pass**, no buffering — the interactive / prefill-cache mode.
> Default is unchanged at 10,000; keep it there for bulk ingest (window=1 = one
> settle pass per record = slower bulk).
>
> **Use the one-call `make_searchable(name, window=1)`.** Build synthesises the
> field and settles at window=1 for you — no field_path. The raw
> `trellis_template_settle` also takes window=1 (reach for it only when you also
> need an explicit floor or your own field_path). Wheel/embedded call:
> ```python
> db.call_json("BuildUltradimV23TrellisIndex", '{"name": "<family>", "window": 1}')
> ```
> `window=0` means unset (the 10,000 default), never window=1.
>
> **Needs the 0.3.4 wheel.** History of this fix, because a mid-version wheel is
> a trap: 0.3.3 lowered the settle floor 100→1 but `window` was **not** on
> BuildUltradimV23TrellisIndex, so on 0.3.3 `make_searchable(window=1)` is
> **silently ignored** (accepted, settles at 10,000, returns success) — the
> record-by-record path there was only the raw settle + a hand-built field_path.
> 0.3.4 threads `window` through Build so the one-call path works. **Do not run
> 0.3.3 for this feature.** On 0.3.2-or-older even the raw settle clamps
> window=1 up to 100. The health banner reports the loaded wheel's real version
> (`ultradim.__version__`); confirm `wheel: "0.3.4"`. All three platforms are
> cut at 0.3.4 and `make_searchable(window=1)` was run functionally on each — no
> partial release.

## Install

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install --force-reinstall UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl
```

All wheels are cp312 — Python 3.12 only. The engine is compiled in, so the wheel
plus **numpy** is the whole setup — install numpy alongside the wheel (the
manylinux wheels do not pull it in transitively; a bare `python:3.12-slim` needs
it added, as above).

| Platform | Wheel |
|---|---|
| macOS Apple Silicon | `UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl` |
| Linux arm64 | `ultradim-0.4.0-cp312-cp312-manylinux_2_28_aarch64.whl` |
| Linux x86_64 | `ultradim-0.4.0-cp312-cp312-manylinux_2_28_x86_64.whl` |

**The Linux wheel tag changed in 0.3.8**: `manylinux_2_28`, not the
`manylinux_2_17…manylinux2014` tag 0.3.7 carried. Both Linux wheels are now built
from the `manylinux_2_28` images, so they need glibc 2.28+ (RHEL/Alma 8+,
Debian 10+, Ubuntu 18.10+). If you pin wheel filenames anywhere, update the pin.

0.4.0 is cut for all three platforms. The engine is the same as 0.3.12: 204
RPCs, 46 tools, no behaviour change. The wheel now carries its licence: the PolyForm Noncommercial 1.0.0 text at
`ultradim/LICENSE`, and the notice at `ultradim/LICENSES/LICENSE.md`. numpy is a
declared dependency, so pip installs it with the wheel.
Noncommercial use is free. Commercial use needs a licence from
jesung@gamakon.ai or andrew@gamakon.ai. Earlier wheels carried no terms.
The wheel metadata now requires Python 3.12; earlier wheels said 3.9 and
were refused by pip on 3.9 to 3.11 with no reason given.

0.3.12 is cut for **all three platforms** as one pack. A housekeeping release:
no new RPC, no new tool, no behaviour change — still **204** RPCs and 46 tools.
It removes the last references to the engine's historical host database from
the shipped artefacts (two retired-RPC error messages and one config-limit
message; the limit itself is unchanged), so the wheel now contains no mention of
it. Verified as a release gate: a scan of every file in each wheel archive finds
zero occurrences. There is no functional reason to upgrade from 0.3.11.

0.3.11 is cut for **all three platforms** as one pack. It adds **no new RPC and
no new tool** — still **204** RPCs and 46 tools — and closes one edge in the
replace/delete path that a customer review found in 0.3.10.

**Upgrade if you use `replace_sparse_point` or `delete_sparse_point`.** 0.3.10
repaired a write that failed part-way through, but the very last step — dropping
the internal record of the operation — could itself fail and was not covered.
The operation had already succeeded and was safe, but the leftover record made
**every later replace and delete on that family fail until the process was
restarted**. Now the family is taken out of service instead, and the error says
that the write succeeded, names the row, and tells you **not** to retry;
reopening recovers it. A related bug is fixed in the same release: a failed
delete could report why the record could not be tidied instead of why the delete
failed.

0.3.10 is cut for **all three platforms** as one pack (no partial release). It
adds **no new RPC and no new tool** — the count stays at **204** RPCs and 46
tools — and fixes one defect in the replace path reported by a customer.

**Upgrade if you use `replace_sparse_point`.** On 0.3.9, if the write failed
part-way through for an ordinary reason — a full disk, an I/O error, not a
crash — the family was left **refusing every subsequent write until the process
was restarted**, and the replacement could be missing from cosine search. Two
things changed:

- The failure is now **repaired in process**. The replacement is completed and
  streamed into the running search engine before the error reaches you, so the
  family keeps serving and keeps accepting writes. The call still reports the
  error — the repair fixes the family, it does not pretend the write
  succeeded — and a retry resolves cleanly to the replacement.
- If that repair cannot itself complete, the family is **taken out of service**
  and says so, rather than answering from a partly recovered state. Reopening
  runs full recovery.

A related durability defect was found while fixing it and is closed in the same
release: a failed replace could cause the *next* replace on that family to
destroy the first one's recorded metadata, which after a crash was the only
surviving copy. Nothing else in the release changes.

**0.3.9** added the **row lifecycle pair** — `replace_sparse_point` and
`delete_sparse_point` — taking the
count **202 → 204** RPCs and 44 → 46 tools. Three behaviour changes came with
it, none of them opt-in:

- **`get_row_by_content_key` returns the NEWEST live match**, where it returned
  the oldest. This applies to **dense** families too, not only sparse ones —
  the lookup is substrate-agnostic. If you relied on the old behaviour, put the
  version in the key.
- **Writers serialise per family.** Replace, delete and upsert take one lock per
  family, held across the whole write. Clients fanning out many parallel
  upserts to one family will see a different latency profile; they were already
  racing an unsafe sequence, so this closes a real defect, but the change is
  measurable.
- **Open-time store reconcile**, which repairs a family whose stores were left
  at different lengths by a crash mid-write. It is **warn-only by default** and
  logs what it finds; set `ULTRADIM_RECONCILE_ENFORCE=1` to RPC the repair.
  Re-projecting a short key tail is deterministic and always runs; only the
  destructive RPC is gated.

One semantic worth reading before you build on replace: a replacement is
durable and resolvable by `content_key` the moment the call returns, but the
cosine **search** sees it only once the settle window flushes. Settle with
`window=1` if you replace live state and search for it straight away. See
`docs/SPARSE_UPSERT_SEMANTICS.md`.

**0.3.8** was an engine bug-fix release — no new RPC and no new MCP tool, so it
reported **202** RPCs. It fixed three defects on the UMAP GPU path:

- the fit built a fresh GPU device on **every** call, so a long
  `incremental_fit` loop created and tore down a Metal device hundreds of times;
  it now shares one device, and drops it if the device is ever lost
- blocking GPU polls on the fit path are now **bounded** (90 s, override with
  `ULTRADIM_GPU_POLL_TIMEOUT_SECS`), so a wedged submission returns an error
  instead of parking the calling thread forever
- the GPU buffer ceiling is clamped to what the graphics adapter actually
  grants, rather than 2/3 of host RAM — which on unified-memory Apple silicon
  bounded nothing at all

(Those UMAP fixes shipped in 0.3.8 and are carried forward here.)

The release before, 0.3.7, adds
NO new engine RPC — so the wheel still reports **202** RPCs — but it does two new
things: it BUNDLES the dataset auto-tuner into the wheel as `ultradim.autotune`
(the wheel is now a mixed Python/Rust package; the engine is imported as
`ultradim._ultradim` and re-exported, so `import ultradim; ultradim.UltraDim(path)`
is unchanged), and it surfaces that tuner as the `autotune` MCP tool. It also
documents that `top_m`/`hnsw_ef` are accepted-but-ignored by the engine on
`trellis_measure_recall` (the live retrieval setting is `active_seeds`; see the
tuning guide and `docs/UltraDim_Tuning_Guide.md`). The
prior release, 0.3.6, cut the UMAP + HDBSCAN density-map tools for all three
platforms, 17 dedicated MCP tools over RPCs
that already shipped — so it too reported **202**. The release before that, 0.3.5,
added the
EXACT identity get (`GetUltradimV23RowByContentKey`) — the
one RPC that took the count 201 → 202. Multi-family search and facet maps
remain live everywhere. The Linux wheels were built in the
`ghcr.io/pyo3/maturin` manylinux2014 container (arm64 native, x86_64 under
emulation); the older 0.3.0–0.3.5 wheels are superseded.
The server runs against any of these wheels unchanged (it dispatches by name);
identify the build you actually loaded by its extension-module digest, not by
the version string (below).

### Verify: the RPC count, then the build

Two different checks, and you need both.

**The RPC count tracks the wheel — 204 on 0.3.9 and later, 202 on 0.3.5/0.3.6/0.3.7/0.3.8,
201 on 0.3.2/0.3.3/0.3.4, 200 on 0.3.0/0.3.1.** The number is `len(capabilities())` read live from whatever
wheel you loaded, not a constant baked into the server. Wheels 0.1.x through
0.3.1 report **200**. The 0.3.2–0.3.4 wheels report **201** — they add
`UltradimV23MultiFamilySearch`. 0.3.5 reports **202** — it adds
`GetUltradimV23RowByContentKey` (the EXACT identity get). 0.3.6, 0.3.7 and
0.3.8 also report **202**: they add no engine RPC, only MCP tools (and, in
0.3.7, a bundled Python tuner) over existing RPCs, or engine bug fixes. 0.3.9
reports **204** — the row lifecycle pair. 0.3.10, 0.3.11, 0.3.12 and 0.4.0 also report
**204**: engine bug-fix, housekeeping or licensing releases, no new RPCs. An *older* wheel simply omits
the newer RPCs. So: check the count against the wheel you actually have, not
against a fixed number.

```bash
python3.12 -c "import ultradim; print(len(ultradim.UltraDim('./probe').capabilities()))"
# 204 on 0.3.9+; 202 on 0.3.5-0.3.8; 201 on 0.3.2/0.3.3/0.3.4; 200 on 0.3.0/0.3.1
```

**Identify the build by its digest, not by its version.** 0.3.0 has been cut
more than once, and two builds carrying that version string can differ. The
version tells you nothing about which binary you have; the sha256 of the
extension module does:

```bash
python3.12 -c "
import ultradim, os, hashlib
p = os.path.join(os.path.dirname(ultradim.__file__), '_ultradim.cpython-312-darwin.so')
print(hashlib.sha256(open(p,'rb').read()).hexdigest())"
```

Quote that digest beside any measurement you report. The server puts it in
`health()` under `wheel_build.sha256` for exactly this reason, and the test
harness records it at start and re-checks it at exit, so a wheel replaced
underneath a run cannot be mistaken for a passing one.

The digests behind this README's numbers:

| Artifact | sha256 |
|---|---|
| macOS arm64 wheel (0.4.0) | `f2300760657f97072d2e1ca31813f5b548acf5ae089cdc24fc01a7a8ac3ee5e2` |
| its extension module (0.4.0) | `ed14a4c7191d5eea6d64bd77c0fcb4ba4645098b22e6f422c5cfb210a94633e1` |
| manylinux aarch64 wheel (0.4.0) | `548303ee3f08582312b1eb5293f8e6e4562411cf3b3ee19f2b2dbeef353a1dfb` |
| manylinux x86_64 wheel (0.4.0) | `4f25292542f1d388b18ea44bf8c6c0167a5254103ab5078fbf0b2f0a63b92350` |
| macOS arm64 wheel (0.3.12) | `e40231b40b5808f16ddd6c232a9e879cef41617a0296459303c9e859bda18f06` |
| its extension module (0.3.12) | `3841f9bea4ca5d27242193341326b2ab0085356a5213def467ce5e159b12386d` |

## Upgrading to a new version

The current release is **0.4.0**. Upgrading is three steps, and they matter in
this order — the engine is compiled into the wheel, so a new version does nothing
until you replace the wheel AND point the server at it.

**1. Replace the wheel (uninstall first — do not install over the top).** A stale
native module can shadow the new one, so remove it before installing:

```bash
pip uninstall -y ultradim UltraDim
pip install --force-reinstall UltraDim-0.4.0-cp312-cp312-macosx_11_0_arm64.whl
#   Linux x86_64: ultradim-0.4.0-cp312-cp312-manylinux_2_28_x86_64.whl
#   Linux arm64:  ultradim-0.4.0-cp312-cp312-manylinux_2_28_aarch64.whl
```

Confirm you are on the new engine:

```bash
python3.12 -c "import ultradim; print(ultradim.__version__)"   # 0.4.0
```

**2. Point `.mcp.json` at the matching server file.** The server filename tracks
the wheel version, so it is renamed every release — `0.4.0` ships as
`mcp/ultradim_mcp_server_v0_4_0.py`. Update the path in `.mcp.json` (see the next
section). Then confirm the wheel and the server file are in step: the `health`
tool reports `wheel`, `expected_wheel`, and `version_aligned` — **`version_aligned`
must be `true`.** If it is not, the wheel and the server file disagree; reinstall
the matching wheel or point at the matching server file.

**3. Re-ingest the docs, and let the server tell you what changed.** An old copy
of this README (or an agent's cached context) will name the wrong filename and
version and omit whatever the new release added. After upgrading, re-read this
README, and call the **`whats_available`** tool — it lists, live from the wheel,
the version, every RPC grouped by area, the happy path, and the analytics tools.
It is generated from the engine's own `capabilities()`, so it is the authoritative
answer to "what does this build have?" and it cannot go stale the way a document
can. If you think a feature is missing, call `whats_available` first — it is very
likely there under a name you did not expect.

The wheels are cumulative: each release carries every prior feature. A build's
extension-module digest (not its version string) identifies exactly which binary
you loaded — see *Verify* above.

## Register the server

`.mcp.json` at the repository root already does this:

```json
{
  "mcpServers": {
    "ultradim": {
      "command": "python3.12",
      "args": ["${workspaceFolder}/mcp/ultradim_mcp_server_v0_4_0.py",
               "--db", "${workspaceFolder}/ultradim_mcp_db"]
    }
  }
}
```

Point `command` at the interpreter that has the wheel installed — the venv's
`.venv/bin/python` if you used one — and `--db` at wherever the store should
live. The directory is created on first use.

## Tools

46 tools. Everything here was probed against a real family on the wheel above
before being described — with one exception, `incremental_fit_umap`, which is
covered at the wrapper/shape level but not yet live-probed end-to-end (its row
says so).

| Tool | What it does |
|---|---|
| `whats_available` | **START HERE.** Live from the wheel: version, happy path, analytics RPCs, retired RPCs, and every RPC grouped by area. The authoritative "what can this do?" — never stale |
| `health` | Engine health, RPC count, version alignment, and the wheel digest serving you |
| `list_collections` | Families in the store, both substrates, with build state |
| `create_collection` | New family, sparse (default) or dense |
| `upsert_sparse` | **Append** sparse rows; ids extend the family contiguously from 0. Append-only: re-sending an existing id is refused, so "upsert" here means "insert a batch", not SQL's insert-or-replace. To CHANGE a row use `replace_sparse_point` (0.3.10) — see `docs/SPARSE_UPSERT_SEMANTICS.md`. Pass `facets=[{"content_key": "..."}]` to tag a row with an exact identity key for `get_row_by_content_key` |
| `replace_sparse_point` | **Change a row's vector (0.3.10).** Sparse only. The old row is retired and the replacement lands at a **new row id** (returned); your `content_key` is what stays stable. Omit `facets` to inherit the old metadata wholesale, supply it to replace the metadata outright — never a partial merge. Changing `content_key` is refused. Retrying a replace that already succeeded resolves to the current row instead of duplicating it |
| `delete_sparse_point` | **Retire a row (0.3.10).** Sparse only. The row id is not freed and the row count does not drop — the row just stops being visible. Idempotent; no undelete |
| `upsert_dense` | Insert dense rows into a dense family |
| `get_row_by_content_key` | **Exact identity lookup (0.3.5).** Fetch a row's numeric id by the exact `content_key` you stored on it — a point lookup, no cosine search, answers before the family is settled. Exact-string only; a one-character difference misses. Returns the **newest live** match (0.3.10; it was the oldest before, for dense families too) |
| `make_searchable` | **The one-call way** to make a loaded family searchable — no field_path, no floor. Pass **`window=1`** for record-by-record (prefill cache); default 10,000 for bulk. (0.3.4 threads `window` through Build, so the one-call path sets it) |
| `trellis_template_settle` | The raw index build; reach for it only when you also need an explicit `floor` or your own `field_path` |
| `trellis_template_search` | Search a sparse family with a sparse query — the live k-NN RPC |
| `trellis_template_status` | Build progress and whether the walk can serve |
| `search` | Search a **dense** family with a dense vector |
| `trellis_measure_recall` | Grade the index against an oracle artifact. Live retrieval setting is `active_seeds`; keep `exclude_self=true` (else recall is exactly 0.9). `top_m`/`hnsw_ef` are accepted-but-ignored by the engine on this build |
| `build_oracle` | **Engine** brute force: exact top-k, written as the artifact |
| `autotune` | **Point it at a sample of your data; it finds a config that clears the recall gate (0.3.7).** Automates `docs/UltraDim_Tuning_Guide.md`: derive max_nnz, sweep `active_seeds` free against one oracle, rebuild wider only when needed. Builds families/oracles as it runs — minutes on a real corpus, not a quick call. The remedy for a refused gate |
| `collection_info` | Registry record: dims, substrate, seeds, matrix, shards |
| `index_status` | Per-shard index state (same record, the "is it ready" name) |
| `restart_indexing` | Re-trigger indexing on a settled family's shards |
| `cluster` | Spherical k-means over the projected rows — **sparse only** |
| `kmeans_save_model` | Open a rolling k-means lineage, fit its first window |
| `kmeans_advance` | Fit the next window, warm-started from the previous |
| `kmeans_apply_model` | Score rows against a saved model without refitting |
| `kmeans_migration_graph` | Mass flows between two windows of a lineage |
| `build_knn_graph` | Build or extend the stored kNN graph a UMAP fit or HDBSCAN lineage uses. **Family must be settled first** (make_searchable) — the graph needs a resident engine and must see every row |
| `fit_umap` | Fit a UMAP embedding of a family (reduce to 2..256-D for maps/clustering). GPU. Enum knobs (`init`, `output_metric`) take friendly strings |
| `transform_umap` | Place new points into a fitted map (out-of-sample). Returns per-row coordinates. `queries` is a plain dense or sparse list |
| `umap_embedding` | Read a fitted map's stored embedding, paged. Returns per-row coordinates (reshaped, not a flat array) |
| `umap_info` / `list_umap_models` / `drop_umap` | Metadata, listing, and deletion of fitted UMAP maps |
| `incremental_fit_umap` | Fold a new (already graph-appended) batch into a fitted map without a full refit. **Not yet live-probed** end-to-end: the fold must carry the parent map's graph params (k etc.), which is a heavier setup than a toy test exercises — the wrapper's shape is covered, the full path is not yet |
| `create_hdbscan_lineage` | Open a density-clustering lineage over a family. `graph_id` **required** — build it first |
| `advance_hdbscan_lineage` | Advance a lineage one time step over new (settled + graph-appended) rows |
| `apply_hdbscan` | Assign a population (queries XOR row_ids) to clusters as-of a time t (or `t_latest`) |
| `cowalk_hdbscan` | Compare one population's clusters at two times `t_a`,`t_b` (both required; (0,0) rejected) |
| `hdbscan_migration_graph` | Cluster migration graph between two times `t_a`,`t_b` |
| `hdbscan_info` / `list_hdbscan_lineages` | Lineage metadata and listing |
| `compact_hdbscan_lineage` / `drop_hdbscan_lineage` | Compact a lineage's history / delete a lineage |
| `drop_collection` | **Destructive** — deletes a family outright, no undo |
| `list_rpcs` | Every RPC the loaded wheel exposes (read live from `capabilities()` — 202 on 0.3.5/0.3.6), each with a live/canonical status |
| `call_rpc` | Call any raw RPC — the escape hatch to the rest of the API |
| `describe_rpc` | An RPC's authoritative status; field shapes still deferred to the proto |

`call_rpc` is the escape hatch. It reaches the whole API (hierarchical
clustering, recommendation, the BERT RPCs) without a dedicated tool for each.
Because `describe_rpc` cannot print field shapes on this wheel, read the request
message in `ultradimdb/proto/ultradim.proto`. A request deep-merges over the
proto defaults, so you state only the fields you mean to change.

### Implemented is not the same as accepting your family

Every RPC in the API is implemented — all 200 on the shipped 0.3.x wheels.
That is a statement about the API, not a promise about your family: an RPC can still refuse the family you point it at,
and it says why in its own words. The three refusals you will actually meet:

- **`cluster` refuses a dense family** by name. Clustering read dense rows
  through a sidecar the current engine does not carry. Everything else works on
  both substrates.
- **Search and `restart_indexing` need a settled family.** Both are served by
  the template engine, so before `trellis_template_settle` has run you get "no
  resident template engine".
- **Settle refuses a corpus with no structure.** See below.

### The noise floor, and why a settle can refuse

`trellis_template_settle` discards candidate edges below a significance floor
that is the exact spherical null — at projection width 128 it is **0.3314**, the
smallest cosine at which at most one noise edge per thousand rows survives. If
every pair in your corpus falls below that, the settle refuses with "settle
produced an EMPTY graph" rather than building a graph of noise.

That refusal is almost always the corpus, not the engine. A few hundred rows of
uniformly random sparse vectors have no real neighbours: draw 32 non-zeros from
100,000 dimensions and nearly every pair shares no dimension at all, so the true
top-10 is a tie at zero. Give the family real structure before reaching for the
`floor` override — the test harness plants 20 topic groups whose same-topic pairs
have a median cosine around 0.5, and settles at the shipped default with no
override at all.

## Hello cache

The simplest thing in the world — put vectors in, get near ones out — with no
`field_path`, no `floor`, and no workaround. Create a family, load five rows of
which two are near-duplicates, make it searchable in one call, and get the
near-duplicate back.

These are MCP tool calls (the arguments an MCP client sends), not Python:

```text
# rows 0 and 4 are near-duplicates: same dimensions, almost identical values.
create_collection   name=cache source_dim=256 projection_dim=128 max_nnz_per_row=8
upsert_sparse       name=cache rows=[
  {indices:[3,7,11,42], values:[0.5,0.5,0.5,0.5]},        # id 0
  {indices:[1,2,3],     values:[0.577,0.577,0.577]},      # id 1
  {indices:[90,91,92,93], values:[0.5,0.5,0.5,0.5]},      # id 2
  {indices:[10,20,30],  values:[0.577,0.577,0.577]},      # id 3
  {indices:[3,7,11,42], values:[0.51,0.49,0.5,0.5]},      # id 4  (near-dup of 0)
]                                                          # values L2-normalised by the caller
make_searchable     name=cache
trellis_template_search  name=cache sparse_query=<row 0> top_k=3 exclude_ids=[0]
```

`make_searchable` resolves the node field and settles the index itself, so you
never touch `field_path` or the noise floor. Actual output from the run above:

```
upsert:          {"success": true, "points_inserted": 5, "row_ids_used": [0, 4]}
make_searchable: {"graph_nodes": 5, "rows_total": 5, "build_ms": 1.96, "epoch_hash": "87659ef5e72b3330"}
search:          {"results": [{"id": 4, "score": 0.9999}, {"id": 1, "score": 0.2887}, {"id": 2, "score": 0.0}]}
```

The near-duplicate, id 4, comes back at the top with score ~1.0. The `score` is
the exact raw cosine in the family's own dimensions, in `[-1, 1]` — not a
key-space score — so it is comparable across families regardless of projection
width.

This tiny corpus is mostly isolated on purpose: ids 1, 2 and 3 share few or no
dimensions with each other or with row 0 (id 2 is orthogonal to it, hence the
0.0 score above), so the settle reports them with no significant neighbours.
That is the empty-graph guard working as designed — the settle only aborts when
EVERY row is isolated on every seed. Here the one real pair (0 and 4) clears the
floor, so the graph builds and the rows with no neighbours are simply reported
isolated. A real cache with more near-duplicates has more edges; nothing here is
a workaround.

One limit, stated in the tool description rather than worked around here:
`make_searchable` builds an already-loaded family. It does not create the family
or insert rows (do that first), and it cannot pass an explicit `floor`. If your
corpus is sparse enough that its real neighbours sit below the exact-null
default (0.3314 at width 128) and the settle refuses with an empty graph, fall
back to `trellis_template_settle` with an explicit `floor` below your neighbour
cosine — that is the one case the one-call path cannot cover.

## Grading an index

`build_oracle` asks the **engine** for ground truth: a full scan over every
committed row, in a bounded worker pool so it cannot starve live search, written
as the artifact `trellis_measure_recall` reads. Hand the path straight across.

```
build_oracle            name=toy query_ids=[0..29] top_k=10
  -> oracle_path "/…/udv23_oracles/toy/oracle_top10_q30.jsonl", rows_scanned 400
trellis_measure_recall  name=toy oracle_path="/…" k=10
  -> recall_at_k 0.600, p50_ms 0.63, n_queries 30
```

Cost is linear in queries times rows, so hold out a few hundred queries rather
than grading the whole family.

## Rolling k-means: saving a model and using it later

`cluster` answers "how does this data group?" — it labels rows and forgets. The
`kmeans_*` tools answer the harder question: "is this NEW data like what I saw
before?" That needs the model kept.

The shape is a **lineage**: a series of models over rolling windows. A one-off
model is a lineage of length one, so you never have to decide up front whether a
series will follow.

```
kmeans_save_model       fit the first window, save it       -> lineage_id, model_id
kmeans_advance          fit the next, warm-started          -> t=1, overlap_rows
kmeans_apply_model      score any rows with a saved model   -> assignments
kmeans_migration_graph  compare two windows of the series   -> typed edges
```

**`event_ts` is required at ingest.** These tools select rows by *when the thing
happened*, not by arrival order, so `upsert_sparse` needs `event_ts` in
epoch-milliseconds or the windows come back empty.

**Cluster ids do not carry meaning across windows.** Cluster 3 at `t=0` and
cluster 3 at `t=1` are labels from two independent fits. The migration graph
works out the correspondence from where the mass actually went, which is why you
need it rather than comparing label numbers. Read `overlap_rows` before trusting
it: the mapping is inferred from rows both windows contain, and a thin overlap
means thin evidence.

**Models are immutable and content-addressed.** Re-issuing an identical
`kmeans_save_model` returns `reused: true` and refits nothing.

## Continuous ingest

Once a family's template engine is resident — one initial settle — every upsert
batch advances the live index at first touch. Rows added after the build are
found at rank 1 with no second settle, which the harness checks explicitly.

## Release history

**0.3.4 — `window` on `make_searchable` (fixes the 0.3.3 one-call gap).** 0.3.3
lowered the settle floor but left `window` reachable only through the raw
`trellis_template_settle` (with a hand-built field_path); the sanctioned
`make_searchable` / `BuildUltradimV23TrellisIndex` had no window knob and
**silently ignored** a `window` a caller passed — accepted it, settled at 10,000,
returned success. That is a hidden-bug failure,
so 0.3.4 fixes the root cause: a `window` field on `BuildUltradimV23TrellisIndexRequest`,
threaded into the settle it runs, so `make_searchable(name, window=1)` does
record-by-record in one call with no field_path. `window=0` = unset (10,000
default), never 1 — on both Build and the raw settle (the raw settle previously
read `Some(0)` as window=1; fixed). **Also fixed the root cause of the silent
ignore, for every RPC:** the wheel's `call_json` dispatch now **rejects unknown
request fields** with an error naming the field, instead of deep-merging and then
dropping them. Before 0.3.4 a typo or an unsupported knob was accepted and dropped
with a `success` response, so success was no proof your field applied — that is
what let 0.3.3 swallow `window` on Build. **Behaviour change for callers:** a
request carrying a field the RPC does not have now raises
`unknown request field(s) [<name>] …` instead of silently succeeding; fix the
field name. Verified non-breaking across the 55-check MCP suite (no legitimate
call rejected). Rust test asserts Build+window=1 searchable, raw settle window=1
produces one window PER RECORD (`window_stats.len()==N`, the real discriminator),
and window=0 yields exactly one window (unset). Cut for all three platforms as one
pack. **Do not use 0.3.3 for `window=1` via make_searchable — it is silently
ignored there.**

**0.3.3 — record-by-record settle for prefill caches (all three platforms).**
One behaviour change, for prefill caches:
the trellis settle `window` micro-batch floor was lowered from 100 to **1**, so
`window=1` makes each upserted record searchable after a single settle pass with
no buffering. Default stays 10,000; no RPC added (count stays 201). `window=1` is
reachable only through `trellis_template_settle` — the high-level `make_searchable`
(and `BuildUltradimV23TrellisIndex`) hard-code window=10,000. Cut for macOS arm64,
Linux aarch64 and Linux x86_64 as one pack — the window=1 path was run
functionally on each platform (the test suite's window=1
section: settle accepted, record searchable after one pass), and each reports 201
RPCs. The health banner now reports the loaded wheel's real `__version__` (was a
hand-maintained constant that had drifted), so `wheel: "0.3.3"` confirms the fix.

**0.3.2 — two customer-requested features (all three platforms).** Two additive
features, now in the wheel:

- **Multi-family search — `UltradimV23MultiFamilySearch`.** A new RPC that fans one query
  over N families and joins per-family scores on `row_id`; missing-in-family is
  the explicit `repeated bool present` marker, never a NaN sentinel. It reuses
  the single-family search core verbatim, so each `score[i]` bit-equals that
  family's own RPC. **This is the RPC that makes the count 201, not 200.**
- **Facet maps on upsert.** `int64`/`keyword` facets carried on the
  upsert batch, validated server-side (length-aligned, reserved keys refused by
  name), and a facet push-down on the template search filter — the filtered
  search fills `top_k` with qualifying rows during collection, not by
  post-filtering a fixed take.

0.3.2 is cut for macOS arm64, Linux aarch64 and Linux x86_64 (the Linux pair
built in the manylinux2014 container). All three report 201 RPCs and serve the
new RPC. Verified end to end: `len(capabilities()) == 201` on every platform,
and the test suite passes with the multi-family and facet
sections running (the facet push-down that returned nothing against the earlier
wheel now returns its qualifying hits — it was the missing wheel, not a code
bug). Full provenance in `wheels_0_3_2_manifest.txt`.

**0.3.1 — the crystal-clear front door.** The RPC list is unchanged from
0.3.0 (the wheel's two 0.3.1 changes are engine-internal — an ESN RNG guard and
a retrieval knob — and reach no new call path). What changed is the server's
clarity, in response to a customer's confusion:

- **`make_searchable(name)` is the one-call way in.** It drives
  `BuildUltradimV23TrellisIndex`, which resolves-or-synthesises the node field
  and settles the index in one call, so the common case needs no `field_path`
  and no noise floor. The raw `trellis_template_settle` stays for the one case
  it cannot cover — passing an explicit `floor` for a low-similarity corpus.
- **The live search RPC is named.** `UltradimV23TrellisTemplateSearch`
  is the canonical k-NN RPC; `list_rpcs` and `describe_rpc` now carry a status
  per RPC and name it, so no one mistakes the reinstatement map's stale "Class C
  dead" for the truth (all three search RPCs are live and route to the same
  core).
- **Tool descriptions carry their one gotcha inline** — settle's `field_path`,
  the noise floor refusing a sparse corpus, the live search RPC. The settle
  tool's floor text was corrected: the default is the exact-null 0.3314 at width
  128, not the old `6/sqrt(D_proj)` = 0.53 it used to claim.

**0.3.0 — 200 RPCs live.** Every name in the API is implemented. The server
was rewritten against that: the ten tools the 0.2.0 server described as
"RETIRED on this build" now describe live behaviour, and three further
corrections came out of re-probing rather than re-reading —

- **Dense is live.** 0.2.0 refused dense creation in Python before the engine
  saw the request. Measured on 0.3.0: create, upsert, settle, and search returns
  the query row at rank 1 with score 1.0. The refusal is gone and `upsert_dense`
  is new.
- **`build_oracle` calls the engine** (it was `write_oracle`). 0.2.0 computed
  exact top-k in Python because it believed `CreateSparseOracles` was retired.
  It is not, so the tool now takes query ids and a k rather than a
  caller-computed neighbour list.
- **`list_collections` reads the registry.** 0.2.0 listed the `udv23_csr`
  directory, which a dense family does not have, so dense families were
  invisible.

`wait_for_indexed` became `restart_indexing`: it triggers and returns rather
than waiting, so it no longer takes a timeout.

**0.2.0 — 7 RPCs live.** The API had been re-hosted on the current engine
but most of it had not yet been reimplemented. 200 names were reachable; seven
answered (health, family create and upsert, the three WideTrellis template RPCs,
and recall measurement) while the other 193 returned a precondition naming their
successor. The server kept every tool registered and passed those preconditions
through verbatim, so a caller could tell "superseded" from "never existed".

**0.1.x — 200 RPCs on the previous engine.** The API ran on the host
database that was removed on 2026-08-02. The Python package was `ultradimdb`
and offered a curated façade plus a keyword raw-call; both are gone. The only
call path now is `db.call_json("RpcName", '{…}')`, returning a JSON string.

## Design notes

**stdout is protocol-only.** MCP frames go to stdout, so every diagnostic —
including the wheel's own logging — goes to stderr. The engine is silent on
stdout by design; that is what makes an in-process MCP server viable rather than
a stream-corruption hazard.

**Tool failures come back as content, not protocol errors.** The engine's
messages name the row, the seed, the field and the substrate, so they are worth
surfacing verbatim to the model, which can then correct its own call.

**No SDK dependency.** JSON-RPC 2.0 over stdio is implemented directly against
the wire format (MCP `2024-11-05`), so the only requirement is the wheel.

**Row ids start at 0** and must extend the family contiguously. Omit `row_ids`
and the tool computes the continuation for you, at the cost of one
rejected probe upsert per call — so pass them explicitly in a tight ingest loop.

## Checking it works

Handshake and tool list:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3.12 mcp/ultradim_mcp_server_v0_4_0.py --db ./probe
```

Expect two JSON frames on stdout.

The full harness drives every tool handler directly — no MCP client, no server
process — against a throwaway storage root it creates and removes, and exits
non-zero on the first broken expectation:

```bash
python3.12 mcp/test_ultradim_mcp_server_v0_4_0.py
```

It needs the 128-wide node field the settle projects against. That file,
`mcp/trellis_field_128d.field`, ships beside the harness; it is deterministic,
so every copy is the same bytes. Point `ULTRADIM_TRELLIS_FIELD` at a different
one if you have made your own, and set `ULTRADIM_TEST_DB` to keep the store for
inspection instead of having it removed on success.

Last run: **118 checks, all passing** — including `make_searchable` end to end
with no `field_path`, the authoritative `list_rpcs`/`describe_rpc` status, the
replace/delete lifecycle over the JSON path, in-process recovery from an
injected tail failure, and the journal-clear out-of-service path — against
extension module `ed14a4c7191d5eea…` (wheel 0.4.0).
