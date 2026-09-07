#!/usr/bin/env python3
"""Exercise the MCP tool handlers directly: no MCP client, no server.

Runs against the INSTALLED wheel, in an isolated scratch storage root — never
the repository's ./storage, never a listening port. Exits non-zero on the
first broken expectation.

WHAT THIS CHECKS THAT THE v0_2_0 HARNESS DID NOT

  * The five tools the old harness expected to REFUSE (cluster,
    collection_info, index_status, restart_indexing, drop_collection) are
    asserted to WORK, because on 0.3.0 they do.
  * Dense end to end: create, upsert, settle, search. The v0_2_0 server
    refused dense creation in Python; the refusal was false.
  * The planted fixture settles at the SHIPPED DEFAULT floor. The old
    harness passed floor=0.05 to force an index out of a corpus too weak to
    produce one; this one builds a corpus whose real neighbours clear the
    default, and checks that geometry with numpy BEFORE settling, so a
    fixture that drifts fails as "fixture too weak" and not as "the engine
    built nothing".
  * The native module's sha256 is recorded at start and re-checked at exit, so
    a wheel replaced underneath a running harness cannot be mistaken for a
    passing one.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np

# Everything is derived from this file's own location, so the harness runs from
# any checkout and any working directory.
MCP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(MCP_DIR)
SRC = os.path.join(MCP_DIR, "ultradim_mcp_server_v0_4_0.py")

# The field file the settle needs. It ships beside this file and is
# deterministic (every copy is the same bytes). Override with
# ULTRADIM_TRELLIS_FIELD to use a different one.
FIELD = os.environ.get(
    "ULTRADIM_TRELLIS_FIELD", os.path.join(MCP_DIR, "trellis_field_128d.field")
)

# A throwaway storage root: never the repository's ./storage, never a path this
# harness did not create, and removed on success. Override with
# ULTRADIM_TEST_DB to keep the store for inspection.
STORAGE = os.environ.get("ULTRADIM_TEST_DB") or tempfile.mkdtemp(
    prefix="mcp_store_"
)
KEEP_STORAGE = bool(os.environ.get("ULTRADIM_TEST_DB"))

FAILURES: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    """Record a failure and carry on, so one run reports every problem."""
    if condition:
        print(f"[ok] {label}")
    else:
        FAILURES.append(f"{label}: {detail}")
        print(f"[FAIL] {label}: {detail}")


def show(label: str, val, cap: int = 380) -> None:
    s = val if isinstance(val, str) else json.dumps(val)
    print(f"[{label}] {s[:cap]}")


# --------------------------------------------------------------------------
# Wheel identification. A version string does not identify a build — 0.3.0 has
# been cut more than once — so the harness pins the extension module's digest
# and re-checks it at the end. A wheel swapped mid-run invalidates the run.
# --------------------------------------------------------------------------
def module_sha() -> tuple[str, str]:
    import ultradim

    pkg = os.path.dirname(os.path.abspath(ultradim.__file__))
    for entry in sorted(os.listdir(pkg)):
        if entry.endswith((".so", ".pyd", ".dylib")):
            with open(os.path.join(pkg, entry), "rb") as fh:
                return entry, hashlib.sha256(fh.read()).hexdigest()
    raise RuntimeError(f"no native module found in {pkg}")


MODULE_NAME, SHA_AT_START = module_sha()
print(f"[wheel] {MODULE_NAME} sha256={SHA_AT_START}")

spec = importlib.util.spec_from_file_location("mcpsrv", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(f"[import] OK — {len(mod.TOOLS)} tools registered, server {mod.SERVER_VERSION}")

# Fail here with a name, rather than several steps later inside settle.
if not os.path.exists(FIELD):
    print(
        f"[FAIL] node-field artifact missing: {FIELD}\n"
        "       The settle projects against a TRLFIELD1 artifact of the same "
        "width as the family's projection_dim (128 here). It is generated, not "
        "checked in; point ULTRADIM_TRELLIS_FIELD at yours."
    )
    sys.exit(1)

os.makedirs(STORAGE, exist_ok=True)
print(f"[storage] {STORAGE}")
T = mod.UltraDimTools(STORAGE)

missing = [t["name"] for t in mod.TOOLS if not callable(getattr(T, t["name"], None))]
check(not missing, "every registered tool has a handler", f"missing: {missing}")

h = T.health()
show("health", h)
# The RPC count tracks the loaded wheel, not a constant. The server
# dispatches by name against capabilities(), so it runs against any wheel.
# Assert self-consistency first, then DERIVE the expected count from which RPCs
# the wheel actually reports, never a hardcoded number:
#   - Multi-family search (UltradimV23MultiFamilySearch): 200 -> 201.
#   - identity get (GetUltradimV23RowByContentKey, EXACT_IDENTITY_GET CR): +1.
#   - the row lifecycle pair (Replace/DeleteUltradimV23Point, SPARSE_REPLACE
#     CR): +2, and they always ship together — one without the other would mean
#     a caller could retire a row's identity but never retire the row.
# So a 0.3.0/0.3.1 wheel is 200, a 0.3.2-0.3.4 wheel is 201, a 0.3.5-0.3.8
# wheel is 202, and a wheel carrying the lifecycle pair is 204. Keying on RPC
# PRESENCE means this never fails on the wheel that ships a new RPC — the tier
# follows the wheel.
live_caps = T.db.capabilities()
live_surface = len(live_caps)
check(
    h["rpc_surface"] == live_surface,
    "health rpc_surface matches the wheel's live capabilities()",
    f"health says {h['rpc_surface']}, capabilities() has {live_surface}",
)
has_q12 = "UltradimV23MultiFamilySearch" in live_caps
has_identity_get = "GetUltradimV23RowByContentKey" in live_caps
has_replace = "ReplaceUltradimV23Point" in live_caps
has_delete = "DeleteUltradimV23Point" in live_caps
check(
    has_replace == has_delete,
    "the row lifecycle pair ships together",
    f"replace={has_replace} delete={has_delete}: a wheel with one and not the "
    "other lets a caller retire an identity but never the row",
)
# facet maps (facet map on upsert) is additive fields on existing messages, not an RPC,
# so it does not change the RPC count. Both multi-family search and facet maps landed in the same
# rebuild window, so a wheel carrying the multi-family RPC also
# carries the facet maps facet fields, and a earlier wheel carries neither.
has_q13 = has_q12
expected_surface = (
    200
    + (1 if has_q12 else 0)
    + (1 if has_identity_get else 0)
    + (2 if has_replace and has_delete else 0)
)
tier = (
    "row lifecycle (replace + delete)" if has_replace and has_delete
    else "0.3.5+ (identity get)" if has_identity_get
    else "multi-family-search wheel" if has_q12
    else "shipped 0.3.x wheel"
)
check(
    h["rpc_surface"] == expected_surface,
    f"surface is {expected_surface} RPCs ({tier})",
    f"got {h['rpc_surface']}, expected {expected_surface}",
)
check(
    h["wheel_build"]["sha256"] == SHA_AT_START,
    "health reports the wheel digest under test",
    f"{h['wheel_build']['sha256']} != {SHA_AT_START}",
)
# Version alignment is DERIVED (server file name vs loaded wheel) — assert the
# server considers itself aligned, whatever the version is, rather than pinning
# a literal that would need editing on every rename.
check(
    h["version_aligned"] is True and h["server_file"] == os.path.basename(SRC),
    "health reports the server file and that it is aligned with the loaded wheel",
    f"server_file={h.get('server_file')} version_aligned={h.get('version_aligned')} "
    f"wheel={h.get('wheel')} expected={h.get('expected_wheel')}",
)

# whats_available is the customer's front door: it must answer live from the
# wheel and account for every RPC the wheel reports (grouped, none dropped).
wa = T.whats_available()
show("whats_available", {k: wa[k] for k in ("version", "rpc_surface_total")})
grouped_total = sum(len(v) for v in wa["rpcs_by_area"].values())
check(
    wa["rpc_surface_total"] == live_surface and grouped_total == live_surface,
    "whats_available groups every RPC the wheel reports, none dropped",
    f"surface_total={wa['rpc_surface_total']} grouped={grouped_total} live={live_surface}",
)
check(
    wa["version"]["aligned"] is True,
    "whats_available reports the wheel aligned with the server file",
    f"{wa['version']}",
)

# The identity get (EXACT_IDENTITY_GET CR) through the JSON call path — the layer
# where the facet oneof bug lived (the Rust unit test used native structs and
# could not catch it). Upsert a content_key, do NOT settle, and assert the get
# HITS before indexing and a one-key edit MISSES.
if has_identity_get:
    idf = "identity_probe_family"
    T.create_collection(name=idf, source_dim=1024, projection_dim=64, seeds=[7, 11])
    T.upsert_sparse(
        name=idf,
        rows=[{"indices": [0, 1, 2], "values": [0.5, 0.5, 0.7071]}] * 3,
        facets=[{"content_key": f"key-{i:04x}"} for i in range(3)],
    )
    hit = T.get_row_by_content_key(name=idf, content_key="key-0001")
    miss = T.get_row_by_content_key(name=idf, content_key="key-0001x")
    show("identity_get", {"hit": hit, "miss": miss})
    check(
        hit["found"] is True and hit["row_id"] == 1,
        "identity get HITS the exact content_key before settle, right row id",
        f"{hit}",
    )
    check(
        miss["found"] is False,
        "identity get MISSES a one-character-edited key (exact, not fuzzy)",
        f"{miss}",
    )
    # The root-cause guard: a wrong facet value shape is REFUSED, not written
    # blank. Send the pre-fix snake_case oneof tag straight through call_rpc.
    refused = False
    try:
        T.call_rpc(
            "UpsertUltradimV23Points",
            {
                "name": idf,
                "batch": {
                    "row_ids": [3],
                    "sparse_vectors": [{"indices": [0, 1, 2], "values": [0.5, 0.5, 0.7071]}],
                    "facets": [{"fields": {"content_key": {"keyword_value": "x"}}}],
                },
            },
        )
    except Exception as exc:  # noqa: BLE001 - asserting the refusal text
        refused = "no value" in str(exc)
    check(
        refused,
        "a wrong facet value shape is refused (not silently written blank)",
        "the wrong-shape upsert was accepted — the silent-empty-facet bug is back",
    )

# The row lifecycle pair (SPARSE_REPLACE CR) through the JSON call path — the
# layer the Rust tests cannot reach, since they build native structs. The facet
# map goes over the wire here as the nested oneof shape, which is exactly where
# the earlier silent-empty-facet bug lived.
if has_replace and has_delete:
    print("\n--- replace / delete a row ---")
    lcf = "lifecycle_probe_family"
    T.create_collection(name=lcf, source_dim=1024, projection_dim=64, seeds=[7, 11])
    T.upsert_sparse(
        name=lcf,
        rows=[{"indices": [0, 1, 2], "values": [0.5, 0.5, 0.7071]}] * 3,
        facets=[{"content_key": f"instr-{i}", "desk": "london"} for i in range(3)],
    )

    # Replace with facets OMITTED: the identity and the rest of the metadata
    # carry over, and the identity now routes to the new row id.
    rep = T.replace_sparse_point(
        name=lcf,
        old_row_id=1,
        indices=[3, 4, 5],
        values=[0.5, 0.5, 0.7071],
    )
    show("replace_sparse_point", rep)
    check(
        rep["success"] is True and rep["new_row_id"] == 3,
        "replace retires the old row and returns a NEW row id",
        f"{rep}",
    )
    routed = T.get_row_by_content_key(name=lcf, content_key="instr-1")
    check(
        routed["found"] is True and routed["row_id"] == 3,
        "the content_key now routes to the replacement — identity stable, id versioned",
        f"{routed}",
    )

    # A retry of a replace that already happened must resolve, not duplicate.
    retry = T.replace_sparse_point(
        name=lcf,
        old_row_id=1,
        indices=[6, 7, 8],
        values=[0.5, 0.5, 0.7071],
    )
    show("replace retry", retry)
    check(
        retry["success"] is False
        and retry["already_replaced"] is True
        and retry["new_row_id"] == 3,
        "a retried replace resolves to the existing successor, never a second copy",
        f"{retry}",
    )

    # Supplying facets REPLACES metadata wholesale but never orphans the key.
    rep2 = T.replace_sparse_point(
        name=lcf,
        old_row_id=3,
        indices=[9, 10, 11],
        values=[0.5, 0.5, 0.7071],
        facets={"venue": "LSE"},
    )
    still = T.get_row_by_content_key(name=lcf, content_key="instr-1")
    check(
        rep2["success"] is True
        and still["found"] is True
        and still["row_id"] == rep2["new_row_id"],
        "supplied facets replace metadata wholesale, identity auto-injected",
        f"rep2={rep2} lookup={still}",
    )

    # Changing the key is refused. It arrives as an invalid_argument STATUS,
    # not a success-false field: the request was malformed, so it never became
    # an operation with a result to report.
    refused_key = ""
    try:
        T.replace_sparse_point(
            name=lcf,
            old_row_id=rep2["new_row_id"],
            indices=[12, 13, 14],
            values=[0.5, 0.5, 0.7071],
            facets={"content_key": "something-else"},
        )
    except Exception as exc:  # noqa: BLE001 - asserting the refusal text
        refused_key = str(exc)
    check(
        "cannot change" in refused_key,
        "changing content_key is refused over the JSON path too",
        f"got: {refused_key or 'NO REFUSAL — the change was accepted'}",
    )
    check(
        "delete" in refused_key and "insert" in refused_key,
        "and the refusal names the alternative rather than only saying no",
        f"got: {refused_key}",
    )

    # Delete: unreachable, idempotent, and the identity goes with it.
    dele = T.delete_sparse_point(name=lcf, row_id=0)
    again = T.delete_sparse_point(name=lcf, row_id=0)
    gone = T.get_row_by_content_key(name=lcf, content_key="instr-0")
    show("delete_sparse_point", {"first": dele, "repeat": again, "lookup": gone})
    check(
        dele["success"] is True and dele["was_already_deleted"] is False,
        "delete retires a row",
        f"{dele}",
    )
    check(
        again["success"] is True and again["was_already_deleted"] is True,
        "a repeated delete succeeds and says the row was already gone",
        f"{again}",
    )
    check(
        gone["found"] is False,
        "a deleted row's identity stops resolving",
        f"{gone}",
    )

    # whats_available must file these under their own area, NOT under ingest —
    # the ingest group's "Point" keyword would otherwise swallow them, telling a
    # caller that "change this row" is a way of adding rows.
    areas = {
        rpc: area
        for area, rpcs in T.whats_available()["rpcs_by_area"].items()
        for rpc in rpcs
    }
    check(
        areas.get("ReplaceUltradimV23Point") == "replace / delete a row"
        and areas.get("DeleteUltradimV23Point") == "replace / delete a row",
        "whats_available files replace/delete under their own area, not ingest",
        f"replace={areas.get('ReplaceUltradimV23Point')} "
        f"delete={areas.get('DeleteUltradimV23Point')}",
    )

    T.drop_collection(name=lcf)

    # 0.3.10: an ordinary write failure in the replace tail recovers IN
    # PROCESS — no restart (ticket
    # the tail-failure recovery, shipped in 0.3.10). On 0.3.9
    # the family was left refusing writes until the process came back.
    #
    # The failure is injected through ULTRADIM_FAULT_INJECT, which the shipped
    # binary honours precisely so this can be proved against the wheel a
    # customer runs rather than against a test-only build.
    print("\n--- replace tail failure recovers in process (0.3.10) ---")
    tf = "tail_recovery_probe_family"
    T.create_collection(name=tf, source_dim=1024, projection_dim=64, seeds=[7, 11])
    T.upsert_sparse(
        name=tf,
        rows=[{"indices": [0, 1, 2], "values": [0.5, 0.5, 0.7071]}] * 3,
        facets=[{"content_key": f"tail-{i}"} for i in range(3)],
    )

    os.environ["ULTRADIM_FAULT_INJECT"] = "payload"
    injected = ""
    try:
        T.replace_sparse_point(
            name=tf, old_row_id=1, indices=[3, 4, 5], values=[0.5, 0.5, 0.7071]
        )
    except Exception as exc:  # noqa: BLE001 - the injected failure is the point
        injected = str(exc)
    finally:
        os.environ.pop("ULTRADIM_FAULT_INJECT", None)

    check(
        "payload" in injected,
        "the injected tail failure is reported to the caller, not swallowed",
        f"got: {injected or 'NO ERROR — the seam did not fire'}",
    )

    # Everything below runs on the SAME process. No restart.
    routed = T.get_row_by_content_key(name=tf, content_key="tail-1")
    check(
        routed["found"] is True and routed["row_id"] == 3,
        "after the failure the identity resolves to the completed successor",
        f"{routed}",
    )
    recovered = T.upsert_sparse(
        name=tf, rows=[{"indices": [6, 7, 8], "values": [0.5, 0.5, 0.7071]}]
    )
    check(
        recovered.get("success", False) is True,
        "the family accepts ordinary writes again WITHOUT a restart",
        f"{recovered} — on 0.3.9 this failed the contiguity check until restart",
    )
    ok_again = T.replace_sparse_point(
        name=tf, old_row_id=3, indices=[9, 10, 11], values=[0.5, 0.5, 0.7071]
    )
    check(
        ok_again["success"] is True,
        "and accepts a further replace",
        f"{ok_again}",
    )
    T.drop_collection(name=tf)

    # 0.3.11: a failed journal CLEAR — the one seam 0.3.10 still returned
    # through — takes the family out of service instead of leaving an intent
    # that would make every later replace and delete fail. The operation
    # itself has already succeeded, so the error must say so.
    cf = "clear_failure_probe_family"
    T.create_collection(name=cf, source_dim=1024, projection_dim=64, seeds=[7, 11])
    T.upsert_sparse(
        name=cf,
        rows=[{"indices": [0, 1, 2], "values": [0.5, 0.5, 0.7071]}] * 3,
        facets=[{"content_key": f"clear-{i}"} for i in range(3)],
    )
    os.environ["ULTRADIM_FAULT_INJECT"] = "journal_clear"
    clear_err = ""
    try:
        T.replace_sparse_point(
            name=cf, old_row_id=0, indices=[3, 4, 5], values=[0.5, 0.5, 0.7071]
        )
    except Exception as exc:  # noqa: BLE001 - the injected failure is the point
        clear_err = str(exc)
    finally:
        os.environ.pop("ULTRADIM_FAULT_INJECT", None)

    check(
        "SUCCEEDED" in clear_err and "Do NOT retry" in clear_err,
        "a failed journal clear reports that the WRITE SUCCEEDED and not to retry",
        f"got: {clear_err or 'NO ERROR — the seam did not fire'}",
    )
    check(
        "out of service" in clear_err,
        "and that the family was taken out of service rather than left wedged",
        f"got: {clear_err}",
    )
    # The family now refuses traffic. Reopening is a process restart, which
    # this in-process harness does not do, so the check ends here — the Rust
    # e2e carries the reopen half.
    refused = ""
    try:
        T.get_row_by_content_key(name=cf, content_key="clear-0")
    except Exception as exc:  # noqa: BLE001 - the refusal is the assertion
        refused = str(exc)
    check(
        "not registered" in refused,
        "the out-of-service family refuses reads rather than serving a stale view",
        f"got: {refused or 'the family still answered'}",
    )

# --------------------------------------------------------------------------
# UMAP + HDBSCAN analytics tools (CR UMAP_HDBSCAN_MCP_TOOLS_CR_v0_01).
#
# Three layers, GPU-free first so they always run:
#  (1) COVERAGE GUARD — every customer-facing analytics RPC has a dedicated tool
#      (in TOOLS AND callable). This is the recurrence guard: a future analytics
#      RPC cannot ship invisible. Grepping self.raw is NOT used — a
#      helper can call self.raw without exposing a tool.
#  (2) WRAPPER UNIT ASSERTS — the enum string->int maps and the dense-XOR-sparse
#      query shaper, the layer where the facet oneof bug lived.
#  (3) GPU ROUND-TRIPS — a real UMAP fit and an HDBSCAN advance through the JSON
#      path. Guarded: on a GPU-absent/engine error they SKIP with a message, never a
#      silent pass.
# --------------------------------------------------------------------------
print("\n--- UMAP + HDBSCAN analytics tools ---")

# (1) Coverage guard: expected RPC -> tool name.
ANALYTICS_TOOLS = {
    "BuildUltradimV23KnnGraph": "build_knn_graph",
    "FitUltradimV23Umap": "fit_umap",
    "TransformUltradimV23Umap": "transform_umap",
    "GetUltradimV23UmapEmbedding": "umap_embedding",
    "GetUltradimV23UmapInfo": "umap_info",
    "ListUltradimV23UmapModels": "list_umap_models",
    "DropUltradimV23Umap": "drop_umap",
    "IncrementalFitUltradimV23Umap": "incremental_fit_umap",
    "CreateUltradimV23HdbscanLineage": "create_hdbscan_lineage",
    "AdvanceUltradimV23HdbscanLineage": "advance_hdbscan_lineage",
    "ApplyUltradimV23Hdbscan": "apply_hdbscan",
    "CoWalkUltradimV23Hdbscan": "cowalk_hdbscan",
    "GetUltradimV23HdbscanMigrationGraph": "hdbscan_migration_graph",
    "GetUltradimV23HdbscanInfo": "hdbscan_info",
    "ListUltradimV23HdbscanLineages": "list_hdbscan_lineages",
    "CompactUltradimV23HdbscanLineage": "compact_hdbscan_lineage",
    "DropUltradimV23HdbscanLineage": "drop_hdbscan_lineage",
}
tool_names = {t["name"] for t in mod.TOOLS}
for rpc, tool in ANALYTICS_TOOLS.items():
    in_tools = tool in tool_names
    is_callable = callable(getattr(mod.UltraDimTools, tool, None))
    check(
        in_tools and is_callable,
        f"analytics RPC {rpc} has a dedicated tool '{tool}' (in TOOLS + callable)",
        f"in_TOOLS={in_tools} callable={is_callable} — a future analytics RPC must "
        "not ship invisible",
    )

# (1b) The autotune tuning tool is exposed and callable (added in wheel 0.3.7). Not a
# wheel RPC — it drives the engine in Python — so it is checked directly rather
# than via the analytics RPC->tool map.
check(
    "autotune" in tool_names and callable(getattr(mod.UltraDimTools, "autotune", None)),
    "autotune tuning tool is in TOOLS and callable",
    "the autotune tool must be discoverable (tools/list) and dispatchable",
)

# (2) Wrapper unit asserts (no GPU).
check(mod._umap_init_wire("spectral") == 1 and mod._umap_init_wire("annealed") == 0
      and mod._umap_init_wire("random") == 2, "umap init string->int map is correct")
check(mod._umap_metric_wire("spherical") == 1 and mod._umap_metric_wire("euclidean") == 0,
      "umap metric string->int map is correct")
bad_enum = False
try:
    mod._umap_init_wire("nope")
except ValueError:
    bad_enum = True
check(bad_enum, "an unknown enum string raises (not a silent default)")
dq = mod._queries_wire([[0.1, 0.2, 0.3]])
check("dense_queries" in dq and dq["dense_queries"][0]["data"] == [0.1, 0.2, 0.3],
      "queries wrapper builds dense_queries for a list of floats")
sq = mod._queries_wire([{"indices": [0, 2], "values": [0.6, 0.8]}])
check("sparse_queries" in sq and sq["sparse_queries"][0]["indices"] == [0, 2],
      "queries wrapper builds sparse_queries for {indices,values}")
empty_raised = mixed_raised = False
try:
    mod._queries_wire([])
except ValueError:
    empty_raised = True
try:
    mod._queries_wire([[0.1], {"indices": [0], "values": [1.0]}])
except ValueError:
    mixed_raised = True
check(empty_raised, "an empty queries list raises (no silent neither-side)")
check(mixed_raised, "a mixed dense/sparse queries list raises")

# (3) GPU round-trips, guarded. A toy sparse family, a graph, a UMAP fit, and the
#     reshaped embedding. On any engine/GPU error we SKIP with a message.
# PLANTED corpus (same shape as the fixture below): 30 of each row's 32 nnz from
# a shared 36-dim topic pool, so same-topic rows are real neighbours (cosine
# ~0.5). A random corpus has NO neighbour structure and the graph fails its
# recall tolerance (measured: 0.43 < 0.99); the fit then refuses, correctly.
_AN_D, _AN_NNZ, _AN_POOL, _AN_SHARED, _AN_G = 20_000, 32, 36, 30, 8
_an_prng = np.random.default_rng(11)
_an_topics = [_an_prng.choice(_AN_D, _AN_POOL, replace=False) for _ in range(_AN_G)]


def _planted_sparse(i: int) -> dict:
    topic = _an_topics[i % _AN_G]
    idx = np.unique(
        np.concatenate([
            _an_prng.choice(topic, _AN_SHARED, replace=False),
            _an_prng.choice(_AN_D, _AN_NNZ - _AN_SHARED, replace=False),
        ])
    )
    v = np.abs(_an_prng.standard_normal(len(idx)).astype(np.float32))
    v /= np.linalg.norm(v)
    order = np.argsort(idx)
    return {"indices": [int(x) for x in idx[order]], "values": [float(x) for x in v[order]]}

UMAP_N = 200
UMAP_K = 15
def _is_gpu_unavailable(exc: Exception) -> bool:
    """True only for a real GPU/adapter-absent error — never a wrapper bug or a
    precondition, which must hard-fail, not silently skip. (An over-broad skip is
    itself the silent-drop disease.)"""
    t = str(exc).lower()
    return any(s in t for s in ("no gpu", "no adapter", "wgpu", "metal", "vulkan",
                                "failed to create device", "no suitable"))


umap_fam = "umap_roundtrip_family"
try:
    T.create_collection(name=umap_fam, source_dim=_AN_D, projection_dim=128, seeds=[7, 11])
    T.upsert_sparse(name=umap_fam, rows=[_planted_sparse(i) for i in range(UMAP_N)])
    T.make_searchable(name=umap_fam)  # kNN graph needs a resident template engine
    T.build_knn_graph(name=umap_fam, k=UMAP_K)
    # Call the FRIENDLY fit_umap wrapper first and assert it is REFUSED at the G1
    # recall tolerance (a 200-row toy corpus measures ~0.96, below 0.99). This
    # proves the wrapper's fields + enum ints deserialize and reach the engine,
    # and documents the tolerance. Then force past it via the raw
    # path (force stays OFF the friendly schema — expert-only). A production
    # corpus clears 0.99 without force.
    refused_gate = False
    try:
        T.fit_umap(name=umap_fam, n_components=2, n_neighbors=UMAP_K, n_epochs=50, seed=7)
    except Exception as fe:  # noqa: BLE001
        refused_gate = "recall" in str(fe).lower() or "REFUSED" in str(fe)
    check(refused_gate, "fit_umap wrapper reaches the engine and is refused below the recall tolerance",
          "the toy graph unexpectedly met the 0.99 tolerance, or the wrapper did not reach the engine")
    fit = T.call_rpc("FitUltradimV23Umap", {
        "name": umap_fam, "n_components": 2, "n_neighbors": UMAP_K,
        "n_epochs": 50, "umap_seed": 7, "force": True,
    })
    umap_id = fit.get("umap_id")
    emb = T.umap_embedding(name=umap_fam, umap_id=umap_id, limit=10)
    rows = emb.get("embeddings", [])
    ok = bool(rows) and all(isinstance(r, list) and len(r) == 2 for r in rows)
    check(ok, "UMAP round-trip: fit -> embedding returns reshaped 2-D rows (not a flat array)",
          f"got {rows[:2]!r}")
    # Probe the remaining UMAP read/transform/list/drop tools on this live map.
    info = T.umap_info(name=umap_fam, umap_id=umap_id)
    check(info is not None, "umap_info returns metadata for the fitted map", f"{info}")
    models = T.list_umap_models(name=umap_fam)
    check(umap_id in json.dumps(models), "list_umap_models lists the fitted map", f"{models}")
    tr = T.transform_umap(name=umap_fam, umap_id=umap_id,
                          queries=[_planted_sparse(i) for i in range(3)])
    tr_rows = tr.get("embeddings", [])
    check(bool(tr_rows) and all(len(r) == 2 for r in tr_rows),
          "transform_umap places new points, returns reshaped 2-D rows", f"{tr_rows[:2]!r}")
    # incremental_fit_umap is NOT live-probed here. It requires the fold's append
    # to carry the parent map's graph params, and the fit pins its own default-k
    # (32) graph rather than a caller's k build — reconciling that at toy scale is
    # a deep engine-contract dance, not wrapper coverage. The wrapper is covered
    # at the coverage-guard + shape level (it is in TOOLS, callable, and its
    # queries/batch_row_ids go through the same _queries_wire path asserted above);
    # its README row states it is not yet live-probed, so the "everything probed"
    # claim stays true.
    T.drop_umap(name=umap_fam, umap_id=umap_id)
    models_after = T.list_umap_models(name=umap_fam)
    check(umap_id not in json.dumps(models_after), "drop_umap removes the fitted map",
          f"{models_after}")
except Exception as exc:  # noqa: BLE001
    if _is_gpu_unavailable(exc):
        print(f"[SKIP] UMAP round-trip: GPU unavailable in this env: {str(exc)}")
    else:
        check(False, "UMAP round-trip: fit -> embedding", str(exc))

# HDBSCAN round-trip: graph -> lineage -> append batch -> advance -> apply.
hdb_fam = "hdbscan_roundtrip_family"
try:
    T.create_collection(name=hdb_fam, source_dim=_AN_D, projection_dim=128, seeds=[7, 11])
    T.upsert_sparse(name=hdb_fam, rows=[_planted_sparse(i) for i in range(UMAP_N)])
    T.make_searchable(name=hdb_fam)  # kNN graph needs a resident template engine
    g = T.build_knn_graph(name=hdb_fam, k=UMAP_K)
    graph_id = g.get("graph_id") or ""
    lin = T.create_hdbscan_lineage(name=hdb_fam, graph_id=graph_id)
    lineage_id = lin.get("lineage_id")
    # Append a second batch to the graph, then advance the lineage over them. The
    # appended rows must be flushed by a settle BEFORE build_knn_graph — the
    # graph must see every row (the engine refuses a graph over a pending
    # sub-window remainder).
    T.upsert_sparse(name=hdb_fam, rows=[_planted_sparse(i) for i in range(UMAP_N, UMAP_N + 40)],
                    row_ids=list(range(UMAP_N, UMAP_N + 40)))
    T.make_searchable(name=hdb_fam)  # flush the appended rows before the graph append
    T.build_knn_graph(name=hdb_fam, k=UMAP_K, append=True,
                      row_ids=list(range(UMAP_N, UMAP_N + 40)))
    T.advance_hdbscan_lineage(name=hdb_fam, lineage_id=lineage_id,
                              batch_row_ids=list(range(UMAP_N, UMAP_N + 40)))
    applied = T.apply_hdbscan(name=hdb_fam, lineage_id=lineage_id, t_latest=True,
                              row_ids=list(range(0, 10)))
    check(applied is not None, "HDBSCAN round-trip: create -> advance -> apply returns a labelling",
          f"{applied}")
    # After the advance there are two time points (t0, t1) — probe the time-pair
    # and metadata tools on them.
    info = T.hdbscan_info(name=hdb_fam, lineage_id=lineage_id)
    check(info is not None, "hdbscan_info returns lineage metadata", f"{info}")
    lins = T.list_hdbscan_lineages(name=hdb_fam)
    check(lineage_id in json.dumps(lins), "list_hdbscan_lineages lists the lineage", f"{lins}")
    cw = T.cowalk_hdbscan(name=hdb_fam, lineage_id=lineage_id, t_a=0, t_b=1,
                          row_ids=list(range(0, 10)))
    check(cw is not None, "cowalk_hdbscan compares clusters at t_a=0 vs t_b=1", f"{cw}")
    mg = T.hdbscan_migration_graph(name=hdb_fam, lineage_id=lineage_id, t_a=0, t_b=1,
                                   row_ids=list(range(0, 10)))
    check(mg is not None, "hdbscan_migration_graph returns the t0->t1 migration", f"{mg}")
    T.compact_hdbscan_lineage(name=hdb_fam, lineage_id=lineage_id)
    check(True, "compact_hdbscan_lineage runs without error")
    T.drop_hdbscan_lineage(name=hdb_fam, lineage_id=lineage_id)
    lins_after = T.list_hdbscan_lineages(name=hdb_fam)
    check(lineage_id not in json.dumps(lins_after), "drop_hdbscan_lineage removes the lineage",
          f"{lins_after}")
    # cowalk_hdbscan / hdbscan_migration_graph must REFUSE a defaulted (0,0) — the
    # no-default t_a/t_b rule. We assert the wrapper requires them (TypeError on
    # omission), which is the loud failure the proto's optional fields protect.
    missing_t_raised = False
    try:
        T.cowalk_hdbscan(name=hdb_fam, lineage_id=lineage_id, row_ids=[0])  # type: ignore[call-arg]
    except TypeError:
        missing_t_raised = True
    check(missing_t_raised, "cowalk_hdbscan requires t_a and t_b (no default -> loud TypeError)")
except Exception as exc:  # noqa: BLE001
    if _is_gpu_unavailable(exc):
        print(f"[SKIP] HDBSCAN round-trip: GPU unavailable in this env: {str(exc)}")
    else:
        check(False, "HDBSCAN round-trip: create -> advance -> apply", str(exc))

# --------------------------------------------------------------------------
# Sparse family with PLANTED structure, settled at the DEFAULT floor.
#
# The default floor at D_proj 128 is 0.3314. A corpus of random sparse rows has no pair anywhere near that, which is why
# the v0_2_0 harness had to override it. The geometry below is sized so real
# neighbours clear it: 30 of each row's 32 non-zeros are drawn from a
# 36-dimension topic pool, giving same-topic pairs a median cosine around 0.5
# while unrelated pairs stay near zero.
# --------------------------------------------------------------------------
D, NNZ, N, G = 20_000, 32, 400, 20
POOL, SHARED = 36, 30
DEFAULT_FLOOR_128 = 0.3314

prng = np.random.default_rng(5)
topics = [prng.choice(D, POOL, replace=False) for _ in range(G)]
rows = []
for i in range(N):
    topic = topics[i % G]
    idx = np.unique(
        np.concatenate(
            [
                prng.choice(topic, SHARED, replace=False),
                prng.choice(D, NNZ - SHARED, replace=False),
            ]
        )
    )
    v = np.abs(prng.standard_normal(len(idx)).astype(np.float32))
    v /= np.linalg.norm(v)
    order = np.argsort(idx)
    rows.append(
        {
            "indices": [int(x) for x in idx[order]],
            "values": [float(x) for x in v[order]],
        }
    )

# Verify the fixture BEFORE the engine sees it. If this fails the corpus is at
# fault, not the index, and the message says which.
M = np.zeros((N, D), dtype=np.float32)
for i, rw in enumerate(rows):
    M[i, rw["indices"]] = rw["values"]
gram = M @ M.T
np.fill_diagonal(gram, -1.0)
same = np.equal.outer(np.arange(N) % G, np.arange(N) % G)
np.fill_diagonal(same, False)
median_intra = float(np.median(gram[same]))
max_inter = float(np.max(gram[~same]))
print(f"[fixture] median intra-topic cosine {median_intra:.3f}, "
      f"max cross-topic {max_inter:.3f}, default floor {DEFAULT_FLOOR_128}")
check(
    median_intra > DEFAULT_FLOOR_128,
    "planted fixture clears the default floor",
    f"median intra {median_intra:.3f} <= {DEFAULT_FLOOR_128} — fixture too weak, "
    "widen the topic overlap rather than lowering the floor",
)
check(
    max_inter < DEFAULT_FLOOR_128,
    "cross-topic pairs stay below the floor",
    f"max inter {max_inter:.3f}",
)

show("list_collections(empty)", T.list_collections())
show(
    "create_collection(sparse)",
    T.create_collection("toy", source_dim=D, projection_dim=128,
                        seeds=[11, 22, 33, 44], max_nnz_per_row=64),
)
show("upsert_sparse(auto ids, 300)", T.upsert_sparse("toy", rows[:300]))

t0 = time.time()
st = T.trellis_template_settle("toy", FIELD, window=100, telemetry_stride=50)
print(f"[settle] wall={time.time()-t0:.2f}s rows_total={st['rows_total']} "
      f"mean_out_degree={[round(x, 2) for x in st['mean_out_degree']]} "
      f"isolated={st['isolated_rows']}")
check(
    max(st["mean_out_degree"]) > 1.0,
    "settle builds an index at the DEFAULT floor, no override",
    f"degrees {st['mean_out_degree']}",
)
show("status(after settle)", T.trellis_template_status("toy"))

r = T.trellis_template_search("toy", rows[0], top_k=5)
show("search(top5)", r)
check(
    bool(r["results"]) and r["results"][0]["id"] == 0 and r["results"][0]["score"] > 0.99,
    "self-match at rank 1, id flattened to an int",
    json.dumps(r)[:200],
)

r2 = T.trellis_template_search("toy", rows[0], top_k=5, exclude_ids=[0])
check(0 not in [x["id"] for x in r2["results"]], "exclude_ids honoured", json.dumps(r2)[:160])

# Continuous ingest: rows added after the build are findable with no settle.
show("upsert_sparse(continue, 100)", T.upsert_sparse("toy", rows[300:]))
r3 = T.trellis_template_search("toy", rows[350], top_k=3)
check(
    bool(r3["results"]) and r3["results"][0]["id"] == 350,
    "post-build row found at rank 1 without a second settle",
    json.dumps(r3)[:200],
)

# --------------------------------------------------------------------------
# Ticket TRELLIS_WINDOW_FLOOR_ALLOW_ONE: window=1 through the MCP -> wheel path.
# The settle floor was lowered 100 -> 1 so a record is searchable after a single
# settle pass, record-by-record (the prefill-cache pattern). A fresh family so this
# does not disturb the window=100 assertions above.
# --------------------------------------------------------------------------
print("\n--- window=1: record-by-record settle (interactive/prefill posture) ---")
show("create_collection(win1)",
     T.create_collection("win1", source_dim=D, projection_dim=128,
                         seeds=[11, 22, 33, 44], max_nnz_per_row=64))
show("upsert_sparse(win1, 300)", T.upsert_sparse("win1", rows[:300]))
sw = T.trellis_template_settle("win1", FIELD, window=1)
check(
    sw["rows_total"] == 300 and max(sw["mean_out_degree"]) > 1.0,
    "window=1 settle accepted (was clamped to 100) and indexes every record",
    f"rows_total={sw['rows_total']} degrees={[round(x, 2) for x in sw['mean_out_degree']]}",
)
rw = T.trellis_template_search("win1", rows[0], top_k=5)
check(
    bool(rw["results"]) and rw["results"][0]["id"] == 0 and rw["results"][0]["score"] > 0.99,
    "window=1: an upserted record is searchable after one settle pass",
    json.dumps(rw)[:200],
)

# THE SANCTIONED ONE-CALL PATH (0.3.4): make_searchable(window=1). Build now
# threads window through, so record-by-record needs no raw settle and no
# field_path — the fix for the make_searchable-can't-do-window=1 gotcha that
# 0.3.3 shipped. A fresh family, its own upsert.
show("create_collection(win1b)",
     T.create_collection("win1b", source_dim=D, projection_dim=128,
                         seeds=[11, 22, 33, 44], max_nnz_per_row=64))
show("upsert_sparse(win1b, 300)", T.upsert_sparse("win1b", rows[:300]))
mb = T.make_searchable("win1b", window=1)
# NOTE ON WHAT THIS PROVES: Build's response does not report the per-window count,
# so rows_total/graph_nodes here prove the one-call path RUNS and builds every row,
# not that window=1 vs 10000 took effect (both build all rows). The window-count
# DISCRIMINATOR — window=1 => N windows, 0/default => 1 — is asserted in the Rust
# test (trellis_window_floor_one.rs) via the raw settle's window_stats, which Build
# does not expose. Here we assert the sanctioned one-call path is wired and serves.
check(
    mb.get("rows_total") == 300 and mb.get("graph_nodes", 0) > 0,
    "make_searchable(window=1) runs in ONE call (no field_path) and builds every row",
    json.dumps(mb)[:200],
)
rb = T.trellis_template_search("win1b", rows[0], top_k=5)
check(
    bool(rb["results"]) and rb["results"][0]["id"] == 0 and rb["results"][0]["score"] > 0.99,
    "make_searchable(window=1): an upserted record is searchable (sanctioned one-call path)",
    json.dumps(rb)[:200],
)

# --------------------------------------------------------------------------
# make_searchable: the acceptance property, not registration. A family is
# created and loaded, then made searchable in ONE call with NO field_path and
# NO floor anywhere in the call — the sanctioned high-level path — and a
# planted near-neighbour comes back. This is what the ticket demands; a
# hasattr check would prove nothing.
# --------------------------------------------------------------------------
print("\n--- make_searchable: one call, no field_path, no floor ---")
check(
    callable(getattr(T, "make_searchable", None)),
    "make_searchable handler exists",
    "no handler registered",
)
T.create_collection("cache", source_dim=D, projection_dim=128, seeds=[11, 22, 33, 44])
T.upsert_sparse("cache", rows[:120])
ms = T.make_searchable("cache")
show("make_searchable(cache)", ms)
check(
    ms.get("rows_total") == 120 and ms.get("graph_nodes") == 120,
    "make_searchable builds the loaded family with no field_path or floor",
    json.dumps(ms)[:200],
)
# The neighbour of row 0 shares its topic (same i % G); it must come back.
ms_res = T.trellis_template_search("cache", rows[0], top_k=5, exclude_ids=[0])
ms_ids = [x["id"] for x in ms_res["results"]]
check(
    bool(ms_ids) and any((i % G) == 0 for i in ms_ids),
    "search after make_searchable returns a same-topic neighbour",
    json.dumps(ms_res)[:200],
)

# --------------------------------------------------------------------------
# facet maps: generic facet map on upsert + facet filter on search. A fresh family is
# built with a row-aligned facet map; ~1 topic in G (topic 0) is tagged
# {security_level:3, org_id:"acme"}. A qualifying probe filtered on those facets
# must return top_k HITS THAT ALL QUALIFY — a post-filter over the same take
# budget could not fill top_k when only ~1/G of rows match, so K qualifying hits
# proves the push-down spent the budget on qualifying rows during collection.
# --------------------------------------------------------------------------
if not has_q13:
    print("\n--- facet maps: facet map on upsert + facet filter on search — SKIPPED ---")
    print("    The loaded wheel predates facet fields; it has "
          "no facet plumbing. Use a wheel at 0.3.4 or later to exercise this "
          "section. RPC count unaffected (facet maps is additive fields, not an RPC).")
else:
    print("\n--- facet maps: facet map on upsert + facet filter on search ---")
    T.create_collection("facet", source_dim=D, projection_dim=128,
                        seeds=[11, 22, 33, 44], max_nnz_per_row=64)

    def qualifies(i: int) -> bool:
        return (i % G) == 0

    facet_rows = [
        {"security_level": 3, "org_id": "acme"} if qualifies(i)
        else {"security_level": 1, "org_id": "other"}
        for i in range(N)
    ]
    show("upsert_sparse(with facets)", T.upsert_sparse("facet", rows, facets=facet_rows))
    T.make_searchable("facet")

    acme = {"must": [
        {"field": "security_level", "match_int": 3},
        {"field": "org_id", "match_keyword": "acme"},
    ]}
    # take_per_seed raised because the filter is ~1/G selective (the recall dial when a scope filter is active).
    K_FACET = 5
    probe_i = 0  # topic 0 qualifies
    assert qualifies(probe_i)
    fr = T.trellis_template_search(
        "facet", rows[probe_i], top_k=K_FACET, template_filter=acme, take_per_seed=400
    )
    show("facet-filtered search", fr)
    fr_ids = [x["id"] for x in fr["results"]]
    check(
        len(fr_ids) == K_FACET,
        f"facet filter returns {K_FACET} qualifying hits (push-down, not post-filter)",
        f"got {len(fr_ids)}: {fr_ids}",
    )
    check(
        all(qualifies(i) for i in fr_ids),
        "every facet-filtered hit qualifies (security_level==3 AND org_id==acme)",
        f"ids {fr_ids} (topics {[i % G for i in fr_ids]})",
    )

    # A reserved-key facet is rejected by the SERVER (not the client), naming the key.
    try:
        T.upsert_sparse("facet", rows[:1], row_ids=[N],
                        facets=[{"world_id": "sneaky"}])
        check(False, "reserved-key facet rejected by server", "it was accepted")
    except RuntimeError as exc:
        check(
            "world_id" in str(exc) and "reserved" in str(exc),
            "reserved-key facet rejected by server, naming the key",
            str(exc)[:160],
        )

    # A float facet VALUE is rejected by the CLIENT before the wire (no float range).
    try:
        T.upsert_sparse("facet", rows[:1], row_ids=[N], facets=[{"score": 0.5}])
        check(False, "float facet value rejected by client", "it was accepted")
    except ValueError as exc:
        check("int or str" in str(exc), "float facet value rejected by client",
              str(exc)[:160])

# --------------------------------------------------------------------------
# multi-family search: batched cross-family search. Two families over the same id space —
# family A holds all N rows, family B a contiguous PREFIX (the CSR admits ids
# only as a contiguous extension from 0). A probe that exists ONLY in A (id >=
# the prefix length) is searched in both in ONE call:
#  - score[i] for a row present in family i bit-equals that family's own
#    single-family RPC (the multi-family RPC reuses the single-family core);
#  - present[] discriminates: the probe self-match is present in A only.
# --------------------------------------------------------------------------
if not has_q12:
    print("\n--- multi-family search: batched cross-family search — SKIPPED ---")
    print("    The loaded wheel has no UltradimV23MultiFamilySearch RPC "
          "(added in 0.3.2). Use a wheel at 0.3.2 or later to exercise this "
          "section; the RPC-count check above already expected 200, not 201.")
else:
    print("\n--- multi-family search: batched cross-family search ---")
    B_ROWS = 200
    T.create_collection("fam_a", source_dim=D, projection_dim=128,
                        seeds=[11, 22, 33, 44], max_nnz_per_row=64)
    T.create_collection("fam_b", source_dim=D, projection_dim=128,
                        seeds=[11, 22, 33, 44], max_nnz_per_row=64)
    T.upsert_sparse("fam_a", rows)          # all N
    T.upsert_sparse("fam_b", rows[:B_ROWS])  # contiguous prefix
    T.make_searchable("fam_a")
    T.make_searchable("fam_b")

    mf_probe = B_ROWS  # exists only in A
    # Single-family ground truth for bit-equality.
    sa = T.trellis_template_search("fam_a", rows[mf_probe], top_k=5)
    sb = T.trellis_template_search("fam_b", rows[mf_probe], top_k=5)
    sa_scores = {r["id"]: r["score"] for r in sa["results"]}
    sb_scores = {r["id"]: r["score"] for r in sb["results"]}

    mf = T.multi_family_search(
        ["fam_a", "fam_b"], sparse_query=rows[mf_probe], top_k=5
    )
    show("multi_family_search", mf)
    check(
        mf["families"] == ["fam_a", "fam_b"],
        "response echoes the family order",
        json.dumps(mf["families"]),
    )
    # Bit-equality per family for a row present in that family.
    mf_ok = True
    mf_detail = ""
    for hit in mf["hits"]:
        rid = hit["row_id"]
        for i, (fam_scores, present_flag, score_i) in enumerate(
            [(sa_scores, hit["present"][0], hit["score"][0]),
             (sb_scores, hit["present"][1], hit["score"][1])]
        ):
            if rid in fam_scores:
                if not present_flag or score_i != fam_scores[rid]:
                    mf_ok = False
                    mf_detail = f"row {rid} fam {i}: score {score_i} vs {fam_scores[rid]}, present={present_flag}"
            else:
                if present_flag or score_i != 0.0:
                    mf_ok = False
                    mf_detail = f"row {rid} fam {i}: absent but present={present_flag} score={score_i}"
    check(mf_ok, "each score[i] bit-equals the single-family RPC; present[] correct",
          mf_detail)
    # The probe self-match is present in A only.
    self_hit = next((h for h in mf["hits"] if h["row_id"] == mf_probe), None)
    check(
        self_hit is not None and self_hit["present"] == [True, False]
        and self_hit["score"][0] > 0.99,
        "probe self-match present in A only (present=[True,False])",
        json.dumps(self_hit) if self_hit else "probe not in join",
    )
    # Mixed substrate is rejected (fam_a sparse vs the dense family created later
    # would need to exist; instead assert empty names is rejected by the client).
    try:
        T.multi_family_search([], sparse_query=rows[0])
        check(False, "multi_family_search rejects empty names", "it was accepted")
    except ValueError as exc:
        check("empty" in str(exc).lower(), "multi_family_search rejects empty names",
              str(exc)[:120])

# --------------------------------------------------------------------------
# Ground truth from the ENGINE, not from numpy. build_oracle calls
# CreateSparseOracles, which brute-forces every committed row and writes the
# artifact itself; the path it returns feeds straight into measure_recall.
# --------------------------------------------------------------------------
ora = T.build_oracle("toy", query_ids=list(range(30)), top_k=10)
show("build_oracle", {k: v for k, v in ora.items() if k != "results"})
check(
    bool(ora["oracle_path"]) and os.path.isabs(ora["oracle_path"])
    and os.path.exists(ora["oracle_path"]),
    "engine wrote the oracle artifact at an absolute path",
    str(ora["oracle_path"]),
)
check(ora["rows_scanned"] == N, "oracle scanned every committed row",
      f"{ora['rows_scanned']} != {N}")

# Cross-check the engine's exact top-k against numpy on the same rows: this is
# the one place the two must agree, and it validates the fixture and the
# engine's brute force at the same time.
engine_top = {q["query_id"]: list(q["neighbor_ids"])[:10] for q in (ora["results"] or [])}
agree = []
for qid, got in engine_top.items():
    want = [int(j) for j in np.argsort(-gram[qid])[:10]]
    agree.append(len(set(got) & set(want)) / 10.0)
check(
    bool(agree) and min(agree) == 1.0,
    "engine brute force matches numpy exactly on every query",
    f"worst overlap {min(agree) if agree else 'n/a'}",
)

rec = T.trellis_measure_recall("toy", ora["oracle_path"], k=10)
print(f"[recall] recall@10={rec['recall_at_k']:.3f} p50={rec['p50_ms']:.2f}ms "
      f"n_queries={rec['n_queries']}")
check(rec["recall_at_k"] > 0.15, "index retrieves planted neighbours",
      json.dumps(rec)[:200])

show("list_rpcs(contains=trellis)", T.list_rpcs(contains="trellis"))
show("call_rpc(HealthCheck)", T.call_rpc("HealthCheck", {"service": "x"}))

# --------------------------------------------------------------------------
# The RPCs the v0_2_0 harness expected to REFUSE. All five must now answer.
# --------------------------------------------------------------------------
print("\n--- RPCs that were RETIRED-FAIL expectations on the 0.2.0 harness ---")

info = T.collection_info("toy")
check(
    info.get("registered") is True and info.get("substrate") == "sparse"
    and info.get("source_dim") == D,
    "collection_info returns the registry record",
    json.dumps(info)[:200],
)

idx_status = T.index_status("toy")
check(bool(idx_status.get("shards")), "index_status reports shards",
      json.dumps(idx_status)[:200])

restarted = T.restart_indexing("toy")
check(
    restarted.get("success") is True and restarted.get("shards_triggered", 0) > 0,
    "restart_indexing triggers the settled family's shards",
    json.dumps(restarted)[:200],
)

clustered = T.cluster("toy", k=4)
check(
    clustered.get("success") is True
    and len(clustered.get("assignments") or []) == N
    and set(clustered["assignments"]) <= {0, 1, 2, 3},
    "cluster assigns every row to one of k clusters",
    json.dumps(clustered)[:200],
)

# --------------------------------------------------------------------------
# The k-means lineage, end to end on its own time-stamped family.
# Rows enter a window by event_ts, so the timestamps are the fixture.
# --------------------------------------------------------------------------
print("\n--- k-means lineage ---")
WINDOW_MS = 86_400_000
T0_MS = 1_700_000_000_000
T.create_collection("lin", source_dim=D, projection_dim=128)
T.upsert_sparse(
    "lin", rows[:200],
    event_ts=[T0_MS + (i // 100) * WINDOW_MS + i for i in range(200)],
)
saved = T.kmeans_save_model("lin", k=4, window_ms=WINDOW_MS, window_start_ms=T0_MS)
show("kmeans_save_model", saved)
check(
    bool(saved.get("lineage_id")) and bool(saved.get("model_id"))
    and saved.get("rows_fitted", 0) > 0,
    "kmeans_save_model opens a lineage and fits window 0",
    json.dumps(saved)[:200],
)

advanced = T.kmeans_advance("lin", saved["lineage_id"], T0_MS + WINDOW_MS)
show("kmeans_advance", advanced)
check(
    advanced.get("t") == 1 and advanced.get("warm_started") is True,
    "kmeans_advance fits window 1, warm-started from window 0",
    json.dumps(advanced)[:200],
)

applied = T.kmeans_apply_model("lin", saved["model_id"], row_ids=[0, 1, 2])
show("kmeans_apply_model", applied)
check(
    len(applied.get("assignments") or []) == 3
    and applied.get("row_id_order") == [0, 1, 2],
    "kmeans_apply_model scores the rows asked for, in order",
    json.dumps(applied)[:200],
)

graph = T.kmeans_migration_graph("lin", saved["lineage_id"], 0, 1)
show("kmeans_migration_graph", graph)
check(
    bool(graph.get("edges"))
    and all({"from_cluster", "to_cluster", "mass"} <= set(e) for e in graph["edges"]),
    "kmeans_migration_graph returns mass flows between windows",
    json.dumps(graph)[:200],
)

# --------------------------------------------------------------------------
# Dense, end to end. v0_2_0 refused this in Python before the engine saw it.
# The planted geometry here mirrors the sparse case: 20 group centroids, rows
# at 0.8 centroid + 0.2 noise, giving same-group cosines around 0.94.
# --------------------------------------------------------------------------
print("\n--- dense family: create, upsert, settle, search ---")
DD, DN, DG = 256, 200, 20
drng = np.random.default_rng(11)
cent = drng.standard_normal((DG, DD)).astype(np.float32)
cent /= np.linalg.norm(cent, axis=1, keepdims=True)
dense_rows = []
for i in range(DN):
    noise = drng.standard_normal(DD).astype(np.float32)
    noise /= np.linalg.norm(noise)
    v = 0.8 * cent[i % DG] + 0.2 * noise
    v /= np.linalg.norm(v)
    dense_rows.append([float(x) for x in v])

created = T.create_collection("dense", source_dim=DD, projection_dim=128,
                              seeds=[11, 22, 33, 44], sparse=False)
check(created.get("success") is True, "dense family created — the 0.2.0 refusal was false",
      json.dumps(created)[:200])
dinfo = T.collection_info("dense")
check(dinfo.get("substrate") == "dense", "registry records the dense substrate",
      json.dumps(dinfo)[:160])

show("upsert_dense(200)", T.upsert_dense("dense", dense_rows))
dst = T.trellis_template_settle("dense", FIELD, window=50)
print(f"[dense settle] mean_out_degree={[round(x, 2) for x in dst['mean_out_degree']]} "
      f"isolated={dst['isolated_rows']}")
check(max(dst["mean_out_degree"]) > 1.0, "dense family settles into a graph",
      f"degrees {dst['mean_out_degree']}")

dres = T.search("dense", dense_rows[0], top_k=3)
hits = dres.get("result") or []
top_id = mod.flatten_point_id(hits[0]["id"]) if hits else None
print(f"[dense search] top_id={top_id} score={hits[0]['score'] if hits else None}")
check(top_id == 0 and hits[0]["score"] > 0.99,
      "dense search returns the query row at rank 1", json.dumps(dres)[:220])

# cluster is the one RPC that still refuses dense, and it must refuse by name.
try:
    T.cluster("dense", k=3)
    check(False, "cluster refuses a dense family", "it returned instead")
except RuntimeError as exc:
    check("dense" in str(exc).lower(),
          "cluster refuses a dense family, naming the substrate", str(exc)[:160])

# list_collections must now see BOTH families — the registry fix.
listing = T.list_collections()
listed = {c["name"] for c in listing["collections"]}
check(
    {"toy", "lin", "dense"} <= listed,
    "list_collections sees dense and sparse families alike",
    f"listed {sorted(listed)}",
)

# --------------------------------------------------------------------------
# Input validation, and the one tool with nothing behind it.
# --------------------------------------------------------------------------
print("\n--- validation ---")
for label, fn in [
    ("mismatched row_ids", lambda: T.upsert_sparse("toy", rows[:2], row_ids=[900])),
    ("bad sparse_query", lambda: T.trellis_template_search("toy", {"indices": [1]})),
    ("empty query_ids", lambda: T.build_oracle("toy", query_ids=[])),
    ("oracle filename with a path", lambda: T.build_oracle("toy", [0], filename="a/b")),
    ("empty dense batch", lambda: T.upsert_dense("dense", [])),
]:
    try:
        fn()
        check(False, f"{label} rejected", "it was accepted")
    except ValueError as exc:
        check(True, f"{label} rejected ({str(exc)[:60]})")

# describe_rpc now reports the RPC's authoritative status (all live on this
# wheel) and defers the field shape to the proto; a KNOWN name
# returns, an UNKNOWN name is refused. The three search RPCs carry the
# canonical-vs-wrapper note so no one calls the reinstatement map's stale
# "Class C dead" label a live RPC.
described = T.describe_rpc("MeasureRecall")
check(
    described.get("status") == "live" and "ultradim.proto" in described.get("field_shape", ""),
    "describe_rpc reports live status and defers field shape to the proto",
    json.dumps(described)[:160],
)
desc_search = T.describe_rpc("UltradimV23Search")
check(
    desc_search.get("status") == "live" and "stale" in desc_search.get("note", "").lower(),
    "describe_rpc marks UltradimV23Search live, not the reinstatement map's dead",
    json.dumps(desc_search)[:160],
)
try:
    T.describe_rpc("NoSuchArmAtAll")
    check(False, "describe_rpc refuses an unknown RPC", "it returned")
except mod.RetiredRpc as exc:
    check("no such RPC" in str(exc), "describe_rpc refuses an unknown RPC", str(exc)[:120])

# list_rpcs is now authoritative: each entry carries a status, and the
# canonical search RPC is named among the three that answer the same question.
lr = T.list_rpcs(contains="TrellisTemplateSearch")
tmpl = next((r for r in lr["rpcs"] if r["name"] == "UltradimV23TrellisTemplateSearch"), None)
check(
    tmpl is not None and tmpl["status"] == "live" and "canonical" in tmpl["note"].lower(),
    "list_rpcs marks the canonical template search RPC live",
    json.dumps(lr)[:200],
)

# --------------------------------------------------------------------------
# drop_collection is destructive, so it goes last and its effect is verified.
# --------------------------------------------------------------------------
print("\n--- drop ---")
dropped = T.drop_collection("dense")
show("drop_collection", dropped)
check(dropped.get("success") is True and dropped.get("meta_dropped") is True,
      "drop_collection removes the family", json.dumps(dropped)[:200])
after = {c["name"] for c in T.list_collections()["collections"]}
check("dense" not in after, "dropped family is gone from the listing", f"still {sorted(after)}")

# --------------------------------------------------------------------------
# The wheel must not have moved underneath the run.
# --------------------------------------------------------------------------
_, sha_at_end = module_sha()
check(
    sha_at_end == SHA_AT_START,
    "wheel unchanged for the whole run",
    f"started {SHA_AT_START[:16]}, ended {sha_at_end[:16]} — re-run against the new wheel",
)

print()
if FAILURES:
    # Leave the store behind: a failure is worth inspecting.
    print(f"FAILED — {len(FAILURES)} check(s), store kept at {STORAGE}:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)

if not KEEP_STORAGE:
    shutil.rmtree(STORAGE, ignore_errors=True)
print(f"DONE — all checks passed against {MODULE_NAME} sha256={SHA_AT_START[:16]}")
