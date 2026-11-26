# Tasks: M2 Inventory, stock movement inside one pool

**Input**: Design documents from `/specs/003-inventory-stock/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included. SC-001 to SC-010 are acceptance criteria that only a suite can prove, and
the constitution requires tests before a feature is called complete. They are not optional here.

**Organization**: Tasks are grouped by user story so each story is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task serves (US1 to US5)
- Every task names the exact file it touches

## Path Conventions

Single project, backend only. `src/apps/<context>/` and `tests/`, both at the repository root.
Django commands run as `uv run python src/manage.py ...`, tests as `uv run pytest`.

---

## Phase 1: Setup

**Purpose**: Confirm the ground is solid before touching code.

- [x] T001 Confirm the baseline from the repository root: `docker compose ps mongo` (expected healthy), `uv run pytest` (expected 162 passing), `uv run ruff check . && uv run ruff format --check .` (expected clean on 81 files). Record the test count so a later regression is visible.

---

## Phase 2: Foundational (blocks every user story)

**Purpose**: The catalog shape the stock read depends on, the permission actions, the two
collections, and the fixtures. No story can be tested before this phase lands.

### Catalog, which the stock read depends on

- [x] T002 Change `src/apps/catalog/models.py`: `price` becomes `models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)`, add `unit = models.CharField(max_length=8, default="pcs")`, add `low_stock_threshold = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)`. Do not add `sellable` (plan decision, R11).
- [x] T003 [P] Create `src/apps/catalog/services.py` with public reads for other contexts: `product_exists(product_id) -> bool`, and batched `product_names(ids) -> dict` / `product_units(ids) -> dict`, or one `product_labels(ids) -> dict[id, (name, unit)]`. `inventory` imports this module, never `catalog.models`.
- [x] T004 Update `src/apps/catalog/serializers.py`: add `unit` and `low_stock_threshold` to the field tuple, and declare `price` as `serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True, required=False)`. Keep `id = core.fields.ObjectIdField(read_only=True)`.
- [x] T005 Update `src/apps/catalog/views.py`: import `require_action` from `apps.identity.permissions` and call `require_action(request.user, "product.change")` at the top of the create, update, and destroy paths. Do not add a check to the read paths beyond the project default. Raise `PermissionDenied(ROLE_DENIED)` for a role that may not write.
- [x] T006 Fix `src/apps/catalog/urls.py`: change `products/<int:pk>/` to `products/<str:pk>/`. This route cannot match an ObjectId today, so detail, edit, and delete are unreachable (R11).
- [x] T007 Update `ProductDetail` in `src/apps/catalog/views.py` to load through `core.shortcuts.object_id_or_404(Product, kwargs["pk"])` instead of the generic `get_object`, so a hex id reaches the filter rather than a coercion error. Keep the generic response behaviour.
- [x] T008 Generate the catalog migration with `uv run python src/manage.py makemigrations catalog`. Expected: one `0002_item_shape.py` altering `price` and adding two fields. The database holds zero product rows, so no data step is needed. Read the migration and confirm no `AlterField` tries to cast a string.

### Permissions and scope helpers

- [x] T009 Update `src/apps/identity/permissions.py`: add `"product.read"`, `"product.change"`, `"stock.read"`, and `"stock.record"` to `ACTIONS`, and to `ROLE_ACTIONS` as follows. `product.read`: all five roles. `product.change`: `ADMIN` and `REGIONAL_MANAGER` only. `stock.read`: all five roles. `stock.record`: `ADMIN`, `REGIONAL_MANAGER`, `MANAGER`, `SUPERVISOR`. No role comparison may appear outside this module.
- [x] T010 Update `src/apps/identity/permissions.py` with two helpers. `reaches_every_store(actor) -> bool`: True for `ADMIN`, otherwise `set(actor.store_ids) == set(stores.services.all_store_ids())`. `require_stock_access(actor, store_id) -> None`: `store_id` is a store id for a branch pool, which delegates to `require_store_access`; `store_id` is `None` for the online pool, which requires `reaches_every_store` and raises `PermissionDenied(STORE_DENIED)` otherwise. Both helpers keep the ADMIN bypass, so nothing outside this module compares a role to decide what a query sees (SC-006).

### The new app and its collections

- [x] T011 Create the app scaffold: `src/apps/inventory/__init__.py` and `src/apps/inventory/apps.py` with `InventoryConfig` (label `apps.inventory`), add `"apps.inventory"` to `INSTALLED_APPS` in `src/core/settings.py`, and add `path("api/", include("apps.inventory.urls"))` to `src/core/urls.py`.
- [x] T012 Create `Stock` in `src/apps/inventory/models.py`: `product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="stock_rows")`, `pool_type` (`CharField(max_length=8, choices=POOL_CHOICES)` with `BRANCH` and `ONLINE`), `store = models.ForeignKey("stores.Store", on_delete=models.CASCADE, null=True, blank=True, related_name="stock_rows")`, `current_stock` and `last_count` as `DecimalField(max_digits=12, decimal_places=3, default=0)`, `last_count_at` and `last_event_at` as `DateTimeField(null=True, blank=True)`. `Meta.indexes` holds a unique index on `("product_id", "pool_type", "store_id")` and a plain index on `("store_id", "pool_type")`. Both references use string labels, so no cross-context model import exists.
- [x] T013 Add `StockEvent` to `src/apps/inventory/models.py`: `stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="events")`, `product_id` and `store_id` as `django_mongodb_backend.fields.ObjectIdField` (null on `store_id`), `pool_type`, `kind` (`MOVEMENT` or `COUNT`), `type` (nullable, `RECEIVED`, `SOLD`, `WASTE`), `quantity` and `counted` (`DecimalField(max_digits=12, decimal_places=3, null=True)`), `by_id` (`ObjectIdField`), `by_name` (`CharField(max_length=120)`), `at` (`DateTimeField`), `note` (`CharField(max_length=200, blank=True, default="")`). No foreign key to `identity.User` (R5). `Meta.indexes` holds `("stock_id", "at")`, `("product_id", "at")`, and `("store_id", "at")`.
- [x] T014 Generate the inventory migration with `uv run python src/manage.py makemigrations inventory`. Read `0001_initial.py` and confirm three things: `ObjectIdAutoField` primary keys, the unique index on the three fields, and all three event indexes. Add any missing index by hand-editing the model and regenerating, not by editing the migration.
- [x] T015 Add `src/apps/inventory/admin.py`: register `Stock` and `StockEvent`, and override `get_readonly_fields`, `has_add_permission`, `has_change_permission`, `has_delete_permission` to make both read only. The comment must state that FR-027 makes the admin a non-write path, following `src/apps/workforce/admin.py`.
- [x] T016 [P] Add `make_product` and `make_stock` fixtures to `tests/conftest.py`. `make_product(name=None, unit="pcs", price=None, threshold=None)`. `make_stock(product, pool_type="BRANCH", store=None, current_stock=0)`. Both create real rows and request `db` in their own signature, following the existing factory style.

**Checkpoint**: schema, permissions, and fixtures exist. No endpoint answers yet.

---

## Phase 3: User Story 1, a manager records a delivery into their store (P1) MVP

**Goal**: `POST /api/stock/movements/` records a delivery, and `GET /api/stock/` plus
`GET /api/stock/{id}/events/` show the number and the history.

**Independent Test**: As the manager of store A, record a delivery of 12.5 litres of milk,
then read the stock of store A and see 12.5 with exactly one event.

- [x] T017 [US1] Create `src/apps/inventory/validators.py` with three functions. `validate_pool(pool, store)` raises `ValidationError({"pool": ["A branch pool needs a store and the online pool forbids one."]})` unless a branch pool has a store and the online pool has none (FR-002). `validate_quantity(value, *, allow_zero=False)` raises `ValidationError` when the value is not finite, is negative (or not strictly positive unless `allow_zero`), or has a scale finer than three places, with the message "The quantity must be greater than zero with at most 3 decimal places." `validate_instant(at, last_count_at)` raises on a future instant ("The instant cannot be in the future.") and on an instant earlier than `last_count_at` ("The instant is earlier than the newest count of this stock."). These functions raise; the caller owns the transaction.
- [x] T018 [US1] Create `src/apps/inventory/services.py` with `record(actor, *, product_id, pool_type, store_id, kind, ...)` as the only function that writes `Stock` or `StockEvent`, plus the public `record_movement(actor, data)` wrapper. Body, in this order: `require_action(actor, "stock.record")`, `require_stock_access(actor, store_id)`, `product_exists`, `store_exists` for a branch pool, then `retry_on_conflict` around `django_mongodb_backend.transaction.atomic` containing: find the row with `.first()`, create it when absent (a duplicate key is the concurrent-create guard, R3), `validate_instant` against `row.last_count_at`, the targeted `update(current_stock=F("current_stock") + quantity, last_event_at=at)`, then `StockEvent.objects.create(...)` with `by_id=actor.pk` and `by_name` from the actor. Never call `count()` inside the transaction (R13). Wrap the whole `retry_on_conflict` call so an exhausted retry answers `rest_framework.exceptions.APIException` subclass with status 409 and the message "The stock changed while this write was being applied. Nothing was saved. Try again."
- [x] T019 [US1] Add to `src/apps/inventory/serializers.py`: `QuantityField` (a `DecimalField` subclass rendering an exact decimal string with no trailing zeros), `StockSerializer` with `id`, `product_id`, `product_name`, `unit`, `pool`, `store_id`, `store_name`, `current_stock`, `last_count`, `last_event_at`, `is_low`; `StockEventSerializer` with every stored field plus `stock_id`; and `MovementWriteSerializer` with `product`, `pool`, `store`, `type`, `quantity`, `note`, `at`. Every id field is `core.fields.ObjectIdField`.
- [x] T020 [US1] Add the read side to `src/apps/inventory/services.py`: `stock_scope(queryset, actor, store_id=None)` delegating to `identity.permissions.scope_store_ids` and adding the online clause through `reaches_every_store`; and `list_stock(actor, params, page, page_size)` which filters by scope, orders by `("product_id", "pool_type", "store_id")`, slices with `core.pagination.StandardPagination`, and fills `product_name`, `unit`, and `store_name` with batched lookups after the page (decision 20).
- [x] T021 [US1] Add `StockList` (GET) and `MovementList` (POST) to `src/apps/inventory/views.py`, plus `src/apps/inventory/urls.py` with `stock/`, `stock/movements/`, and the `stock/` prefix registered in `src/core/urls.py`. A movement answers 201 with `{"stock": ..., "event": ...}`. Path ids go through `core.shortcuts.object_id_or_404`; body ids go through `ObjectIdField`.
- [x] T022 [US1] Add `StockEventList` (GET `stock/{id}/events/`) to `src/apps/inventory/views.py` and its route. Load the stock row through `object_id_or_404`, call `require_store_access` (or `require_stock_access` for the online row), then order `("at", "id")` descending and paginate. No join: `by_name` is stored on the event.
- [x] T023 [US1] Write `tests/test_stock_movements.py`: a delivery into an existing row reads back the sum; a first delivery creates the row; quantity 0, negative, and four decimal places each answer 400 with the field; a delivery of `2.75` reads back exactly `2.75` on a repeated read; a manager recording into another store answers 403; a barista answers 403 with the role message; a barista reads the number after the delivery; the response carries both `stock` and `event` with `by_name`; an event names actor, instant, and kind (SC-010); a missing product or store answers 400.

**Checkpoint**: US1 is demonstrable on its own. Stop and validate before US2.

---

## Phase 4: User Story 2, the online pool and a store pool move independently (P1)

**Goal**: A row is one pool, so isolation is structural. This phase adds the read filters that
expose it and the rules that keep the online pool out of reach below regional manager.

**Independent Test**: Record a delivery online and waste in store A for one product, then read
both pools and see each number moved by its own operation only.

- [x] T024 [US2] Add the `pool`, `store`, and `product` query parameters to `StockList` in `src/apps/inventory/views.py`: parse them with an `ObjectIdField` and a choice field, answer 403 when `store` is outside the actor's assignments, and answer 403 when `pool=ONLINE` and `reaches_every_store` is false. Unknown parameters are ignored, as elsewhere in the project.
- [x] T025 [US2] Enforce one pool per request in `record`: a body naming both a branch pool and a store that the pool forbids is a 400 through `validate_pool` (T017), and the write touches exactly one row because the row is identified by the three fields. Add the `SOLD` refusal for a branch pool with the message "A sale cannot be recorded in a store pool yet." in `src/apps/inventory/validators.py`, in one function, with a comment naming FR-013 and the fact that it is a milestone policy, not a storage rule.
- [x] T026 [US2] Write `tests/test_stock_pools.py`: one product in three pools, and each operation changes exactly one number (SC-001, I2); a delivery online leaves the branch pools untouched and the reverse; a request naming two pools answers 400; a branch pool without a store answers 400; an online pool with a store answers 400; a manager cannot see the online row in a list and cannot record against it (403); a regional manager can do both; deleting a store removes its rows and their events (FR-044).

**Checkpoint**: isolation is proven, not assumed.

---

## Phase 5: User Story 3, a manager records waste (P2)

**Goal**: Waste subtracts, needs a note, and cannot take a number below zero.

**Independent Test**: Record waste of 2 with a note against a row at 10, then read 8 and one
waste event carrying the note.

- [x] T027 [US3] In `src/apps/inventory/validators.py`, add `validate_note(kind, movement_type, note)`: a `WASTE` movement needs a note that is not empty and not only whitespace, with the message "Waste needs a note." Any other kind accepts an empty note.
- [x] T028 [US3] In `src/apps/inventory/services.py`, add the subtraction branch to `record`: `Stock.objects.filter(pk=stock_pk, current_stock__gte=quantity).update(current_stock=F("current_stock") - quantity, last_event_at=at)`, and when the returned row count is zero raise `ValidationError({"quantity": ["There is not enough stock for this movement. Record a count first."]})`. The guard lives in the match, never in a Python comparison against a read value (R2, I4).
- [x] T029 [US3] Extend `tests/test_stock_movements.py` with the waste cases: waste 2 from 10 reads 8 with one event carrying the note and the actor; waste 11 from 10 answers 400 and the number stays 10 with no event stored; waste with no note and with a whitespace-only note each answer 400; waste reaching exactly zero succeeds; a sale in a branch pool answers 400 and stores nothing.

**Checkpoint**: a store number can now fall by a recorded reason.

---

## Phase 6: User Story 4, a count reconciles a shelf discrepancy (P2)

**Goal**: A count sets the number, resets the baseline, and the gap is derived, not stored.

**Independent Test**: From a row whose movements predict 8, record a count of 6, then read 6
and derive a difference of 2 from the events alone.

- [x] T030 [US4] Add `CountWriteSerializer` to `src/apps/inventory/serializers.py`: `product`, `pool`, `store`, `counted`, `note`, `at`. Sending `type` or `quantity` is a field error, because a count has no direction (FR-011).
- [x] T031 [US4] In `src/apps/inventory/services.py`, add the count branch to `record` and the public `record_count` wrapper: `update(current_stock=counted, last_count=counted, last_count_at=at, last_event_at=at)`. The written value comes from the request, never from a read (FR-016, R2). Set `last_count_at` inside the same update so FR-014 holds for the next movement.
- [x] T032 [US4] Add `CountList` (POST `stock/counts/`) to `src/apps/inventory/views.py` and its route, answering 201 with `{"stock": ..., "event": ...}` where `current_stock` and `last_count` both equal `counted`.
- [x] T033 [US4] Add `derived_discrepancy(stock)` to `src/apps/inventory/services.py`: read the two newest `COUNT` events for the row (`.values_list` on `(stock_id, at)` is not enough, so read the two rows with `.filter(kind="COUNT").order_by("-at")[:2]`), sum the signed quantities of `MOVEMENT` events strictly between them, and return `newest.counted - (previous.counted + summed)` or, for a first count, `newest.counted - summed`. No endpoint exposes it in M2; M3 calls it.
- [x] T034 [US4] Write `tests/test_stock_counts.py`: a count of 6 from 8 reads 6 with `last_count` 6; a count above the number raises it; a count equal to the number is stored and changes nothing; a count of 0 is accepted; a negative count answers 400; a count with `type` or `quantity` answers 400; a delivery after a count applies on top of the count; a movement earlier than `last_count_at` answers 400; a movement later applies; `derived_discrepancy` returns the expected gap for a movements-then-count sequence and for the first count of a record (SC-002).

**Checkpoint**: the M2 reconciliation criterion is proven.

---

## Phase 7: User Story 5, a manager sees which items are low (P3)

**Goal**: Strictly-below, never-guessed, worst-first, and only ADMIN or REGIONAL_MANAGER may
set the level.

**Independent Test**: Set a level of 5 on two products, bring one to 3 and one to exactly 5,
then read the low list and see only the first.

- [x] T035 [US5] Add `low_stock(actor, store_id, page, page_size)` to `src/apps/inventory/services.py`: load the scoped rows with `stock_scope`, load the thresholds of the products that have one in a single query, keep rows where the threshold exists and `current_stock` is strictly below it, sort by `(threshold - current_stock)` descending with `product_id` as the tie-break, then slice the page and fill `product_name`, `unit`, and `store_name` in batch (R9).
- [x] T036 [US5] Add `StockLow` (GET `stock/low/`) to `src/apps/inventory/views.py` and its route. `count` must be the number of low rows, not the number of stock rows, because the page is taken after the ordering. Answer 403 for a `store` outside the actor's assignments.
- [x] T037 [US5] Write `tests/test_stock_low.py`: below the level appears; exactly at the level does not; no level never appears at any quantity, including zero; three rows below their own levels appear worst first; the level set by ADMIN applies in every pool of the product; a barista reads the list; a manager sees only their store's pools; a MANAGER may not `PATCH` a product (403) while a REGIONAL_MANAGER may (200); `PATCH {"low_stock_threshold": null}` clears it and the row stops appearing (SC-009).

**Checkpoint**: every user story works independently.

---

## Phase 8: Polish and cross-cutting gates

- [x] T038 [P] Write `tests/test_stock_scope.py`: two stores, a manager of one, exactly zero foreign rows in a list (SC-005); a direct read or history request for the other store answers 403 with the outside-access message and no field leaked; an actor with no assignments gets an empty list and 200; an admin sees every store; an unauthenticated request answers 401.
- [x] T039 Write `tests/test_stock_concurrency.py` with `@pytest.mark.django_db(transaction=True)`: ten threads recording one unit each against one pool, with a `threading.Barrier`, asserting every request succeeded, `current_stock == 10`, and exactly ten events (SC-004). Then a second test at forty threads asserting `current_stock == accepted_count` and `event_count == accepted_count`, printing the accepted count. Record that number in `research.md` R16. Do not raise the assertion to a number that happens to pass.
- [x] T040 [P] Write `tests/test_single_write_path.py`: read the source of `src/apps/inventory` with `pathlib` and assert that `.update(` and `.create(` on `Stock` or `StockEvent` appear only in `services.py` (SC-003), and that `User.Role` appears nowhere in the package (SC-006).
- [x] T041 Run `uv run pytest` over `tests/` and `uv run ruff check . && uv run ruff format --check .` over `src/` and `tests/`. Compare against the T001 count and report the new total. Any pre-existing test that changed behaviour must have a documented reason, not a quietly edited assertion.
- [x] T042 Run `specs/003-inventory-stock/quickstart.md` end to end against a migrated database, including the `SOLD` refusal (6.4), the backdated movement (6.5), the threshold clearing (6.6), and both halves of the catalog guard (6.8). Correct the document where a step does not match the code, as M1 had to do.
- [x] T043 Re-read `docs/MACRO.md` section 4, section 5, and section 6 against the shipped code. Two known items must be resolved here: the `Stock` shape needs `last_count_at` added with a dated note (R4), and decision 19 must still describe the one write function accurately. Report the exact line for any amendment rather than editing the macro silently.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: run first, records the baseline
- **Foundational (Phase 2)**: depends on T001 and blocks every story
- **US1 (Phase 3)**: depends on Phase 2. This is the MVP
- **US2 (Phase 4)**: depends on US1, because it exercises the same write path and read shape
- **US3 (Phase 5)**: depends on US1. It edits the two files US1 created
- **US4 (Phase 6)**: depends on US1, and shares `record` with US3. Land US3 before US4 so the subtraction branch and the count branch are written one at a time
- **US5 (Phase 7)**: depends on Phase 2 for the catalog field and on US1 for the read helpers
- **Polish (Phase 8)**: depends on every story being delivered

### Story dependencies

- **US1 (P1)**: independent after Phase 2
- **US2 (P1)**: needs US1's write path and list view
- **US3 (P2)**: needs US1 only, and edits `validators.py` and `services.py`
- **US4 (P2)**: needs US1 only
- **US5 (P3)**: needs Phase 2's `low_stock_threshold` and US1's `stock_scope`

US3, US4, and US5 have no dependency on each other and can be reordered freely.

### Within each story

Tests come last in this feature, unlike a TDD project. The reason is that every rule lives in
one validator or one branch, and the tests exist to pin the exact refusal messages. Two tests
must be shown to fail when the guard is removed, and T039 and T040 are the two: delete the
`current_stock__gte` match once, and add an `.update(` call outside `services.py` once, and
watch each fail before restoring it.

### Parallel opportunities

- T003 runs beside T002, different file
- T016 runs beside T009 and T010, different file
- T038 and T040 are independent files and can be written together
- T012 and T013 are one file, so sequential by necessity
- Every story phase is a separate file set except US3's tests, which extend US1's file

---

## Parallel Example: Phase 2

```bash
# Three different files, no ordering between them:
Task: "Add product_exists and the batched label read in src/apps/catalog/services.py"
Task: "Add the four permission actions in src/apps/identity/permissions.py"
Task: "Add make_product and make_stock in tests/conftest.py"
```

## Parallel Example: Phase 8

```bash
# Two gates that do not touch each other:
Task: "Write tests/test_stock_scope.py"
Task: "Write tests/test_single_write_path.py"
```

---

## Implementation Strategy

### MVP first

US1 alone is demonstrable: a manager records a delivery, reads the number, and sees the
history. That is Phases 1 to 3, 23 tasks, and it proves the single write function and I4.

Phase 2 is larger than the "foundational" label suggests, because the catalog shape and the
route bug have to be fixed before any stock read can render a unit or a threshold. Do not
try to reach US1 without it.

### Incremental delivery

1. Phases 1 to 2: schema, permissions, catalog shape. No endpoint answers yet
2. Phase 3: US1, the delivery and the read. Demonstrable, and the invariant is in place
3. Phase 4: US2, isolation proven with three pools
4. Phase 5: US3, waste and the non-negative guard
5. Phase 6: US4, counts and the derived discrepancy. This closes the M2 exit criteria
6. Phase 7: US5, low stock
7. Phase 8: the gates and the walkthrough

### Order that must not change

T017 before T018: the validator is called from inside the transaction, and writing it after
the service means writing it twice. T012 and T013 before T014, because the migration must be
generated from the final models. T033 before T030's tests, because the count tests assert the
derived gap.

---

## Notes

- `[P]` means different files and no incomplete dependency, not "do it at the same time"
- Every refusal message in T017, T025, T027, T028, and T031 is asserted verbatim in its test,
  so the contract in `contracts/api.md` and the code cannot drift
- The concurrency test is the only place a thread is created in this suite, and it needs
  `transaction=True` or the other thread's connection cannot see the seeded rows (002 T023)
- No test may use `time.sleep` to create an interleaving. Use `threading.Barrier`
- A 409 is a correct answer, not a failure. A test that treats it as a crash will be wrong
  about the system

---

## Delivered, with what changed during implementation

All 43 tasks are done. Eight things differed from the plan, each for a reason found while
building it.

| Task | What differed | Why |
|---|---|---|
| T002 | Uniqueness is a `UniqueConstraint`, not `models.Index(unique=True)`. | `Index.__init__` rejects a `unique` keyword on this backend. The migration emits `CreateConstraint uniq_stock_per_pool`. |
| T008 | The catalog migration is `0002_product_shape.py` (renamed from the generated name), and the inventory migration depends on that name. | The generated name was `0002_product_low_stock_threshold_product_unit_and_more`, which says nothing useful in a migration list. |
| T009 | `product.read` was not added; `product.change`, `stock.read`, and `stock.record` were. | Every role may read the catalog, so no role decision exists to record, and an action nothing consults is dead data. The permission table in `contracts/api.md` still describes the behaviour correctly. |
| T014 | No hand edits were needed. Three indexes and one constraint came out as intended. | The model was correct on the first generation. |
| T033 | The discrepancy is `predicted - counted`, not `counted - predicted`. | A loss must read as a positive number for M3's waste report. `research.md` R6 and the quickstart were corrected to match. |
| T035 | `low_stock` returns `(total, page_rows)` rather than serializing inside the service. | Keeps the serializer out of the service and lets the view own the envelope. |
| T039 | Asserted level is **3** and measured level is **20**, both on the shared **3** retries. | Measured: 3 retries carry 3 simultaneous writers on 6 of 6 runs and cannot carry 10 at any pause; 8 retries would carry 10 and the Kyaor rejected the cost, so SC-004 moved to three. Forty threads also crashed mongod against a 1024 descriptor limit, which led to the compose change below. See `research.md` R19. |
| T043 | Two macro amendments were needed, both applied. | `Stock` gains `last_count_at` (decision 18 and the data shape, dated), and the macro version moved to 0.8. No other contradiction was found in sections 4, 5, or 6. |

Two changes landed outside this feature's own files:

1. `src/core/transactions.py`: `retry_on_conflict` now waits a jittered pause between attempts.
   The shared helper is used by `workforce` and `stores` as well, so their tests were re-run and
   all pass. The pause only delays a retry; it changes no semantics.
2. `docker-compose.yml`: the `mongo` service now sets `ulimits.nofile` to 64000 soft and hard.
   The default soft limit was 1024, and mongod died with `WiredTiger ... Too many open files`
   during the concurrency work. See `research.md` R20.

Final state: **227 tests pass**, up from 162, and `ruff check` with `ruff format --check` is
clean on 97 files. The quickstart was executed end to end against a real server as 38 explicit
checks, all of which passed without needing a correction to the document.
