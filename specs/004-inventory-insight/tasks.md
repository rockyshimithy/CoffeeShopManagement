# Tasks: M3 Inventory Insight

**Input**: Design documents from `/specs/004-inventory-insight/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included. The constitution requires tests before a feature is called complete, the
plan names three test files, and SC-001 to SC-010 are criteria only a suite can prove.

**Organization**: Tasks are grouped by user story so each story is independently testable. Both
reads share the foundational phase, and each read is demonstrable on its own after it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task serves (US1 to US3)
- Every task names the exact file it touches

## Path Conventions

Single project, backend only. `src/apps/<context>/` and `tests/`, both at the repository root.
Django commands run as `uv run python src/manage.py ...`, tests as `uv run pytest`.

---

## Phase 1: Setup

**Purpose**: Confirm the ground is solid before touching code.

- [x] T001 Confirm the baseline from the repository root: `git branch --show-current` (expected `feature/m3-inventory-insight`), `docker compose ps mongo` (expected healthy), `uv run pytest` (expected 227 passing), `uv run ruff check . && uv run ruff format --check .` (expected clean). Then run `uv run python src/manage.py migrate` and confirm it reports nothing pending, because this feature adds no model and no migration. Record the test count so a later regression is visible. Baseline on 2026-11-27: 228 passing, not the 227 this task predicted; branch and Mongo checks green, ruff clean, no migrations pending.

---

## Phase 2: Foundational (blocks both reads)

**Purpose**: the shared queryset helper, the enrichment, the event serializer, the permission
call, and the fixtures. Neither read can be built or tested before this phase lands.

- [x] T002 Add `event_scope(actor, store_id, product_id)` to `src/apps/inventory/services.py`. It calls `stock_scope(StockEvent.objects.all(), actor, store_id)`, applies `filter(product_id=product_id)` when the item is not None, and returns `order_by("-at", "-id")`. `stock_scope` is not modified: it already filters the `store_id` field both models carry (R5). The function returns an unsliced queryset so the report can aggregate and page on the same object.
- [x] T003 [P] Add `enrich_events(events, more_product_ids=())` to `src/apps/inventory/services.py` beside the existing `enrich`. It materializes the events, unions their `product_id` values with `more_product_ids`, and returns `{"labels": product_labels(product_ids), "store_names": store_names([row.store_id for row in rows])}`. Never fetch `product_thresholds` (R9). The key names must match what `StockSerializer` already reads from its context.
- [x] T004 [P] Add `EventReadSerializer` to `src/apps/inventory/serializers.py` as a subclass of `StockEventSerializer`. Add `product_name`, `unit`, and `store_name` as `SerializerMethodField`, read them from `self.context.get("labels", {})` and `self.context.get("store_names", {})`, and extend `Meta.fields` with the three names. An unresolved label is an empty string; an online row's `store_name` is None. Do not modify `StockEventSerializer` (D5).
- [x] T005 In `src/apps/inventory/views.py`, call `require_action(request.user, "stock.read")` at the top of `StockList.get_queryset`, `StockLow.get`, and `StockEventList.get`, after the path or query ids are parsed and before the scope check. Import `require_action` from `apps.identity.permissions`. No response changes for any current role, because all five hold the action (R11, D9).
- [x] T006 [P] Add `make_event` and `make_events` to `tests/conftest.py`, plus a module level `EVENT_START = datetime(2026, 11, 24, 8, 0, tzinfo=UTC)`. `make_event(stock, **fields)` creates one `StockEvent` with defaults for `kind`, `type`, `quantity`, `at=EVENT_START`, `by_id`, and `by_name`, and sets a non blank note whenever the type is `WASTE`. `make_events(count, *, stock, at=EVENT_START, step=timedelta(seconds=1), **fields)` builds `count` instances with `at = at + step * i` and inserts them with `bulk_create(..., batch_size=1000)`, which the Mongo backend turns into `insert_many` (D10). Import `StockEvent` at the top of the file.

**Checkpoint**: shared plumbing exists. No new route answers yet.

---

## Phase 3: User Story 1, a manager reviews waste over a date range (P1) MVP

**Goal**: `GET /api/stock/waste/` returns every waste event in an inclusive range, newest
first, with per item totals and a grand total that cover the whole range.

**Independent Test**: Record waste against three items in one store on two different days, then
read the report for day one, for day two, and for both days, and confirm the exact events and
per item totals in all three answers.

### The totals aggregation, proven before anything depends on it

- [x] T007 [US1] Add `waste_totals(queryset)` to `src/apps/inventory/services.py`. It runs `queryset.values("product_id").annotate(total=Sum("quantity"), events=Count("id")).order_by("-total", "product_id")` and returns a list of dicts. The queryset passed in is already filtered by scope, kind, type, instant range, and item, and is unsliced. Import `Count` and `Sum` from `django.db.models` (R2).
- [x] T008 [US1] Write the aggregate proof at the top of `tests/test_waste_report.py`: two waste events of `2.5` and `0.25` on one item, one range read, and assert the total is `Decimal("2.75")` and the grand total is `Decimal("2.75")` before serialization. This task decides whether R2's fallback is needed: if the aggregation returns a type other than `Decimal`, stop and replace `waste_totals` with the Python grouping from R2, then continue.

### The report itself

- [x] T009 [US1] Add `WasteReportQuerySerializer` to `src/apps/inventory/serializers.py` with `start` and `end` as required `serializers.DateTimeField`, and optional `store` and `product` as `ObjectIdField`. Add a `validate` that raises `serializers.ValidationError({"end": ["The end must not be earlier than the start."]})` when `start > end`. Equal bounds are valid (R7).
- [x] T010 [US1] Add `WasteReport` to `src/apps/inventory/views.py` as an `APIView` with `get()`. In order: validate the query serializer (400), read `page` and `page_size` from `_page_args`, build the queryset from `event_scope`, add `kind=MOVEMENT`, `type=WASTE`, `at__gte=start`, `at__lte=end`, call `waste_totals` on the unsliced queryset, take `count` from `sum(row["events"] for row in totals)`, slice the page, call `enrich_events(events, more_product_ids=<totals product ids>)`, serialize with `EventReadSerializer`, compute `grand_total = sum(row["total"] for row in totals)`, and answer through `_paged_response` with `totals` and `grand_total` added. Format `total` and `grand_total` through the shared `core.fields.QuantityField`, either in a small serializer or with `QuantityField().to_representation(...)`, never by summing rendered strings (D4, R3).
- [x] T011 [US1] Add the route `path("stock/waste/", views.WasteReport.as_view(), name="waste-report")` to `src/apps/inventory/urls.py`. Place it before the `stock/<str:pk>/events/` entry for readability; there is no matching conflict either way.

### Tests for User Story 1

- [x] T012 [US1] Extend `tests/test_waste_report.py` with the range and row rules: an event at `start`, at `start - 1ms`, at `end`, and at `end + 1ms`, with only the inner two present; `start == end` answers that one instant; a delivery, a sale, a count, and a waste in range, with only the waste returned; an empty range answers 200 with `count` 0, empty `results`, empty `totals`, and `grand_total` `"0"`; an item renamed after the event reads under its current name; an event whose actor account was deleted still renders `by_name`.
- [x] T013 [US1] Extend `tests/test_waste_report.py` with the totals rules: one row per item with its event count and exact total; totals ordered by total descending then `product_id`; 25 waste events across two items read with `page_size=10`, page 1 holding 10 rows while `count`, `totals`, and `grand_total` still cover all 25; the item filter narrowing rows and totals together (FR-029); the sum of `totals[].total` equal to `grand_total` with a difference of exactly zero (SC-002); the sum of `totals[].events` equal to `count`.
- [x] T014 [US1] Extend `tests/test_waste_report.py` with the refusals and the timing test: missing `start`, missing `end`, `start > end`, malformed `start`, malformed `product`, and malformed `store`, each asserted on the exact field; page 99 answering 404; and the SC-008 test that seeds 3,000 waste plus 7,000 other events in one store across 30 days with `make_events`, times only the GET with `time.perf_counter()`, asserts it is under one second, and prints the elapsed time.

**Checkpoint**: US1 is demonstrable on its own. Stop and validate before US2.

---

## Phase 4: User Story 2, a manager reads the newest stock changes as one timeline (P1)

**Goal**: `GET /api/stock/activity/` returns deliveries, sales, waste, and counts in one list,
newest first, in the shared page envelope.

**Independent Test**: Record 25 changes of mixed kinds across several items, read the feed, and
confirm page 1 holds the newest 20 in order and page 2 holds the other five, with no overlap.

- [x] T015 [US2] Add `ActivityFeed` to `src/apps/inventory/views.py` as a `generics.ListAPIView` with `serializer_class = EventReadSerializer` and `name = "activity-feed"`. `get_queryset` parses `store` and `product` with the existing `_object_id` helper and returns `event_scope(request.user, store_id, product_id)`. Override `list()` the way `StockList.list()` already does: paginate first, then build the serializer with `context=enrich_events(events)`, then answer with `get_paginated_response`. Do not add a second paginator or a custom envelope (D7, R8).
- [x] T016 [US2] Add the route `path("stock/activity/", views.ActivityFeed.as_view(), name=views.ActivityFeed.name)` to `src/apps/inventory/urls.py`.
- [x] T017 [US2] Write `tests/test_activity_feed.py`: five changes in scope all appear newest first; 25 changes give page 1 the newest 20 and page 2 the other five, with 25 distinct ids across the two pages; mixed kinds appear in one list ordered by instant; two events at the same instant keep the same order across two reads; a tie that straddles the page boundary never repeats or drops one; 120 changes with `page_size=1000` return at most 100; page 99 answers 404; an empty scope answers an empty page; a deleted actor still renders `by_name`; a renamed item reads under its new name.

**Checkpoint**: US2 is demonstrable on its own. It depends on M2's stored events, not on US1.

---

## Phase 5: User Story 3, a manager narrows either read (P3)

**Goal**: both reads accept a store filter and an item filter, together or separately.

**Independent Test**: With waste recorded in two stores and against two items, request each
filter combination and confirm every answer is exactly its subset.

- [x] T018 [US3] Confirm and complete the filter parameters in `src/apps/inventory/views.py`: the report reads `store` and `product` from `WasteReportQuerySerializer`, the feed reads them through `_object_id` in `ActivityFeed.get_queryset`. Both must apply the store through `event_scope` so a foreign store raises 403 and an unknown item answers empty, and both must apply the item filter to the totals as well as the rows. Fix whichever side is missing rather than duplicating the logic (R6).
- [x] T019 [US3] Add the filter tests to `tests/test_waste_report.py` and `tests/test_activity_feed.py`: item filter alone, store filter alone, both at once, an item with no events answering empty, a malformed item id answering 400, and a malformed store id answering 400. The foreign store 403 belongs to the scope file, not here.

**Checkpoint**: all three stories work independently.

---

## Phase 6: Scope, authorization, and the structural guard

**Purpose**: the cross-cutting requirements that belong to both reads.

- [x] T020 Write `tests/test_insight_scope.py`: a manager in store A sees exactly zero rows from store B in both reads; naming store B is a 403 with `"This record is outside your store access."` and no field of any row; a regional manager with no store named sees every assigned store plus the online pool; a manager with no store named never sees the online pool on either read; naming a store excludes the online pool even for ADMIN; an online row renders `pool: "ONLINE"`, `store_id: null`, and `store_name: null`; a barista reads both endpoints; an unauthenticated request answers 401 on both; deleting a store removes its rows and events so neither read names it (FR-025).
- [x] T021 In `tests/test_insight_scope.py`, add the two role gate tests for D9: a parametrized test that all five roles get 200 on both endpoints, and a test that patches `ROLE_ACTIONS["stock.read"]` to an empty set and asserts both endpoints answer 403 with `"Your role may not perform this action."`. The patch is what proves the call exists, because every current role holds the action.
- [x] T022 In `tests/test_insight_scope.py`, add the `derived_discrepancy` guard: scan `src/apps/inventory/*.py` except `services.py` and assert no line mentions `derived_discrepancy`, then assert the name still appears in `services.py` so the scan cannot pass vacuously (R12, D11).

**Checkpoint**: scope and authorization are proven for both reads, and the waste-only boundary is enforced.

---

## Phase 7: Polish and validation

**Purpose**: the gates the milestone must pass before it is called done.

- [x] T023 Run `uv run ruff check .` and `uv run ruff format --check .` over the changed files and fix every finding. Do not reformat a file this feature did not touch.
- [x] T024 Run `uv run pytest` and confirm the M0, M1, and M2 suites still pass, plus the new files. Record the total. Compare it with T001's baseline, and re-run `tests/test_single_write_path.py` explicitly so SC-007 is a fact and not an assumption.
- [x] T025 Run `uv run python src/manage.py makemigrations --check --dry-run` and confirm no model change is detected. A generated migration means this feature touched a model, which it must not.
- [x] T026 Execute `specs/004-inventory-insight/quickstart.md` end to end against a real server, every step, including the cleanup. Record any step that needed a correction, and correct the document rather than the memory of it.
- [x] T027 Append a `Delivered, with what changed during implementation` section to this file, naming every task whose implementation differed from the plan and why. Follow the M2 record at `specs/003-inventory-stock/tasks.md`.

---

## Dependencies and execution order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup, and blocks both reads
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational, not on US1
- **US3 (Phase 5)**: depends on US1 and US2, because it narrows both
- **Scope (Phase 6)**: depends on US1 and US2, because it exercises both routes
- **Polish (Phase 7)**: depends on every phase above

### Order that must not change

- T007 before T010: the totals function is called by the view.
- T008 before T010: the aggregate proof decides whether R2's fallback is needed, and that
  choice changes one function, not the response shape.
- T004 and T003 before T010 and T015: the serializer reads the keys the enrichment provides.
- T005 before T020 and T021: the role gate tests cannot pass until the calls exist.
- T006 before T014: the timing test seeds through the fixtures.
- T002 before T015 and T019: the feed has no queryset without it.

### Parallel opportunities

- Phase 2: T003 and T004 touch different files from T002 and T006, and T004 only needs the key
  names T003 defines, so they can be written together in one pass. T005 touches the existing
  views and can run beside them.
- After Phase 2, US1 and US2 can be built in either order. They share no file except
  `views.py`, `urls.py`, and `serializers.py`, so building them in one sitting avoids merge
  churn; two developers would touch the same three files and should not.
- Phase 3's three test tasks are one file, so they are sequential, not [P].

---

## Implementation strategy

### MVP first

US1 alone is demonstrable: seed waste, pick a range, read the rows and the totals. That is
Phases 1 to 3, and it proves the aggregation, the inclusive bounds, and the scope rule. Do not
skip T008: the rest of the report is built on that one result.

### Incremental delivery

1. Phases 1 and 2: helpers, serializer, permission call, fixtures. No route answers.
2. Phase 3: the waste report. Demonstrable, and the milestone's first exit criterion.
3. Phase 4: the activity feed. The second exit criterion, and no dependency on US1.
4. Phase 5: filters. The cheapest slice, and it narrows data that already exists.
5. Phase 6: scope and authorization across both reads, plus the structural guard.
6. Phase 7: gates, the quickstart walk, and the delivered record.

### The one risky assumption

That the backend's `Sum` aggregation returns `datetime`-free, exact `Decimal` values. T008 is
the test that settles it before any view depends on it. If it fails, the fallback in R2 keeps
the response shape and changes one service function.

---

## Notes

- `[P]` means different files and no incomplete dependency, not "run at the same time"
- Every refusal message in T009, T010, T014, and T017 is asserted verbatim in its test, so the
  contract in `contracts/api.md` and the code cannot drift
- The timing test prints its elapsed time instead of hiding it, the same honesty the M2
  concurrency test uses
- No test may use `time.sleep`. The feed's tie test uses fixed instants, not timing
- The `derived_discrepancy` guard is the one test a future loss report will delete on purpose
- The delivery record in T027 is appended after the work, never predicted now

## Delivered, with what changed during implementation

All 27 tasks are done. The baseline was 228 passing, not the 227 T001 predicted, and the final
suite is 285. Six things differed from the plan, each for a reason found while building it.

| Task | What differed | Why |
|---|---|---|
| T008 | The R2 fallback was not used. | The aggregation returns a real `Decimal`, so `Sum` over `Decimal128` is exact on this backend. The proof reads `2.5 + 0.25` as `Decimal("2.75")`. |
| T010 | `WasteReport.get` calls `require_action(request.user, "stock.read")` before `event_scope`. | The planned view did not, and T021's role gate test answered 200 where the contract requires 403. Position matches T005's call sites. |
| T012 | The deleted actor test captures the pk before `actor.delete()`. | Django sets `instance.pk` to `None` on delete, so the assertion read `None` instead of the stored id. |
| T013 | The paging test reads three pages, not two. | 25 events at `page_size=10` fill three pages; the planned two could hold only 20. Totals equality is asserted across all three. |
| T021 | BARISTA has no separate test. | The parametrized all-roles test includes it, and a second test would prove the same call twice. |
| T026 | The quickstart was corrected. | Step 8 wasted a coffee bag that was never delivered, so M2's overdraw rule refused it and day one answered `count` 2. The walk now records a coffee delivery at 07:30 and states the counts it shifts: nine events in total, feed 7, regional 9, store A narrowing 7, four pages, and 57 new tests rather than "roughly 30". |

The 10,000 event timing test measured 0.064s on this machine, against the one second bound in
SC-008. The corrected quickstart was executed end to end as explicit checks, all of which
passed, including the cleanup.
