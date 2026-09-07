# Replacing and deleting a sparse row

**Short answer: yes, since 0.3.9.** Two operations do it, and neither is an
overload of upsert:

- **`ReplaceUltradimV23Point`** — change the vector held for a row you already
  know. MCP tool: `replace_sparse_point`.
- **`DeleteUltradimV23Point`** — retire a row for good. MCP tool:
  `delete_sparse_point`.

`UpsertUltradimV23Points` remains append-only and still refuses a row id it has
already committed. That is deliberate: a caller must be able to see which of
the two things they asked for, and an upsert that silently replaced would be
indistinguishable from one that appended.

> **Before 0.3.9** neither operation existed, and the rest of this document
> described the workarounds. They still work — appending versions is a good fit
> for a true history — but they are no longer the only option.

## The one thing that surprises people: row ids do not change in place

A replace **retires the old row and writes the replacement at a new row id**,
which comes back in the response. The old id is never reused and never becomes
live again.

What stays stable is **your own key** — the `content_key` facet. Logical
identity is stable; the physical row is versioned. So:

```
row 4   content_key "EURUSD"          <- replace(old_row_id=4, ...)
row 4   retired
row 12  content_key "EURUSD"          <- the response says new_row_id=12
```

and `GetUltradimV23RowByContentKey("EURUSD")` now returns **12**. You do not
have to track the id yourself, though the response gives it to you if you want
to.

The reason ids are immutable is the store: the sparse substrate is a CSR
(compressed sparse row) store with rows packed end to end. Rewriting row 4 with
a vector of a different length would mean moving everything after it. Retiring
and appending keeps every other row's id — and every index built over those
ids — untouched.

## Metadata: inherited wholesale, or replaced outright

There is no partial merge, on purpose. A partial merge is the option that looks
helpful and is not: you could not tell from the response which of your fields
survived.

| You send | What the replacement carries |
|---|---|
| **no `facets`** | the old row's metadata, wholesale. `ingest_ts` is re-stamped fresh; `event_ts` is inherited unless you supply one |
| **`facets`** | exactly what you sent, and nothing else. An **empty map clears** the metadata — which is why "omitted" and "empty" are different instructions |

Your `content_key` is protected either way:

- Omit it from a supplied map and **the old key is carried over**, so adding one
  unrelated facet cannot orphan the row from the key you know it by.
- Try to **change** it and the call is **refused** (`invalid_argument`). A
  replace targets one logical identity; changing the identity is a delete plus
  an insert, and should be asked for as two calls so neither is implicit.
- A row that had **no** key may gain one.

**Restriction.** This protection covers the literal facet name `content_key`.
`GetUltradimV23RowByContentKey` accepts a custom `facet_name`, but the replace
request has no equivalent, so a family that keeps its identity under a
different facet name gets no inheritance protection for it — supply that facet
explicitly on every replace, or use the conventional name.

## Retrying a replace is safe

If you never saw the response — a dropped connection, a client restart — send
the same replace again. It comes back:

```
success=false  already_replaced=true  new_row_id=<the current row>
```

rather than creating a second copy. The id is resolved through the retired
row's `content_key`, so after a chain of replaces you get the **newest live**
row for that key, which is the row you want.

Two cases where a retry cannot be resolved and you get a plain failure instead:
the retired row carried no `content_key` (nothing to resolve through), or the
row was **deleted** rather than replaced (no successor exists — the message
says so specifically).

## Delete

Retires a row so no search or lookup returns it. The row id is **not** freed and
the family's committed-row count does not go down: the row simply stops being
visible, which is what keeps every other id stable. There is no undelete.

Deleting an already-deleted row **succeeds** and reports
`was_already_deleted=true`. That is unlike replace, which refuses:
a repeated delete asks for the same end state, whereas a repeated replace asks
to version a row that no longer exists.

## When a replacement becomes searchable

It is durable and live in the store when the call returns, and
`GetUltradimV23RowByContentKey` finds it immediately — that read goes to the
payloads, not the index.

Whether the **cosine search** finds it depends on the window the family was
settled with. The settle buffers rows, so at the bulk default (10,000) a single
replacement waits for the window to fill. Meanwhile the retired row leaves the
results **at once**, because liveness is applied when candidates are taken
rather than when they are indexed — so for a moment a bulk-settled family
answers with neither version.

**If you are replacing live state and searching for it straight away, settle
with `window: 1`** (`make_searchable(window=1)`), record-by-record mode.
This is the settle's existing buffering behaviour, not something replace
introduces.

## Identity lookup returns the NEWEST live row

`GetUltradimV23RowByContentKey` returns the **newest live** row carrying the
key. Before 0.3.9 it returned the **oldest** match, which after one replace is
a row you can no longer use.

**This changed for dense families too**, not only sparse ones. The lookup is
substrate-agnostic, so a dense family with several rows sharing a key now gets
the newest rather than the oldest. If you relied on the old behaviour, put the
version in the key instead (see below).

The lookup is still exact-string and still non-authoritative: it routes a key
to a row id, it does not prove two rows hold the same content. Collisions are
yours to resolve.

## Still want append-only history? Keep it

Replace gives you one stable current-state row. It does **not** replace the
append-a-version pattern, and for a true history you want both:

- a **current-state family**, one row per entity, replaced as the state moves;
- a **history family**, append-only, every version retained for backtests,
  UMAP evolution and analogue search.

That is the shape the feature was built for. If you keep versions in one family
and want a specific one, put the version in the key (`instrument-42@v7`) or
make it a facet (`entity_id` keyword plus `version` int) and filter at
search time.

## What replace does not do

- **No compaction.** Retired rows keep their storage. The family grows with
  each replace, and there is no reclaim path today.
- **Sparse families only.** A dense family is refused, naming the scope.
- **Raw-decoder families are refused.** The request carries no
  `raw_decoder_values`, and writing the CSR row without the raw one would leave
  the raw store permanently short — a divergence the engine treats as
  unrecoverable.
- **Writers serialise per family.** Replace, delete and upsert take one lock per
  family, held across the whole write. Clients fanning out many parallel
  upserts to a single family will see a different latency profile than before;
  they were already racing an unsafe sequence, but the change is real.

## Durability

A successful response survives a process or host failure. Each operation
durably records its intent before it begins, and an interrupted replace **rolls
forward** on the next open: the retired row stays retired and the recorded
replacement is completed, keys and payload included. A crash mid-replace does
not silently degrade a valid current state into a delete.

**An ordinary write failure needs no restart either — from 0.3.10.** On 0.3.9
a tail failure left the family refusing writes until the process was restarted; upgrade if you use replace.

If the tail of a replace
fails outright — a full disk, an I/O error, rather than a crash — the operation
is rolled forward in process before the error is returned: the old row stays
retired, the replacement is completed with its keys and payload, and it is
streamed into the running search engine so it is findable, not merely stored.
The call still reports the error. Recovery repairs the family; it does not
pretend the write succeeded, and a retry resolves cleanly to the replacement.

If that repair cannot itself complete, the family is **taken out of service**
rather than left partly recovered: it refuses reads and writes, naming why,
until the next open runs full recovery. A degraded family that answers is worse
than one that says it cannot.

**From 0.3.11 the same applies to the last step of a write that succeeded.**
Once a replace or delete has landed, the engine drops its internal record of the
operation. If that drop fails, the write is still durable and correct — but the
leftover record would make every later replace and delete on the family fail, so
the family is taken out of service too. The error you get says the write
**succeeded**, names the row, and tells you **not** to retry: retrying an
operation that already happened is the one wrong move there. Reopening clears
it. On 0.3.10 this case left the family refusing lifecycle operations until a
restart.
