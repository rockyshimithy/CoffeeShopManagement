# Research: M1 Workforce, shifts inside store scope

Phase 0 decisions. Each entry states the decision, why it wins here, and what was
rejected. Evidence is either a file in this repository or a fact checked against the
installed backend.

## R1. Two foreign keys with cascade, declared by string label

**Decision**: `Shift.employee = ForeignKey("identity.Employee", on_delete=CASCADE)` and
`Shift.store = ForeignKey("stores.Store", on_delete=CASCADE)`. Both labels are strings.

**Rationale**: The domain boundary rule forbids importing another context's models. A
string label resolves through the app registry at runtime, so no import exists. The
cascade then satisfies FR-024 and FR-025 with no service code and no cross-context call.

The backend reports `supports_on_delete_db_cascade = False`
(`django_mongodb_backend/features.py:46`), which means Django's collector performs the
cascade with ordinary per-collection queries instead of a database level rule. The
backend refuses only a delete that queries across collections in one statement
(`compiler.py:1277`), and the collector issues one delete per collection, so it stays
inside the supported shape.

`Employee.user` already uses `on_delete=CASCADE`
(`src/apps/identity/models.py:37`), so deleting an account collects the profile, and
collecting the profile collects that profile's shifts.

**Alternatives considered**: a bare `employee_id = ObjectIdField()` with hand-written
cleanup (FR-025 then needs a service, and the admin shows a raw id); an explicit service
call from `stores` into `workforce` on store deletion (cross-context coupling for
something the relation already expresses).

**Caveat**: no M0 test exercises a cascade delete. The first test in this milestone is a
real proof, not a formality.

## R2. The overlap rule and its own index

**Decision**: The overlap query is
`Shift.objects.filter(employee_id=e, starts_at__lt=other.ends_at, ends_at__gt=other.starts_at)`,
with the shift being edited excluded by id. Add index `(employee_id, starts_at)`.

**Rationale**: This is FR-006 word for word, and touching endpoints fall out of the strict
comparisons. FR-007 makes the rule per person across stores, so the query never filters on
`store_id`. Without the index every create scans the whole collection. The compound index
on `(store_id, starts_at)` required by decision 20 and the constitution serves the
schedule read, not this check.

**Alternatives considered**: a unique index over time buckets (a discrete index cannot
express an arbitrary interval).

## R3. Snapshot isolation allows write skew, so the check needs a shared document

**Decision**: Every shift write bumps a per-store revision counter for each store the
employee is assigned to, inside the same transaction as the check and the write. Two
concurrent writes for one employee therefore always write at least one document in common,
and MongoDB aborts one of them with a write conflict. `core.transactions.retry_on_conflict`
replays the whole body, the replayed check sees the committed shift, and the second request
answers 400.

**Rationale**: MongoDB transactions provide snapshot isolation, not serializability. Two
transactions that both read "no overlap exists" and then insert two different documents
never write the same document, so both commit. A plain read-then-insert inside `atomic()`
satisfies the letter of FR-009 and fails SC-004. A shared document is the only cheap
serialization point available, because no unique index can express an interval.

M0 already relies on this exact mechanism: `identity.services.add_store_to_regional_managers`
replaces a whole `store_ids` list inside a transaction and depends on the conflict to avoid
a lost append (`src/apps/identity/services.py`).

**Alternatives considered**: a dedicated per-employee guard collection (the same trick with
one more collection and no other use); one global lock document for the whole Shift
collection (simplest possible, serializes every shift write in the system); bumping a
counter on `Employee` through a new identity service (writes identity's collection from
workforce, and puts a workforce concern on an identity model).

**Caveat**: this is a serialization point, not a general purpose lock. It must never be
treated as one.

## R4. Ordering by employee name requires a join

**Decision**: `select_related("employee__user", "store")` on the schedule list, ordered by
`starts_at`, then `employee__user__first_name`, then `employee__user__last_name`, then
`pk` as the final tie-break.

**Rationale**: FR-020 requires the employee name as the tie-break, and the name lives in
`identity_user`. `prefetch_related` is unsupported. A manual batch cannot fix ordering
either, because a page cannot be re-sorted in Python without breaking at the page
boundaries.

Verified against the installed backend: `Employee.objects.select_related("user").order_by("user__email")`
compiles to `$lookup`, `$unwind`, `$addFields`, `$sort` in one aggregation.

**Cost**: the `$sort` runs after the join, so it cannot use `(store_id, starts_at)`. The
working set is bounded by the 31 day window cap and by the store filter.

**Alternatives considered**: order by `starts_at, employee_id` and sort names inside each
page (wrong across page boundaries, and it changes FR-020); copy the employee name onto the
shift (a rename goes stale, and FR-021 wants the current name).

**Deviation**: this is the one place where the constitution's "related data on a list
endpoint loads by manual batch after pagination" rule is not followed. The justification is
carried in `plan.md` under Complexity Tracking. Every other list keeps the batch rule.

## R5. Window parsing and the selection predicate

**Decision**: `store`, `from`, and `to` are parsed by one serializer in `filters.py`. No
range given means Monday 00:00 of the current week in the project time zone up to the next
Monday. One side alone gets a 7 day partner. `end <= start` or a span over 31 days is a
400. Selection is `starts_at__gte=from, starts_at__lt=to`.

**Rationale**: FR-016 to FR-019. `starts_at` selection is exact here because FR-004 forbids
a shift crossing midnight, so no shift can start before the window and end inside it. It
also lets the compound index serve the range instead of a full scan.

**Alternatives considered**: an overlap predicate (`ends_at__gt=from, starts_at__lt=to`),
also correct but it cannot use the compound index for the lower bound.

## R6. One validation function for create and edit

**Decision**: `validate_shift_window(starts_at, ends_at, *, exclude_pk=None)` checks
FR-003, FR-004, FR-005 and FR-006. Both the create path and the edit path call it inside
the write transaction.

**Rationale**: The rules are identical on both paths, and duplicated rules drift. The
overlap part needs to run inside the transaction and needs the id to exclude, so it cannot
live only in a serializer.

**Alternatives considered**: serializer-only validation, which cannot see the stored row
being edited and cannot run after the guard bump.

## R7. Employee-store assignment through a public identity service

**Decision**: Add `identity.services.employee_store_ids(employee_id) -> list[ObjectId] | None`
and call it from `workforce.services`. `None` means no profile with that id, which is a 400
field error. A list that does not contain the shift's store is the FR-008 400.

**Rationale**: Workforce needs the employee's stores, and `Employee` has no store field:
scope comes from `user.store_ids`. The domain boundary forbids importing `identity.models`
from workforce, so a public function is the sanctioned path, exactly like
`stores.services.all_store_ids()` already is for identity.

**Alternatives considered**: an `Employee.store_ids` copy (a second source of truth for the
invariant); a two-hop `select_related` from Shift through Employee to User (works, two
`$lookup`s, and still needs the model import).

## R8. Schedule cache: stored snapshots keyed by a revision token

**Decision**: Two internal collections. `ScheduleRevision` holds one row per store with an
integer that every shift write in that store bumps. `ScheduleSnapshot` holds a serialized
page body. The cache key is a SHA-256 of the sorted `(store_id, revision)` pairs of the
actor's effective scope, plus the window and the page parameters. A cached read runs one
indexed `values_list` over the revisions and one lookup by unique key. Rows for the scope
older than one hour are deleted lazily on a miss. Only `count` and `results` are stored, so
the `next` and `previous` links are always built from the live request.

**Rationale**: FR-022 and SC-005 need a cache that stays correct when more than one worker
process serves the app. In process memory a write in one worker leaves every other worker
stale, and the test suite would not notice because pytest runs a single process. Bumping a
revision makes the key itself change at the moment of the write, so there is nothing to
invalidate, no delete to forget, and no delete-versus-insert race.

**Alternatives considered**: `LocMemCache` with a short TTL (correct only in one process,
and SC-005 fails in production); memcached or redis (a new dependency and a compose
service, and the only option that answers without touching MongoDB at all); Django's
`DatabaseCache` backend (emits SQL, unsupported on this engine); a fingerprint query over
the window's shifts instead of revisions (no write side, but it reads the shifts collection
on every cached read).

**Reading of the constitution**: "does not need to reach the database" is taken to mean
"does not run the schedule query". A cached read performs two small indexed finds and no
`$lookup`, no sort, and no name resolution.

## R9. One counter, two jobs

**Decision**: The revision bumped for the write guard in R3 is the same field used as the
cache token in R8.

**Rationale**: The overlap guard already has to touch a shared document per employee, and
the cache already has to change per store. Bumping the store rows of every store the
employee belongs to satisfies both with one write set, and removes a second bookkeeping
mechanism.

**Cost**: a write touches one document per store of that employee, usually one. Two
concurrent writes for different employees in the same store serialize even though they
could not conflict. At human scheduling rates this is unmeasurable.

## R10. New permission actions, no role comparison in workforce

**Decision**: Replace the unused `shift.schedule` action with `shift.read`, `shift.create`,
`shift.change`, and `shift.delete` in `identity.permissions`. Workforce imports only the
helper functions, never a role constant comparison.

**Rationale**: SC-006 requires every role decision to resolve through the one helper.
`shift.schedule` was reserved in M0 and never used by any code, so renaming it costs
nothing.

**Alternatives considered**: keep `shift.schedule` for reads and add three writes (a name
that no longer matches what it covers).

## R11. ObjectId handling in DRF

**Decision**: `core.fields.ObjectIdField` on every id in every serializer, and
`core.shortcuts.object_id_or_404` for URL parameters. The `store` filter id is parsed by
the same field.

**Rationale**: `ObjectIdAutoField` subclasses `AutoField`, so DRF would otherwise infer an
integer. This is already the M0 pattern in every app.

## R12. Time representation

**Decision**: `DateTimeField` in DRF, default rendering. A UTC instant renders as
`2026-11-30T08:00:00Z`. Input accepts any ISO 8601 string with an offset. Input without an
offset is taken as the project time zone, which is UTC.

**Rationale**: FR-002 asks for ISO 8601 with an explicit offset and `Z` is the ISO 8601 UTC
designator. `USE_TZ` and `TIME_ZONE="UTC"` make the stored instant unambiguous.

**Alternatives considered**: forcing the literal `+00:00` suffix (a custom field, and no
consumer cares); storing local wall time (loses the instant).

## R13. Test strategy, including the concurrency proof

**Decision**: pytest against the Compose MongoDB. New files `tests/test_shifts.py`,
`tests/test_shift_scope.py`, and `tests/test_shift_cache.py`. The SC-004 test runs two
threads behind a `threading.Barrier`, with `Shift.objects.create` patched so the first
thread blocks after its overlap check, which forces the interleaving instead of hoping for
it.

**Rationale**: SC-004 cannot be proven by a sequential test. Everything else follows the M0
style: real sessions through `APIClient.force_login`, real collections, no stubs.

**Alternatives considered**: `mongomock` (does not implement transactions or the backend's
query compilation); a sequential test that creates a shift, commits, then creates the
overlap (proves the rule, not the atomicity).

## R14. Two routes, no separate schedule route

**Decision**: `/api/shifts/` and `/api/shifts/{id}/`. The list is the schedule: it carries
the window filters, the default week, the ordering, and the cache. There is no
`/api/schedule/`.

**Rationale**: One collection, one resource. A second route would duplicate the serializer,
the scope logic, and the cache for a different name.

**Alternatives considered**: a dedicated `GET /api/schedule/` (a second surface to keep in
sync with the first).

## R15. Account deletion for ADMIN

**Decision**: `DELETE /api/accounts/{id}/`, ADMIN only, through
`identity.services.delete_account`, wrapped in `django_mongodb_backend.transaction.atomic`
and `core.transactions.retry_on_conflict`. Success is 204. The existing
`LAST_ADMIN_DENIED` guard is extended from deactivation and demotion to deletion. The new
`account.delete` action is added to the permission helper, so no view compares a role.

**Rationale**: FR-025 had no trigger. M0 shipped deactivation only, and no route deletes an
account. Deletion is the destructive twin of store deletion, which M0 already keeps
ADMIN-only, so the same authority applies. One transaction removes the account, its
profile, and its shifts, which is the only way to keep FR-025 true without leaving shifts
that point at a person who cannot sign in.

The `Shift` cascades from R1 do the work. `identity` needs no knowledge of shifts: the
collector walks the reverse relations declared on `Shift`.

One consequence needs code: a cascade delete removes shifts without writing a
`ScheduleRevision`, so a cached schedule for that store would keep showing a person who is
gone. `delete_account` therefore calls two small public functions on `workforce.services`
inside the same transaction, `shift_store_ids(employee_id)` and
`bump_store_revisions(store_ids)`, imported inside the function body to avoid a circular
import. `delete_shift` bumps only its own store: a delete cannot create a conflict, and
the shift only ever appeared in that store's schedule, so moving the other stores of the
same employee would be wasted writes.

**Alternatives considered**: letting a regional manager or a manager delete BARISTA
accounts (a wider blast radius than store deletion, and M0 never granted the region that
power); a soft delete that sets `is_active` to false (deactivation already exists and keeps
the shifts, which is not what "this person left" means); deleting only the employee profile
(it leaves an account with no employment record, which is legal in M0 and therefore
ambiguous).

**Concurrency**: the guard counts the other active admins, so two admins deleting each
other in the same instant can both pass it and leave zero admins. M0's deactivation guard
has exactly the same shape. It is closed in this milestone, see R16.

## R16. The last-admin guard is serialized on one shared document

**Decision**: Add `identity.AdminGuard`, one row with a unique constant key and a revision
counter. `_take_admin_slot()` bumps it inside the transaction, before the count, on every
path that can remove an active admin: deactivation, demotion, and deletion. `update_account`
gains `atomic()` and `retry_on_conflict`, which it never had. `ensure_not_last_active_admin`
becomes `ensure_admin_remains(user, *, keeps_admin: bool)` so the delete path expresses the
same rule without pretending to be an update.

**Rationale**: The guard reads a count and then writes. Under snapshot isolation two
concurrent removals each read a count that still contains the other target, both pass, and
the system ends with zero admins. This is the same shape as R3: a read that a later write
depends on, with nothing in common to conflict on. The one shared document supplies that
conflict. The unique key guarantees exactly one row, so the row is a constant, not a lookup
table.

**Alternatives considered**: a guard row per target admin (two removals of different
targets still do not conflict); counting after the delete inside the transaction (the count
would see its own uncommitted delete while the other transaction's delete stays invisible);
a unique partial index that forbids the zero-admin state (MongoDB cannot express "at least
one document matching a filter"); accepting the race (it is a lockout, and the Kyaor asked
for it closed).

**Cost**: every removal of an admin serializes against every other, which is the point. A
concurrent create of a new admin can cause a spurious 403 for a removal that would have been
safe, because the snapshot predates the create. That is the conservative direction.

## R17. Never call count() inside a transaction

**Decision**: Inside `atomic()`, use `.exists()`, `.first()`, or a `values_list` read. Never
`QuerySet.count()`.

**Rationale**: This backend compiles `count()` with a `$unionWith` stage, which is there to
return a row when the collection is empty. MongoDB refuses `$unionWith` in a multi-document
transaction with `OperationNotSupportedInTransaction`, so a count inside the write path is a
500, not a number. Found while making the last-admin guard transactional: `exists()` compiles
to `$match` plus `$limit 1` and works.

**Alternatives considered**: counting outside the transaction (the count would predate the
other transaction and the guard would be pointless); a raw pymongo count (bypasses the ORM
for one call).

## R18. The concurrency design is verified, not assumed

**Decision**: Keep `core.transactions.retry_on_conflict` as it is, three attempts, no sleep.

**Rationale**: `tests/test_shifts.py::test_the_admin_slot_serializes_two_writers` opens one
transaction, holds it after writing the guard row, and starts a second, which raises
`django.db.DatabaseError` at the write. That is exactly what the helper catches, so the
conflict is translated by the backend's `wrap_database_errors` and the retry is enough. The
two API level tests then prove the outcomes: one 201 and one 400 for overlapping creates of
one employee, and exactly one active admin after two admins remove each other.

**Alternatives considered**: also catching `pymongo.errors.PyMongoError` around commit
(unnecessary here: the conflict surfaced at the write, and `commit_mongo` is not wrapped by
the backend's error translation, so widening the helper would have been a guess).
