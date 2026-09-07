#!/usr/bin/env python3
"""UltraDim MCP server — expose the embedded engine as MCP tools.

Speaks MCP over stdio, so an assistant can create a family, ingest vectors,
build the WideTrellis index, search it and grade it without the caller writing
any Python. The database runs in-process here; there is no server process.

========================================================================
START HERE
========================================================================
0. ONE ENGINE, ONE API. There is exactly one database and it lives in the
   `ultradim` wheel. It is reached three ways, and ALL THREE expose the IDENTICAL
   RPC list — nothing is in one and missing from another:
     (a) EMBEDDED, in-process: `db = ultradim.UltraDim(path)` then
         `db.call_json("RpcName", '{…}')`. No server, no port. This is the whole
         database, the simplest path.
     (b) THIS MCP SERVER: a thin wrapper that calls the SAME embedded wheel and
         names the RPCs as tools. It adds no capability.
     (c) gRPC server (the client-server edition, :6334, UltraDimClient): the SAME
         engine behind a socket, for out-of-process callers.
   A UMAP / clustering example shown over gRPC is NOT a fuller API — the same
   call is `db.call_json("FitUltradimV23Umap", '{…}')` embedded. If you already
   drive the wheel in-process, do EVERYTHING in-process — search, UMAP, HDBSCAN,
   k-means, all of it. Pick the transport for your process, not for the feature.
   `capabilities()` returns the same list on all three.

1. VERSION. The server filename tracks the wheel it is built against; every
   release bumps the filename to match (this file is the current one). Install
   the matching wheel and run this file:
       pip install ./UltraDim-<version>-cp312-cp312-<platform>.whl
       python <this file> --db ./mydb
   The `wheel:` field in the health output reports the ACTUAL loaded
   `ultradim.__version__`, and `version_aligned` says whether it matches this
   file. If `version_aligned` is false, the wheel and the server file are out of
   step; reinstall the matching wheel.

2. WHAT CAN THIS DO? Ask the server, do not guess from docs. The
   `whats_available` tool prints, from the live wheel: the version, the happy
   path, the analytics RPCs, and every RPC the wheel actually exposes, grouped.
   That listing is generated from the wheel's own `capabilities()`, so it is
   never stale. `list_rpcs` gives the flat list; `describe_rpc` names an RPC.

3. THE HAPPY PATH (WideTrellis): create_collection -> upsert_sparse ->
   make_searchable -> trellis_template_search  (+ `cluster` for analytics).
   Do NOT use the retired UltradimV23Search / get_keys.

WHAT "SETTLE" MEANS. Throughout this server, to "settle" a family means to
FINISH INDEXING its records — build the searchable index over the rows you have
upserted. A row is not searchable until the family has been settled. `make_
searchable` is the one-call way to do it; `trellis_template_settle` is the raw
form. The `window` knob is how many records are indexed per commit.

CHOOSING YOUR `window` — READ THIS, it decides your latency:

  * SENDING RECORDS ONE AT A TIME (singletons)? Use `window=1`. Each record is
    added to the index the moment it arrives — immediately searchable, no wait.
    This is what you want if a record must be findable right after you send it.

  * THE COST: `window=1` runs one full indexing pass PER RECORD, so a stream of
    singletons is SLOW. If you are pushing many records, that overhead adds up.

  * THE RECOMMENDED MIDDLE GROUND: collect records for a short interval — about
    ONE MINUTE is a good default — then upsert them as one small batch (a
    "micro-batch") with `window` set to that batch's size. You get near-realtime
    freshness without paying the per-record indexing cost. This is a PREFERENCE,
    not a rule: pick the interval that suits you. Every minute, every 10 seconds,
    every 500 records — your call. window=1 on singletons and a periodic
    micro-batch are the two ends; anything between is fine.

  * BULK LOADING a whole corpus at once? Leave `window` at its 10,000 default.

Once a family has been settled once and its engine is resident, every later
upsert advances the live index at first touch — so after the initial build you
keep streaming (singletons at window=1, or your periodic micro-batches) and each
new record becomes searchable as it lands, with no second settle call.

ANALYTICS (2026-08-13): the UMAP and HDBSCAN density-map engine is now surfaced
as first-class tools. Both start from a SETTLED family (the kNN graph needs a
resident template engine): make_searchable -> build_knn_graph -> fit_umap ->
umap_embedding, and make_searchable -> build_knn_graph -> create_hdbscan_lineage
-> advance -> apply. Previously these RPCs were reachable only via call_rpc. Call
`whats_available` and see the "umap / density maps" group. Shipped in wheel 0.3.6
(no new engine RPC — the RPC count stays 202; the bump marks the new tools).

TUNING (added 2026-08-13 in wheel 0.3.7): the `autotune` tool points at a sample of your
data and finds a configuration that clears the recall gate — the remedy for a
refused gate, so a limit is never called "intrinsic" without a sweep as evidence.
Two facts it encodes, both documented in docs/UltraDim_Tuning_Guide.md: the live
retrieval setting on `trellis_measure_recall` is `active_seeds` (top_m/hnsw_ef are
accepted-but-ignored by the engine on this build — see the tuning guide), and `exclude_self` must stay true for a self-query test or recall is
exactly 0.9. To raise recall: use more seeds first (free), then rebuild
wider (projection_dim).

Implemented is not the same as accepting your family: every RPC answers, but a call can still be
refused for the family it names (wrong substrate, or the records not yet
indexed). Those refusals come back as the engine's own text.

The only call path into the wheel is

    db.call_json("RpcName", '{"field": value, ...}')  -> JSON string

with a partial-JSON deep-merge contract — fields you omit take their proto
defaults, so a request states only what it means to change.

STDIO DISCIPLINE: MCP uses stdout for protocol frames, so NOTHING else may be
written there. Every diagnostic in this file goes to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import traceback
from typing import Any

import ultradim

PROTOCOL_VERSION = "2024-11-05"
# SERVER_VERSION is the ACTUAL loaded wheel version (ultradim.__version__ =
# CARGO_PKG_VERSION) — never a hand-maintained constant.
SERVER_VERSION = getattr(ultradim, "__version__", None) or "unknown"


def _expected_version_from_filename() -> str:
    """The version this server FILE is built for, parsed from its own name.

    The filename tracks the wheel (ultradim_mcp_server_v0_3_5.py -> 0.3.5). We
    derive the expected version from the name rather than hardcoding a literal,
    so a future rename is ONE move (rename the file) and the alignment check
    follows automatically — no second literal to forget. If the name ever stops
    matching the pattern, alignment is reported unknown rather than silently
    wrong.
    """
    m = re.search(r"_v(\d+)_(\d+)_(\d+)\.py$", os.path.basename(__file__))
    return ".".join(m.groups()) if m else "unknown"


EXPECTED_VERSION = _expected_version_from_filename()
VERSION_ALIGNED = SERVER_VERSION == EXPECTED_VERSION
SERVER_INFO = {"name": "ultradim", "version": SERVER_VERSION}

# No hardcoded live/retired split any more. On 0.3.0+ every name the wheel
# reports is implemented, so `list_rpcs` reads capabilities() and says so; a
# frozen set here would be a second source of truth waiting to go stale
# against the wheel actually loaded.
#
# The one thing capabilities() cannot say is the RELATIONSHIP between RPCs that
# answer the same question — which is the canonical one and which are compat
# wrappers routing to it. The reinstatement map (RPC_REINSTATEMENT_MAP_v0_01,
# dated 2026-08-03, "analysis only, no code changed") labelled several of these
# "Class C dead" / "superseded", but the final-sweep reinstatement wired them
# all to real implementations on the template engine (verified in
# ultradimdb/src/service.rs), so "dead" is the wrong word for an RPC the
# harness exercises green. This table records the status the SOURCE shows, so
# list_rpcs/describe_rpc can be authoritative about it. Every entry is "live";
# the note names the canonical RPC to prefer for new work.
RPC_STATUS: dict[str, dict[str, str]] = {
    "UltradimV23TrellisTemplateSearch": {
        "status": "live",
        "note": (
            "canonical k-NN search RPC; scores are exact cosines. Prefer this for "
            "new work."
        ),
    },
    "UltradimV23TrellisSearch": {
        "status": "live",
        "note": (
            "live compat wrapper routing to UltradimV23TrellisTemplateSearch's "
            "k-NN core. Sparse query only."
        ),
    },
    "UltradimV23Search": {
        "status": "live",
        "note": (
            "live — reinstated in the final sweep, re-routed onto the same "
            "k-NN core. The reinstatement map's "
            "'Class C dead' is stale."
        ),
    },
    "BuildUltradimV23TrellisIndex": {
        "status": "live",
        "note": (
            "live compat wrapper on the template engine — the sanctioned "
            "make-searchable RPC; make_searchable tool "
            "drives it. The reinstatement map's 'superseded' is stale."
        ),
    },
    "GetUltradimV23TrellisIndexInfo": {
        "status": "live",
        "note": (
            "live compat wrapper on the template engine. "
            "For build progress prefer GetUltradimV23TrellisTemplateStatus."
        ),
    },
}


def wheel_fingerprint() -> dict[str, Any]:
    """Identify the loaded wheel by the sha256 of its native module.

    A version string is not an identification: 0.3.0 was rebuilt more than
    once, and two builds bearing that version can differ. The extension
    module's digest is what distinguishes them, so every report this server
    makes about its own capabilities carries the digest that produced it.
    """
    pkg_dir = os.path.dirname(os.path.abspath(ultradim.__file__))
    for entry in sorted(os.listdir(pkg_dir)):
        if entry.endswith((".so", ".pyd", ".dylib")):
            path = os.path.join(pkg_dir, entry)
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            return {"module": entry, "sha256": digest, "path": path}
    return {"module": None, "sha256": None, "path": pkg_dir}


def log(msg: str) -> None:
    """Diagnostics to stderr — stdout belongs to the protocol."""
    print(f"[ultradim-mcp/{SERVER_VERSION}] {msg}", file=sys.stderr, flush=True)


class RetiredRpc(RuntimeError):
    """A tool this wheel cannot serve. Carries the engine's own text.

    On 0.3.0 the engine raises no retirement precondition, so this is reached
    only by `describe_rpc`, which needs a proto descriptor the wheel does not
    carry. It is kept because the harness and callers distinguish "cannot be
    served at all" from an ordinary argument or state error.
    """


def flatten_point_id(pid: Any) -> Any:
    """Unwrap the proto point id `{"point_id_options": {"Num": 7}}` to `7`.

    The JSON is a faithful rendering of the wire message, but three levels of
    wrapper around an integer is noise for a reader, and the ids come back out
    of this tool to be fed straight into `exclude_ids` or an oracle.
    """
    if isinstance(pid, dict):
        opts = pid.get("point_id_options", pid)
        if isinstance(opts, dict):
            for key in ("Num", "num", "Uuid", "uuid"):
                if key in opts:
                    return opts[key]
    return pid


def _facet_map(fields: dict[str, Any]) -> dict[str, Any]:
    """Render one row's flat facet dict to the wire `UdV23FacetMap` (facet maps).

    The wire value is a oneof `{"kind": {"IntValue": n}}` or
    `{"kind": {"KeywordValue": s}}` — the two types the engine filters on
    (int -> MatchInt/RangeInt, str -> MatchKeyword). A float or bool value is
    rejected HERE, before the wire, because the engine has no float-range or
    bool-match condition; sending one would store an unfilterable facet. The
    externally-tagged PascalCase variant name (`IntValue`/`KeywordValue`) is how
    serde renders the proto oneof, matching `UdV23FilterCondition.cond`.
    """
    out: dict[str, Any] = {}
    for name, val in fields.items():
        # bool is a subclass of int in Python — check it FIRST, and reject it,
        # so True does not silently become IntValue(1).
        if isinstance(val, bool):
            raise ValueError(
                f"facet '{name}': bool values are not supported (no bool-match "
                "condition); use an int (e.g. 0/1) as a keyword or int facet."
            )
        if isinstance(val, int):
            out[name] = {"kind": {"IntValue": int(val)}}
        elif isinstance(val, str):
            out[name] = {"kind": {"KeywordValue": val}}
        else:
            raise ValueError(
                f"facet '{name}': value must be int or str, got {type(val).__name__} "
                "(the engine filters int64 via MatchInt/RangeInt and string via "
                "MatchKeyword — no float ranges in this cut)."
            )
    return {"fields": out}


def _template_filter(spec: dict[str, Any]) -> dict[str, Any]:
    """Render a friendly filter dict to the wire `UdV23Filter` (facet maps, search side).

    Input: {"must": [{"field": F, "match_int": N} | {"field": F,
    "match_keyword": S} | {"field": F, "range_int": {"gte": a, "lte": b}}]}.
    The wire oneof is externally tagged in PascalCase (`{"cond": {"MatchInt": n}}`)
    — the same shape serde gives `UdV23FilterCondition.cond` — so the friendly
    lower-snake key is mapped here rather than pushed onto the caller.
    """
    must_in = spec.get("must", [])
    if not isinstance(must_in, list):
        raise ValueError("template_filter.must must be a list of conditions")
    must_out: list[dict[str, Any]] = []
    for i, c in enumerate(must_in):
        field = c.get("field")
        if not field:
            raise ValueError(f"template_filter.must[{i}] needs a 'field'")
        if "match_int" in c:
            cond = {"MatchInt": int(c["match_int"])}
        elif "match_keyword" in c:
            cond = {"MatchKeyword": str(c["match_keyword"])}
        elif "range_int" in c:
            r = c["range_int"]
            rng: dict[str, Any] = {}
            if r.get("gte") is not None:
                rng["gte"] = int(r["gte"])
            if r.get("lte") is not None:
                rng["lte"] = int(r["lte"])
            cond = {"RangeInt": rng}
        else:
            raise ValueError(
                f"template_filter.must[{i}] needs one of match_int / "
                "match_keyword / range_int"
            )
        must_out.append({"field": str(field), "cond": cond})
    return {"must": must_out}


# UMAP enum maps. The proto enums (UmapInit, UmapOutputMetric) are i32 on the
# wire, and serde over the JSON call path takes the INTEGER, not the name — a
# friendly string is rejected ("invalid type: string, expected i32"), the same
# silent-drop class as the facet oneof. So these tools take a friendly string and
# map it here; an unknown value raises rather than silently defaulting.
_UMAP_INIT_WIRE = {"annealed": 0, "spectral": 1, "random": 2}
_UMAP_METRIC_WIRE = {"euclidean": 0, "spherical": 1}


def _umap_init_wire(s: str) -> int:
    """Friendly UMAP init string -> UmapInit enum int (annealed/spectral/random)."""
    try:
        return _UMAP_INIT_WIRE[s]
    except KeyError:
        raise ValueError(
            f"init '{s}' is not one of {sorted(_UMAP_INIT_WIRE)}"
        ) from None


def _umap_metric_wire(s: str) -> int:
    """Friendly UMAP output metric string -> UmapOutputMetric enum int."""
    try:
        return _UMAP_METRIC_WIRE[s]
    except KeyError:
        raise ValueError(
            f"output_metric '{s}' is not one of {sorted(_UMAP_METRIC_WIRE)}"
        ) from None


def _queries_wire(queries: list[Any]) -> dict[str, Any]:
    """Render a plain query list to the wire dense-XOR-sparse pair.

    A UMAP transform / HDBSCAN apply takes EITHER dense_queries (a list of
    `{"data": [floats]}`) OR sparse_queries (a list of `{"indices","values"}`) —
    never both. The caller passes one plain list and this builds the right side:
      - list of list-of-number  -> dense_queries
      - list of {indices,values} -> sparse_queries
    A mixed list, an empty list, or an unrecognised element raises (an
    empty list has no defined side, so it is an error, not a silent no-op).
    """
    if not queries:
        raise ValueError(
            "queries is empty: pass at least one dense vector ([floats]) or one "
            "sparse vector ({'indices':[...], 'values':[...]})"
        )
    is_dense = [isinstance(q, (list, tuple)) for q in queries]
    is_sparse = [isinstance(q, dict) and "indices" in q and "values" in q for q in queries]
    if all(is_dense):
        return {"dense_queries": [{"data": [float(x) for x in q]} for q in queries]}
    if all(is_sparse):
        return {
            "sparse_queries": [
                {
                    "indices": [int(i) for i in q["indices"]],
                    "values": [float(v) for v in q["values"]],
                }
                for q in queries
            ]
        }
    raise ValueError(
        "queries must be ALL dense ([float,...] each) or ALL sparse "
        "({'indices':[...], 'values':[...]} each), not a mix or an unrecognised "
        "shape"
    )


# --------------------------------------------------------------------------
# Tool definitions. `inputSchema` is what the model reads to call correctly,
# so each one states units, defaults and the non-obvious contracts (row ids
# start at 0 and must stay contiguous; the field artifact must match the
# family's projection width).
# --------------------------------------------------------------------------
TOOLS: list[dict[str, Any]] = [
    {
        "name": "whats_available",
        "description": (
            "START HERE. Answers 'what can this database do?' — the version, "
            "the happy path, the analytics RPCs, the retired RPCs to avoid, and "
            "every RPC the loaded wheel exposes grouped by area. Generated live "
            "from the wheel's own capabilities(), so it is authoritative and "
            "never stale. If you think a feature is missing, call this FIRST — "
            "it is probably here under a name you did not expect."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "health",
        "description": (
            "Is the embedded engine answering? Returns the engine's health "
            "status plus the RPC count. The quickest way to confirm "
            "the wheel loaded and the storage root opened."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_collections",
        "description": (
            "List the families in this database with their row counts and "
            "WideTrellis build state. Start here to see what exists."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_collection",
        "description": (
            "Create a family, sparse or dense. Both substrates serve through "
            "the WideTrellis template engine, so either way the family must be "
            "settled before it can be searched. `sparse` defaults to true; set "
            "it false and pass dense vectors to upsert_dense. "
            "`projection_dim` must equal the width of the node-field artifact "
            "you will settle against (the 128-D field needs projection_dim "
            "128). `max_nnz_per_row` caps the non-zeros admitted per row and "
            "applies to sparse families only. Note that `cluster` serves "
            "sparse families only — everything else works on both."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Family name."},
                "source_dim": {
                    "type": "integer",
                    "description": "Dimensionality of the vectors you will insert (D_raw).",
                },
                "projection_dim": {
                    "type": "integer",
                    "description": (
                        "Working width the walk runs at. Must match the node-field "
                        "artifact used at settle time. Default 128."
                    ),
                },
                "seeds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Projection seeds, 1 to 8 of them. Default [11, 22, 33, 44].",
                },
                "max_nnz_per_row": {
                    "type": "integer",
                    "description": (
                        "Maximum non-zeros admitted per row, sparse only. Default 64."
                    ),
                },
                "sparse": {
                    "type": "boolean",
                    "description": (
                        "Sparse substrate. Default true. Set false for a dense "
                        "family, which settles and searches like a sparse one."
                    ),
                },
            },
            "required": ["name", "source_dim"],
        },
    },
    {
        "name": "upsert_sparse",
        "description": (
            "Insert sparse rows. Each row is {indices: [...], values: [...]} "
            "with STRICTLY ASCENDING unique indices below source_dim, and the "
            "values L2-normalised (the engine rejects a row whose squared norm "
            "is off by more than 1e-4). Row ids must EXTEND THE FAMILY "
            "CONTIGUOUSLY from the count already committed — the first batch "
            "starts at 0, not 1. Omit `row_ids` and this tool computes that "
            "continuation for you. Once the family's template engine is "
            "resident, every batch advances the live index at first touch, so "
            "no second settle is needed for rows added after the build."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "rows": {
                    "type": "array",
                    "description": "Sparse rows: [{indices: [int], values: [float]}].",
                    "items": {
                        "type": "object",
                        "properties": {
                            "indices": {"type": "array", "items": {"type": "integer"}},
                            "values": {"type": "array", "items": {"type": "number"}},
                        },
                    },
                },
                "row_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "One id per row, contiguous from the committed count. "
                        "Omit to continue automatically — which costs two "
                        "extra round trips per call (one to read the family's "
                        "substrate, one rejected upsert to read "
                        "the count out of the engine), so pass ids explicitly "
                        "in a tight ingest loop."
                    ),
                },
                "skip_degenerate": {
                    "type": "boolean",
                    "description": (
                        "Drop rows whose projection has a zero norm instead of "
                        "failing the whole batch; the dropped ids come back in "
                        "`skipped_row_ids`."
                    ),
                },
                "event_ts": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Epoch-MILLISECONDS per row: when the thing actually "
                        "happened, as distinct from when we received it."
                    ),
                },
            },
            "required": ["name", "rows"],
        },
    },
    {
        "name": "upsert_dense",
        "description": (
            "Insert dense rows into a DENSE family. Each vector must have "
            "exactly source_dim components. The same contiguity rule as the "
            "sparse path applies — ids extend the family from the count "
            "already committed, starting at 0 — and omitting `row_ids` "
            "computes that continuation for you. Settle afterwards to make "
            "the rows searchable."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "vectors": {
                    "type": "array",
                    "description": "Dense rows, each source_dim floats.",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "row_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "One id per vector, contiguous from the committed count. "
                        "Omit to continue automatically, at the cost of two "
                        "extra round trips per call — pass ids explicitly in a "
                        "tight ingest loop."
                    ),
                },
            },
            "required": ["name", "vectors"],
        },
    },
    {
        "name": "make_searchable",
        "description": (
            "THE sanctioned one-call way to make a loaded family searchable — "
            "i.e. to FINISH INDEXING its records ('settle' is this server's word "
            "for 'finish indexing'; a row is not searchable until the family is "
            "settled). "
            "Drives BuildUltradimV23TrellisIndex, which resolves-or-synthesises "
            "the node-field artifact and settles the index in one call, so you "
            "pass NEITHER a field_path NOR a noise floor. Use this instead of "
            "the raw trellis_template_settle for the common case. GOTCHA — it "
            "builds an ALREADY-LOADED family; it does not create the family and "
            "does not upsert rows (do create_collection then upsert_* first, or "
            "it returns 'has no rows'). It also cannot pass an explicit floor: "
            "a sparse or low-similarity corpus that trips the empty-graph guard "
            "cannot be rescued here — fall back to trellis_template_settle with "
            "an explicit `floor` for that one case. Runs synchronously and "
            "returns the built graph's figures (graph_nodes, rows_total, "
            "build_ms, epoch_hash); there is no status to poll afterwards. "
            "Long-running at volume (the settle underneath is ~80 min per 500k "
            "rows); a few hundred toy rows finish in well under a second."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Family to make searchable."},
                "edge_degree": {
                    "type": "integer",
                    "description": (
                        "Neighbour tier width. Omit for the "
                        "proven default tier shape (13/16)."
                    ),
                },
                "refine_rounds": {
                    "type": "integer",
                    "description": (
                        "Offline correction passes after the stream. Omit for 0 "
                        "(rolling correction only, the template default)."
                    ),
                },
                "window": {
                    "type": "integer",
                    "description": (
                        "How many records are indexed per commit. THREE choices: "
                        "(1) SINGLETONS — sending records one at a time and each "
                        "must be searchable immediately? Use window=1: the record "
                        "is added to the index the moment it arrives. It is SLOWER "
                        "(one indexing pass per record). "
                        "(2) MICRO-BATCH (recommended for a stream) — collect "
                        "records for a short interval (~1 minute is a good "
                        "default; your call) and upsert them together with window "
                        "set to that batch size: near-realtime, without the "
                        "per-record cost. "
                        "(3) BULK — loading a whole corpus at once? Omit this for "
                        "the 10,000 default. 0 = unset (takes the 10,000 default, "
                        "NOT window=1)."
                    ),
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_row_by_content_key",
        "description": (
            "EXACT identity lookup — 'have I seen this EXACT thing before?' Give "
            "a family and the exact key string you stored on a row (see below), "
            "and get that row's numeric id back, or found=false. This is NOT a "
            "search: it does not run the cosine walk and it does not rank — it is "
            "a point lookup by an exact key. It answers even BEFORE the family is "
            "indexed (settled), so you can store a key and immediately ask if it "
            "is present. Note it is exact-string only: a one-character difference "
            "misses. HOW TO STORE THE KEY: when you upsert_sparse, put your key in "
            "the row's facet metadata under the name 'content_key' (a keyword "
            "facet). This tool then finds it. Collisions are the caller's to "
            "resolve — the lookup routes a key to a row, it does not prove they "
            "are the same content."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The family to look in."},
                "content_key": {
                    "type": "string",
                    "description": "The exact key string to match (stored under the "
                    "'content_key' facet at upsert).",
                },
                "facet_name": {
                    "type": "string",
                    "description": "Which facet holds the key. Omit for the default "
                    "'content_key'. Set only if you stored it under a different name.",
                },
            },
            "required": ["name", "content_key"],
        },
    },
    {
        "name": "replace_sparse_point",
        "description": (
            "Replace the sparse vector held for a row you already know — the "
            "'update this record' operation, as opposed to upsert_sparse, which "
            "only ever ADDS. Use it when one row tracks a thing's CURRENT state "
            "and the state has moved on. Sparse families only. IMPORTANT, and it "
            "surprises people: row ids do not change in place. The old row is "
            "retired and the replacement is written at a NEW row id, which comes "
            "back in the response. What stays stable is your own key — the "
            "'content_key' facet — so get_row_by_content_key keeps finding the "
            "current row. METADATA: leave 'facets' out and the old row's metadata "
            "is carried over wholesale; supply it and it REPLACES the old metadata "
            "entirely (an empty map therefore clears it). There is no partial "
            "merge — you would not be able to tell which of your "
            "fields survived. Your content_key is protected either way: omit it "
            "and it is carried over, but trying to CHANGE it is refused, because "
            "that is a delete plus an insert and should be asked for as two calls. "
            "Retrying a replace that already succeeded is safe: it comes back "
            "success=false with already_replaced=true and tells you the row id the "
            "first call produced, rather than creating a second copy."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The family."},
                "old_row_id": {
                    "type": "integer",
                    "description": "The row being replaced. Find it with "
                    "get_row_by_content_key if you know the key but not the id.",
                },
                "indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "The replacement vector's indices, ascending "
                    "and unique.",
                },
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "The replacement vector's values, aligned with "
                    "indices and L2-normalised (they must square-sum to 1).",
                },
                "facets": {
                    "type": "object",
                    "description": "The replacement's metadata as a flat "
                    "string-to-string map. OMIT to keep the old row's metadata; "
                    "supply it to replace the metadata outright.",
                },
                "event_ts": {
                    "type": "integer",
                    "description": "The replacement's event time (epoch ms). When "
                    "you supply 'facets' and omit this, the old event time is "
                    "dropped along with the rest of the old metadata.",
                },
            },
            "required": ["name", "old_row_id", "indices", "values"],
        },
    },
    {
        "name": "delete_sparse_point",
        "description": (
            "Retire a row so no search or lookup returns it again. Sparse "
            "families only. The row id is NOT freed and the family's row count "
            "does not go down — the row simply stops being visible, which is what "
            "keeps every other row's id stable. Safe to repeat: deleting an "
            "already-deleted row succeeds and tells you it was already gone. "
            "There is no undelete."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The family."},
                "row_id": {"type": "integer", "description": "The row to retire."},
            },
            "required": ["name", "row_id"],
        },
    },
    # -- UMAP + HDBSCAN density maps (the analytics RPCs) -------------------
    {
        "name": "build_knn_graph",
        "description": (
            "Build (or extend) the stored kNN graph that a UMAP fit or an HDBSCAN "
            "lineage is built over. The family must be SETTLED FIRST (run "
            "make_searchable) — the graph needs a resident template engine and "
            "must see every row, so an unsettled family (or unflushed appended "
            "rows) is refused. Do this BEFORE fit_umap or create_hdbscan_lineage. "
            "`append=true` extends an existing graph with new rows (settle them "
            "first too), for incremental fit or lineage advance."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The family."},
                "k": {"type": "integer", "description": "Neighbours per row (engine default if omitted)."},
                "append": {"type": "boolean", "description": "Extend an existing graph rather than build fresh."},
                "row_ids": {"type": "array", "items": {"type": "integer"}, "description": "Rows to append (with append=true)."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "fit_umap",
        "description": (
            "Fit a UMAP embedding of a family (reduce its vectors to n_components "
            "dimensions for visualisation or downstream clustering). Needs a kNN "
            "graph first (build_knn_graph); an empty graph builds-or-reuses with "
            "defaults. Runs on the GPU. Expert knobs (learning_rate, "
            "negative_sample_rate, repulsion_strength, init_num_clusters, "
            "init_levels, checkpoint_every_epochs, force) are on the raw "
            "FitUltradimV23Umap via call_rpc."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The family."},
                "n_components": {"type": "integer", "description": "Output dims, 2..256 (default 2)."},
                "n_neighbors": {"type": "integer", "description": "UMAP n_neighbors (default 15; <= graph k)."},
                "min_dist": {"type": "number", "description": "UMAP min_dist (default 0.1)."},
                "output_metric": {"type": "string", "enum": ["euclidean", "spherical"], "description": "Embedding metric (default euclidean)."},
                "init": {"type": "string", "enum": ["annealed", "spectral", "random"], "description": "Initialisation (default annealed)."},
                "n_epochs": {"type": "integer", "description": "0/omit = auto."},
                "deterministic": {"type": "boolean", "description": "Bit-reproducible gather (default true)."},
                "seed": {"type": "integer", "description": "RNG seed."},
                "row_ids": {"type": "array", "items": {"type": "integer"}, "description": "Fit a subset of the graph rows."},
                "graph_id": {"type": "string", "description": "Pin a specific kNN graph; omit to build-or-reuse."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "transform_umap",
        "description": (
            "Place NEW points into an existing fitted UMAP map (out-of-sample "
            "projection). Returns each query's embedding coordinates. `queries` is "
            "a plain list — either dense vectors [[f,...],...] or sparse rows "
            "[{indices,values},...], matching the family's substrate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "umap_id": {"type": "string", "description": "The fitted map ('umap-{hash}')."},
                "queries": {"type": "array", "description": "Dense vectors or sparse rows to place."},
                "refine_epochs": {"type": "integer", "description": "0 = pure placement (default); 30 typical."},
                "return_diagnostics": {"type": "boolean"},
                "persist": {"type": "boolean", "description": "Append results into the embedding artifact (needs persist_row_ids)."},
                "persist_row_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["name", "umap_id", "queries"],
        },
    },
    {
        "name": "umap_embedding",
        "description": (
            "Read a fitted map's stored embedding, one page at a time. Returns "
            "per-row coordinates. Pass the previous response's next_offset_ordinal "
            "as offset_ordinal to continue."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "umap_id": {"type": "string"},
                "limit": {"type": "integer", "description": "Rows this page (default 1000; server may clamp)."},
                "offset_ordinal": {"type": "integer", "description": "First ordinal of this page (0-based)."},
            },
            "required": ["name", "umap_id"],
        },
    },
    {
        "name": "umap_info",
        "description": "Metadata for one fitted UMAP map (params, row count, provenance).",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "umap_id": {"type": "string"}},
            "required": ["name", "umap_id"],
        },
    },
    {
        "name": "list_umap_models",
        "description": "List the fitted UMAP maps on a family.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "drop_umap",
        "description": "Drop a fitted UMAP map.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "umap_id": {"type": "string"}},
            "required": ["name", "umap_id"],
        },
    },
    {
        "name": "incremental_fit_umap",
        "description": (
            "Fold a new batch into an existing fitted map without a full refit "
            "(the arriving rows must ALREADY be graph-appended via "
            "build_knn_graph append=true). `queries` is the same plain dense/"
            "sparse list as transform_umap. Research/sweep knobs (m_warm, m_floor, "
            "lambda_mass, wake_*, rebaseline_* [not yet wired], replay/spring) are "
            "on the raw IncrementalFitUltradimV23Umap via call_rpc, not here."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "parent_umap_id": {"type": "string", "description": "The fitted map the batch folds into."},
                "queries": {"type": "array", "description": "The arriving vectors (dense or sparse), echoed for placement."},
                "batch_row_ids": {"type": "array", "items": {"type": "integer"}, "description": "Graph row ids of the arrivals, in query order."},
                "e_micro": {"type": "integer", "description": "Micro-fit epochs; 0 = default (50)."},
                "fold_search": {"type": "string", "enum": ["", "exact", "approx"], "description": "Neighbour-search class; empty = substrate default."},
                "persist": {"type": "boolean"},
            },
            "required": ["name", "parent_umap_id", "queries", "batch_row_ids"],
        },
    },
    {
        "name": "create_hdbscan_lineage",
        "description": (
            "Open a density-clustering (HDBSCAN) lineage over a family, advanced "
            "over time windows. `graph_id` is REQUIRED — build it first with "
            "build_knn_graph. Then advance_hdbscan_lineage adds time steps, and "
            "apply_hdbscan / cowalk_hdbscan / hdbscan_migration_graph read it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "graph_id": {"type": "string", "description": "The stored base kNN graph ('umapknn-{hash}') — REQUIRED."},
                "min_samples": {"type": "integer", "description": "0 = derive from N (default); else 1..k."},
                "lineage_tag": {"type": "string", "description": "Optional label so multiple lineages with equal params coexist."},
            },
            "required": ["name", "graph_id"],
        },
    },
    {
        "name": "advance_hdbscan_lineage",
        "description": (
            "Advance a lineage by one time step with the arriving rows. Those rows "
            "must already be appended to the base graph (build_knn_graph "
            "append=true), their ordinals extending the lineage watermark "
            "contiguously — a gap or overlap is a loud error."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineage_id": {"type": "string", "description": "'hdb-{hash}' to advance."},
                "batch_row_ids": {"type": "array", "items": {"type": "integer"}, "description": "Graph row ids of the arrivals."},
                "fold_search": {"type": "string", "enum": ["", "exact", "approx"]},
            },
            "required": ["name", "lineage_id", "batch_row_ids"],
        },
    },
    {
        "name": "apply_hdbscan",
        "description": (
            "Assign a population to clusters as-of time t (or the latest committed "
            "t with t_latest=true). Population is EXACTLY ONE of `queries` (dense "
            "or sparse list) OR `row_ids` (in-sample). t is literal (t=0 = the t0 "
            "model). Research knobs (displacement_mode=oracle) are call_rpc only."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineage_id": {"type": "string"},
                "t": {"type": "integer", "description": "As-of t, literal (default 0)."},
                "t_latest": {"type": "boolean", "description": "Ignore t, use the latest committed t."},
                "queries": {"type": "array", "description": "External dense/sparse queries (XOR row_ids)."},
                "row_ids": {"type": "array", "items": {"type": "integer"}, "description": "In-sample rows (XOR queries)."},
                "min_cluster_size": {"type": "integer"},
                "selection": {"type": "string", "enum": ["eom", "leaf"]},
            },
            "required": ["name", "lineage_id"],
        },
    },
    {
        "name": "cowalk_hdbscan",
        "description": (
            "Compare one population's clustering at two times, t_a and t_b — both "
            "REQUIRED (a defaulted (0,0) is rejected, never a plausible "
            "t0-vs-t0 answer). Population is EXACTLY ONE of `queries` OR `row_ids`. "
            "t is literal (t=0 = the t0 model)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineage_id": {"type": "string"},
                "t_a": {"type": "integer", "description": "First as-of t (REQUIRED)."},
                "t_b": {"type": "integer", "description": "Second as-of t (REQUIRED)."},
                "queries": {"type": "array", "description": "External dense/sparse queries (XOR row_ids)."},
                "row_ids": {"type": "array", "items": {"type": "integer"}, "description": "In-sample rows (XOR queries)."},
                "min_cluster_size": {"type": "integer"},
                "selection": {"type": "string", "enum": ["eom", "leaf"]},
            },
            "required": ["name", "lineage_id", "t_a", "t_b"],
        },
    },
    {
        "name": "hdbscan_migration_graph",
        "description": (
            "The cluster migration graph between two times t_a and t_b — both "
            "REQUIRED ((0,0) rejected). Population is `row_ids`, OR set "
            "all_fitted_asof_t_a=true for every fitted row as-of t_a. t is literal."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineage_id": {"type": "string"},
                "t_a": {"type": "integer", "description": "First as-of t (REQUIRED)."},
                "t_b": {"type": "integer", "description": "Second as-of t (REQUIRED)."},
                "row_ids": {"type": "array", "items": {"type": "integer"}, "description": "Explicit in-sample population."},
                "all_fitted_asof_t_a": {"type": "boolean", "description": "Population = every fitted row as-of t_a (XOR row_ids)."},
                "min_cluster_size": {"type": "integer"},
                "selection": {"type": "string", "enum": ["eom", "leaf"]},
            },
            "required": ["name", "lineage_id", "t_a", "t_b"],
        },
    },
    {
        "name": "hdbscan_info",
        "description": "Metadata for one HDBSCAN lineage (params, watermark, committed t).",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "lineage_id": {"type": "string"}},
            "required": ["name", "lineage_id"],
        },
    },
    {
        "name": "list_hdbscan_lineages",
        "description": "List the HDBSCAN lineages on a family.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "compact_hdbscan_lineage",
        "description": "Compact a lineage's on-disk history (prune runs the cycle-property prune first, default true).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineage_id": {"type": "string"},
                "prune": {"type": "boolean"},
            },
            "required": ["name", "lineage_id"],
        },
    },
    {
        "name": "drop_hdbscan_lineage",
        "description": "Drop an HDBSCAN lineage.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "lineage_id": {"type": "string"}},
            "required": ["name", "lineage_id"],
        },
    },
    {
        "name": "trellis_template_settle",
        "description": (
            "The RAW low-level way to FINISH INDEXING a family's records "
            "('settle' = finish indexing; nothing is searchable until this has "
            "run). Prefer make_searchable, which "
            "needs no field_path or floor and takes the same `window` knob "
            "(including window=1 for record-by-record). Reach for this only "
            "when you must pass an explicit `floor` (a sparse/low-similarity "
            "corpus the default floor would refuse) or a specific "
            "field_path. GOTCHA "
            "— `field_path` is REQUIRED and must be a server-local TRLFIELD1 "
            "artifact whose width equals the family's projection_dim (absolute "
            "path when embedded). "
            "Build the WideTrellis index for a family: stream its rows through "
            "the windowed settle with the rolling correction (defaults: "
            "default floor, 10k windows, rolling lag 2), "
            "hold the engine resident. "
            "`field_path` is the server-local TRLFIELD1 node-field artifact and "
            "its width must equal the family's projection_dim. Long-running at "
            "volume: roughly 80 minutes per 500k rows, plus about an hour per "
            "optional correction pass — poll trellis_template_status while it "
            "runs. A few hundred toy rows settle in well under a second."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "field_path": {"type": "string", "description": "TRLFIELD1 artifact path."},
                "window": {
                    "type": "integer",
                    "description": (
                        "Records indexed per commit. SINGLETONS (one record at a "
                        "time, each searchable at once) → window=1 (slower, one "
                        "indexing pass per record). STREAM → collect ~1 minute of "
                        "records and upsert as a micro-batch with window=that size "
                        "(recommended: near-realtime without the per-record cost; "
                        "the interval is your preference). BULK → 10000 default; "
                        "0 = unset (10000, NOT window=1). Same knob as make_searchable."
                    ),
                },
                "rolling_lag": {
                    "type": "integer",
                    "description": "Rolling correction lag in windows; 0 disables. Default 2.",
                },
                "correction_passes": {
                    "type": "integer",
                    "description": "Offline passes after the stream. Default 0 (rolling only).",
                },
                "m": {"type": "integer", "description": "Neighbour tier width. Default 13."},
                "m_max": {"type": "integer", "description": "Max tier width. Default 16."},
                "floor": {
                    "type": "number",
                    "description": (
                        "Floor: the smallest similarity the settle keeps. The "
                        "default is set from the projection width (0.3314 at "
                        "width 128). A corpus whose real neighbour cosines all "
                        "sit below the default settles to nothing and is REFUSED "
                        "with 'settle produced an EMPTY graph' — that is policy "
                        "(an index of pure noise is refused), not a failed build. For "
                        "a sparse or low-similarity corpus whose meaningful "
                        "pairs sit below the default, pass `floor` explicitly, "
                        "set below your corpus's typical near-neighbour cosine "
                        "and above the noise bulk (~0.25 at width 128). This is "
                        "the ONE knob make_searchable cannot set, which is why "
                        "the raw settle stays exposed."
                    ),
                },
                "telemetry_stride": {
                    "type": "integer",
                    "description": (
                        "Brute-verify every Nth arrival against the rows already "
                        "loaded and return per-window statistics. 0 = recorder off."
                    ),
                },
            },
            "required": ["name", "field_path"],
        },
    },
    {
        "name": "trellis_template_search",
        "description": (
            "Search a WideTrellis-indexed family. Scores are exact cosines. "
            "`sparse_query` is {indices: [...], values: [...]}, L2-normalised. "
            "Returns `results` as [{id, score}], score descending (1.0 is "
            "identical). The effort knobs default to the measured bar "
            "configuration; raising the breadth settings raises recall and costs latency."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "sparse_query": {
                    "type": "object",
                    "properties": {
                        "indices": {"type": "array", "items": {"type": "integer"}},
                        "values": {"type": "array", "items": {"type": "number"}},
                    },
                },
                "top_k": {"type": "integer", "description": "Default 10."},
                "active_seeds": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Seed subset; omit for all the family's seeds.",
                },
                "exclude_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Ids to exclude, e.g. the query's own row.",
                },
                "walk_ef": {"type": "integer"},
                "walk_expansions": {"type": "integer"},
                "walk_row_budget": {"type": "integer"},
                "beam_ef": {"type": "integer"},
                "beam_expansions": {"type": "integer"},
                "take_per_seed": {
                    "type": "integer",
                    "description": "Candidates kept per seed.",
                },
            },
            "required": ["name", "sparse_query"],
        },
    },
    {
        "name": "trellis_template_status",
        "description": (
            "Health check for a WideTrellis build: phase (idle / reading-keys / "
            "settling / done), seeds completed, wall-clock so far, and whether "
            "the engine is resident (serving) and persisted (crash-safe states "
            "on disk). Poll this while trellis_template_settle runs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "trellis_measure_recall",
        "description": (
            "Grade the WideTrellis index server-side against a saved exact "
            "oracle: every oracle query is served through the template engine "
            "and scored, returning the recall/latency pair. This is the trusted "
            "measurement path. The oracle is JSON-lines, one object per query "
            "({query_id, neighbor_ids, neighbor_scores}), and must sit under "
            "<db>/udv23_oracles/<family>/ — the engine refuses a path outside "
            "that directory. Query VECTORS are not in the file; the engine "
            "reads each query's row out of the family by its id. "
            "TUNING: the live retrieval settings here are active_seeds (which of "
            "the family's seeds are used — build a family at many seeds, then use "
            "over a subset per call, no rebuild) and k. Always keep "
            "exclude_self=true when your query rows are in the index, or recall "
            "is exactly 0.9 (each row matches itself). NOTE this build does "
            "NOT accept top_m/hnsw_ef on recall — the underlying MeasureRecall "
            "RPC ignores them on the serving path, so they are not exposed here; "
            "to raise recall, use more seeds, then rebuild wider "
            "(projection_dim). See docs/UltraDim_Tuning_Guide.md and the pending "
            "the tuning guide. The autotune tool automates this."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "oracle_path": {"type": "string"},
                "k": {"type": "integer", "description": "recall@k. Default 10."},
                "exclude_self": {
                    "type": "boolean",
                    "description": "Exclude each query's own row from its results. Default true.",
                },
                "active_seeds": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["name", "oracle_path"],
        },
    },
    {
        "name": "autotune",
        "description": (
            "Point the tuner at a SAMPLE of your sparse data; it finds a "
            "configuration whose measured recall@k clears the gate, or reports "
            "the best it found with the full sweep as evidence. It automates the "
            "discipline in docs/UltraDim_Tuning_Guide.md: derive max_nnz from the "
            "data, build one family per projection width at the largest seed "
            "count, sweep active_seeds (4/8/16) FREE against one exact oracle, "
            "and only rebuild wider (projection_dim) when more seeds do not clear "
            "the gate. It BUILDS FAMILIES AND ORACLES as it runs, so on a real "
            "corpus expect MINUTES, not milliseconds — pass a representative "
            "few-thousand-row sample, not your whole dataset. This is the "
            "remedy for a refused recall gate: never conclude a limit is "
            "'intrinsic' without this sweep."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rows": {
                    "type": "array",
                    "description": (
                        "A sample of your sparse data. Each row is "
                        "{indices:[int], values:[float]} with strictly-ascending "
                        "indices and L2-normalised values."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "indices": {"type": "array", "items": {"type": "integer"}},
                            "values": {"type": "array", "items": {"type": "number"}},
                        },
                        "required": ["indices", "values"],
                    },
                },
                "gate": {
                    "type": "number",
                    "description": "Recall@k target to clear. Default 0.99 (the UMAP fit gate).",
                },
                "k": {"type": "integer", "description": "recall@k. Default 10."},
                "n_queries": {
                    "type": "integer",
                    "description": (
                        "How many rows to hold out as queries. Default 200. The "
                        "sample must have more than n_queries+10 rows."
                    ),
                },
                "family_prefix": {
                    "type": "string",
                    "description": "Name prefix for the throwaway families it builds. Default 'autotune'.",
                },
            },
            "required": ["rows"],
        },
    },
    {
        "name": "build_oracle",
        "description": (
            "Compute exact nearest neighbours for a set of query rows and "
            "persist them as the ground-truth artifact trellis_measure_recall "
            "grades against. The ENGINE does the brute force "
            "(CreateSparseOracles) — a full scan over every committed row, in "
            "a bounded worker pool so it cannot starve live search — and "
            "writes the artifact itself, next to a manifest. Returns the path "
            "to hand straight to trellis_measure_recall. Cost is linear in "
            "queries times rows, so hold out a few hundred queries rather "
            "than grading the whole family."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Family the oracle grades."},
                "query_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Row ids to compute ground truth for. Each must be below "
                        "the committed row count."
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Neighbours per query. Default 10.",
                },
                "max_threads": {
                    "type": "integer",
                    "description": (
                        "Worker cap for the scan. Default (0) is half the cores. "
                        "Bounded so repeated runs are comparable."
                    ),
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Bare filename, no directories. Omit and the engine picks "
                        "a deterministic name from k and the query count."
                    ),
                },
            },
            "required": ["name", "query_ids"],
        },
    },
    {
        "name": "list_rpcs",
        "description": (
            "List every RPC the loaded wheel reports, read from its own "
            "capabilities() rather than a list kept here — the flat form of "
            "`whats_available`. Every name listed is implemented. That is a "
            "statement about the API, not a promise about your family: an "
            "RPC can still refuse the family you point it at — wrong substrate, "
            "or an index not yet built — and it says so in its own words. "
            "Filter with `contains`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "contains": {
                    "type": "string",
                    "description": "Case-insensitive substring filter, e.g. 'trellis'.",
                },
            },
        },
    },
    {
        "name": "call_rpc",
        "description": (
            "Call a raw RPC by name with its fields as a JSON object, and get "
            "the response JSON back. Omitted fields take their proto defaults "
            "(the request deep-merges over the message's zero value), so state "
            "only what you mean to change. Reach for this for the RPCs the "
            "dedicated tools do not cover — most of the API. "
            "An unknown name is refused; a known one answers or says why not."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rpc": {"type": "string", "description": "PascalCase name, e.g. HealthCheck."},
                "fields": {"type": "object", "description": "Request fields."},
            },
            "required": ["rpc"],
        },
    },
    # -- live on 0.3.0; each re-probed against a real family ----------------
    {
        "name": "search",
        "description": (
            "Search a DENSE family with a dense query vector, whose length must "
            "equal the family's source_dim. Served by the same template engine "
            "as the sparse path, so the family must be settled first — before "
            "that you get 'no resident template engine'. For a sparse family "
            "use trellis_template_search, which is what this tool's error will "
            "tell you to do."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "query": {"type": "array", "items": {"type": "number"}},
                "top_k": {"type": "integer"},
                "exclude_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["name", "query"],
        },
    },
    {
        "name": "collection_info",
        "description": (
            "The family's registry record: source_dim, projection_dim, "
            "substrate, seeds, configuration, the "
            "search defaults, and one entry per shard. Works on both "
            "substrates and needs no settle. Use trellis_template_status for "
            "build state, which is a different question."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "index_status",
        "description": (
            "Per-shard index state, read from the same registry record as "
            "collection_info — it is the same RPC, kept under the name callers "
            "reach for when asking 'is it ready'. For whether the walk can "
            "serve queries, trellis_template_status is the direct answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "restart_indexing",
        "description": (
            "Re-trigger indexing on the family's shards "
            "(RestartUltradimV23Indexing) and report how many were triggered "
            "against how many were already ready. Requires a settled family: "
            "with no resident engine and no persisted manifest it refuses and "
            "names trellis_template_settle. Named wait_for_indexed on the "
            "0.2.0 server, when it polled an optimizer that no longer exists; "
            "it does not wait, so it takes no timeout."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "cluster",
        "description": (
            "Spherical k-means over the family's reduced rows, returning a "
            "cluster assignment per row. SPARSE FAMILIES ONLY — a dense family "
            "is refused by name, because clustering read the dense rows "
            "through a sidecar the clean build removed. `iterations` caps the "
            "Lloyd cycles."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "k": {"type": "integer"},
                "iterations": {"type": "integer"},
            },
            "required": ["name", "k"],
        },
    },
    {
        "name": "kmeans_save_model",
        "description": (
            "Open a rolling k-means LINEAGE and fit its first window. A "
            "lineage is a series of models over successive time windows of the "
            "same family, so clusters can be followed as they move. Rows enter "
            "a window by their `time_field` (the event_ts you gave at upsert, "
            "epoch-milliseconds), NOT by arrival order. Returns a lineage_id "
            "and the first model_id, with rows_fitted, inertia and cluster "
            "sizes. Advance it with kmeans_advance."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "k": {"type": "integer"},
                "window_ms": {"type": "integer"},
                "stride_ms": {"type": "integer"},
                "window_start_ms": {"type": "integer"},
                "time_field": {"type": "string"},
                "warm_start": {"type": "boolean"},
                "iterations": {"type": "integer"},
            },
            "required": ["name", "k", "window_ms", "window_start_ms"],
        },
    },
    {
        "name": "kmeans_advance",
        "description": (
            "Fit the next window of an existing lineage, warm-starting from "
            "the previous model's centroids so cluster identity carries "
            "forward and the migration graph means something. Returns the new "
            "model_id, its window index t, rows_fitted and overlap_rows."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineage_id": {"type": "string"},
                "window_start_ms": {"type": "integer"},
            },
            "required": ["name", "lineage_id"],
        },
    },
    {
        "name": "kmeans_apply_model",
        "description": (
            "Assign rows to an already-fitted model's clusters without "
            "refitting it — scoring new or held-out rows against a saved "
            "model. Returns assignments aligned to row_id_order. Omit "
            "`row_ids` to apply to the whole family."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "model_id": {"type": "string"},
                "row_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["name", "model_id"],
        },
    },
    {
        "name": "kmeans_migration_graph",
        "description": (
            "How mass moved between two windows of a lineage: one edge per "
            "from-cluster/to-cluster pair, each carrying the number of rows "
            "that took it and whether it was a stay or a move. `t_a` and `t_b` "
            "are window indices within the lineage, not timestamps."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "lineage_id": {"type": "string"},
                "t_a": {"type": "integer"},
                "t_b": {"type": "integer"},
            },
            "required": ["name", "lineage_id", "t_a", "t_b"],
        },
    },
    {
        "name": "drop_collection",
        "description": (
            "DESTRUCTIVE AND NOT REVERSIBLE. Deletes the family: its shards, "
            "its registry entry and its substrate sidecar, reporting how many "
            "of each went. The rows are gone — there is no undo and no "
            "confirmation prompt, so only call this when the caller has asked "
            "for this family by name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "describe_rpc",
        "description": (
            "Report an RPC's authoritative status — live | dead | "
            "superseded-by-X — and, where several RPCs answer the same "
            "question, name the canonical one. GOTCHA — it cannot print the "
            "RPC's FIELD SHAPE: that needs a proto descriptor and the wheel "
            "exposes names only (capabilities() returns strings), so for the "
            "field list read the request message in "
            "ultradimdb/proto/ultradim.proto (and note call_rpc lets you omit "
            "anything you do not want to set). An unknown name is refused."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"rpc": {"type": "string"}},
            "required": ["rpc"],
        },
    },
]


class UltraDimTools:
    """Lazily-opened database plus the tool implementations."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: Any | None = None

    @property
    def db(self) -> Any:
        # Opened on first use so a misconfigured path surfaces as a tool error
        # the model can report, not a silent startup crash before handshake.
        if self._db is None:
            log(f"opening database at {self.db_path}")
            self._db = ultradim.UltraDim(self.db_path)
        return self._db

    def close(self) -> None:
        # The wheel has no close(): the service is process-wide (one storage
        # root per process) and lives until the process exits.
        self._db = None

    def raw(self, rpc: str, fields: dict[str, Any] | None = None) -> Any:
        """One call path for every tool: partial JSON in, parsed JSON out.

        Engine errors propagate as the RuntimeError PyO3 raises, message
        intact. 0.3.0 has no retirement text left to translate — an RPC that
        will not serve says why in its own words, and that is what the caller
        should read.
        """
        return json.loads(self.db.call_json(rpc, json.dumps(fields or {})))

    # -- live tools ---------------------------------------------------------
    def health(self) -> Any:
        surface = self.db.capabilities()
        return {
            "health": self.raw("HealthCheck", {"service": "ultradim"}),
            "rpc_surface": len(surface),
            "surface_note": (
                f"all {len(surface)} RPCs implemented; an RPC may still refuse "
                "a given family on substrate or build state"
            ),
            "db_path": self.db_path,
            "wheel": SERVER_VERSION,
            # Flag if the loaded wheel is not the version this server file
            # is built for (both derived — see EXPECTED_VERSION), so a version
            # skew is caught at the cheapest call rather than surfacing later as
            # a missing field or a silent default.
            "server_file": os.path.basename(__file__),
            "expected_wheel": EXPECTED_VERSION,
            "version_aligned": VERSION_ALIGNED,
            # The digest, not the version, is what identifies a build: report
            # it here so any number this server produces can be traced to the
            # binary that produced it.
            "wheel_build": wheel_fingerprint(),
        }

    def list_collections(self) -> Any:
        # There is no list-families RPC, so names come from the registry, which
        # holds one <name>.json per family and is the only place that covers
        # BOTH substrates — a dense family has no udv23_csr directory, and
        # scanning that directory (as the 0.2.0 server did) made dense families
        # invisible. drop_collection removes the entry, so the listing follows.
        reg_dir = os.path.join(self.db_path, "udv23_registry")
        if not os.path.isdir(reg_dir):
            return {"collections": [], "count": 0, "note": "no families created yet"}
        names = sorted(
            f[: -len(".json")] for f in os.listdir(reg_dir) if f.endswith(".json")
        )
        out = []
        for n in names:
            entry: dict[str, Any] = {"name": n}
            try:
                record = self.collection_info(n)
                entry["substrate"] = record.get("substrate")
                entry["source_dim"] = record.get("source_dim")
                entry["projection_dim"] = record.get("projection_dim")
            except Exception as exc:  # a broken family must not hide the rest
                entry["registry_error"] = str(exc)
            entry["trellis_state_on_disk"] = os.path.isdir(
                os.path.join(self.db_path, "udv23_trellis", n)
            )
            try:
                entry["status"] = self.trellis_template_status(n)
            except Exception as exc:
                # Expected for a family that has never been settled: report the
                # engine's reason rather than dropping the family from the list.
                entry["status_error"] = str(exc)
            out.append(entry)
        return {"collections": out, "count": len(out)}

    def create_collection(
        self,
        name: str,
        source_dim: int,
        projection_dim: int = 128,
        seeds: list[int] | None = None,
        max_nnz_per_row: int = 64,
        sparse: bool = True,
    ) -> Any:
        seeds = [int(s) for s in (seeds or [11, 22, 33, 44])]
        fields: dict[str, Any] = {
            "name": name,
            "source_dim": int(source_dim),
            "projection_dim": int(projection_dim),
            "seeds": seeds,
            "sparse_substrate": bool(sparse),
        }
        if sparse:
            # trellis_only and the non-zero cap are properties of the sparse
            # substrate; a dense family carries neither.
            fields["max_nnz_per_row"] = int(max_nnz_per_row)
            fields["trellis_only"] = True
        return self.raw("CreateUltradimV23Collection", fields)

    def upsert_dense(
        self,
        name: str,
        vectors: list[list[float]],
        row_ids: list[int] | None = None,
        facets: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Insert dense rows into a dense family.

        Same contiguity rule as the sparse path: ids extend the family from
        the count already committed, and omitting them asks the engine what
        that count is.

        facets (facet maps; optional, default off): one flat dict of facet name ->
        scalar value per vector, filterable at search time via template_filter.
        GOTCHA: a facet VALUE is int or str only (int -> MatchInt/RangeInt,
        str -> MatchKeyword — the two types the engine can filter on); a float
        or bool is rejected here before the wire. A facet KEY that collides with
        a reserved payload key (radix_*, world_*, absolute_radix_address,
        world_id, point_type, origin_kind, source_world_id, ingest_ts,
        event_ts) is rejected by the server — rename it. When given,
        len(facets) MUST equal len(vectors).
        """
        if not vectors:
            raise ValueError("vectors is empty: nothing to insert.")
        if row_ids is None:
            start = self._committed_rows(name)
            row_ids = list(range(start, start + len(vectors)))
        elif len(row_ids) != len(vectors):
            raise ValueError(
                f"row_ids has {len(row_ids)} entries for {len(vectors)} vectors."
            )
        batch: dict[str, Any] = {
            "row_ids": [int(r) for r in row_ids],
            "vectors": [{"data": [float(x) for x in v]} for v in vectors],
        }
        if facets is not None:
            if len(facets) != len(vectors):
                raise ValueError(
                    f"facets has {len(facets)} entries for {len(vectors)} vectors."
                )
            batch["facets"] = [_facet_map(f) for f in facets]
        return self.raw("UpsertUltradimV23Points", {"name": name, "batch": batch})

    def _committed_rows(self, name: str) -> int:
        """How many rows the family already holds, for the contiguity rule.

        Read from the engine itself, by offering row id 0 and reading the
        count out of its refusal ("expected row_ids[0]=N"). That looks
        indirect, but this build has no count RPC that can be trusted for
        it: the status RPC returns rows_total 0 both for an empty family and
        for a finished build (it drops its progress entry at phase=done),
        and the progress file only exists once a settle has run — a family
        ingested but not yet settled would read as empty and every id would
        collide. The engine's own validator is the one source that is right
        in all three states, and it rejects before writing anything.
        """
        # The probe row must be well-formed — a single unit-norm entry — or
        # the L2 gate rejects it before the contiguity check runs and the
        # count never appears. It is offered at an id no family can accept
        # (2^63) so the contiguity check is guaranteed to be what refuses it:
        # a probe at id 0 would be VALID on an empty family and would insert
        # a junk row.
        #
        # The probe must also match the family's SUBSTRATE: a dense family
        # refuses a sparse batch outright ("`vectors` required") and that
        # refusal carries no count, so the substrate is read first.
        probe_id = 1 << 63
        record = self.collection_info(name)
        if str(record.get("substrate", "")).lower() == "dense":
            width = int(record["source_dim"])
            unit = [1.0] + [0.0] * (width - 1)
            batch = {"row_ids": [probe_id], "vectors": [{"data": unit}]}
        else:
            batch = {
                "row_ids": [probe_id],
                "sparse_vectors": [{"indices": [0], "values": [1.0]}],
            }
        try:
            self.raw("UpsertUltradimV23Points", {"name": name, "batch": batch})
        except RuntimeError as exc:
            match = re.search(r"expected row_ids\[0\]=(\d+)", str(exc))
            if match:
                return int(match.group(1))
            raise
        # An accepted probe would mean the contiguity rule changed under us;
        # refuse to guess rather than leave the junk row unmentioned.
        raise RuntimeError(
            f"row-count probe was ACCEPTED at id {probe_id} on family {name!r}: "
            "the contiguity rule has changed, and a probe row may now be "
            "committed. Pass row_ids explicitly and check the family."
        )

    def upsert_sparse(
        self,
        name: str,
        rows: list[dict[str, Any]],
        row_ids: list[int] | None = None,
        skip_degenerate: bool = False,
        event_ts: list[int] | None = None,
        facets: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Insert sparse rows into a sparse family.

        facets (facet maps; optional, default off): one flat dict of facet name ->
        scalar value per row, filterable at search time via template_filter.
        GOTCHA: a facet VALUE is int or str only (int -> MatchInt/RangeInt,
        str -> MatchKeyword); float/bool is rejected before the wire. A facet
        KEY colliding with a reserved payload key (radix_*, world_*,
        absolute_radix_address, world_id, point_type, origin_kind,
        source_world_id, ingest_ts, event_ts) is rejected by the server. When
        given, len(facets) MUST equal len(rows).
        """
        if not rows:
            raise ValueError("rows is empty")
        vectors = []
        for i, r in enumerate(rows):
            if "indices" not in r or "values" not in r:
                raise ValueError(f"row {i} needs both 'indices' and 'values'")
            idx = [int(x) for x in r["indices"]]
            val = [float(x) for x in r["values"]]
            if len(idx) != len(val):
                raise ValueError(
                    f"row {i}: {len(idx)} indices but {len(val)} values"
                )
            vectors.append({"indices": idx, "values": val})
        # The CSR sidecar admits rows only as a contiguous extension of what is
        # already committed, and the first row of an empty family is id 0. That
        # is the opposite of the old UDV23 convention, where 0 was reserved for
        # family metadata, so defaulting to 1..N here would fail every time.
        if row_ids is None:
            base = self._committed_rows(name)
            ids = list(range(base, base + len(vectors)))
        else:
            ids = [int(i) for i in row_ids]
            if len(ids) != len(vectors):
                raise ValueError(
                    f"row_ids has {len(ids)} entries but rows has {len(vectors)}"
                )
        if event_ts is not None and len(event_ts) != len(vectors):
            raise ValueError(
                f"event_ts has {len(event_ts)} entries but rows has {len(vectors)}"
            )
        if facets is not None and len(facets) != len(vectors):
            raise ValueError(
                f"facets has {len(facets)} entries but rows has {len(vectors)}"
            )
        batch: dict[str, Any] = {"row_ids": ids, "sparse_vectors": vectors}
        if event_ts:
            batch["event_ts"] = [int(t) for t in event_ts]
        if facets is not None:
            batch["facets"] = [_facet_map(f) for f in facets]
        out = self.raw(
            "UpsertUltradimV23Points",
            {
                "name": name,
                "batch": batch,
                "skip_degenerate": bool(skip_degenerate),
            },
        )
        out["row_ids_used"] = [ids[0], ids[-1]] if ids else []
        return out

    def make_searchable(
        self,
        name: str,
        edge_degree: int = 0,
        refine_rounds: int = 0,
        window: int = 0,
    ) -> Any:
        """Make an already-loaded family searchable in one call.

        A thin pass-through to BuildUltradimV23TrellisIndex, the sanctioned
        high-level "make this family searchable" RPC: it resolves or
        synthesises the node-field artifact and settles the index itself, so
        the caller supplies no field_path and no noise floor. Named for what
        it does — it builds an already-loaded family; it neither creates the
        family nor upserts rows, and it cannot pass an explicit floor (the
        raw trellis_template_settle is the fallback for the low-similarity
        corpus that trips the empty-graph guard).

        `window` is the settle micro-batch size: default 10,000 for bulk
        ingest; set window=1 for record-by-record — each upserted record is
        searchable after a single settle pass, the interactive / prefill-cache
        posture. Build synthesises the field for you, so this is the one call
        needed; no field_path.
        """
        fields: dict[str, Any] = {"name": name}
        # Only send what the caller set: an omitted knob takes the engine's
        # measured default (edge_degree -> m_max 13/16; refine_rounds -> 0;
        # window -> 10,000). A 0 means "unset", matching the server (0 is
        # treated as unset, not as window=1).
        if edge_degree:
            fields["edge_degree"] = int(edge_degree)
        if refine_rounds:
            fields["refine_rounds"] = int(refine_rounds)
        if window:
            fields["window"] = int(window)
        return self.raw("BuildUltradimV23TrellisIndex", fields)

    def trellis_template_settle(
        self,
        name: str,
        field_path: str,
        window: int = 0,
        rolling_lag: int | None = None,
        correction_passes: int = 0,
        m: int = 0,
        m_max: int = 0,
        floor: float | None = None,
        telemetry_stride: int = 0,
    ) -> Any:
        fields: dict[str, Any] = {"name": name, "field_path": field_path}
        # Only send what the caller set: an omitted optional takes the
        # engine's measured default, and sending 0 would not mean the same.
        if window:
            fields["window"] = int(window)
        if rolling_lag is not None:
            fields["rolling_lag"] = int(rolling_lag)
        if correction_passes:
            fields["correction_passes"] = int(correction_passes)
        if m:
            fields["m"] = int(m)
        if m_max:
            fields["m_max"] = int(m_max)
        if floor is not None:
            fields["floor"] = float(floor)
        if telemetry_stride:
            fields["telemetry_stride"] = int(telemetry_stride)
        return self.raw("UltradimV23TrellisTemplateSettle", fields)

    def trellis_template_search(
        self,
        name: str,
        sparse_query: dict[str, Any],
        top_k: int = 10,
        active_seeds: list[int] | None = None,
        exclude_ids: list[int] | None = None,
        walk_ef: int = 0,
        walk_expansions: int = 0,
        walk_row_budget: int = 0,
        beam_ef: int = 0,
        beam_expansions: int = 0,
        take_per_seed: int = 0,
        template_filter: dict[str, Any] | None = None,
    ) -> Any:
        """Search over one family.

        template_filter (facet maps; optional, default off): a conjunctive facet
        predicate applied DURING candidate collection (R6 push-down), before
        each seed's take budget — never a post-filter. Shape:
        {"must": [{"field": "security_level", "match_int": 3},
                  {"field": "org_id", "match_keyword": "acme"},
                  {"field": "token_position", "range_int": {"gte": 0, "lte": 5}}]}
        GOTCHA: a row MISSING a filtered field FAILS the condition (fail closed),
        and a family settled before facets shipped filters only on radix keys.
        A highly selective filter usually wants take_per_seed raised so the take
        budget lands enough qualifying rows.
        """
        if "indices" not in sparse_query or "values" not in sparse_query:
            raise ValueError("sparse_query needs both 'indices' and 'values'")
        fields: dict[str, Any] = {
            "name": name,
            "sparse_query": {
                "indices": [int(x) for x in sparse_query["indices"]],
                "values": [float(x) for x in sparse_query["values"]],
            },
            "top_k": int(top_k),
        }
        if active_seeds:
            fields["active_seeds"] = [int(s) for s in active_seeds]
        if exclude_ids:
            fields["exclude_ids"] = [int(i) for i in exclude_ids]
        if template_filter is not None:
            fields["template_filter"] = _template_filter(template_filter)
        for key, val in (
            ("walk_ef", walk_ef),
            ("walk_expansions", walk_expansions),
            ("walk_row_budget", walk_row_budget),
            ("beam_ef", beam_ef),
            ("beam_expansions", beam_expansions),
            ("take_per_seed", take_per_seed),
        ):
            if val:
                fields[key] = int(val)
        out = self.raw("UltradimV23TrellisTemplateSearch", fields)
        return {
            "results": [
                {"id": flatten_point_id(p.get("id")), "score": p.get("score")}
                for p in (out.get("result") or [])
            ],
            "stats": out.get("stats", {}),
        }

    def multi_family_search(
        self,
        names: list[str],
        sparse_query: dict[str, Any] | None = None,
        dense_query: list[float] | None = None,
        top_k: int = 10,
        template_filter: dict[str, Any] | None = None,
        exclude_ids: list[int] | None = None,
        walk_ef: int = 0,
        walk_expansions: int = 0,
        walk_row_budget: int = 0,
        beam_ef: int = 0,
        beam_expansions: int = 0,
        take_per_seed: int = 0,
    ) -> Any:
        """Search N families with ONE query in one call, joined on row_id (multi-family search).

        GOTCHA: this is a convenience/atomicity win, NOT a speed win. The
        per-family search is rayon work that already saturates cores, so the N
        searches do NOT overlap — the wall is about the SUM of the per-family
        search times (only the engine loads overlap). What you gain is one round
        trip and one joined answer in place of the four-call-and-join pattern.

        Each returned hit carries `score[i]` and `present[i]` aligned to `names`:
        present[i] is TRUE iff the row was in families[i]'s top_k. present[i] ==
        FALSE is an EXPLICIT missing-in-family marker (score[i] is 0.0 then, not
        a real score) — read present[i], never treat 0.0 as a real low score.
        All families must share a substrate (all sparse or all dense); one top_k
        for all. sparse_query for sparse families, dense_query for dense.
        """
        if not names:
            raise ValueError("names is empty: name at least one family.")
        if (sparse_query is None) == (dense_query is None):
            raise ValueError(
                "pass exactly one of sparse_query / dense_query, matching the "
                "families' shared substrate."
            )
        fields: dict[str, Any] = {"names": [str(n) for n in names], "top_k": int(top_k)}
        if sparse_query is not None:
            if "indices" not in sparse_query or "values" not in sparse_query:
                raise ValueError("sparse_query needs both 'indices' and 'values'")
            fields["sparse_query"] = {
                "indices": [int(x) for x in sparse_query["indices"]],
                "values": [float(x) for x in sparse_query["values"]],
            }
        else:
            fields["dense_query"] = {"data": [float(x) for x in dense_query]}
        if template_filter is not None:
            fields["template_filter"] = _template_filter(template_filter)
        if exclude_ids:
            fields["exclude_ids"] = [int(i) for i in exclude_ids]
        for key, val in (
            ("walk_ef", walk_ef),
            ("walk_expansions", walk_expansions),
            ("walk_row_budget", walk_row_budget),
            ("beam_ef", beam_ef),
            ("beam_expansions", beam_expansions),
            ("take_per_seed", take_per_seed),
        ):
            if val:
                fields[key] = int(val)
        out = self.raw("UltradimV23MultiFamilySearch", fields)
        return {
            "families": out.get("families") or [],
            "hits": [
                {
                    "row_id": h.get("row_id"),
                    "score": h.get("score") or [],
                    "present": h.get("present") or [],
                }
                for h in (out.get("hits") or [])
            ],
            "stats": out.get("stats") or [],
        }

    def _progress_file(self, name: str) -> dict[str, Any]:
        """Parse the settle progress file the engine writes beside the states.

        The status RPC serves an in-memory table, and the engine DROPS a
        family's entry the moment its phase becomes `done`
        — so a finished
        build reports phase done with seeds 0/0 and rows 0. The same call
        wrote `phase=done seeds=4/4 rows=300` to disk on its way out, so the
        completed counts are read back from there.
        """
        path = os.path.join(self.db_path, "udv23_trellis", name, "settle_progress.txt")
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read().strip()
        except OSError:
            return {}
        # `phase=...` is written first and a failure phase carries spaces
        # ("failed: seed 3 ..."), so the numeric keys are read by name and the
        # phase takes whatever is left between it and the next known key —
        # splitting the line on whitespace would truncate it at the first word.
        out: dict[str, Any] = {}
        for key, caster, field in (
            ("seeds", str, "seeds"),
            ("rows", int, "rows_total"),
            ("running_s", float, "running_s"),
        ):
            match = re.search(rf"\b{key}=(\S+)", text)
            if not match:
                continue
            if key == "seeds" and "/" in match.group(1):
                done, _, total = match.group(1).partition("/")
                out["seeds_done"], out["seeds_total"] = int(done), int(total)
            elif key != "seeds":
                out[field] = caster(match.group(1))
        phase = re.search(r"phase=(.*?)(?=\s+(?:seeds|rows|running_s)=|$)", text, re.S)
        if phase:
            out["phase"] = phase.group(1).strip()
        return out

    def trellis_template_status(self, name: str) -> Any:
        st = self.raw("GetUltradimV23TrellisTemplateStatus", {"name": name})
        # Fill the zeroed counts of a finished build from the progress file,
        # and say where each number came from rather than blending them
        # silently: a live build's RPC numbers are the current truth, and the
        # file's are the last ones written.
        if not st.get("seeds_total") and not st.get("rows_total"):
            fromfile = self._progress_file(name)
            if fromfile:
                file_phase = fromfile.pop("phase", None)
                st.update(fromfile)
                st["counts_from"] = (
                    "settle_progress.txt (build finished; the status RPC "
                    "drops its in-memory entry at phase=done)"
                )
                # The engine drops the entry on FAILURE too, and the fallback
                # branch then derives the phase from residency alone — so a
                # settle that died mid-stream but left states on disk reports
                # "done". The file recorded what actually happened, so when
                # the two disagree the file's phase wins and the RPC's claim
                # is kept beside it, named, rather than either being hidden.
                if file_phase and file_phase != st.get("phase"):
                    st["phase_reported_by_rpc"] = st.get("phase")
                    st["phase"] = file_phase
                    st["phase_from"] = (
                        "settle_progress.txt — the status RPC inferred its "
                        "phase from residency alone, which cannot tell a "
                        "finished build from a failed one"
                    )
        return st

    def trellis_measure_recall(
        self,
        name: str,
        oracle_path: str,
        k: int = 10,
        exclude_self: bool = True,
        active_seeds: list[int] | None = None,
    ) -> Any:
        fields: dict[str, Any] = {
            "name": name,
            "oracle_path": oracle_path,
            "k": int(k),
            "exclude_self": bool(exclude_self),
            "use_template": True,
        }
        if active_seeds:
            fields["active_seeds"] = [int(s) for s in active_seeds]
        return self.raw("MeasureRecall", fields)

    def autotune(
        self,
        rows: list[dict[str, Any]],
        gate: float = 0.99,
        k: int = 10,
        n_queries: int = 200,
        family_prefix: str = "autotune",
    ) -> Any:
        """Point the tuner at a SAMPLE of your sparse data and let it find a
        configuration whose measured recall@k clears the gate.

        This drives the same engine handle the server holds, running the
        discipline in docs/UltraDim_Tuning_Guide.md §3: derive max_nnz from the
        data, build one family per projection width at the largest seed count,
        sweep active_seeds (4/8/16) for free against one exact oracle, and only
        rebuild wider when more seeds do not clear the gate. It BUILDS FAMILIES
        and ORACLES as it goes, so on a real corpus it runs for minutes, not
        milliseconds — pass a representative few-thousand-row sample, not your
        whole dataset. Every `rows` entry is {indices:[int], values:[float]}
        with strictly-ascending indices and L2-normalised values.

        Returns the best config found (or null if the gate is unreachable) plus
        the full sweep — so a 'cannot reach the gate' answer arrives with the
        evidence, not a shrug.
        """
        from ultradim.autotune import autotune as _autotune, SparseRow

        if not rows:
            raise ValueError("autotune: rows is empty — pass a sample of your data")
        sparse_rows = [
            SparseRow(
                indices=[int(i) for i in r["indices"]],
                values=[float(v) for v in r["values"]],
            )
            for r in rows
        ]
        result = _autotune(
            self.db,
            sparse_rows,
            gate=float(gate),
            k=int(k),
            n_queries=int(n_queries),
            family_prefix=str(family_prefix),
            log=lambda m: log(m),
        )

        def _cfg(c: Any) -> dict[str, Any] | None:
            if c is None:
                return None
            return {
                "projection_dim": c.projection_dim,
                "active_seeds": c.active_seeds,
                "max_nnz_per_row": c.max_nnz_per_row,
                "k": c.k,
            }

        return {
            "best": _cfg(result.best),
            "best_recall": result.best_recall,
            "gate": result.gate,
            "derived_max_nnz": result.derived_max_nnz,
            "verdict": result.verdict,
            "sweep": [
                {"config": _cfg(t.config), "recall": t.recall, "note": t.note}
                for t in result.sweep
            ],
        }

    def build_oracle(
        self,
        name: str,
        query_ids: list[int],
        top_k: int = 10,
        max_threads: int = 0,
        filename: str | None = None,
    ) -> Any:
        """Ask the engine for exact ground truth and return the artifact path.

        The 0.2.0 server computed top-k in Python because it believed this RPC
        was retired. It is not: CreateSparseOracles is the engine's own
        full-scan brute force, it runs in a bounded pool so it cannot starve
        live search, and it writes the artifact plus its manifest itself.
        """
        if not query_ids:
            raise ValueError("query_ids is empty: nothing to build ground truth for.")
        if top_k < 1:
            raise ValueError(f"top_k must be at least 1, got {top_k}.")
        fields: dict[str, Any] = {
            "name": name,
            "query_ids": [int(q) for q in query_ids],
            "top_k": int(top_k),
        }
        if max_threads:
            fields["max_threads"] = int(max_threads)
        if filename is not None:
            if os.path.sep in filename or filename.startswith("."):
                raise ValueError(
                    "filename must be a bare file name: the engine resolves it "
                    "strictly under the family's own oracle directory."
                )
            fields["out_name"] = filename
        response = self.raw("CreateSparseOracles", fields)
        # The engine returns its path as given, which is relative when the
        # database was opened on a relative path. measure_recall may be called
        # from a different working directory, so resolve it here.
        path = response.get("artifact_path")
        if path:
            response["artifact_path"] = os.path.abspath(path)
        return {
            "oracle_path": response.get("artifact_path"),
            "queries": response.get("n_queries"),
            "top_k": response.get("top_k"),
            "rows_scanned": response.get("n_committed"),
            "build_ms": response.get("build_ms"),
            "results": response.get("results"),
        }

    def list_rpcs(self, contains: str | None = None) -> Any:
        surface = self.db.capabilities()
        names = surface
        if contains:
            needle = contains.lower()
            names = [n for n in names if needle in n.lower()]
        # Every name the wheel reports is implemented, so the default status is
        # "live"; RPC_STATUS overrides that only to name the canonical RPC among
        # a set of RPCs that answer the same question (see the table's comment).
        rpcs = [
            {
                "name": n,
                "status": RPC_STATUS.get(n, {}).get("status", "live"),
                "note": RPC_STATUS.get(n, {}).get(
                    "note", "implemented on this wheel"
                ),
            }
            for n in names
        ]
        return {
            "rpcs": rpcs,
            "count": len(rpcs),
            "surface_total": len(surface),
            "note": (
                "every name listed is implemented (status 'live'); a call can "
                "still be refused for the family it names (wrong substrate, or "
                "an index not yet built). Where several RPCs answer the same "
                "question, the note names the canonical one to prefer."
            ),
        }

    def get_row_by_content_key(
        self, name: str, content_key: str, facet_name: str | None = None
    ) -> Any:
        """EXACT identity get: return a row's numeric id by an exact content-key
        facet, with no cosine search. Answers before the family is settled.
        """
        fields: dict[str, Any] = {"name": name, "content_key": content_key}
        if facet_name:
            fields["facet_name"] = facet_name
        resp = self.raw("GetUltradimV23RowByContentKey", fields)
        return {
            "found": resp.get("found", False),
            "row_id": resp.get("row_id") if resp.get("found") else None,
        }

    def replace_sparse_point(
        self,
        name: str,
        old_row_id: int,
        indices: list[int],
        values: list[float],
        facets: dict[str, str] | None = None,
        event_ts: int | None = None,
    ) -> Any:
        """Replace the sparse vector held for a known row.

        The old row is retired and the replacement lands at a NEW row id.
        Omitting `facets` inherits the old row's metadata wholesale; supplying
        it replaces the metadata outright.
        """
        fields: dict[str, Any] = {
            "name": name,
            "old_row_id": old_row_id,
            "sparse_vector": {"indices": indices, "values": values},
        }
        if facets is not None:
            fields["facets"] = {
                "fields": {
                    k: {"kind": {"KeywordValue": str(v)}} for k, v in facets.items()
                }
            }
        if event_ts is not None:
            fields["event_ts"] = event_ts
        resp = self.raw("ReplaceUltradimV23Point", fields)
        return {
            "success": resp.get("success", False),
            "new_row_id": resp.get("new_row_id"),
            "already_replaced": resp.get("already_replaced", False),
            "error_message": resp.get("error_message"),
        }

    def delete_sparse_point(self, name: str, row_id: int) -> Any:
        """Retire a row. Idempotent; the row id is never freed."""
        resp = self.raw("DeleteUltradimV23Point", {"name": name, "row_id": row_id})
        return {
            "success": resp.get("success", False),
            "was_already_deleted": resp.get("was_already_deleted", False),
        }

    # -- kNN graph + UMAP + HDBSCAN density maps (the analytics RPCs) -------
    # These wrap engine RPCs that already answer via call_rpc; the wrappers hide
    # the raw proto shape (enums as friendly strings, the dense-XOR-sparse query
    # pair) and reshape the flat embedding arrays into per-row vectors.

    def build_knn_graph(
        self,
        name: str,
        k: int = 32,
        append: bool = False,
        row_ids: list[int] | None = None,
    ) -> Any:
        """Build (or extend) the stored kNN graph a UMAP fit or an HDBSCAN lineage
        is built over. `append=true` extends an existing graph with new rows (for
        incremental fit / lineage advance). Expert knobs live on the raw
        BuildUltradimV23KnnGraph via call_rpc.

        k defaults to 32 and is ALWAYS sent: the engine requires k >= 1 (the wire
        zero is rejected "k must be >= 1"), so the proto's "default 32" is a
        client convention this wrapper supplies, not an engine fallback.
        """
        if int(k) < 1:
            raise ValueError("k must be >= 1 (neighbours per row)")
        fields: dict[str, Any] = {"name": name, "k": int(k), "append": bool(append)}
        if row_ids is not None:
            fields["row_ids"] = [int(r) for r in row_ids]
        return self.raw("BuildUltradimV23KnnGraph", fields)

    def fit_umap(
        self,
        name: str,
        n_components: int = 2,
        n_neighbors: int | None = None,
        min_dist: float | None = None,
        output_metric: str = "euclidean",
        init: str = "annealed",
        n_epochs: int | None = None,
        deterministic: bool = True,
        seed: int | None = None,
        row_ids: list[int] | None = None,
        graph_id: str | None = None,
    ) -> Any:
        """Fit a UMAP embedding of a family. The family needs a kNN graph first
        (build_knn_graph); an empty graph_id builds-or-reuses one with defaults.
        Expert knobs (learning_rate, negative_sample_rate, repulsion_strength,
        init_num_clusters, init_levels, checkpoint_every_epochs, force) are on the
        raw FitUltradimV23Umap via call_rpc.
        """
        fields: dict[str, Any] = {
            "name": name,
            "n_components": int(n_components),
            "output_metric": _umap_metric_wire(output_metric),
            "init": _umap_init_wire(init),
            "deterministic": bool(deterministic),
        }
        if n_neighbors is not None:
            fields["n_neighbors"] = int(n_neighbors)
        if min_dist is not None:
            fields["min_dist"] = float(min_dist)
        if n_epochs is not None:
            fields["n_epochs"] = int(n_epochs)
        if seed is not None:
            fields["umap_seed"] = int(seed)
        if row_ids is not None:
            fields["row_ids"] = [int(r) for r in row_ids]
        if graph_id:
            fields["graph_id"] = graph_id
        return self.raw("FitUltradimV23Umap", fields)

    @staticmethod
    def _reshape_embeddings(resp: dict[str, Any]) -> Any:
        """Reshape a flat row-major `embeddings` array + `n_components` into a
        list of per-row vectors, so the tool returns coordinates a caller can use
        directly rather than a flat array they must reshape by hand.
        """
        flat = resp.get("embeddings") or []
        nc = int(resp.get("n_components") or 0)
        rows = (
            [flat[i : i + nc] for i in range(0, len(flat), nc)]
            if nc > 0
            else []
        )
        out = dict(resp)
        out["embeddings"] = rows
        return out

    def transform_umap(
        self,
        name: str,
        umap_id: str,
        queries: list[Any],
        refine_epochs: int | None = None,
        return_diagnostics: bool = False,
        persist: bool = False,
        persist_row_ids: list[int] | None = None,
    ) -> Any:
        """Place new points into an existing fitted UMAP map. `queries` is a plain
        list of dense vectors ([float,...]) OR sparse rows ({indices,values}); the
        wrapper builds the wire dense-XOR-sparse pair. Returns per-row embedding
        coordinates.
        """
        fields: dict[str, Any] = {"name": name, "umap_id": umap_id}
        fields.update(_queries_wire(queries))
        if refine_epochs is not None:
            fields["refine_epochs"] = int(refine_epochs)
        if return_diagnostics:
            fields["return_diagnostics"] = True
        if persist:
            fields["persist"] = True
            if persist_row_ids is not None:
                fields["persist_row_ids"] = [int(r) for r in persist_row_ids]
        return self._reshape_embeddings(self.raw("TransformUltradimV23Umap", fields))

    def umap_embedding(
        self, name: str, umap_id: str, limit: int = 1000, offset_ordinal: int = 0
    ) -> Any:
        """Read a fitted map's stored embedding, one page at a time. Pass the
        previous response's `next_offset_ordinal` as `offset_ordinal` to continue.
        Returns per-row coordinates.
        """
        resp = self.raw(
            "GetUltradimV23UmapEmbedding",
            {
                "name": name,
                "umap_id": umap_id,
                "limit": int(limit),
                "offset_ordinal": int(offset_ordinal),
            },
        )
        return self._reshape_embeddings(resp)

    def umap_info(self, name: str, umap_id: str) -> Any:
        """Metadata for one fitted UMAP map (params, row count, provenance)."""
        return self.raw("GetUltradimV23UmapInfo", {"name": name, "umap_id": umap_id})

    def list_umap_models(self, name: str) -> Any:
        """List the fitted UMAP maps on a family."""
        return self.raw("ListUltradimV23UmapModels", {"name": name})

    def drop_umap(self, name: str, umap_id: str) -> Any:
        """Drop a fitted UMAP map."""
        return self.raw("DropUltradimV23Umap", {"name": name, "umap_id": umap_id})

    def incremental_fit_umap(
        self,
        name: str,
        parent_umap_id: str,
        queries: list[Any],
        batch_row_ids: list[int],
        e_micro: int | None = None,
        fold_search: str = "",
        persist: bool = False,
    ) -> Any:
        """Fold a new batch into an existing fitted map (the arriving rows must
        ALREADY be graph-appended). `queries` is the same plain dense/sparse list
        shape as transform_umap. The research/sweep knobs (m_warm, m_floor,
        lambda_mass, wake_*, rebaseline_* [STUBBED], replay/spring) are on the raw
        IncrementalFitUltradimV23Umap via call_rpc, not exposed here.
        """
        fields: dict[str, Any] = {
            "name": name,
            "parent_umap_id": parent_umap_id,
            "batch_row_ids": [int(r) for r in batch_row_ids],
        }
        fields.update(_queries_wire(queries))
        if e_micro is not None:
            fields["e_micro"] = int(e_micro)
        if fold_search:
            fields["fold_search"] = fold_search
        if persist:
            fields["persist"] = True
        return self.raw("IncrementalFitUltradimV23Umap", fields)

    def create_hdbscan_lineage(
        self,
        name: str,
        graph_id: str,
        min_samples: int | None = None,
        lineage_tag: str | None = None,
    ) -> Any:
        """Open a density-clustering lineage over a family. `graph_id` is REQUIRED
        — build it first with build_knn_graph. Advance it over time with
        advance_hdbscan_lineage.
        """
        fields: dict[str, Any] = {"name": name, "graph_id": graph_id}
        if min_samples is not None:
            fields["min_samples"] = int(min_samples)
        if lineage_tag:
            fields["lineage_tag"] = lineage_tag
        return self.raw("CreateUltradimV23HdbscanLineage", fields)

    def advance_hdbscan_lineage(
        self,
        name: str,
        lineage_id: str,
        batch_row_ids: list[int],
        fold_search: str = "",
    ) -> Any:
        """Advance a lineage by one time step with the arriving rows. Those rows
        must already be appended to the base graph (build_knn_graph append=true),
        their ordinals extending the lineage watermark contiguously.
        """
        fields: dict[str, Any] = {
            "name": name,
            "lineage_id": lineage_id,
            "batch_row_ids": [int(r) for r in batch_row_ids],
        }
        if fold_search:
            fields["fold_search"] = fold_search
        return self.raw("AdvanceUltradimV23HdbscanLineage", fields)

    def apply_hdbscan(
        self,
        name: str,
        lineage_id: str,
        t: int = 0,
        t_latest: bool = False,
        queries: list[Any] | None = None,
        row_ids: list[int] | None = None,
        min_cluster_size: int | None = None,
        selection: str | None = None,
    ) -> Any:
        """Assign a population to clusters as-of time t (or the latest committed t
        with t_latest=true). The population is EXACTLY ONE of: `queries` (a plain
        dense/sparse list) OR `row_ids` (in-sample). `t` is literal (t=0 = the t0
        model).
        """
        fields: dict[str, Any] = {"name": name, "lineage_id": lineage_id}
        if t_latest:
            fields["t_latest"] = True
        else:
            fields["t"] = int(t)
        pops = [p for p in (queries, row_ids) if p]
        if len(pops) != 1:
            raise ValueError(
                "apply_hdbscan needs EXACTLY ONE population: queries OR row_ids"
            )
        if queries:
            fields.update(_queries_wire(queries))
        else:
            fields["row_ids"] = [int(r) for r in row_ids]
        if min_cluster_size is not None:
            fields["min_cluster_size"] = int(min_cluster_size)
        if selection:
            fields["selection"] = selection
        return self.raw("ApplyUltradimV23Hdbscan", fields)

    def cowalk_hdbscan(
        self,
        name: str,
        lineage_id: str,
        t_a: int,
        t_b: int,
        queries: list[Any] | None = None,
        row_ids: list[int] | None = None,
        min_cluster_size: int | None = None,
        selection: str | None = None,
    ) -> Any:
        """Compare one population's clustering at two times t_a and t_b. `t_a` and
        `t_b` are REQUIRED (no default): the engine rejects (0,0), so a
        defaulted call must fail rather than return a plausible t0-vs-t0 answer —
        the wrapper never injects 0 for an omitted t. Population is EXACTLY ONE of
        `queries` OR `row_ids`. t is literal (t=0 = the t0 model).
        """
        fields: dict[str, Any] = {
            "name": name,
            "lineage_id": lineage_id,
            "t_a": int(t_a),
            "t_b": int(t_b),
        }
        pops = [p for p in (queries, row_ids) if p]
        if len(pops) != 1:
            raise ValueError(
                "cowalk_hdbscan needs EXACTLY ONE population: queries OR row_ids"
            )
        if queries:
            fields.update(_queries_wire(queries))
        else:
            fields["row_ids"] = [int(r) for r in row_ids]
        if min_cluster_size is not None:
            fields["min_cluster_size"] = int(min_cluster_size)
        if selection:
            fields["selection"] = selection
        return self.raw("CoWalkUltradimV23Hdbscan", fields)

    def hdbscan_migration_graph(
        self,
        name: str,
        lineage_id: str,
        t_a: int,
        t_b: int,
        row_ids: list[int] | None = None,
        all_fitted_asof_t_a: bool = False,
        min_cluster_size: int | None = None,
        selection: str | None = None,
    ) -> Any:
        """The cluster migration graph between two times t_a and t_b. `t_a`/`t_b`
        are REQUIRED (no default; (0,0) is rejected — the wrapper never injects 0).
        Population is `row_ids`, OR set all_fitted_asof_t_a=true for every fitted
        row as-of t_a. t is literal (t=0 = the t0 model).
        """
        fields: dict[str, Any] = {
            "name": name,
            "lineage_id": lineage_id,
            "t_a": int(t_a),
            "t_b": int(t_b),
        }
        if all_fitted_asof_t_a:
            fields["all_fitted_asof_t_a"] = True
        elif row_ids is not None:
            fields["row_ids"] = [int(r) for r in row_ids]
        if min_cluster_size is not None:
            fields["min_cluster_size"] = int(min_cluster_size)
        if selection:
            fields["selection"] = selection
        return self.raw("GetUltradimV23HdbscanMigrationGraph", fields)

    def hdbscan_info(self, name: str, lineage_id: str) -> Any:
        """Metadata for one HDBSCAN lineage (params, watermark, committed t)."""
        return self.raw(
            "GetUltradimV23HdbscanInfo", {"name": name, "lineage_id": lineage_id}
        )

    def list_hdbscan_lineages(self, name: str) -> Any:
        """List the HDBSCAN lineages on a family."""
        return self.raw("ListUltradimV23HdbscanLineages", {"name": name})

    def compact_hdbscan_lineage(
        self, name: str, lineage_id: str, prune: bool = True
    ) -> Any:
        """Compact a lineage's on-disk history (prune runs the cycle-property
        prune first, default true).
        """
        return self.raw(
            "CompactUltradimV23HdbscanLineage",
            {"name": name, "lineage_id": lineage_id, "prune": bool(prune)},
        )

    def drop_hdbscan_lineage(self, name: str, lineage_id: str) -> Any:
        """Drop an HDBSCAN lineage."""
        return self.raw(
            "DropUltradimV23HdbscanLineage", {"name": name, "lineage_id": lineage_id}
        )

    def whats_available(self) -> Any:
        """One place that answers 'what can this do?' — generated live from the
        wheel, so it never drifts from the code. Groups every RPC the loaded
        wheel reports into areas, and names the happy path and the analytics
        RPCs explicitly so a caller does not have to reverse-engineer them from
        200-odd RPC names. If a customer cannot find a feature, THIS is the tool
        that shows it exists.
        """
        surface = sorted(self.db.capabilities())
        loaded = getattr(ultradim, "__version__", None)

        # Group by a coarse area keyword found in the RPC name. Order matters:
        # the first area whose keyword matches wins, so specific comes before
        # general. A name matching nothing lands in "other" — visible, never
        # hidden.
        areas = [
            ("identity get (exact key, no search)", ("ByContentKey", "RowByContent")),
            ("trellis / search", ("Trellis", "Search", "Recommend")),
            # Before "ingest / family": Drop*Umap / Build*KnnGraph would otherwise
            # first-match "Drop"/"Build" and land in ingest/index. Keywords omit
            # "Embedding" on purpose (every UMAP RPC has "Umap"; "Embedding" would
            # wrongly capture the BERT RPC BulkIngestEmbeddings). GetGraphEdges
            # (a debug RPC) stays in "other" by design.
            ("umap / density maps", ("Umap", "Hdbscan", "KnnGraph")),
            # Before "ingest / family": that group's "Point" keyword would
            # otherwise swallow ReplaceUltradimV23Point and
            # DeleteUltradimV23Point, filing "change this row" under "add
            # rows" — the exact confusion the separate RPCs exist to avoid.
            ("replace / delete a row", ("ReplaceUltradimV23Point", "DeleteUltradimV23Point")),
            ("ingest / family", ("Upsert", "CreateCollection", "Collection", "Point", "Drop")),
            ("finish indexing (settle) / index", ("Settle", "Index", "Build", "Restart")),
            ("clustering / lineage", ("Kmeans", "Cluster", "Migration", "Lineage")),
            ("oracle / grade", ("Oracle", "Recall", "Grade")),
            ("blue world / nav", ("BlueWorld", "Blue", "Nav", "Gene", "Esn")),
            ("health / meta", ("Health", "Capabilit", "List", "Stats", "Info")),
        ]
        grouped: dict[str, list[str]] = {a[0]: [] for a in areas}
        grouped["other"] = []
        for n in surface:
            placed = False
            for label, keys in areas:
                if any(k in n for k in keys):
                    grouped[label].append(n)
                    placed = True
                    break
            if not placed:
                grouped["other"].append(n)
        grouped = {k: v for k, v in grouped.items() if v}

        return {
            "version": {
                "wheel_loaded": loaded,
                "server_file": os.path.basename(__file__),
                "expected_wheel": EXPECTED_VERSION,
                "aligned": VERSION_ALIGNED,
                "note": (
                    "server file and wheel are in step"
                    if VERSION_ALIGNED
                    else f"MISMATCH: this server file is built for wheel "
                    f"{EXPECTED_VERSION}, loaded {loaded} — reinstall the "
                    f"{EXPECTED_VERSION} wheel or run the server file for the "
                    "wheel you have"
                ),
            },
            "happy_path": [
                "create_collection  — make a sparse (or dense) family",
                "upsert_sparse      — add rows (upsert_dense for dense)",
                "make_searchable    — FINISH INDEXING the records so they can be "
                "searched (our word for this is 'settle'). window=1 indexes each "
                "record as it arrives (prefill-cache); default 10,000 for bulk",
                "trellis_template_search — retrieve; exact scores, self-verifying",
                "get_row_by_content_key — EXACT identity lookup: fetch a row's id "
                "by an exact key you stored on it, no search. Works BEFORE the "
                "family is indexed (settled). For 'have I seen this exact thing?'",
                "replace_sparse_point — UPDATE a row whose current state has "
                "moved on (upsert_sparse only ever ADDS). The replacement gets a "
                "NEW row id; your content_key is what stays stable, so the "
                "lookup above keeps finding the current row. delete_sparse_point "
                "retires a row for good.",
            ],
            "analytics_arms": [
                "cluster                 — spherical k-means (SPARSE families)",
                "kmeans_save_model / _advance / _apply_model / _migration_graph "
                "— the lineage: fit, roll forward, migrate",
                "build_oracle / measure_recall — exact brute-force ground truth "
                "and recall grading",
                "UMAP: make_searchable -> build_knn_graph -> fit_umap -> "
                "umap_embedding (+ transform_umap / incremental_fit_umap) — reduce "
                "a family to a 2..256-D map for visualisation or downstream "
                "clustering (the graph needs a settled family)",
                "HDBSCAN: make_searchable -> build_knn_graph -> "
                "create_hdbscan_lineage -> advance_hdbscan_lineage -> apply_hdbscan "
                "/ cowalk_hdbscan / hdbscan_migration_graph — density clusters "
                "tracked over time",
            ],
            "retired_do_not_use": [
                "UltradimV23Search — superseded by trellis_template_search",
                "get_keys          — no longer the read path",
            ],
            "rpc_surface_total": len(surface),
            "rpcs_by_area": grouped,
            "one_engine_one_surface": (
                "There is ONE database, in the wheel. These same RPCs are reached "
                "embedded in-process (db.call_json), via this MCP server, or via "
                "the gRPC server (:6334) — ALL THREE expose this IDENTICAL list. "
                "A feature shown over gRPC is NOT a fuller API; the same "
                "call is db.call_json(rpc, fields) embedded. Drive everything "
                "in-process if you already have the wheel — you never need the "
                "gRPC server to reach a feature."
            ),
            "how_to_dig_deeper": (
                "list_rpcs(contains='...') filters this flat; describe_rpc(name) "
                "names one RPC; call_rpc(rpc, fields) calls any RPC raw. This "
                "listing comes from the wheel's own capabilities(), so it is the "
                "authoritative answer to 'what is available' — not the docs."
            ),
        }

    def call_rpc(self, rpc: str, fields: dict[str, Any] | None = None) -> Any:
        return self.raw(rpc, fields or {})

    # -- RPCs that were refused by the 0.2.0 server and are live now --------
    # These always forwarded to their real RPC names; only the descriptions
    # were wrong. Each was re-probed against a real family before this file
    # was written, and the measured behaviour is what the tool now claims.
    def search(
        self,
        name: str,
        query: list[float],
        top_k: int = 10,
        exclude_ids: list[int] | None = None,
    ) -> Any:
        return self.raw(
            "UltradimV23Search",
            {
                "name": name,
                "query": {"data": [float(x) for x in query]},
                "top_k": int(top_k),
                "exclude_ids": [int(i) for i in (exclude_ids or [])],
            },
        )

    def collection_info(self, name: str) -> Any:
        return self.raw("GetUltradimV23CollectionInfo", {"name": name})

    def index_status(self, name: str) -> Any:
        return self.raw("GetUltradimV23CollectionInfo", {"name": name})

    def restart_indexing(self, name: str) -> Any:
        # Renamed from the 0.2.0 server's wait_for_indexed: it triggers and
        # returns, it does not wait, so it takes no timeout. Use
        # trellis_template_status to watch a build in flight.
        return self.raw("RestartUltradimV23Indexing", {"name": name})

    def cluster(self, name: str, k: int, iterations: int = 25) -> Any:
        return self.raw(
            "ClusterUltradimV23",
            {"name": name, "num_clusters": int(k), "max_cycles": int(iterations)},
        )

    def kmeans_save_model(
        self,
        name: str,
        k: int,
        window_ms: int,
        window_start_ms: int,
        stride_ms: int = 0,
        time_field: str = "event_ts",
        warm_start: bool = True,
        iterations: int = 25,
    ) -> Any:
        return self.raw(
            "CreateUltradimV23KmeansLineage",
            {
                "name": name,
                "num_clusters": int(k),
                "window_ms": int(window_ms),
                "stride_ms": int(stride_ms),
                "time_field": time_field,
                "window_start_ms": int(window_start_ms),
                "warm_start": bool(warm_start),
                "max_cycles": int(iterations),
            },
        )

    def kmeans_advance(self, name: str, lineage_id: str, window_start_ms: int = 0) -> Any:
        return self.raw(
            "AdvanceUltradimV23KmeansLineage",
            {
                "name": name,
                "lineage_id": lineage_id,
                "window_start_ms": int(window_start_ms),
            },
        )

    def kmeans_apply_model(
        self, name: str, model_id: str, row_ids: list[int] | None = None
    ) -> Any:
        return self.raw(
            "ApplyUltradimV23Kmeans",
            {
                "name": name,
                "model_id": model_id,
                "row_ids": [int(r) for r in (row_ids or [])],
            },
        )

    def kmeans_migration_graph(
        self, name: str, lineage_id: str, t_a: int, t_b: int
    ) -> Any:
        return self.raw(
            "GetUltradimV23KmeansMigrationGraph",
            {"name": name, "lineage_id": lineage_id, "t_a": int(t_a), "t_b": int(t_b)},
        )

    def drop_collection(self, name: str) -> Any:
        return self.raw("DropUltradimV23Collection", {"name": name})

    # -- authoritative status; field shapes are not available on this wheel --
    def describe_rpc(self, rpc: str) -> Any:
        """The RPC's authoritative status, plus a note on field shapes.

        capabilities() lists the implemented RPCs, and RPC_STATUS records
        the relationship between RPCs that answer the same question (which is
        canonical, which is a compat wrapper). What this wheel CANNOT give is
        an RPC's field shape — those needed a proto descriptor the earlier
        wheel embedded and this one does not — so the field list is deferred
        to the proto rather than invented.
        """
        surface = self.db.capabilities()
        if rpc not in surface:
            raise RetiredRpc(
                f"describe_rpc({rpc!r}): no such RPC on wheel {SERVER_VERSION} "
                f"(the API has {len(surface)} RPCs). Check the spelling with "
                "list_rpcs."
            )
        entry = RPC_STATUS.get(rpc, {})
        return {
            "rpc": rpc,
            "status": entry.get("status", "live"),
            "note": entry.get("note", "implemented on this wheel"),
            "field_shape": (
                "unavailable on this wheel — capabilities() returns names only, "
                "not proto descriptors. Read the request message in "
                "ultradimdb/proto/ultradim.proto; with call_rpc you state only "
                "the fields you want to change, the rest deep-merge over the "
                "proto defaults."
            ),
        }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=f"UltraDim MCP server {SERVER_VERSION} (stdio)."
    )
    ap.add_argument("--db", default="./ultradim_mcp_db", help="Storage directory.")
    args = ap.parse_args()

    tools = UltraDimTools(args.db)
    log(f"ready; db={args.db}; {len(TOOLS)} tools")

    def respond(msg_id: Any, result: Any = None, error: Any = None) -> None:
        out: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            out["error"] = error
        else:
            out["result"] = result
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            method, msg_id = msg.get("method"), msg.get("id")

            if method == "initialize":
                respond(
                    msg_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": SERVER_INFO,
                    },
                )
            elif method == "notifications/initialized":
                pass  # notification: no reply
            elif method == "tools/list":
                respond(msg_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = msg.get("params") or {}
                tool_name = params.get("name")
                tool_args = params.get("arguments") or {}
                fn = getattr(tools, tool_name, None) if tool_name else None
                if fn is None or tool_name.startswith("_"):
                    respond(msg_id, error={"code": -32601, "message": f"unknown tool {tool_name!r}"})
                    continue
                try:
                    result = fn(**tool_args)
                    respond(
                        msg_id,
                        {
                            "content": [
                                {"type": "text", "text": json.dumps(result, indent=2)}
                            ]
                        },
                    )
                except Exception as exc:
                    # Report the failure as tool content, not a protocol error:
                    # the model can read it and correct its call. The engine's
                    # messages name the row, seed and successor API, so they
                    # are worth surfacing verbatim.
                    log(f"tool {tool_name} failed: {exc}")
                    respond(
                        msg_id,
                        {
                            "content": [
                                {"type": "text", "text": f"{type(exc).__name__}: {exc}"}
                            ],
                            "isError": True,
                        },
                    )
            elif msg_id is not None:
                respond(msg_id, error={"code": -32601, "message": f"unknown method {method!r}"})
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    finally:
        tools.close()
        log("shut down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
