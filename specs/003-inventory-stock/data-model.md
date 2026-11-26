# Data Model: M2 Inventory

Two new collections, plus three changes to the catalog. `Stock` holds one number per item per
pool. `StockEvent` holds every change, one document per change, and is never modified.

Everything reuses the engine rules already in force: `ObjectIdAutoField` primary keys,
references held as ObjectIds, no `prefetch_related`, and writes inside
`django_mongodb_backend.transaction.atomic`.

## Stock, collection `inventory_stock`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key, `ObjectIdAutoField` |
| `product` | reference to `catalog.Product` | Required. Cascade on product delete. No name, price, or unit is copied here (I3). |
| `pool_type` | string, choices `BRANCH` and `ONLINE` | Required. |
| `store` | reference to `stores.Store` | Null allowed. Required when `pool_type` is `BRANCH`, and must be null when `ONLINE` (FR-002). Cascade on store delete. |
| `current_stock` | decimal, 12 digits, 3 places | Default `0`. Never negative (FR-009). |
| `last_count` | decimal, 12 digits, 3 places | Default `0`. The number observed at the newest count (FR-004). |
| `last_count_at` | datetime, null | Set when a count is applied. Null until the first count. Read by FR-014. |
| `last_event_at` | datetime, null | The instant of the newest event of any kind (FR-004). |

No `version` field, no `is_low` field, no `updated_at`. The three numbers and two instants are
exactly what the requirements read, and nothing else.

`last_count_at` is one field more than `docs/MACRO.md` draws for `Stock`. `research.md` R4
explains why it cannot be derived cheaply, and the macro needs a dated amendment to match.

### Indexes

| Index | Kind | Serves |
|---|---|---|
| `(product_id, pool_type, store_id)` | unique | One row per item per pool (FR-003), the concurrent-create guard (R3), and the list order (FR-032, R10). |
| `(store_id, pool_type)` | plain | The scoped list and the low stock scan, which filter on store and pool. |

The unique index does double duty as the ordering index, because the list orders by the same
three fields in the same order.

## StockEvent, collection `inventory_stockevent`

| Field | Type | Rules |
|---|---|---|
| `_id` | ObjectId | Primary key |
| `stock` | reference to `inventory.Stock` | Required. Cascade on stock delete, which is how a store delete reaches events. |
| `product_id` | ObjectId | Required. Copy of the stock row's product, because M3 reads events across items and cannot afford a join (macro decision 18). |
| `pool_type` | string, `BRANCH` or `ONLINE` | Required. |
| `store_id` | ObjectId, null | Null exactly when the pool is `ONLINE`. |
| `kind` | string, `MOVEMENT` or `COUNT` | Required (FR-006). |
| `type` | string, `RECEIVED`, `SOLD`, or `WASTE`, null | Required when `kind` is `MOVEMENT`, must be null when `kind` is `COUNT` (FR-011). |
| `quantity` | decimal, 12 digits, 3 places, null | Required and greater than zero when `kind` is `MOVEMENT`, must be null when `COUNT` (FR-008, FR-011). Always positive. |
| `counted` | decimal, 12 digits, 3 places, null | Required and zero or greater when `kind` is `COUNT`, must be null when `MOVEMENT` (FR-010, FR-011). |
| `by_id` | ObjectId | Required. The actor (FR-015). |
| `by_name` | string, 120 | Required. Display name snapshot taken at write time (R5). |
| `at` | datetime | Required. Defaults to now. Not in the future, and not earlier than the stock row's `last_count_at` (FR-014). |
| `note` | string, 200, blank | Required and non-blank for `WASTE` (FR-012). Optional otherwise. |

No `sign` field, no `predicted`, no `discrepancy`, no `SHRINKAGE` type. The gap a count closes
is derived (R6), and a signed quantity would contradict macro decision 25.

### Indexes

| Index | Serves |
|---|---|
| `(stock_id, at)` | One record's history, newest first (FR-033), and the discrepancy derivation (FR-019). Required by the constitution. |
| `(product_id, at)` | M3's cross-item reports. Required by the constitution now, while the collection is empty. |
| `(store_id, at)` | M3's per-store waste report. Required by the constitution now. |

All three are declared in `Meta.indexes` in this feature even though M3 reads two of them. The
constitution names them, and adding an index to a collection that already has rows is a
different, slower operation than declaring it while the collection is empty.

## Product, collection `catalog_product` (changed)

| Field | Now | Becomes |
|---|---|---|
| `name` | `CharField(max_length=40)` | unchanged |
| `description` | `CharField(max_length=100)` | unchanged |
| `price` | `CharField(max_length=10)` | `DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)` |
| `unit` | absent | `CharField(max_length=8, default="pcs")`, a display label only (macro decision 14) |
| `low_stock_threshold` | absent | `DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)` |

`sellable` is not added. Nothing in M2 reads it, and it arrives with M4.

The database holds zero product rows, so the two type changes need no data migration step.
The migration is `0002_item_shape.py`, following `0001_initial` which stays untouched.

### Validation rules

| Rule | Requirement | Where |
|---|---|---|
| Pool and store agree: `BRANCH` needs a store, `ONLINE` forbids one | FR-002, FR-021 | `validators.validate_pool` |
| A request names one pool, never two | FR-020, FR-021 | The request shape itself: one `pool`, one optional `store` |
| Movement quantity finite, greater than zero, at most 3 places | FR-008 | `validators.validate_quantity` |
| Counted number finite, zero or greater, at most 3 places | FR-010 | `validators.validate_quantity`, with `allow_zero=True` |
| A `COUNT` carries no type and no quantity; a movement carries no counted number | FR-011 | The two request serializers |
| `SOLD` refused on a branch pool while no point of sale exists | FR-013 | `validators.validate_pool_and_type`, one rule, nothing structural (spec assumptions) |
| `WASTE` needs a non-blank note | FR-012 | `validators.validate_note` |
| The instant is not in the future and not before `last_count_at` | FR-014 | `services.record`, inside the transaction, reading the stored row |
| The product exists | FR-045 | `catalog.services.product_exists`, inside the transaction |
| The store exists | FR-045 | `stores.services.store_exists`, unchanged from M1 |
| A subtraction may not cross zero | FR-009 | The `current_stock__gte=quantity` match on the update (R2) |

A validation failure is a 400 with a field map. The transaction aborts, so no number moves and
no event is stored.

## Write path

One function, `inventory.services.record`, called by `record_movement` and `record_count`.
Both wrappers validate their own request shape first, outside the transaction, because a shape
error does not need a transaction.

```text
retry_on_conflict(operation)
  operation:
    with atomic():
      require_action(actor, "stock.record")                       # 403 on the role
      require_stock_access(actor, store_id or None)               # 403 outside access / online
      product_exists(product_id)                                  # 400 when missing
      store_exists(store_id) when the pool is a branch pool        # 400 when missing
      row = Stock.objects.filter(product, pool_type, store).first()
      if row is None:
          row = Stock.objects.create(...)                         # duplicate key -> retry
      stock_pk = row.pk
      validate_instants(at, row.last_count_at)                    # 400 when older or future
      if kind is MOVEMENT and the type subtracts:
          updated = Stock.objects.filter(
              pk=stock_pk, current_stock__gte=quantity
          ).update(current_stock=F("current_stock") - quantity, last_event_at=at)
          if not updated: raise ValidationError(overdraw)          # 400, FR-009
      elif kind is MOVEMENT:
          Stock.objects.filter(pk=stock_pk).update(
              current_stock=F("current_stock") + quantity, last_event_at=at)
      else:
          Stock.objects.filter(pk=stock_pk).update(
              current_stock=counted, last_count=counted,
              last_count_at=at, last_event_at=at)                 # absolute, not a read value
      event = StockEvent.objects.create(...)
      return event
```

Three properties this path has to keep, and the test that proves each:

1. The number and the event commit together, or neither does (FR-024). The single transaction
   is the whole mechanism.
2. The number is never computed in Python from a value read earlier (I4). The arithmetic is in
   the update. The only value written from a read is nothing at all.
3. Two concurrent writers cannot lose an update (FR-028). Either MongoDB serializes them, or
   one raises a write conflict, the transaction aborts, and `retry_on_conflict` replays it
   against the committed number.

`Stock.objects.create` inside the transaction is the one place a duplicate key error is an
expected outcome rather than a bug. It is a `DatabaseError`, so the retry helper catches it and
the replay finds the row the other writer created.

## Read paths

**Stock list** (`GET /api/stock/`). One query filtered by scope, ordered by the unique index,
sliced by the paginator, then two batched lookups: product ids to `{id: (name, unit)}`, store
ids to `{id: name}`. That is decision 20's manual batch, and it is why a page of 20 costs four
queries and not forty-one.

**Low stock** (`GET /api/stock/low/`). One query for the scoped rows, one for the thresholds of
products that have one, then the comparison, the sort, and the page, all in Python (R9).

**History** (`GET /api/stock/{id}/events/`). One query on `(stock_id, at)` descending, sliced by
the paginator. No join: `by_name` is stored on the event, and `product_id` needs no resolution
because the record already names it.

**Derived discrepancy.** Not exposed on an endpoint in M2. It is a read of the two newest
`COUNT` events plus the signed movements between them, and the function that computes it lives
with the model so M3 can call it without reimplementing the rule.

## Access rules

All role decisions go through `src/apps/identity/permissions.py`. Inventory adds two actions
and no role comparison of its own.

| Action | ADMIN | REGIONAL_MANAGER | MANAGER | SUPERVISOR | BARISTA |
|---|---|---|---|---|---|
| `stock.read` | all stores plus online | all stores plus online | own stores | own stores | own stores |
| `stock.record` | all stores plus online | all stores plus online | own stores | own stores | no |

- `stock_scope(queryset, actor, store_id=None)` filters with
  `store_id__in=scope_store_ids(actor, store_id)`, and adds `store_id__isnull=True` as an
  alternative only when `reaches_every_store(actor)` is true. Both helpers live in
  `identity.permissions`, so neither the ADMIN bypass nor the "sees every store" question is
  answered anywhere else (SC-006).
- The online pool is therefore invisible to MANAGER, SUPERVISOR, and BARISTA, whose
  assignments never cover every store. That is the spec's stated assumption, and it is data,
  not a role list.
- A stock record outside the actor's stores is a 403 with
  `"This record is outside your store access."` and no field of the record.
- A BARISTA attempting to record returns 403 with
  `"Your role may not perform this action."`
- An actor with no store assignments gets an empty list, never an error.

Catalog gains two actions for FR-040: `product.read` for every role, and `product.change` for
ADMIN and REGIONAL_MANAGER.

## Deletion and lifecycle

| Deleted | Collected automatically | Requirement |
|---|---|---|
| `Stock` | its events, by the `StockEvent.stock` cascade | implicit |
| `Product` | its stock rows, then their events, by the `Stock.product` cascade | out of scope in M2, reachable only from a product delete |
| `Store` | its stock rows, then their events, by the `Stock.store` cascade | FR-044 |
| `User` (account) | nothing in inventory. Events keep `by_id` and `by_name`. | FR-029, R5 |

Store deletion needs no new code: `stores.services.delete_store` already runs inside a
transaction with `retry_on_conflict`, and the collector follows the reverse relation declared
on `Stock`. This is the same mechanism M1 used for shifts, and it is proven end to end rather
than by a direct model delete.

Account deletion is the case M1 had to hand-patch for the schedule cache. It needs nothing here
for two reasons: the event keeps its own name, and no stock number depends on who recorded it.

## State transitions

`Stock` has no lifecycle. It is created on the first write for a pool and lives until its
product or its store is deleted.

`StockEvent` is append only. There is no edit, no delete, and no status. The two kinds are
distinct shapes in one collection, and the rules keep them distinct: a count never carries a
direction, and a movement never carries an absolute number.

The one value that changes meaning over time is `current_stock`. Between counts it is the
running total. At a count it becomes an observation, and the difference between that
observation and the running total is the unexplained loss. Nothing stores the difference, so
nothing can drift from it.
