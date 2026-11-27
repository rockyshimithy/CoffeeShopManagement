# Implementation Plan: M3 Inventory Insight

**Branch**: `feature/m3-inventory-insight` | **Date**: 2026-11-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-inventory-insight/spec.md`

**Note**: the branch was created from `master` at `06cb2d6`. `setup-plan.sh` was not run,
because its only effect is to copy the plan template into this file, which is written directly.
`.specify/extensions.yml` does not exist, so there are no hooks to dispatch.

## Summary

Deliver the two reads M3 asks for, over the event collection M2 already stores. No new
collection, no field, no index, no migration, and no write path.

The waste report takes a start and an end instant and answers every waste movement in that
window, newest first, in one page at a time, with a per item totals block and a grand total
that cover the whole range. The activity feed answers the newest changes across items, all
kinds mixed, in the project's standard paged envelope.

Both reads are one filtered queryset plus batched label lookups. The report adds one `$group`
for its totals, and takes its page count from that same group, so the envelope cannot
contradict its own totals. The four defaults the spec took without asking were settled on
2026-11-27, and the third one changed the spec: the feed is paged, not a fixed 20.

Three things this feature touches outside its own new code, all named here so they are not
discovered in review:

1. The three existing read views gain `require_action(request.user, "stock.read")`. The action
   was declared in M2 and consulted by nothing (R11).
2. `tests/conftest.py` gains two event fixtures.
3. A source scan guard asserts no read uses `derived_discrepancy` (R12).

## Technical Context

**Language/Version**: Python 3.12 or newer

**Primary Dependencies**: unchanged from M2. Django 6.1.3, django-mongodb-backend 6.1.0,
djangorestframework 3.18.x, django-filter 26.2. This feature adds no dependency.

**Storage**: MongoDB 8.0, the existing single-node replica set. Reads only. No collection,
field, index, or migration is added.

**Testing**: pytest 8 with pytest-django 4.14 against the Compose MongoDB. Three new test
files, two new fixtures, and one structural scan test. The M2 suite must stay green.

**Target Platform**: Linux containers through Docker Compose, development on Ubuntu 24.04

**Project Type**: Web service, one backend, no frontend in this milestone

**Performance Goals**: a 30 day report over 10,000 stored events in one store answers in under
one second (SC-008), measured through the API including serialization. Each read costs four
queries per page.

**Constraints**: `prefetch_related()` is unsupported, so names load by manual batch after
pagination. `QuerySet.count()` is forbidden inside a transaction; these reads are not in one.
Pagination is mandatory on every list. A sort with an `id` tiebreak forces a blocking sort on
this backend (R4). Totals must cover the range while the list paginates.

**Scale/Scope**: no new app, no new collection, two new routes, two new serializers, three new
service functions, three new test files, about 30 new tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Modular monolith, module under `src/apps/` | PASS | Both routes live in the existing `apps.inventory`. No new app and no new context. |
| Domain boundary rule | PASS | `inventory` reads product labels through `catalog.services.product_labels` and store names through `stores.services.store_names`. No model import crosses a context. `StockEvent` already carries `product_id` and `store_id` as copies, so no relation is traversed. |
| Ponytail, no unneeded patterns | PASS | One new serializer subclass, three small service functions, two views, no repository, no event bus, no cache, no sort parameter, no pool filter, no index. Every rejected abstraction is recorded in `research.md`. |
| Strict SDD | PASS | Spec amended on 2026-11-27, plan here, tasks next, then code. |
| Code quality, type hints, tests | PASS | Ruff and pytest already wired. Three new test files, and every FR has a home in the traceability table. |
| I1 store scoped access | PASS | `event_scope` calls `stock_scope`, which derives every read from `scope_store_ids`. A named store outside the assignments is a 403 raised inside the helper. `require_action("stock.read")` runs first in every read view. A two store test asserts exactly zero foreign rows. |
| I2 pool isolation | PASS | No operation changes stock. The reads group by product, never by pool, and an online row names no store. Nothing here can write two pools because nothing writes. |
| I3 one product identity | PASS | `product_name` and `unit` are read live from the catalog on every request. No name is copied onto an event. The actor name remains the one snapshot, for the reason FR-024 gives. |
| I4 stock is never read then saved | PASS | No write path exists in this feature. The only writes in the project remain M2's `record`. A source scan proves no new write call appears in the module. |
| Data layer, engine version match | PASS | No dependency change. |
| Data layer, ObjectId handling | PASS | `ObjectIdField` on every id that travels, `object_id_or_404` on the path id the history route already uses. Query parameters parse through `ObjectIdField`. |
| Data layer, query rules | PASS | Both reads paginate. No `prefetch_related`, no `select_for_update`, no transaction, no `count()` in one. The existing `(store_id, at)` and `(product_id, at)` indexes serve the range and the filters. The sort cost is recorded in R4 and below. |
| Scheduled endpoint is cached | N/A | Only the schedule is cached. A waste report changes on every waste event, so a cache would need invalidation on the write path, which M3 must not add. |
| Complexity justification | PASS | No new dependency and no new abstraction. See Complexity Tracking. |

**Post-design re-check**: PASS. `research.md` and `data-model.md` keep `stock_scope` as the
only scope rule, keep the write path untouched, and resolve every name at read time. The
blocking sort and the offset paging are accepted costs, recorded under Known limitations, not
gate failures.

## Project Structure

### Documentation (this feature)

```text
specs/004-inventory-insight/
├── spec.md              # Feature specification, amended 2026-11-27
├── plan.md              # This file
├── research.md          # Phase 0 decisions, R1 to R12
├── data-model.md        # Phase 1 read shapes, query plans, access rules
├── quickstart.md        # Phase 1 end to end validation guide
├── contracts/
│   └── api.md           # Phase 1 HTTP contract for the two reads
├── checklists/
│   └── requirements.md  # Spec quality checklist, two validation runs
└── tasks.md             # Phase 2 output, created by /speckit.tasks
```

### Source Code (repository root)

```text
src/apps/inventory/
├── services.py          # CHANGED: event_scope, waste_totals, enrich_events.
│                        #   derived_discrepancy stays, still unused outside tests.
├── serializers.py       # CHANGED: EventReadSerializer, WasteReportQuerySerializer
├── views.py             # CHANGED: WasteReport, ActivityFeed, and require_action in the
│                        #   three existing read views
└── urls.py              # CHANGED: stock/waste/ and stock/activity/

tests/
├── conftest.py              # CHANGED: make_event, make_events fixtures
├── test_waste_report.py     # NEW: range rules, waste only, totals, refusals, SC-008 timing
├── test_activity_feed.py    # NEW: paging, order, tiebreak, kinds, filters
└── test_insight_scope.py    # NEW: store scope, online pool, role gate, derived guard
```

No change to `models.py`, no migration, no new app, no change to another context.

**Structure Decision**: one module per bounded context stays as it is. Both reads are
`apps.inventory` reads over `apps.inventory` data, so the module gains code and nothing else.
Cross-context data arrives through the public service functions M2 already added, which is the
pattern `stores.services.store_names` set in M1.

## Phase Plan

### Phase 0, research

Complete. `research.md` holds twelve decisions. The four that shape the code:

- R2: the totals are one ORM aggregation that compiles to `$group`, with the backend evidence
  named and a Python fallback if the result type is wrong.
- R3: the grand total is the sum of the per item totals, so SC-002 is true by construction.
- R5: the scope rule is `stock_scope`, reused unchanged, so a store manager never sees the
  online pool on either read.
- R11: every read view checks `stock.read` before it applies scope, so the declared action is
  no longer dead and FR-023 is structural.

### Phase 1, design

`data-model.md` defines the two response shapes, the filter sets, the four query plans, the
indexes used and not used, the validation table, and the deletion behaviour.
`contracts/api.md` defines both routes, every parameter, every error, and the permission table.
`quickstart.md` is the runnable proof.

### Phase 2, tasks

`/speckit.tasks` turns this plan into ordered tasks. Expected order:

1. `event_scope`, `waste_totals`, and `enrich_events` in `services.py`, with the aggregate
   proven by a `Decimal` equality test before anything is built on it.
2. `EventReadSerializer` and `WasteReportQuerySerializer`.
3. `WasteReport` and `ActivityFeed` views, then the two routes.
4. `require_action` in the three existing read views.
5. `conftest.py` fixtures.
6. The three test files, then the guard test.
7. The quickstart run against a real server.

The aggregate proof comes before the views, because if the backend returns the wrong type the
fallback changes one service function and nothing else.

## Decisions this plan carries

The eleven decisions settled with the Kyaor on 2026-11-27.

| # | Decision | Where |
|---|---|---|
| 1 | Routes are `GET /api/stock/waste/` and `GET /api/stock/activity/`, under the existing `stock/` prefix. | D1, `urls.py` |
| 2 | Totals come from one ORM aggregation over the same queryset, ordered by total descending then `product_id`. No sort parameter. | D2, R2 |
| 3 | The grand total is the Python sum of the per item totals, before serialization. | D3, R3 |
| 4 | Totals are top level keys on the report envelope, recomputed on every request, returned on every page, with `count` taken from their `events` sum. | D4, R3 |
| 5 | One `EventReadSerializer` subclasses M2's, adding `product_name`, `unit`, and `store_name`. M2's response is untouched. | D5 |
| 6 | `enrich_events(events, more_product_ids=())` batches labels and store names in two queries and never fetches thresholds. | D6, R9 |
| 7 | The feed is a `ListAPIView` with `list()` overridden for enrichment. The report is an `APIView` on `_page_args` and `_paged_response`. | D7 |
| 8 | No new index and no migration. The blocking sort and its escape hatches are recorded. | D8, R10 |
| 9 | `require_action(actor, "stock.read")` in all five read views, role before scope. | D9, R11 |
| 10 | Three test files, two new fixtures, the 10,000 event timing test seeded with `bulk_create`. | D10 |
| 11 | `derived_discrepancy` is not called, and a source scan guard with its own guard enforces that. | D11, R12 |

## Complexity Tracking

**No constitution violations.** Three accepted costs are recorded rather than justified,
because none of them breaks a gate:

| Cost | Why it is accepted | What would change the answer |
|---|---|---|
| A blocking sort on every query, caused by the `id` tiebreak | The order must be stable across reads and page boundaries (FR-017, FR-018, SC-005). At the 10,000 event scale of SC-008 it is milliseconds. | A measurement above the one second bound, or a range that makes the 32MB sort limit reachable. |
| The report recomputes its totals on every page | A cache would need invalidation on every waste event, which couples a read to the write path. | A measured report latency problem, which the shared page size and the `$group` make unlikely. |
| Offset paging on the feed | The shared pager gives the envelope, validation, and maximum for free, and the write rate is a few changes per hour. | Deep pages becoming a real use, which would justify keyset paging by `(at, id)`. |

## Requirement traceability

Groups, because thirty-three rows would repeat the data model.

| Requirements | Design | Proof |
|---|---|---|
| FR-001 to FR-004 report rows, range, only waste | `data-model.md` filter sets, `research.md` R1 and R7 | `test_waste_report.py` |
| FR-005 to FR-008 row fields, totals, grand total | `data-model.md` response shapes, R2 and R3 | `test_waste_report.py` |
| FR-009 paginated list with range wide totals | R1, R3, D4 | `test_waste_report.py`, page 1 against 25 events |
| FR-010 empty range | `contracts/api.md` empty report | `test_waste_report.py` |
| FR-011 live item label, stored actor label | `data-model.md` resolved at read time, R9 | `test_waste_report.py`, rename and account deletion |
| FR-012 to FR-018 feed rows, kinds, paging, order | `research.md` R4 and R8, `contracts/api.md` feed | `test_activity_feed.py` |
| FR-019 to FR-021 scope and refusals | R5, R6, `data-model.md` access rules | `test_insight_scope.py` |
| FR-022 unauthenticated refused | Global `IsAuthenticated` | `test_insight_scope.py` |
| FR-023 same roles as the history read | R11, D9 | `test_insight_scope.py`, five roles plus the patched empty set |
| FR-024 account deletion keeps the name | `data-model.md` deletion table | `test_waste_report.py`, `test_activity_feed.py` |
| FR-025 item and store deletion cascade | `data-model.md` deletion table | `test_insight_scope.py` |
| FR-026 to FR-029 filters | R6, `data-model.md` filter sets | `test_waste_report.py`, `test_activity_feed.py`, `test_insight_scope.py` |
| FR-030 and FR-031 reads only, events only | R12, the guard test, no model change | `tests/test_single_write_path.py` still green, plus the `derived_discrepancy` guard |
| FR-032 10,000 events under one second | R2, R10, D4 | `test_waste_report.py`, timed and printed |
| FR-033 ISO instants and three place quantities | `core.fields.QuantityField`, DRF datetime rendering | `test_waste_report.py`, exact string assertions |

| Success criterion | Proof |
|---|---|
| SC-001 every waste event once, none outside the range | `test_waste_report.py`, four boundary instants |
| SC-002 totals agree exactly | `test_waste_report.py`, 2.5 plus 0.25 reads `2.75`, grand total equals the sum |
| SC-003 zero foreign rows, direct request refused | `test_insight_scope.py`, two stores, both reads |
| SC-004 page 1 is the newest 20, page 2 the other five | `test_activity_feed.py`, 25 changes |
| SC-005 two identical reads, identical order | `test_activity_feed.py`, including a tie that crosses the page boundary |
| SC-006 empty range is zero, not an error | `test_waste_report.py` |
| SC-007 no new write path | `tests/test_single_write_path.py` unchanged and green |
| SC-008 10,000 events under one second | `test_waste_report.py`, elapsed time printed |
| SC-009 no delivery, sale, or count in the report | `test_waste_report.py`, all three in range |
| SC-010 every row names an actor, an instant, and an item | Both read test files, asserted on every returned row |

## Known limitations

- **The tiebreak forces a blocking sort.** `(store_id, at)` serves the match but not `_id`
  order within an equal instant, so MongoDB sorts every matching document before the first
  page. At 10,000 events this is milliseconds. A covering `(store_id, at, id)` index would
  remove it, and whether the backend emits a compound index that includes `_id` is unverified.
- **The feed sorts on every page and its cost grows with the store's history.** Offset pages
  re-sort the same documents and skip `offset` rows, so page 100 costs more than page 1. The
  escape hatch is keyset paging by `(at, id)`, with the response shape unchanged.
- **A scope wide feed over roughly 100,000 events risks MongoDB's 32MB blocking sort limit**,
  which fails the query rather than slowing it. The fix is an index on `(at)` or a date bound,
  and neither is needed at this scale. Named here so it is a risk, not a surprise.
- **Totals are recomputed on every page request.** That is deliberate (D4), and it is one
  aggregation per page. The alternative is a cache that must be invalidated on every waste
  event, which is a write-path coupling this milestone does not accept.
- **A change recorded between two page loads can shift one entry across a page boundary**, and
  the report's totals can change between page 1 and page 2. Per response the numbers always
  agree with each other. A snapshot token would fix the across-request case and is not built.
- **`derived_discrepancy` is unused by M3.** A guard test keeps it from being wired in without
  a decision. A future loss report needs its own window rule for count intervals, because the
  function reads the two newest counts with no range.
- **Online waste appears in no store report.** It has no store, and attributing it would invent
  an attribution. It appears in a scope wide read by an actor who reaches every store, and only
  those actors can record it.
- **The report's totals combine pools** in a scope wide read, because FR-006 totals per item
  and never per pool. Every row names its pool, so a reader can separate them. When a store is
  named, every row is that store's branch pool and nothing is mixed.

## What changes outside this feature's own files

1. `src/apps/inventory/views.py`: `require_action(request.user, "stock.read")` in `StockList`,
   `StockLow`, and `StockEventList`, before the scope check. No response changes for any
   current role, because all five hold the action.
2. `tests/conftest.py`: `make_event` and `make_events`, the batch one using `bulk_create` with
   `batch_size=1000`, which the Mongo backend turns into `insert_many`.
3. The `derived_discrepancy` guard. It lives with the structural scans, so it can be removed
   deliberately by the feature that first uses the function.

No other file moves. No commit and no push is part of this plan; the repository stays the
Kyaor's to publish.
