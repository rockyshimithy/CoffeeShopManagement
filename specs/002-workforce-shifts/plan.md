# Implementation Plan: M1 Workforce, shifts inside store scope

**Branch**: `feature/m1-workforce` | **Date**: 2026-11-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-workforce-shifts/spec.md`

**Note**: `setup-plan.sh` reports the feature directory name as the branch. The real git
branch is `feature/m1-workforce`, created in the previous session and still without an
upstream.

## Summary

Deliver the rota. One new collection, `Shift`, holding who works in which store and when.
A manager or supervisor fills the rota of their own stores, a regional manager fills any
store, an admin fills anywhere, and every role reads the schedule of its own stores. Four
refusal rules guard every write: end after start, same UTC day, at most 12 hours, no
overlap for the same person in any store. The employee must already be assigned to the
shift's store.

`workforce` stops being an empty stub: it gets models, a service module, serializers,
views, routes, and the first migration in that app. Nothing in `identity`, `stores`, or
`catalog` changes shape, with four exceptions:

1. `identity.permissions` gains three shift actions, the `account.delete` action, and
   renames the unused `shift.schedule` to `shift.read`.
2. `identity.services` gains `employee_store_ids(employee_id)`, a public read that
   `workforce` uses to enforce FR-008 without importing an identity model.
3. `identity` gains `DELETE /api/accounts/{id}/` for ADMIN, which is the trigger FR-025
   never had. The route removes the account, and the `Shift` cascades remove its profile
   and shifts.
4. The last-admin guard is closed against the concurrent case the Kyaor asked for. It gains
   one serialization document (`AdminGuard`), and `update_account` gains the transaction it
   never had, so deactivation, demotion, and deletion share one rule (FR-027, SC-008).

Two internal collections support the two hard requirements:

- `ScheduleRevision` doubles as the write guard that makes the overlap check atomic and as
  the token that invalidates the schedule cache.
- `ScheduleSnapshot` holds the cached schedule pages.

## Technical Context

**Language/Version**: Python 3.12 or newer

**Primary Dependencies**: unchanged from M0. Django 6.1.3, django-mongodb-backend 6.1.0,
djangorestframework 3.18.x, django-filter 26.2. No new dependency is added by this feature.

**Storage**: MongoDB 8.0, the existing single-node replica set, which transactions require.

**Testing**: pytest 8 with pytest-django 4.14 against the Compose MongoDB. Three new test
files, including one threaded test for SC-004.

**Target Platform**: Linux containers through Docker Compose, development on Ubuntu 24.04

**Project Type**: Web service, one backend, no frontend in this milestone

**Performance Goals**: a cached schedule read answers with two indexed finds and no
aggregation. An uncached read answers within 200 ms at the 95th percentile with 10,000
accounts, 50 stores, and 52 weeks of shifts. Targets, not release gates.

**Constraints**: `prefetch_related()` is unsupported. `django.db.transaction.atomic()` is a
no-op. `select_for_update()` is a no-op. MongoDB isolation is snapshot, so a
read-then-insert is not serializable by itself. A `$sort` on a joined field cannot use an
index. Pagination is mandatory on every list.

**Scale/Scope**: one app filled in, one app extended, four collections (one exposed), six
endpoints, five permission actions, two new indexes, three test files, one migration.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Evidence |
|---|---|---|
| Modular monolith, module under `src/apps/` | PASS | `src/apps/workforce` gains models, services, views, and routes. It stays a Django app with the existing `apps.workforce` label. |
| Domain boundary rule | PASS | `Shift` references `"identity.Employee"` and `"stores.Store"` by string label, so no model import exists. The two cross-context reads go through public services: `identity.services.employee_store_ids` and the existing `stores.services.all_store_ids`. |
| Ponytail, no unneeded patterns | PASS | DRF generic views, one service module, one validation function, no repository, no event bus, no abstract base class. The two bookkeeping collections exist because a requirement needs each of them, not because a pattern wants them. |
| Strict SDD | PASS | Spec approved by the Kyaor on 2026-11-26, plan here, tasks next, then code. |
| Code quality, type hints, tests | PASS | Ruff and pytest already wired. The overlap rule, the store scope, the cache, and both cascades each get tests. |
| I1 store scoped access | PASS | Every shift read resolves its store ids through `scope_store_ids`, which is the same helper that owns the ADMIN bypass, and `scope_stores` stays the filter for other lists. Detail, edit, and delete call `require_store_access`. A two-store test proves zero leakage, and `store` as a filter is checked against the actor's stores. |
| I2 pool isolation | N/A | No stock in this milestone. |
| I3 one item identity | PASS | `catalog` is untouched. A shift copies no item data. |
| I4 stock is never read then saved | N/A | No stock in this milestone. |
| Data layer, engine version match | PASS | No dependency change. Django 6.1 with backend 6.1.0 stays the documented pairing. |
| Data layer, ObjectId and contrib setup | PASS | `ObjectIdAutoField` inherited from `DEFAULT_AUTO_FIELD`. `ObjectIdField` declared explicitly on every serializer id. `object_id_or_404` for path and filter ids. |
| Data layer, query rules | PASS | Pagination everywhere. Both indexes required by the read and the check exist. No `prefetch_related`, no `select_for_update`, no `django.db.transaction`. Every write opens `django_mongodb_backend.transaction.atomic`. |
| Scheduled endpoint is cached | PASS | `ScheduleSnapshot` holds the page; the key carries the store revisions, so a write makes the old key unreachable. |
| Complexity justification | PASS | One deviation, recorded in Complexity Tracking below. |

**Post-design re-check**: PASS. The design in `data-model.md` and `contracts/api.md` keeps
the permission helper as the only authorization path, keeps store scope as data, and uses
only backend features already proven in M0. The one deviation is the joined sort required
by FR-020.

## Project Structure

### Documentation (this feature)

```text
specs/002-workforce-shifts/
├── spec.md              # Feature specification, approved
├── plan.md              # This file
├── research.md          # Phase 0 decisions, R1 to R15
├── data-model.md        # Phase 1 collections, indexes, cascades
├── quickstart.md        # Phase 1 end to end validation guide
├── contracts/
│   └── api.md           # Phase 1 HTTP contract for shifts and account deletion
├── checklists/
│   └── requirements.md  # Spec quality checklist, all items pass
└── tasks.md             # Phase 2 output, created by /speckit.tasks
```

### Source Code (repository root)

```text
src/apps/workforce/            # the empty stub, now filled in
├── models.py                  # Shift, ScheduleRevision, ScheduleSnapshot
├── validators.py              # validate_shift_window, the four refusal rules
├── services.py                # create_shift, update_shift, delete_shift, the transaction
├── cache.py                   # schedule key, read through, lazy cleanup
├── serializers.py             # ShiftSerializer, ShiftWriteSerializer
├── filters.py                 # store, from, to parsing and window normalization
├── views.py                   # ShiftList, ShiftDetail
├── urls.py                    # /api/shifts/ and /api/shifts/<pk>/
├── admin.py                   # read only registration, no write path
└── migrations/0001_initial.py # first migration in this app

src/apps/identity/
├── models.py                  # CHANGED: AdminGuard, the last-admin serialization row
├── permissions.py             # CHANGED: four shift actions, account.delete, scope_store_ids
├── services.py                # CHANGED: employee_store_ids, delete_account, _take_admin_slot
├── views.py                   # CHANGED: AccountDetailView gains delete
├── urls.py                    # UNCHANGED: accounts/<pk>/ already routes the delete
└── migrations/0003_adminguard.py  # NEW

src/apps/stores/
└── services.py                # CHANGED: store_exists, one public read
src/core/                      # UNCHANGED: fields, shortcuts, transactions, pagination already exist

tests/
├── conftest.py                # CHANGED: make_shift fixture
├── test_accounts.py            # CHANGED: delete route, last admin guard, two admins removing each other
├── test_shifts.py             # create, edit, delete, four refusals, threaded overlap
├── test_shift_scope.py        # store scope, cross-store 403, barista refusal
└── test_shift_cache.py        # cache hit, cache invalidation on write, cleanup
```

**Structure Decision**: One Django project under `src/`, one module per bounded context.
The feature stays inside `src/apps/workforce/` and touches its neighbours only through named
public functions: `identity.services.employee_store_ids` and `identity.services.delete_account`,
`identity.permissions.scope_store_ids` plus the five actions, `stores.services.store_exists`
and `all_store_ids`, and, in the other direction, `workforce.services.shift_store_ids` and
`bump_store_revisions` for the identity delete path. The cascade for store and account
deletion is expressed on the `Shift` model, so `stores` needs no code change at all.

## Phase Plan

### Phase 0, research

Complete. `research.md` holds fifteen decisions, each with the evidence behind it. The two
that change the shape of the code:

- R3: MongoDB snapshot isolation permits two concurrent overlapping inserts, so the overlap
  check needs a shared document to force a write conflict.
- R8: the schedule cache keys on store revisions rather than on an invalidate-on-write
  delete, so it stays correct with more than one worker process.

### Phase 1, design

`data-model.md` defines the four collections, the two indexes, the cascade table, and the
write path. `contracts/api.md` defines the six endpoints, the permission matrix, the
window rules, and every error code. `quickstart.md` is the runnable proof.

### Phase 2, tasks

`/speckit.tasks` turns this plan into ordered tasks. Expected order: permission actions and
both identity functions, models and migration, validators, services with the transaction and
the revision bump, cache, serializers, filters, views and routes, the
`DELETE /api/accounts/{id}/` route, the three new test files plus the account deletion test
in `tests/test_accounts.py`, then the quickstart run.

## Decisions this plan carries that the spec left open

These are the plan's own calls, named so they can be vetoed before the code exists.

| # | Decision | Where |
|---|---|---|
| 1 | FR-024 and FR-025 are a model level cascade: two `ForeignKey` declarations with `CASCADE`. No service code, no cross-context call. `stores.services.delete_store` keeps working untouched. | R1, data-model |
| 2 | The overlap check is made atomic by bumping a per-store revision for each store the employee belongs to, inside the write transaction. Without a shared document, two concurrent creates both commit. | R3, R9 |
| 3 | The schedule cache lives in MongoDB as stored pages keyed by the store revisions. In-process memory is rejected because it goes stale per worker and the test suite would not notice. | R8 |
| 4 | The schedule list uses `select_related` and sorts on the employee name, because FR-020 requires that tie-break. This is the one deviation from the batch-after-pagination rule. | R4, Complexity Tracking |
| 5 | The schedule is `GET /api/shifts/`. There is no separate `/api/schedule/` route. | R14 |
| 6 | A shift edit accepts only `starts_at` and `ends_at`; sending `employee_id` or `store_id` is a 400, not a silent ignore. | FR-010, contracts |
| 7 | Account deletion is ADMIN only, answers 204, and refuses the last active admin with the existing 403. The `Shift` cascades do the profile and shift cleanup, so no service code touches them, but the affected stores' revisions are bumped so the cache cannot serve the deleted person. | R15, contracts |
| 8 | The last-admin guard is serialized on one `AdminGuard` row for all three removal paths, and `update_account` gains the transaction M0 never gave it. | R16, contracts |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| The schedule list uses `select_related` and sorts on a joined field, against the constitution's "load related data by manual batch after pagination" rule. | FR-020 orders by start, then employee name, and the name lives in `identity_user`. A page cannot be re-sorted in Python without breaking at the page boundaries, so batching cannot produce the required order. | Ordering by start then employee id keeps the batch rule but breaks FR-020, and a spec change to hide a design gap is worse than one justified join. The working set stays bounded by the 31 day window cap and the store filter. |
| Two internal collections exist for one feature. | FR-009 and SC-004 cannot be met by a read-then-insert under snapshot isolation, and FR-022 and SC-005 cannot be met across worker processes by in-process memory. Each collection answers exactly one of the two. | A per-employee guard plus a fingerprint query (same two collections, one more read per cached request); redis or memcached (a new dependency and a compose service for one endpoint). |

## Known limitations

- Two admins removing each other at the same instant is closed by `AdminGuard`. What is not
  closed: the guard counts active admins, so a concurrent create of a new admin can cause a
  spurious 403 for a removal that would have been safe. Conservative, and not a lockout.
- A `ScheduleSnapshot` row survives until the next cleanup after it is an hour old. The
  cleanup is global, so a row for a deleted store is still collected, but it lives slightly
  longer than one hour.
- The schedule sort runs after the join, so it cannot use the compound index. The working
  set is capped by the 31 day window and the store filter, and the cache absorbs repeated
  reads. A denormalized employee name is the escape hatch if this ever becomes a measured
  problem.
