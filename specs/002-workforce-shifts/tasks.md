# Tasks: M1 Workforce, shifts inside store scope

**Input**: Design documents from `/specs/002-workforce-shifts/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: Included. SC-001 to SC-008 are acceptance criteria that only a suite can prove,
and the constitution requires tests before completion. They are not optional here.

**Organization**: Tasks are grouped by user story so each story is independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task serves (US1 to US4)
- Every task names the exact file it touches

## Path Conventions

Single project, backend only. `src/apps/<context>/` and `tests/`, both at the repository
root. Django management commands run as `uv run python src/manage.py ...`, tests as
`uv run pytest`.

---

## Phase 1: Setup

**Purpose**: Confirm the ground is solid before touching code.

- [x] T001 Confirm the baseline: run `docker compose ps mongo`, `uv run pytest`, and `uv run ruff check .` from the repository root. Expected: mongo healthy, 112 tests pass, ruff clean. Record the count so a later regression is visible.

---

## Phase 2: Foundational (blocks every user story)

**Purpose**: The schema, the permission actions, and the fixture every story needs.

- [x] T002 Add the four shift actions to `src/apps/identity/permissions.py`: replace `"shift.schedule"` with `"shift.read"`, `"shift.create"`, `"shift.change"`, `"shift.delete"` in `ACTIONS`, and add matching entries to `ROLE_ACTIONS`. `shift.read` for all five roles, the other three for `ADMIN`, `REGIONAL_MANAGER`, `MANAGER`, `SUPERVISOR`. No `BARISTA` write entry.
- [x] T003 Create `Shift` in `src/apps/workforce/models.py` with `employee = models.ForeignKey("identity.Employee", on_delete=models.CASCADE)`, `store = models.ForeignKey("stores.Store", on_delete=models.CASCADE)`, `starts_at` and `ends_at` (`DateTimeField`). Both relations use string labels, so no cross-context import exists. `Meta.indexes` holds `["store_id", "starts_at"]` and `["employee_id", "starts_at"]`.
- [x] T004 Add `ScheduleRevision` to `src/apps/workforce/models.py`: `revision = models.PositiveIntegerField(default=0)`. `_id` is the store id, held as the plain ObjectId primary key with no relation.
- [x] T005 Add `ScheduleSnapshot` to `src/apps/workforce/models.py`: `key = models.CharField(max_length=64, unique=True)`, `body = models.JSONField()`, `created_at = models.DateTimeField(auto_now_add=True)`.
- [x] T006 Generate the first migration in the app with `uv run python src/manage.py makemigrations workforce`. Expected: one `0001_initial.py` holding the three models and both indexes. Read it and confirm `ObjectIdAutoField` is the primary key and that the cascades are `on_delete=CASCADE`.
- [x] T007 [P] Add a `make_shift` fixture to `tests/conftest.py` that takes `employee`, `store`, `starts_at`, and `ends_at`, defaulting to a 08:00 to 16:00 shift on `2026-11-30`. It creates a real `Shift` row. The module docstring already explains why the factories request `db` themselves; follow that style.

---

## Phase 3: User Story 1, a staff member reads the store schedule (P1)

**Goal**: `GET /api/shifts/` returns the ordered, paginated, cached schedule of the actor's
stores for a window.

**Independent Test**: Seed three shifts in store A, sign in as a barista assigned to store
A, and confirm the current week shows exactly those three with names and times.

- [x] T008 [US1] Create `src/apps/workforce/filters.py` with one serializer parsing `store` (`core.fields.ObjectIdField`, optional), `from`, and `to` (ISO 8601, optional). Normalize: neither bound means Monday 00:00 of the current week in the project time zone up to the next Monday; only `from` means `from` plus 7 days; only `to` means `to` minus 7 days. Raise a 400 with `{"detail": "The window must start before it ends and span at most 31 days."}` when `to <= from` or the span exceeds 31 days. Return both bounds as aware UTC datetimes.
- [x] T009 [US1] Create `src/apps/workforce/cache.py`. Build the key as a SHA-256 hex of the sorted `(store_id, revision)` pairs of the actor's effective scope, plus the two window bounds, `page`, and `page_size`. Read: `ScheduleSnapshot.objects.filter(key=key).first()`. Write: store `{"count": n, "results": [...]}` only, never the pagination links, so the links are always built from the live request. On a miss, delete rows with `created_at__lt` one hour before now before inserting. Return a hit as a raw dict.
- [x] T010 [US1] [P] Create `ShiftSerializer` in `src/apps/workforce/serializers.py`: `id = core.fields.ObjectIdField(read_only=True)`, `employee_id`, `employee_name` (a `SerializerMethodField` returning `"{first} {last}".strip()` from the linked account, falling back to the account email when both names are empty), `store_id`, `store_name` (from the related store), `starts_at`, `ends_at`. All id fields use `core.fields.ObjectIdField` explicitly.
- [x] T011 [US1] Add `schedule(actor, window, page, page_size)` to `src/apps/workforce/services.py`. Scope with `scope_stores(Shift.objects.all(), actor)`, filter `starts_at__gte=from, starts_at__lt=to`, use `select_related("employee__user", "store")` and `order_by("starts_at", "employee__user__first_name", "employee__user__last_name", "pk")`. Collect the revision of every store in the effective scope in one `values_list`, build the cache key, return the cached body on a hit, otherwise serialize the page and store it. `store` as a filter calls `require_store_access` first.
- [x] T012 [US1] Add the read side to `src/apps/workforce/views.py` and `src/apps/workforce/urls.py`: `ShiftList` handling `GET /api/shifts/` with `core.pagination.StandardPagination`, and the `shifts/` route registered in `src/core/urls.py` next to the existing three includes. Unauthenticated requests answer 401 through the project default.
- [x] T013 [US1] Write `tests/test_shift_scope.py`: a barista of store A sees only store A's shifts for the week; a manager of store A does not see store B's; an actor with no store assignments gets an empty list and 200; a shift in store B requested by id by a store A user answers 403 with the existing outside-access message and no shift field; an admin sees every store; a 32 day window answers 400.
- [x] T014 [US1] Write `tests/test_shift_cache.py`: the first read creates one `ScheduleSnapshot`; the second read of the same window returns the same body and does not create a second row; a shift write changes the revision so the next read reflects it and never serves the old body; a snapshot row older than one hour is deleted on the next miss.

---

## Phase 4: User Story 2, a manager or supervisor fills the store rota (P2)

**Goal**: Create, edit, and delete a shift with the four refusal rules and the per-person
overlap guarantee.

**Independent Test**: As the manager of store A, create a shift for a barista of store A,
edit its end, then delete it, with a barista of store A reading each state.

- [x] T015 [US2] Create `src/apps/workforce/validators.py` with `validate_shift_window(employee_id, starts_at, ends_at, *, exclude_pk=None)`. Rules: `ends_at > starts_at` (message "The end must be later than the start."); both instants on the same calendar day in the project time zone (message "A shift cannot cross midnight."); span at most 12 hours, exactly 12 allowed (message "A shift cannot last more than 12 hours."); no overlap for the same `employee_id` in any store, using `starts_at__lt=other.ends_at, ends_at__gt=other.starts_at` with `exclude_pk` removed (message "This shift overlaps another shift for the same employee."). Raise `rest_framework.serializers.ValidationError` with the failing field as the key. The function queries but does not open a transaction; the caller owns the transaction.
- [x] T016 [US2] Refactor the last-admin guard in `src/apps/identity/services.py`: rename `ensure_not_last_active_admin(user, new_role, new_is_active)` to `ensure_admin_remains(user, *, keeps_admin: bool)` and update the one call site in `update_account`. No behaviour change in this task; the transaction and the serialization document come with US4.
- [x] T017 [US2] Add a public `employee_store_ids(employee_id) -> list[ObjectId] | None` to `src/apps/identity/services.py`: return the linked account's `store_ids`, or `None` when no employee profile has that id. `workforce` calls this and never imports an identity model.
- [x] T018 [US2] Add `create_shift(actor, data)` to `src/apps/workforce/services.py`. Validate through the write serializer, then run `retry_on_conflict` around `django_mongodb_backend.transaction.atomic`: read the employee's stores through `employee_store_ids` (400 when `None`, 400 when the shift's store is not in the list), bump `ScheduleRevision` for every store in that list with a filter-update then a create when no row exists, call `validate_shift_window`, then `Shift.objects.create`. Answer 400 field errors, never 500.
- [x] T019 [US2] Add `update_shift(actor, shift, data)` to the same file. Same transaction and guard bump as create, with `exclude_pk=shift.pk` in the overlap check. Only `starts_at` and `ends_at` are accepted; a request carrying `employee_id` or `store_id` answers 400 with `{"employee_id": ["A shift's employee cannot change. Delete the shift and create a new one."]}` and the same shape for `store_id`.
- [x] T020 [US2] Add `delete_shift(actor, shift)` to the same file: `require_action(actor, "shift.delete", shift.store_id)` inside `atomic()` and `retry_on_conflict`, bump the shift's own store revision, then delete by pk. Only that store is bumped: a delete cannot create an overlap, and the shift never appeared in the schedules of the employee's other stores.
- [x] T021 [US2] Add the write serializer and the detail view: `ShiftWriteSerializer` in `src/apps/workforce/serializers.py` (write fields `employee_id`, `store_id`, `starts_at`, `ends_at`), and `ShiftDetail` in `src/apps/workforce/views.py` with `get_object` using `core.shortcuts.object_id_or_404` then `require_store_access`. Add `shifts/<str:pk>/` to `src/apps/workforce/urls.py`. Wire `POST` on the list and `GET`, `PATCH`, `DELETE` on the detail.
- [x] T022 [US2] Write `tests/test_shifts.py` for the sequential rules: create 201; overlap 400 and nothing stored; touching endpoints 201; midnight crossing 400; 12 hours 201 and one second more 400; `ends_at` equal to `starts_at` 400; employee from another store 400; unknown employee 400; barista create, edit, and delete all 403; cross-store edit and delete 403; edit end into an overlap 400 with the stored end unchanged; edit changing `employee_id` 400; delete 204 then detail 404; a deactivated employee keeps their shifts.
- [x] T023 [US2] Write the SC-004 concurrency test in `tests/test_shifts.py`: two threads behind a `threading.Barrier`, each posting an overlapping shift for the same employee, with `Shift.objects.create` patched so the first thread blocks after its overlap check. Assert exactly one shift exists afterwards, one response is 201, and the other is 400 with the overlap message. Close each thread's connection in a `finally`.

---

## Phase 5: User Story 3, a regional manager or admin schedules across stores (P3)

**Goal**: The same rules, with the region's reach coming from `store_ids` rather than an
exemption.

**Independent Test**: As a regional manager assigned to two stores, create one shift in each
and confirm both appear in the schedule.

- [x] T024 [US3] Extend `tests/test_shift_scope.py`: a regional manager with two stores creates a shift in each (201, 201) and reads both; a store created after the account exists is immediately schedulable by every regional manager, because M0 appends it to `store_ids`; an admin creates, edits, and deletes in any store; a regional manager attempting to create an `ADMIN` account still gets the 001 refusal.
- [x] T025 [US3] Verify, do not code: confirm by reading the diff that no module under `src/apps/workforce/` compares a role value, and that every authorization call goes through `can`, `require_action`, `require_store_access`, or `scope_stores`. If a comparison appears, remove it. This is SC-006.

---

## Phase 6: User Story 4, an admin closes an account (P3)

**Goal**: `DELETE /api/accounts/{id}/` for ADMIN, with the last-admin guard holding under
concurrent requests.

**Independent Test**: Create an account with a profile and two shifts, delete it as an
admin, confirm the profile and both shifts no longer answer.

- [x] T026 [US4] Add `AdminGuard` to `src/apps/identity/models.py`: `key = models.CharField(max_length=16, unique=True, default="last-admin")` and `revision = models.PositiveIntegerField(default=0)`. Generate `src/apps/identity/migrations/0002_adminguard.py`. The unique index on `key` is what guarantees exactly one row.
- [x] T027 [US4] Add `_take_admin_slot()` to `src/apps/identity/services.py`: `AdminGuard.objects.filter(key="last-admin").update(revision=F("revision") + 1)`; when zero rows update, `AdminGuard.objects.create(key="last-admin")`. A concurrent create raises `IntegrityError`, which is a `DatabaseError`, so the outer `retry_on_conflict` replays it. No transaction of its own: it runs inside the caller's.
- [x] T028 [US4] Make `update_account` transactional: wrap `_take_admin_slot()`, `ensure_admin_remains`, and `serializer.save()` in `django_mongodb_backend.transaction.atomic` inside `retry_on_conflict`, and move the regional-manager store assignment inside the same block so a role change and its assignments commit once. Re-read the target inside the closure before the guard, so a retry does not use a stale role or `is_active`.
- [x] T029 [US4] Add `delete_account(actor, user)` to `src/apps/identity/services.py`: `can(actor, "account.delete")` or 403 with `ROLE_DENIED`; then `retry_on_conflict` around `atomic()` containing `_take_admin_slot()`, `ensure_admin_remains(target, keeps_admin=False)`, the revision bump for the stores that will lose shifts, and `User.objects.filter(pk=user.pk).delete()`. Answer 404 when the target is already gone inside the closure. Also add the two public functions it needs to `src/apps/workforce/services.py`: `shift_store_ids(employee_id) -> list[ObjectId]` (distinct store ids of that profile's shifts) and `bump_store_revisions(store_ids) -> None` (the same filter-update-then-create as T027, for each store). Import them inside the function body, not at module top, to avoid a circular import: `workforce` imports `identity`, so `identity` cannot import `workforce` at load time.
- [x] T030 [US4] Add `"account.delete"` to `ACTIONS` and to `ROLE_ACTIONS` with `{User.Role.ADMIN}` in `src/apps/identity/permissions.py`.
- [x] T031 [US4] Add `delete` to `AccountDetailView` in `src/apps/identity/views.py`: fetch through the existing `get_object` (which already answers 404 on a bad id), call `delete_account`, return 204. No URL change: `accounts/<str:pk>/` already routes it.
- [x] T032 [US4] Extend `tests/test_accounts.py`: admin deletes an account with a profile and two shifts, then the account detail, the profile, and both shifts answer 404 (SC-007); delete answers 204 with an empty body; manager, regional manager, and barista all get 403 on delete; deleting an unknown id 404; an account with no profile deletes alone; the last active admin gets 403 and survives, for delete as well as for deactivate and demote. Also read the store's schedule twice around the delete and assert the deleted person is absent from both reads, which proves the revision bump in T029 and not just a cold cache.
- [x] T033 [US4] Add the SC-008 concurrency test to `tests/test_accounts.py`: two admins, each deleting the other through two threads behind a `threading.Barrier`. Assert the database ends with exactly one active admin and that one response is 204 and the other 403. Repeat the same test shape for one deleting while the other deactivates, and mark both with a short comment naming the invariant they defend.

---

## Phase 7: Polish

- [x] T034 [P] Run `uv run ruff format .` then `uv run ruff check .` and fix every finding. The scope is `src/` and `tests/`, `migrations/` is excluded by config.
- [x] T035 [P] Run the full `uv run pytest` and confirm the count from T001 plus the new tests. Any M0 test that changed behaviour must have a documented reason in the diff, not a quietly updated assertion.
- [x] T036 Run the `quickstart.md` walkthrough end to end, including step 6.7 (cache) and step 6.9 (store cascade), against a fresh database, and note any step that needed a change.
- [x] T037 Re-read `docs/MACRO.md` section 4 and section 6 against this plan. Two things must not contradict it: decision 20's index and cache sentence, and the M1 exit criteria row. Amend the macro doc only if a contradiction exists, and report the line if so.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependency, run first
- **Foundational (Phase 2)**: depends on T001, blocks every user story
- **US1 (Phase 3)**: depends on Phase 2
- **US2 (Phase 4)**: depends on Phase 2. Its transaction writes the `ScheduleRevision` rows that US1's cache key reads, so US1 lands first in reality even though the code is separable
- **US3 (Phase 5)**: depends on US1 and US2, because it exercises both
- **US4 (Phase 6)**: depends on Phase 2 only. T028 touches `update_account`, which no shift task touches, so it can run alongside US1
- **Polish (Phase 7)**: depends on every story that is being delivered

### Story Dependencies

- **US1 (P1)**: independent after Phase 2. This is the MVP
- **US2 (P2)**: independent after Phase 2, with `ScheduleRevision` from T004
- **US3 (P3)**: needs US1 and US2 to exist, then adds reach tests and no new code
- **US4 (P3)**: independent after Phase 2, and the only story touching `identity`'s account set

### Within Each Story

- Tests last in this feature, because the rules live in one validator and the tests are the
  proof of the refusal messages. Exception: T023 and T033 come after their story's
  implementation and must fail if the guard is removed. Verify that by deleting the bump
  once and watching the test fail, then restore it.

### Parallel Opportunities

- T003, T004, T005 are one file, so they are sequential by necessity, but T007 can run beside
  them
- T010 beside T008 and T009
- T026 beside T010, different app
- T034 and T035 are the two independent gates at the end

---

## Parallel Example: User Story 1

```bash
# Three files, no ordering between them:
Task: "Create the window serializer in src/apps/workforce/filters.py"
Task: "Create the snapshot cache in src/apps/workforce/cache.py"
Task: "Create ShiftSerializer in src/apps/workforce/serializers.py"
```

## Parallel Example: User Story 4

```bash
# The model and its migration, beside the permission action:
Task: "Add AdminGuard in src/apps/identity/models.py and migration 0002"
Task: "Add account.delete to src/apps/identity/permissions.py"
```

---

## Implementation Strategy

### MVP First

US1 alone is demonstrable: a barista reads the week's rota with the scope invariant proven
and the cache in place. That is Phases 1 to 3, 14 tasks.

### Incremental Delivery

1. Phases 1 to 2: schema and permissions, no endpoint yet
2. Phase 3: US1, the schedule read, demonstrable on its own
3. Phase 4: US2, the write path and the overlap guarantee
4. Phase 5: US3, reach without new code
5. Phase 6: US4, account deletion and the last-admin guarantee
6. Phase 7: gates and the walkthrough

### Before Writing Any Code

T016 is a pure rename with no behaviour change, and it comes before US4 so that T028 can
change the right function in one place. Do not reorder it after T029.

---

## Notes

- `[P]` means different files and no incomplete dependency, not "do it at the same time"
- The two concurrency tests (T023, T033) are the only places a thread is created in this
  suite. Keep them together in their files, not spread across modules
- No test may use `time.sleep` to create an interleaving. Use the barrier and the patched
  create
- Every refusal message in T015, T018, and T019 is asserted verbatim in its test, so the
  contract and the code cannot drift
