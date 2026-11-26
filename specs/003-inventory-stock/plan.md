# Implementation Plan: M2 Inventory, stock movement inside one pool

**Branch**: `feature/m2-inventory` | **Date**: 2026-11-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-inventory-stock/spec.md`

**Note**: `setup-plan.sh` reports the feature directory name as the branch. The real git
branch is `feature/m2-inventory`, created from `master` at `320a6a5` and without an upstream.

## Summary

Deliver the stock ledger. Two new collections. `Stock` holds one number per item per pool:
the online pool, and one branch pool per store. `StockEvent` holds every change, in its own
collection, one document per movement or count. A delivery adds, waste subtracts, a count
sets, and the gap a count closes is never stored, it falls out of the events.

The whole feature is one write function. `inventory.services.record` opens a transaction,
validates the instant and the pool, applies the number with a targeted `$inc`, and appends
the event. No code path reads a number, edits it in Python, and saves it. That is invariant
I4, and it is the reason the module exists at all.

`catalog` stops being a stub that lies. Four things change there, and one of them is a bug:

1. `Product.price` becomes a real money value. Today it is `CharField(max_length=10)`.
2. `Product.unit` is added, because the stock read must display `2.5 L`. Decision 14 keeps
   it a label with no conversion.
3. `Product.low_stock_threshold` is added, nullable, shared by every pool.
4. `catalog/urls.py` routes the detail endpoint as `products/<int:pk>/`, but every id in
   this project is an ObjectId. That route cannot match any product, so detail, edit, and
   delete are unreachable today. Without fixing it, FR-040 (ADMIN sets the low stock level)
   has no endpoint. Fixed to `<str:pk>` plus `core.shortcuts.object_id_or_404`.

`workforce` is untouched. `identity` gains four permission actions, two scope helpers, and
no model change.

## Technical Context

**Language/Version**: Python 3.12 or newer

**Primary Dependencies**: unchanged from M1. Django 6.1.3, django-mongodb-backend 6.1.0,
djangorestframework 3.18.x, django-filter 26.2. This feature adds no dependency. It uses
`bson.Decimal128` and `decimal.Decimal`, both already installed.

**Storage**: MongoDB 8.0, the existing single-node replica set, which transactions require.
`DecimalField` stores as `Decimal128` on this backend (`operations.py`, `adapt_decimalfield_value`).

**Testing**: pytest 8 with pytest-django 4.14 against the Compose MongoDB. Six new test
files, one of them threaded for the concurrent delivery case.

**Target Platform**: Linux containers through Docker Compose, development on Ubuntu 24.04

**Project Type**: Web service, one backend, no frontend in this milestone

**Performance Goals**: a stock read answers with two indexed finds and no aggregation. A
movement write is three round trips inside one transaction: read the row, targeted update,
insert the event. The low stock read loads the actor's stock rows in one query and computes
the order in Python. Targets, not release gates.

**Constraints**: `prefetch_related()` is unsupported, so item names and units load by manual
batch after pagination. `django.db.transaction.atomic()` is a no-op, use
`django_mongodb_backend.transaction.atomic`. `select_for_update()` is a no-op, so the
non-negative guard is a filter on the update, never a lock. `count()` inside a transaction
is a 500 on this backend (002 `research.md` R17), so the write path uses `.first()`,
`.exists()`, and the row count returned by `.update()`. Pagination is mandatory on every
list.

**Scale/Scope**: one new app, one app extended, two new collections, five exposed routes,
four new permission actions, four new indexes, two migrations, six test files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Modular monolith, module under `src/apps/` | PASS | New app `src/apps/inventory` with label `apps.inventory`, next to `identity`, `stores`, `workforce`, `catalog`. |
| Domain boundary rule | PASS | `Stock.product` references `"catalog.Product"` by string label. `Stock.store` references `"stores.Store"` by string label. No model import crosses a context. Cross-context reads go through `stores.services.store_exists` and one new `catalog.services.product_exists`, plus the `identity.permissions` helpers. `StockEvent` keeps no foreign key to `identity.User`, so the deleted-actor case needs no cross-context code at all. |
| Ponytail, no unneeded patterns | PASS | One service module, one validator, one scope helper, DRF views, no repository, no event bus, no abstraction that a second caller does not justify. The four new permission actions are data in the existing table. |
| Strict SDD | PASS | Spec written 2026-11-26, plan here, tasks next, then code. |
| Code quality, type hints, tests | PASS | Ruff and pytest already wired. Isolation, counts, scope, refusals, low stock, and concurrency each get tests. |
| I1 store scoped access | PASS | `stock_scope()` derives every read from `identity.permissions.scope_store_ids`. Detail routes call `require_store_access`. A two-store test proves zero leakage, and SC-005 demands exactly zero. |
| I2 pool isolation | PASS | A stock row is identified by `(product, pool_type, store_id)`, so one row is one pool. The write path touches exactly one row. A request naming two pools is a 400 in the serializer, not a runtime guard that could be forgotten. FR-021. |
| I3 one product identity | PASS | `Stock` and `StockEvent` store `product_id` only. No name, price, or unit is copied into stock. The only copy in the system stays `OrderItem.unit_price`, for a different reason. |
| I4 stock is never read then saved | PASS | The number is written with `Stock.objects.filter(pk=...).update(current_stock=F("current_stock") + quantity)`, which compiles to `$add`/`$subtract` on one document (verified in `django_mongodb_backend/operations.py`, `combine_expression`). The row is read for validation only, and the read value is never written back. A count writes the request value, which is not a read. |
| Data layer, engine version match | PASS | No dependency change. Django 6.1 with backend 6.1.0 stays the documented pairing. |
| Data layer, ObjectId and contrib setup | PASS | `ObjectIdAutoField` inherited. `core.fields.ObjectIdField` declared on every serializer id and on every ObjectId that travels in a body. `core.shortcuts.object_id_or_404` on every path id. The catalog route bug is fixed as part of this. |
| Data layer, query rules | PASS | Pagination everywhere, including the Python-side low stock page. Stock event indexes on `(store_id, at)`, `(product_id, at)`, and `(stock_id, at)` are required by the constitution and all three are declared. No `prefetch_related`, no `select_for_update`, no `django.db.transaction`. Every write opens `django_mongodb_backend.transaction.atomic`. No `count()` inside a transaction. |
| Scheduled endpoint is cached | N/A | Only the schedule is required to be cached. Stock reads must be correct without a cache, and adding one here would be a second cache to invalidate. |
| Complexity justification | PASS | Two deviations, both recorded in Complexity Tracking. |

**Post-design re-check**: PASS. The design in `data-model.md` and `contracts/api.md` keeps
the permission helper as the only authorization path, keeps the write in one function, and
uses only backend features already proven in M0 and M1. The two deviations are the
denormalized actor name on events and the Python side ordering of the low stock page.

## Project Structure

### Documentation (this feature)

```text
specs/003-inventory-stock/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 decisions, R1 to R16
├── data-model.md        # Phase 1 collections, indexes, write path, cascades
├── quickstart.md        # Phase 1 end to end validation guide
├── contracts/
│   └── api.md           # Phase 1 HTTP contract for stock and the catalog changes
├── checklists/
│   └── requirements.md  # Spec quality checklist, all items pass
└── tasks.md             # Phase 2 output, created by /speckit.tasks
```

### Source Code (repository root)

```text
src/apps/inventory/            # NEW app
├── __init__.py
├── apps.py                    # InventoryConfig, label apps.inventory
├── models.py                  # Stock, StockEvent
├── validators.py              # the pool and instant rules
├── services.py                # record(), the only write function; reads for the views
├── serializers.py             # StockSerializer, StockEventSerializer, the two write shapes
├── filters.py                 # store, pool, product, low query parsing
├── views.py                   # StockList, StockLow, StockEventList, MovementList, CountList
├── urls.py                    # /api/stock/ and its children
├── admin.py                   # read only both models, no write path
└── migrations/0001_initial.py

src/apps/catalog/
├── models.py                  # CHANGED: price becomes money, unit, low_stock_threshold
├── services.py               # NEW: product_exists, product_names, product_units (public reads)
├── serializers.py             # CHANGED: unit and low_stock_threshold, price as money
├── views.py                   # CHANGED: permission helper on writes
├── urls.py                    # CHANGED: <int:pk> becomes <str:pk>, the bug fix
└── migrations/0002_item_shape.py  # NEW

src/apps/identity/
├── permissions.py             # CHANGED: four actions, reaches_every_store, require_stock_access
└── models.py                  # UNCHANGED

src/apps/stores/services.py    # UNCHANGED: store_exists and all_store_ids already exist

tests/
├── conftest.py                # CHANGED: make_stock and make_product fixtures
├── test_stock_movements.py    # received, waste, refusals, decimal exactness
├── test_stock_pools.py        # I2 and SC-001, online against two branch pools
├── test_stock_counts.py       # counts, baseline reset, derived discrepancy
├── test_stock_scope.py        # store scope, online visibility, cross-store 403
├── test_stock_low.py          # threshold rules, ordering, ADMIN and regional manager setter
└── test_stock_concurrency.py  # threaded deliveries against one pool, SC-004
```

**Structure Decision**: One Django project under `src/`, one module per bounded context.
`inventory` is new and imports no other context's model. `catalog` gains a services module
because `inventory` must read product names and units without importing `catalog.models`;
that is the same pattern `stores.services.store_exists` already set in M1.

## Phase Plan

### Phase 0, research

Complete. `research.md` holds eighteen decisions (R17 and R18 belong to 002 and are referenced,
not repeated). The four that change the shape of the code:

- R1: quantities are `DecimalField(max_digits=12, decimal_places=3)`, stored as `Decimal128`,
  so `2.75 L` never becomes `2.7500000000001`.
- R2: the number moves with a targeted `F()` update, which is what makes I4 true rather than
  merely intended.
- R3: a unique index on `(product_id, pool_type, store_id)` is the only thing that stops two
  concurrent first deliveries from creating two rows for one pool.
- R5: an event stores the actor's id and name, with no foreign key, because a cascade or a
  `SET_NULL` would modify stored events, which FR-029 forbids.

### Phase 1, design

`data-model.md` defines the two collections, the four indexes, the validation table, and the
write path step by step. `contracts/api.md` defines the five routes, the permission matrix,
and every error code. `quickstart.md` is the runnable proof.

### Phase 2, tasks

`/speckit.tasks` turns this plan into ordered tasks. Expected order: the catalog shape and
its route fix first, because the stock read depends on `unit` and the threshold setter
depends on the fixed detail route; then the permission actions and scope helpers; then
models and both migrations; then validators and the write function with its transaction;
then serializers, filters, views, routes; then the six test files; then the quickstart run.

## Decisions this plan carries that the spec left open

These are the plan's own calls, named so they can be vetoed before the code exists.

| # | Decision | Where |
|---|---|---|
| 1 | Quantities and prices are decimals with three and two decimal places, never floats. | R1, data-model |
| 2 | `Stock` gains `last_count_at`. The macro data shape lists `last_count` but not its instant, and FR-014 cannot be evaluated without it. | R4, data-model |
| 3 | A stock event stores `by_id` and `by_name` and no foreign key, so deleting an account cannot rewrite history. | R5, data-model |
| 4 | The discrepancy is derived from the COUNT events, not stored. The first count treats the baseline as zero. | R6, data-model |
| 5 | One private write function, two public entry points, `record_movement` and `record_count`. | R7 |
| 6 | The online pool is visible only to actors who reach every store, which is decided by one new helper, `identity.permissions.reaches_every_store`. | R8 |
| 7 | Low stock is ordered in Python over the actor's stock rows, because the shortage spans two collections. Pagination happens after that ordering. | R9, Complexity Tracking |
| 8 | The stock list is ordered by `product_id, pool_type, store_id`, which is exactly the unique index, so no join and no in-memory sort. | R10 |
| 9 | `catalog` writes become ADMIN and REGIONAL_MANAGER only through a new `product.change` action. That tightens today's behaviour, where any signed-in account may create or edit a product. | R12 |
| 10 | Both models are registered read only in the admin, the same guard `Shift` already has, because FR-027 says the admin is not a write path. | R14 |
| 11 | Two write routes rather than one, because a movement and a count have disjoint validation and merging them would make one serializer carry two rule sets. | R15 |
| 12 | A stock write that exhausts its retries answers 409 with no change applied, and that response carries `Retry-After: 1` so the client supplies the next round. A conflict is a reported outcome, not a server error. | FR-028, R13, R19, contracts |
| 13 | The stock write path keeps the shared default of 3 attempts, and SC-004 promises three concurrent writers. Measured: 3 attempts carry 3 writers on every run, and cannot carry 10 whatever the pause. 8 attempts would, and the Kyaor rejected the cost. | R19 |
| 14 | `core.transactions.retry_on_conflict` waits a random pause that doubles per attempt. No caller overrides the shared attempt count. | R19 |
| 15 | `docker-compose.yml` sets the mongo service open-file limit to 64000. A 1024 soft limit crashed mongod during the concurrency work. | R20 |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `StockEvent.by_name` duplicates a name that also lives in `identity_user`. | FR-029 says an event is never modified. A foreign key with `CASCADE` would delete the events of a deleted account, and `SET_NULL` would write null into them. Both modify stored events. A name snapshot also removes the join that FR-033 would otherwise need. | A foreign key plus a live lookup breaks on account deletion (M1 FR-025 promises that deletion succeeds), and the history would then disagree with `current_stock`. |
| The low stock page is ordered and paginated in Python, which is normally what pagination exists to avoid. | FR-043 orders by how far below the level a row sits, and the level lives on `catalog_product` while the quantity lives in `inventory_stock`. A page cannot be re-sorted after pagination, and a Mongo `$lookup` sort would bypass the ORM for one endpoint. | Sorting by `current_stock` alone needs no join but answers a different question than FR-043 asks. A stored `is_low` flag would need maintaining on every threshold change and every product edit. The working set is bounded by the actor's stores times the catalog size. |

## Requirement traceability

Every functional requirement has a home. Groups, because forty-five rows would repeat the
data model.

| Requirements | Design | Proof |
|---|---|---|
| FR-001 to FR-005 stock record shape | `data-model.md`, `Stock` table | `test_stock_movements.py` |
| FR-006 to FR-015 recording and validation | `data-model.md` validation table, `research.md` R2 and R4 | `test_stock_movements.py`, `test_stock_counts.py` |
| FR-016 to FR-019 applying a count, no stored gap | `research.md` R6, `data-model.md` write path | `test_stock_counts.py` |
| FR-020 to FR-023 pool isolation | `data-model.md` unique index, `research.md` R3 and R8 | `test_stock_pools.py`, `test_stock_scope.py` |
| FR-024 to FR-029 the single write path | `research.md` R2, R7, R13, R14 | `test_stock_movements.py`, `test_stock_concurrency.py` |
| FR-030 reads are store scoped | `research.md` R8, `data-model.md` access rules | `test_stock_scope.py` |
| FR-031 to FR-034 read shape, pagination, history, refusal | `contracts/api.md` | `test_stock_scope.py`, `test_stock_movements.py` |
| FR-035 to FR-038 roles | `contracts/api.md` permission table | `test_stock_scope.py` |
| FR-039 to FR-043 low stock | `research.md` R9, `contracts/api.md` low route | `test_stock_low.py` |
| FR-044 store deletion cascade | `data-model.md` deletion table | `test_stock_pools.py` |
| FR-045 existing product and store | `research.md` R11 | `test_stock_movements.py` |

| Success criterion | Proof |
|---|---|
| SC-001 one pool per operation | `test_stock_pools.py`, three pools of one product |
| SC-002 a count sets the number exactly | `test_stock_counts.py`, asserted on the stored decimal |
| SC-003 exactly one write path | a search for `.update(` and `.create(` on stock outside `services.py`, plus the admin guard |
| SC-004 concurrent deliveries | `test_stock_concurrency.py`: ten threads all succeed, plus a higher level asserting accepted count equals the number and the event count (R16) |
| SC-005 zero foreign rows | `test_stock_scope.py`, two stores, exactly zero |
| SC-006 no role comparison outside the helper | a search for `User.Role` inside `apps/inventory` returns nothing |
| SC-007 never negative | `test_stock_movements.py`, overdraw refused and the number unchanged |
| SC-008 visible on the next read | `test_stock_movements.py`, read after write in one test |
| SC-009 low stock never guesses | `test_stock_low.py`, equality, missing level, and ordering |
| SC-010 every event names actor, instant, kind | `test_stock_movements.py`, asserted on every created event |

## Known limitations

- The low stock read loads every stock row in scope before paginating. With 50 stores and
  200 products that is 10,000 rows, which is fine for this project and is not fine for a
  chain. The escape hatch is an aggregation with `$lookup` on the threshold, and it is a
  change inside `services.low_stock` only, because the contract stays the same.
- `retry_on_conflict` uses the shared 3 attempts (R19). A losing request answers 409 and changes
  nothing, so the number is never corrupt, but a refused write is still a write the client has to
  send again. Measured: three simultaneous writers all succeed on every run, and twenty accept a
  subset, which is why the higher level asserts only the no-lost-update equation.
- Each concurrency writer is a Python thread with its own Django connection, which is its own
  Mongo client, which costs two descriptors and a monitor thread on the database side. Twenty is
  comfortable here and forty crashed a container with a 1024 soft limit, which is why the compose
  file now sets 64000 (R20). A test that raises the level without raising the limit will crash
  mongod instead of failing an assertion.
- Deleting an account leaves its `by_id` on past events pointing at an id that no longer
  resolves. That is deliberate: the name snapshot still renders, and no query joins on it.
- A product deleted from the catalog takes its stock rows and their events with it, through
  the cascade. M2 adds no product deletion route, so this is only reachable from the admin,
  which is read only for stock and writable for products only through the service.
- The stock read resolves product names and store names with two batched queries after
  pagination. A page of 20 therefore costs four queries, not one. That is the decision 20
  pattern, not an oversight.
