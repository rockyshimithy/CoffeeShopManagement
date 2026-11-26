# Research: M2 Inventory

Phase 0 decisions. Each entry states the decision, why it wins here, and what was rejected.
Where a claim rests on something in this repository or in the installed backend, the evidence
is named so it can be checked rather than believed.

Sources carried in from M1 and not repeated here: `specs/002-workforce-shifts/research.md`
R17 (never call `count()` inside a transaction) and R18 (a write conflict surfaces as
`DatabaseError` at the write, so `core.transactions.retry_on_conflict` is sufficient).

## R1. Quantities are decimals, never floats

**Decision**: `current_stock` and `last_count` are `DecimalField(max_digits=12, decimal_places=3)`.
`counted` and `quantity` on the event are the same. `Product.price` becomes
`DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)`.
`Product.low_stock_threshold` is `DecimalField(max_digits=12, decimal_places=3, null=True)`.

**Rationale**: Milk is measured in litres and coffee in kilograms, so a quantity is not an
integer. A float cannot hold `0.1` and summing floats drifts, which would make a count
disagree with the movements that produced it by a fraction nobody can explain. Three decimal
places covers a millilitre, and the spec forbids more (FR-008, FR-010). The backend stores
`DecimalField` as `Decimal128` and converts back on read: `adapt_decimalfield_value` and
`convert_decimalfield_value` in `django_mongodb_backend/operations.py`. No new dependency is
needed, `bson.Decimal128` already ships with the backend.

**Alternatives considered**: `IntegerField` in thousandths (exact, but every read and write
has to remember the scaling, and the API would return `12500` for twelve and a half litres);
`FloatField` (silently inexact, and the count-versus-movements comparison would eventually
fail); a string like today's `Product.price` (no comparison, no sum, no ordering).

## R2. The number moves with a targeted update, never a read then save

**Decision**: Every quantity change is one of two statements, and neither loads a value to
compute a new one in Python:

```python
# add, and the only legal way to raise a number without a count
Stock.objects.filter(pk=pk).update(
    current_stock=F("current_stock") + quantity, last_event_at=at
)

# subtract, with the non-negative guard inside the same match
updated = Stock.objects.filter(pk=pk, current_stock__gte=quantity).update(
    current_stock=F("current_stock") - quantity, last_event_at=at
)
if not updated:
    raise serializers.ValidationError({"quantity": [OVERDRAW]})
```

**Rationale**: This is invariant I4, and it is only true if the write is arithmetic on the
stored document rather than a number that travelled through Python. The backend compiles
`CombinedExpression` to `$add` and `$subtract` through `combine_expression` in
`django_mongodb_backend/operations.py`, so the update is a single document operation. The
guard for FR-009 rides in the match, which means losing the race cannot produce a negative
number: the match is re-evaluated against the committed value. `.update()` returns the number
of matched documents, which is also how the write path avoids `count()` (002 R17).

**Alternatives considered**: reading the row, computing in Python, and calling `save()` (this
is exactly what I4 forbids, and it loses concurrent writes); `select_for_update()` (a no-op on
this backend, per the constitution); a compare-and-set loop on a version field (correct, but
`F()` already gives the same guarantee with less code).

The row is still read once inside the transaction, for two validation rules that need stored
data: FR-014 compares the submitted instant with `last_count_at`, and the pool lookup needs
the existing row to decide between create and update. That read is never written back.

## R3. The unique index is the concurrent-create guard

**Decision**: `Stock` carries a unique index on `(product_id, pool_type, store_id)`. The write
path attempts a create when no row exists, and a duplicate key error is allowed to abort the
transaction, which makes `retry_on_conflict` replay it and take the update path.

**Rationale**: Two simultaneous first deliveries for the same item and pool both find no row
and both insert. Snapshot isolation permits that, which is the same write skew M1 hit
(002 R3). The unique index is the shared document in this case, and it costs nothing because
the index is needed for the read path anyway. A duplicate key error is a `DatabaseError`, so
the existing retry helper catches it with no change.

**Alternatives considered**: a per-pool revision counter like `ScheduleRevision` (a second
collection and a bump on every write, for a race that only exists on the very first write);
finding or creating inside a lock (`select_for_update` is a no-op here).

For the online pool, `store_id` is null. MongoDB treats null as a value in a unique index, so
one online row per product is enforced by the same index.

## R4. Stock carries `last_count_at`

**Decision**: `Stock` gains `last_count_at`, a nullable datetime, set whenever a count is
applied. The macro data shape in `docs/MACRO.md` lists `current_stock`, `last_count`, and
`last_event_at` only, so this is one field more than the macro draws.

**Rationale**: FR-014 refuses a movement that predates the newest count, and FR-019 has to say
what the movements predicted. Neither can be evaluated without knowing when the newest count
happened. The alternative is an indexed read of the newest COUNT event on every single write,
which is a second query on the hottest path for a field that costs eight bytes.

**Alternatives considered**: reading the newest count event each time (one extra indexed query
per write, and it still has to be done inside the transaction to be correct); trusting the
caller to send the baseline (FR-026 forbids taking a number from the request).

**Action required outside this feature**: `docs/MACRO.md` line 60 needs `last_count_at` added
to the `Stock` shape, with a dated note, the same way decision 20 was amended. The plan flags
it and does not assume it will be forgotten.

## R5. An event keeps the actor's name, and no foreign key

**Decision**: `StockEvent` stores `by_id` (ObjectId, required) and `by_name` (a string
snapshot of the actor's display name). There is no foreign key to `identity.User`.

**Rationale**: FR-029 says an event is never modified. A foreign key with `CASCADE` would
delete an account's events when that account is deleted, which silently rewrites
`current_stock` history and breaks FR-019. `SET_NULL` would write null into stored events,
which is also a modification. Neither is acceptable, so the reference is by value. The
snapshot also means FR-033 renders the actor without a join and keeps rendering after the
account is gone, which is what an audit trail is for. M1's `Shift` uses a cascade because a
rota is a plan, not a record; an event is a record.

**Alternatives considered**: `ForeignKey` with `CASCADE` (loses history, corrupts the
derivable discrepancy); `ForeignKey` with `SET_NULL` (modifies stored rows); a foreign key
with `PROTECT` (would make account deletion fail, contradicting M1 FR-025).

The display name is `"{first_name} {last_name}".strip()`, falling back to the email when both
are empty, which is the same rule `workforce.serializers.ShiftSerializer` already uses.

## R6. The discrepancy is derived from count events, not stored

**Decision**: No field stores the gap a count closes, and no event type expresses it. It is
computed by reading the two newest COUNT events of one stock record:

```text
predicted = previous_count.counted + sum(signed quantity of MOVEMENT events with
            previous_count.at < at <= newest_count.at)
discrepancy = predicted - newest_count.counted
```

For the first count of a record, the baseline is zero and the window starts at the row's
creation, so `predicted` is the sum of every movement before it.

**Rationale**: This is macro decision 25 and the spec's FR-016 to FR-019. The result is
``predicted - counted``, so a positive number is stock that went missing and a negative one is
stock that was recorded after it arrived. That sign matters for M3, where the waste report will
want a loss to read as a positive number. It also explains why
the events must never be deleted: they are the only record of what the number was before a
count replaced it. A stored gap would need the same derivation to be correct anyway, and would
then be a second source of truth.

**Alternatives considered**: a `SHRINKAGE` event type (macro decision 25 rejects it, and it
would double count, because the count already carries the absolute number); storing the
predicted number on the count event (a copy of a derived value that goes wrong as soon as one
event is backdated, which FR-014 already forbids).

## R7. One write function, two public entry points

**Decision**: `inventory.services.record(actor, ...)` is the only function that writes stock or
events. `record_movement(...)` and `record_count(...)` are thin public wrappers that validate
their own request shape and then call it. Nothing else in the project calls
`Stock.objects.update(...)` or `StockEvent.objects.create(...)`, and the admin cannot.

**Rationale**: Macro decision 19 and FR-024. Two entry points rather than one because a
movement and a count have disjoint shapes (FR-011): a movement needs a type and a positive
quantity, a count needs an absolute number and must carry neither. Merging them would give one
function two rule sets and one serializer two branches, which is more code, not less.

**Alternatives considered**: one endpoint and one function with a `kind` discriminator (branchy
validation, and the error map would have to explain which half failed); a Django signal on
save (a second write path that nobody can enumerate, which FR-027 forbids).

## R8. Pool visibility follows store reach, not a role list

**Decision**: `identity.permissions.reaches_every_store(actor)` returns True for ADMIN, and for
any actor whose `store_ids` equals every existing store id, which today is REGIONAL_MANAGER
through the M0 propagation rule. `require_stock_access(actor, store_id)` allows a branch pool
only through `require_store_access`, and allows the online pool only through
`reaches_every_store`. `stock_scope(queryset, actor)` includes `store_id__isnull=True` only for
those actors.

**Rationale**: The online pool has no store, so a `store_id__in` filter would hide it from
everyone, including ADMIN. Deleting that special case by hand-writing a role comparison in
`inventory` would violate SC-006 and the constitution. Making the check a helper keeps one
authorization path and answers the question the feature actually asks, which is "does this
actor see every store", not "is this actor an admin". ADMIN is still the only role that
bypasses the store filter, and it does so inside the helper.

**Alternatives considered**: a second `pool` allow-list per role (a second role matrix, and
zero answers to "which stores does this actor see"); giving the online pool a sentinel store
row (a fake store that every scope filter would have to know about).

## R9. Low stock is ordered in Python over a bounded set

**Decision**: `services.low_stock` loads the stock rows in scope, loads the thresholds of the
products that have one, keeps the rows strictly below their threshold, sorts by
`(threshold - current_stock)` descending, then slices the page.

**Rationale**: FR-043 orders by how far below the level a row sits, and the two numbers live in
different collections. A page cannot be re-sorted after pagination, so either the sort happens
before the page in the database (a `$lookup`, which means leaving the ORM for one endpoint) or
the page is taken after the sort in Python. The working set is the actor's stores times the
catalog size, which is a few thousand rows for this project. Macro decision 20 permits a join
when ordering needs a related field, and this is the one place where the Python sort is
cheaper than the join.

**Alternatives considered**: a `$lookup` aggregation (correct, and the escape hatch if the
working set grows, but it bypasses the ORM and needs its own serialization path); a stored
`is_low` flag (a third write path to maintain on every threshold edit and every movement);
ordering by `current_stock` only (not what FR-043 asks).

## R10. The stock list order is the unique index

**Decision**: `GET /api/stock/` orders by `product_id`, then `pool_type`, then `store_id`.

**Rationale**: That is exactly the unique index from R3, so the sort is served by the index and
nothing joins. Ordering by product name would read better and would need a join, which decision
20 allows only when a page cannot otherwise be ordered; here it can. The name arrives anyway in
the batched enrichment that fills `product_name` and `unit`.

**Alternatives considered**: ordering by name (`$lookup` plus a `$sort` outside the index, for a
cosmetic gain); ordering by `last_event_at` (useful later, and not what FR-032 asks).

## R11. Catalog changes, and one bug that blocks them

**Decision**: `catalog` changes in four ways:

1. `price` becomes `DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)`.
2. `unit` is added as `CharField(max_length=8, default="pcs")`.
3. `low_stock_threshold` is added as `DecimalField(max_digits=12, decimal_places=3, null=True)`.
4. `catalog/urls.py` changes `products/<int:pk>/` to `products/<str:pk>/`.

**Rationale**: The first three are `specs/001-foundation/research.md` D10, which deferred them
to M2, plus FR-039. FR-031 returns the unit label, so the field has to exist, and decision 14
keeps it a label. The fourth is a real defect: every primary key in this project is an
ObjectId, and an `<int:pk>` converter cannot match a 24 character hex string, so
`ProductDetail` is unreachable. The consequences are concrete: FR-040 cannot be implemented
without it, and today a product can be created but never read, edited, or deleted by id. The
converter alone is not enough, because the generic view would then try to coerce a hex string
into an ObjectId pk itself, so the detail view loads through
`core.shortcuts.object_id_or_404`, which is the pattern `workforce.views.ShiftDetail` uses.

**Alternatives considered**: leaving the route and adding a separate threshold route (two
routes to work around one bug); `<uuid:pk>` (wrong type entirely).

`Product.sellable` is deliberately not added. The macro data shape lists it, and no M2
requirement reads it. It arrives with M4, when the storefront has to hide milk. Adding it now
would be a field that no code reads, which the Ponytail principle forbids.

## R12. Catalog writes become ADMIN and REGIONAL_MANAGER only

**Decision**: `identity.permissions` gains `product.read` (every role) and `product.change`
(ADMIN and REGIONAL_MANAGER). `catalog.views` checks `require_action` on create, update, and
delete.

**Rationale**: The low stock level arrives on the same `PATCH` as the price and the name, so
guarding one field and not the others would be a guard that leaks. Product data is global, so
no store rule applies (001 FR-022), which leaves the role as the only control. A regional
manager already owns store setup and naming (macro decision 28), so owning what those stores
stock is the same authority one level up. This still tightens today's behaviour: right now
every signed-in account, including a BARISTA, can create and edit products, because
`ProductList` and `ProductDetail` declare no permission check beyond the global
`IsAuthenticated`. The Kyaor chose ADMIN plus REGIONAL_MANAGER on 2026-11-26, which is why
FR-040 was amended from ADMIN alone.

**Alternatives considered**: ADMIN only (the plan's first proposal, rejected by the Kyaor:
the region buys the stock, so it sets the levels); a separate threshold route guarded by its
own permission (one more route, and the leak above stays for price); MANAGER allowed to edit
the catalog (defensible for one store, and it would let a store change a global price).

## R13. The write path never calls `count()`

**Decision**: Inside `atomic()`, the write path uses `.first()`, `.exists()`, `.update()` and
its returned row count. `QuerySet.count()` does not appear anywhere in a transaction.

**Rationale**: 002 R17 established that `count()` compiles to a pipeline with `$unionWith`,
which MongoDB refuses inside a multi-document transaction. This feature writes on every
delivery, so it would be the first place to hit it. The guards in R2 and R3 both read a row
count that `.update()` already returns.

**Alternatives considered**: counting outside the transaction (the count would predate the
concurrent write, which is the whole problem).

## R14. The admin is read only for stock

**Decision**: `inventory/admin.py` registers both models with `has_add_permission`,
`has_change_permission`, and `has_delete_permission` returning False, and every field in
`get_readonly_fields`, which is the guard `workforce/admin.py` already applies to `Shift`.

**Rationale**: FR-027 says no other write path may exist, including the admin. A `ModelAdmin`
that allows `save_model` is a second path that bypasses the transaction and the event insert,
so it would let the number and the events disagree.

**Alternatives considered**: not registering the models at all (the admin then looks empty and
an operator assumes the data is missing); an admin that calls the service (more code than
switching it off, for a screen nobody asked for).

## R15. Two write routes, three read routes

**Decision**:

| Route | Method | Purpose |
|---|---|---|
| `/api/stock/` | GET | Stock list, filterable by store, pool, product, low |
| `/api/stock/low/` | GET | Low stock, ordered by shortage |
| `/api/stock/{id}/events/` | GET | One record's history, newest first |
| `/api/stock/movements/` | POST | Record a delivery, a sale, or waste |
| `/api/stock/counts/` | POST | Record a count |

**Rationale**: The two writes are separate because their rules are disjoint (R7). The writes
are top level rather than nested under a record id because the first delivery to a pool has no
record yet, so a nested route would force the client to create an empty record first. The low
stock list is its own route because its ordering and its pagination are computed differently
from the plain list; folding it in as `?low=true` would put two paginators behind one URL.

**Alternatives considered**: one `POST /api/stock/events/` with a kind discriminator (R7);
`?low=true` on the list (two orderings and two paginators on one route); a route per movement
type (three routes that differ by one field).

## R16. Test strategy, including the honest limit of SC-004

**Decision**: Six test files. Isolation (SC-001) uses one item held in three pools and asserts
that each operation moves exactly one. Counts use a movement history, then a count, then a
derived discrepancy, in the account deletion sense of "derive it again from events only".
Scope (SC-005) uses two stores and asserts exactly zero foreign rows in a list and a 403 with
no field leaked. Low stock covers equality, missing level, and ordering. Concurrency uses
`@pytest.mark.django_db(transaction=True)`, which 002 established is required for a second
thread's connection to see what the test thread created.

**Rationale**: Every success criterion in the spec maps to a test, and the two invariants (I2,
I4) get direct tests rather than being assumed from the code shape.

**The concurrency criterion**: SC-004 states two things, and only one of them needs a number.
At ten concurrent deliveries, every request must succeed and the row must end at exactly 10
with exactly 10 events. At a higher level, the row must equal the number of requests the API
accepted, and the event count must equal that same number, so a refused write changes nothing
and no accepted write is lost. The test prints that accepted count.

Ten was chosen from the domain, not from a round number: a store has a handful of devices
writing stock. The measurement runs at a higher level, so the printed ceiling comes from this
machine. Three attempts per write mean a high enough level will always refuse some requests,
which is why the criterion promises no lost update rather than universal success. A refused
write answers 409, so the test can count refusals as outcomes instead of treating them as
crashes. An earlier draft of the spec asked for one hundred simultaneous writes; that number
had no basis, and the Kyaor replaced it on 2026-11-26.

**Alternatives considered**: asserting a hundred threads all succeed (needs unbounded retries
or a queue, and is unprovable in principle with finite attempts); asserting only the
no-lost-update equation (a service that refused every write would pass).

## R19. Three retries carry three writers, and the measurement says why

**Decision**: The stock write path uses the shared default of 3 attempts. The shared helper in
`core.transactions` waits a random, exponentially growing pause between attempts. SC-004 states
three concurrent writers, not ten.

**Rationale**: Measured on this machine, not reasoned about. MongoDB aborts every writer but one
per document per attempt, so N simultaneous writers need roughly N rounds. Attempts are the
number of rounds, which is why the attempt count is the binding constraint and the pause is not:

| Attempts | Spacing | Ten simultaneous writers |
|---|---|---|
| 3 | immediate | 5 of 10, three runs in a row |
| 3 | linear jitter | 5 of 10 |
| 3 | exponential jitter, 50 ms base | 0 of 3 runs passed |
| 3 | exponential jitter, 100 ms base | 1 of 3 runs passed |
| 4 | exponential jitter | 2 of 3 runs passed |
| 5 | exponential jitter | 5 of 6 runs passed |
| 8 | linear jitter | 10 of 10, repeatedly |

Widening the pause does not substitute for another round, which is why "3 attempts with a longer
sleep" cannot promise ten. Eight attempts bought the promise, and five bought it with a flake.

The Kyaor's objection was that more than three retries is too many, and the evidence agrees:
eight retries is not a property of the domain, it is the price of a promise nobody needed. A
store has a few devices writing one item, not ten. So the criterion moved to the number that is
both defensible from the domain and deterministic in the suite: three writers, three attempts,
6 of 6 runs green. The no-lost-update half of SC-004 still runs at twenty writers, where a
refused write is an expected outcome rather than a failure.

**If ten is wanted later**: set `STOCK_ATTEMPTS = 8` in `inventory/services.py` and restore the
ten in SC-004. Nothing else changes.

**The second layer is the client, not a bigger cap**: the 409 carries `Retry-After: 1`, so a
client that reads the contract supplies the rounds past the third one. That buys availability at
the only place it is still cheap: the server refuses in about 15 ms instead of holding a
connection through eight rounds. The boundary matters, and it is written into the contract: a
client may resend on a 409, because that status states nothing was applied, but never on a
timeout or a dropped connection, because a movement POST is not idempotent and a blind resend
would count the same delivery twice. An idempotency key is the way to make the timeout case safe
too, and it is deliberately not built: nothing on this side retries yet.

`core.transactions.retry_on_conflict` is shared with `workforce` and `stores`. The change only
delays a retry; it changes no semantics, and the M1 suite still passes.

**Alternatives considered**: `ATTEMPTS = 8` (worked, and the Kyaor rejected the cost);
`ATTEMPTS = 5` (worked 5 runs in 6, so it flakes); a queue that serializes writers (real
machinery for a 409 the contract already reports cleanly); sharded counters or deriving the
number from the event log (both remove the contended document, and both break the one atomically
updated number per product per pool that decision 18 chose); a lock document (same contention,
one round trip further out, plus a lease that can be orphaned); the driver's own transaction retry
(not reachable: `django_mongodb_backend.transaction.atomic()` starts and commits the transaction
directly on the connection and never calls `with_transaction`, so there is no
`TransientTransactionError` loop to borrow).

## R20. The database needs its documented file descriptor limit

**Decision**: `docker-compose.yml` sets `ulimits.nofile` to 64000 soft and hard on the `mongo`
service.

**Rationale**: The container inherited a soft limit of 1024, which is MongoDB's own threshold
for a startup warning and far below its documented recommendation of 64000. With the soft limit
at 1024, a 40-thread concurrency run exhausted descriptors and mongod died:
`WiredTiger __posix_directory_sync ... Too many open files`, then `WT_PANIC`, then a segfault
with exit code 139. The hard limit was already 524288, so only the soft value was wrong, which
is exactly the failure mode the MongoDB documentation warns about. Descriptor cost per the same
page: two per incoming connection, one per data file, one per journal file.

Soft and hard are set equal so nothing can raise the soft limit behind our back, which is what
the documentation recommends.

**Alternatives considered**: leaving the limit and shrinking the test (the cap stays wrong and
the next heavier test crashes the container again); `ulimit -n unlimited` (not accepted for this
resource on all kernels, and it removes the ceiling that stops a descriptor leak from starving
the host).

**Source**: https://www.mongodb.com/docs/manual/reference/ulimit/
