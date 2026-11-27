# Research: M3 Inventory Insight

Phase 0 decisions. Each entry states the decision, why it wins here, and what was rejected.
Where a claim rests on something in this repository or in the installed backend, the evidence
is named so it can be checked rather than believed.

Sources carried in and not repeated here: `specs/003-inventory-stock/research.md` R1 (decimals,
never floats), R5 (the actor name is a snapshot with no foreign key), R8 (pool visibility
follows store reach), R19 (retry budget), and `specs/002-workforce-shifts/research.md` R17
(never call `count()` inside a transaction).

## R1. The report is one indexed range read plus one aggregation

**Decision**: the waste report is one queryset filtered by pool scope, kind, type, and the
inclusive instant range, ordered newest first, paginated with the shared page size. The per
item totals are one aggregation over the same filtered queryset, unsliced.

**Rationale**: the two requirements pull in different directions. FR-009 paginates the event
list and says the totals cover the whole range, so the totals cannot be computed from a page.
Both read the same collection with the same filter, which is the only place the two numbers
can drift apart, so the plan builds the filter once and uses it twice. The events are indexed
on `(store_id, at)` and `(product_id, at)`, which serve the range and the store or item
filter.

**Alternatives considered**: computing totals from the fetched page (wrong by construction,
because page 2 would report the totals of page 2); a stored total on the stock row (rejected
by the spec's Assumptions and by I4, which forbids a second write path).

## R2. The totals are one ORM aggregation, not a Python grouping

**Decision**:

```python
queryset.values("product_id").annotate(
    total=Sum("quantity"),
    events=Count("id"),
).order_by("-total", "product_id")
```

**Rationale**: one `$group` returns one row per item instead of one document per event, which
is what keeps a 10,000 event range inside the one second bound of SC-008. The backend compiles
`Sum` and `Count` in `django_mongodb_backend/aggregates.py` (`MONGO_AGGREGATIONS` maps `Count`
to `sum`, and the aggregation pipeline is built in `query.py`). `convert_decimalfield_value`
in `operations.py` turns the `Decimal128` result back into `decimal.Decimal`, so the sum is
exact. This is a code path that is verified in the backend source; the first implementation
test proves it with a `Decimal` equality assertion (`2.5 + 0.25` reads `2.75`).

**Alternatives considered**: a Python loop over `.values_list("product_id", "quantity")`
(correct and exact, but it moves every matching event across the wire on every page request
and its memory grows with the range, and the spec accepts a ten year window); a stored total
(see R1); a raw `$facet` pipeline (one query for both blocks, but it leaves the ORM for one
endpoint and buys no accuracy over R3).

**Fallback**: if the aggregate returns a type other than `Decimal`, the same response shape
can be served by the Python grouping, contained to one service function. The test in R2 is
what decides.

## R3. The grand total is the sum of the per item totals

**Decision**: `grand_total = sum(row["total"] for row in totals)`, computed in Python before
serialization.

**Rationale**: SC-002 compares the per item totals, the listed quantities, and the grand total,
and demands a difference of exactly zero. Summing the totals in hand makes that true by
construction rather than by testing. A second aggregate would be a second calculation, and two
reads are not one snapshot, so it could disagree with the block it sits beside. The sum is over
a small list, and every value is already a `Decimal`.

**Alternatives considered**: a second `aggregate(Sum("quantity"))` (one more query and one more
place for the same arithmetic); letting the client sum (FR-008 requires the field, and a client
that sums the current page gets a wrong number with no warning).

## R4. Both reads order by instant then id, and that forces a blocking sort

**Decision**: `order_by("-at", "-id")` on both reads.

**Rationale**: FR-017 and FR-018 require a stable order, including two events recorded at the
same instant, and SC-005 requires two reads to agree. The tiebreak makes the order total. M2's
per record history already uses the same pair, so the two views of the same events agree.

The cost is real and is recorded under Known limitations in `plan.md`: an index satisfies a
sort only when it provides the whole key, and `(store_id, at)` does not provide `_id` order
within an equal instant. MongoDB therefore sorts every matching document before returning the
first page. At the 10,000 event scale of SC-008 that is milliseconds, and it is the price of a
stable order.

**Alternatives considered**: ordering by `at` alone and relying on the index's internal order
for ties (not guaranteed by MongoDB, and it can change after a compaction, so SC-005 would be
a hope); a covering index including `_id` (rejected in R10 as unmeasured cost on the write
path).

## R5. The scope rule is the stock list's, reused

**Decision**: `event_scope` calls `stock_scope(StockEvent.objects.all(), actor, store_id)`,
then applies the item filter and the order. `stock_scope` is unchanged.

**Rationale**: FR-019 says both reads are filtered by the actor's store assignments plus the
online pool only for a role that reaches every store, and the spec's Assumptions say this is
the same rule the stock list already applies. `StockEvent` carries the same `store_id` field
that `stock_scope` filters on, so the helper works without modification. A second scope
expression in this module would be the exact drift I1 exists to prevent.

Two consequences follow and are deliberate:

- A store manager never sees the online pool, on either read. They also cannot record into it,
  because `require_stock_access` allows the online pool only for an actor who reaches every
  store. Read and write access agree.
- Naming a store excludes the online pool for every role, including ADMIN, because a named
  store is a single `store_id` filter.

**Alternatives considered**: a second filter written in `inventory` (drifts from the stock
list); a role comparison for the online pool (forbidden by SC-006, which scans for
`User.Role` outside the permission helper).

## R6. Filters validate the shape of an id, not its existence

**Decision**: a malformed `store` or `product` is a 400. A well formed id that matches nothing
is an empty result. A store outside the actor's assignments is a 403, raised by
`scope_store_ids` through `stock_scope`.

**Rationale**: FR-028 says an item filter naming an item with no events answers an empty
result, not an error, and a value that is not a valid identifier is refused as invalid. Those
are two different questions. Checking existence would also be a join the read does not need,
and it would leak whether an id exists. The store case is different because the scope rule
must refuse, not silently narrow, which is what FR-021 and FR-027 require.

**Alternatives considered**: a 404 for an unknown product (contradicts FR-028); silently
ignoring a foreign store (contradicts FR-021, and it hides a client bug).

## R7. Both date bounds are required, inclusive, and parsed by the client's instants

**Decision**: `start` and `end` are required `DateTimeField` values. The filter is
`at__gte=start, at__lte=end`. A missing bound, a malformed bound, or `start > end` is a 400.
`start == end` is legal. The server performs no day arithmetic.

**Rationale**: the spec's Assumptions chose this shape so the server never answers a window the
manager did not ask for. It also keeps time zone logic out of the backend: the project has
`TIME_ZONE = "UTC"` and `USE_TZ = True`, and the client sends the first and last instant of the
day it means. Inclusive at both ends is exact at MongoDB's millisecond resolution, so adjacent
days neither overlap nor leave a gap when the client sends `23:59:59.999` rather than the next
midnight. The contract states that rule once.

`start > end` is reported on `end`, with `"The end must not be earlier than the start."`, so the
field map names the value that is wrong.

**Alternatives considered**: a default window when a bound is missing (hides old waste, and
"no results" becomes ambiguous); a half open `[start, end)` window (the common API convention,
but it changes FR-002 and acceptance scenario 5, and the client is already computing the day
bounds); server side day arithmetic (a time zone rule per client, which the spec avoided).

## R8. The feed is a standard paged list

**Decision**: `generics.ListAPIView` over `event_scope`, ordered `-at`, `-id`, paginated with
`StandardPagination`. The envelope is the project's usual
`{"count", "next", "previous", "results"}`. `page_size` defaults to 20 and is capped at 100.

**Rationale**: the spec was amended on 2026-11-27: the feed is paged, because a manager must
reach past changes. Page 1 is still the newest 20, so the MACRO exit criterion still describes
what the manager sees first. The shared pager already provides the envelope, the page
validation, and the maximum, so no paging code is new.

Offset paging drifts: a change recorded between two page loads can shift one entry across a
page boundary. That is accepted and stated in the spec's edge cases. The order never changes,
and reloading from page 1 shows the current window. The escape hatch, if deep pages ever
matter, is keyset paging by `(at, id)` with the response shape unchanged.

**Alternatives considered**: a fixed 20 with no pages (the original spec, reversed by the
Kyaor on 2026-11-27 because the past became unreachable); a `limit` parameter (a bigger window,
not paging, and it still stops at the maximum).

## R9. Names are resolved in two batches per page

**Decision**: `enrich_events(events, more_product_ids=())` returns
`{"labels": product_labels(...), "store_names": store_names(...)}`. The report passes the
totals' product ids as `more_product_ids`, so one batch covers the page rows and the totals
table.

**Rationale**: `prefetch_related()` is unsupported on this backend, so the manual batch after
pagination is the rule. `product_labels` returns `(name, unit)` per id and `store_names`
returns a name per id; both already skip `None` and return `{}` for an empty batch, which is
what an online row needs.

The existing `enrich` was rejected even though `StockEvent` happens to carry `product_id` and
`store_id`: it also fetches low stock thresholds, which neither read uses, and its docstring
describes stock rows. Reusing it would add a query and would work by coincidence of attribute
names rather than by design.

**Alternatives considered**: a per row lookup (N+1, the thing the batch rule exists to
prevent); copying names onto the event (I3 forbids it, and the actor name is the one deliberate
exception because the account can disappear).

## R10. No new index and no migration

**Decision**: the three existing `StockEvent` indexes stay as they are. M3 changes no model, so
it adds no migration.

**Rationale**: SC-008 bounds the hard case at 10,000 events in one store over 30 days, and a
blocking sort of 10,000 small documents is far inside one second. An index is not free: every
insert maintains it, and M3 must not change the cost of the write path. The spec explicitly
allows one index later if a measured read needs it, so the reopening condition is concrete.

Three costs are written into `plan.md` as known limitations: the tiebreak forces a blocking
sort (R4); the feed re-sorts on every page and its cost grows with the store's history; and a
scope wide feed over roughly 100,000 events risks MongoDB's 32MB blocking sort limit. The
escape hatches, in order, are an index on `(at)` for the scope wide feed, a covering
`(store_id, at, id)` index, or keyset paging.

**Alternatives considered**: an `(at)` index (helps only the scope wide feed, and no
measurement asks for it); covering sort indexes (two more indexes on an append only
collection, and whether the backend emits a compound index that includes `_id` is unverified).

## R11. Every read view checks `stock.read`, then scope

**Decision**: `require_action(actor, "stock.read")` is added to all five read views:
`StockList`, `StockLow`, `StockEventList`, `WasteReport`, `ActivityFeed`. The order is
parameters (400), role (403), scope (403).

**Rationale**: `stock.read` was declared in `ACTIONS` and `ROLE_ACTIONS` and consulted by
nothing. Leaving it that way would keep two authorization stories in one module: writes go
through the action table, reads through scope. Adding the call to all five makes one rule, and
FR-023 ("every role that may read one record's history may read both reports, with no new role
decision") becomes structural rather than true by inspection.

The call changes no current behaviour: all five roles hold `stock.read`. It costs five lines,
no query, and its only effect today is that a future edit to the table takes effect
immediately. A test patches `ROLE_ACTIONS["stock.read"]` to an empty set and asserts a 403, so
the call cannot be silently removed later.

**Alternatives considered**: no call, matching the read path as it was (leaves the declared
action dead and a future role ungated); a call in the two new views only (two policies in one
module); removing `stock.read` from the table (deletes a model M2 added, and removes the hook a
future role such as `CUSTOMER` would need).

## R12. `derived_discrepancy` is not called, and a guard says so

**Decision**: no M3 read calls `derived_discrepancy`. A source scan test asserts the name
appears only in `services.py` and in tests, and a second assertion proves the function still
exists so the scan cannot pass vacuously.

**Rationale**: decision 1 keeps the report waste only, so count discrepancies stay out. The
function also cannot answer a range question even if the report wanted it: it reads the two
newest counts of one stock row with no window, and a gap belongs to an interval between counts
while both M3 reads filter instants. It stays in `services.py`, still covered by M2's tests, as
the basis for a future loss report that would need its own window rule.

The guard is the same idea as `tests/test_single_write_path.py`, which turns SC-003 and SC-006
into searchable facts. The obvious next request is "just add a gap column to the report", and
with the guard that request fails a named test instead of quietly changing what "total wasted"
means.

**Alternatives considered**: recording it in the docs only (the checklist asked for the plan to
say so, but a future commit can still wire it in); deleting the function (breaks four M2
assertions and removes a delivered derivation).
